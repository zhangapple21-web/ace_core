"""Fail-closed, local at-most-once claim records for scheduled attempts.

This is deliberately smaller than TaskPool.  It protects a *scheduled attempt*
such as ``daily_learning:YYYY-MM-DD`` from being run twice by two daemon
processes.  It does not lease, steal, retry, or recover abandoned work.

If an owner dies before completion, a later process receives
``recovery_required``.  A human or a separately governed recovery procedure
must decide what happens next; this component must never silently rerun it.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


SCHEMA_VERSION = 1
OUTCOMES = frozenset({"acquired", "completed", "busy", "recovery_required"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


class RuntimeClaimStore:
    """File-backed claims with O_EXCL acquisition and token fencing."""

    def __init__(self, directory: str | Path, *, owner_alive: Callable[[Mapping[str, Any]], bool] | None = None):
        self.directory = Path(directory)
        self.owner_alive = owner_alive or self._owner_alive

    @staticmethod
    def _owner_alive(owner: Mapping[str, Any]) -> bool:
        """Return whether a same-host process appears alive; failures are unsafe.

        An owner from another host, a malformed PID, or an access-check failure
        cannot be assumed dead.  They deliberately return ``True`` so callers
        get ``busy`` rather than an unsafe recovery decision.
        """
        if str(owner.get("host", "")) != os.environ.get("COMPUTERNAME", ""):
            return True
        pid = owner.get("pid")
        if not isinstance(pid, int) or pid <= 0:
            return True
        if os.name == "nt":
            # ``os.kill(pid, 0)`` is a POSIX existence idiom.  On Windows it
            # still enters Python's signal/console-control path, which is not
            # an appropriate dependency for a local lifecycle lock (and has
            # destabilized the desktop host during test runs).  Querying an
            # already-existing process handle is read-only and avoids sending
            # any signal at all.  An access/API failure remains fail-closed:
            # another owner is treated as alive rather than retried.
            try:
                import ctypes

                query_limited_information = 0x1000
                still_active = 259
                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                handle = kernel32.OpenProcess(query_limited_information, False, pid)
                if not handle:
                    return True
                try:
                    exit_code = ctypes.c_ulong()
                    if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                        return True
                    return exit_code.value == still_active
                finally:
                    kernel32.CloseHandle(handle)
            except (AttributeError, OSError):
                return True
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except OSError:
            return True
        return True

    @staticmethod
    def _validate_key(key: str) -> str:
        normalized = str(key).strip()
        if not normalized or len(normalized) > 240:
            raise ValueError("claim key must be non-empty and at most 240 characters")
        return normalized

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @classmethod
    def _read_settled(cls, path: Path) -> dict[str, Any] | None:
        """Allow only the creator's tiny write window to settle.

        This does not retry acquisition or extend ownership.  Without it, a
        same-key racer can observe the zero-byte interval between O_EXCL file
        creation and fsync, incorrectly classifying a healthy owner as a
        malformed crash record.
        """
        for _ in range(10):
            value = cls._read(path)
            if value is not None:
                return value
            time.sleep(0.005)
        return None

    @staticmethod
    def _owner() -> dict[str, Any]:
        return {"pid": os.getpid(), "host": os.environ.get("COMPUTERNAME", "")}

    def acquire(self, key: str) -> dict[str, Any]:
        """Acquire a key once or report its immutable/unsafe existing state."""
        key = self._validate_key(key)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self._path(key)
        token = secrets.token_urlsafe(24)
        record = {
            "schema_version": SCHEMA_VERSION,
            "key": key,
            "state": "running",
            "claim_token": token,
            "owner": self._owner(),
            "acquired_at": _utc_now(),
        }
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            existing = self._read_settled(path)
            if not existing or existing.get("schema_version") != SCHEMA_VERSION or existing.get("key") != key:
                return {"outcome": "recovery_required", "key": key, "reason": "malformed_or_mismatched_claim"}
            if existing.get("state") == "completed" and "result" in existing:
                return {"outcome": "completed", "key": key, "result": _json_copy(existing["result"])}
            if existing.get("state") != "running" or not isinstance(existing.get("owner"), Mapping):
                return {"outcome": "recovery_required", "key": key, "reason": "unknown_claim_state"}
            if self.owner_alive(existing["owner"]):
                return {"outcome": "busy", "key": key, "owner": _json_copy(existing["owner"])}
            return {"outcome": "recovery_required", "key": key, "reason": "owner_not_alive"}
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                handle.flush()
                os.fsync(handle.fileno())
        except Exception:
            # The file exists but may be incomplete.  Do not delete or retry:
            # later callers must see recovery_required instead of duplicate work.
            raise
        return {"outcome": "acquired", "key": key, "claim_token": token}

    def complete(self, key: str, claim_token: str, result: Mapping[str, Any]) -> dict[str, Any]:
        """Fence completion to the original owner and make the result immutable."""
        key = self._validate_key(key)
        token = str(claim_token).strip()
        if not token:
            raise ValueError("claim_token must be non-empty")
        if not isinstance(result, Mapping):
            raise ValueError("claim result must be a mapping")
        path = self._path(key)
        current = self._read(path)
        if not current or current.get("schema_version") != SCHEMA_VERSION or current.get("key") != key:
            raise ValueError("claim record is missing or malformed")
        if current.get("state") == "completed":
            if current.get("claim_token") != token:
                raise PermissionError("claim token does not own this completed record")
            return {"outcome": "completed", "key": key, "result": _json_copy(current["result"])}
        if current.get("state") != "running" or current.get("claim_token") != token:
            raise PermissionError("claim token does not own this running record")
        completed = {
            **current,
            "state": "completed",
            "completed_at": _utc_now(),
            "result": _json_copy(dict(result)),
        }
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(completed, ensure_ascii=False, sort_keys=True))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return {"outcome": "completed", "key": key, "result": _json_copy(completed["result"])}
