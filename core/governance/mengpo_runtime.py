"""Mengpo runtime: make forgetting real, and make it selective.

Why this module exists
----------------------
Mengpo's design work is finished and its running is not. Three specific defects,
each pinned in ops/test_mengpo_never_runs.py:

1. ``MengpoAutoTrigger`` - the component written to do the forgetting, with
   thresholds, cooldown, daily cap, backup-first - has zero call sites. It was
   built and never wired.
2. ``MengpoMemoryDecay.forget()`` writes a graveyard tombstone and nothing
   else. The artifact is never removed from the store, which is why all 2837
   records in mengpo_records.jsonl carry ``affected_items: []``.
3. Nothing reads the question the owner actually asks. ``ForgettingCandidate``
   has an ``alternatives_exist`` field, and neither ``forget()`` nor
   ``identify_forgetting_candidates()`` ever reads it. What to forget is decided
   by "is this dirty" alone; "what would I lose by forgetting it" is unasked.

What this adds
--------------
Substitution is the gate, not a tiebreaker. A candidate is only forgettable
when something else can cover its job. Four sources of substitution, each
resolvable from records rather than from a model's opinion:

  a substitute    - another artifact with the same normalised name and a
                    superseding record, the classic supersede-not-delete path.
  structured       - a MemoryLine (core principle, axiom, constraint, invariant,
                     identity) covering the same category: forgetting the detail
                     loses nothing because the rule stands.
  absorbed         - a later artifact whose record cites this one as a
                    reference: its content was already carried forward.
  never            - protected by lineage, or core-typed.

The runtime then forgets for real: it removes the artifact from the lexicon or
the experience store, records the affected item and its substitution in the
mengpo record, and keeps the tombstone. Reversible, because the tombstone
carries the original payload.

Bounded: a daily cap, a per-run cap, and a cooldown. A run that finds no
substitute forgets nothing and says so, because a deletion that cannot be
undone is the one failure this subsystem must never have.
"""
from __future__ import annotations

import base64
import binascii
import json
import math
import os
import re
import shutil
import stat
import tempfile
import threading
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent.parent

CONTRACT_VERSION = "ace.governance.mengpo_runtime.v1"

#: How many artifacts one run may forget. Small on purpose.
MAX_PER_RUN = 5
#: How many runs per day. Conservative, mirrored from the auto-trigger's design.
MAX_RUNS_PER_DAY = 3
MIN_RUN_INTERVAL_HOURS = 6

STATE_FILE = "08_GOVERNANCE/decisions/mengpo_runtime_state.json"
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


@dataclass(frozen=True)
class Substitution:
    """Why forgetting this artifact costs nothing."""

    kind: str            # substitute / structured / absorbed
    detail: str
    evidence: str        # a path or id, so the claim is checkable


@dataclass
class Assessment:
    """Whether one artifact is forgettable, and why."""

    artifact_id: str
    forgettable: bool
    reason: str
    substitution: Substitution | None = None
    pollution_score: float = 0.0


def _normalise(text: Any) -> str:
    return "".join(str(text or "").split()).lower()


def _same_payload(stored: Mapping[str, Any], supplied: Mapping[str, Any]) -> bool:
    """Require exact JSON-compatible equality before removing a record."""
    try:
        stored_json = json.dumps(
            stored, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
        supplied_json = json.dumps(
            supplied, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        )
    except (TypeError, ValueError):
        return False
    return stored_json == supplied_json


def _safe_artifact_id(identifier: str) -> str:
    value = str(identifier)
    if not value or value in {".", ".."}:
        raise ValueError("artifact id is empty or reserved")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError("artifact id must be a safe filename component")
    return value


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _atomic_write_json(path: Path, value: Mapping[str, Any], *, sort_keys: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=sort_keys)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _append_jsonl_record(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        original_size = handle.tell()
        try:
            handle.write(line.encode("utf-8"))
            handle.flush()
            os.fsync(handle.fileno())
        except BaseException:
            handle.truncate(original_size)
            handle.flush()
            os.fsync(handle.fileno())
            raise


def _read_complete_tombstone(path: Path, identifier: str) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(value, dict) or value.get("id") != identifier:
        return None
    payload = value.get("payload")
    if not isinstance(payload, dict) or str(
        payload.get("id") or payload.get("experience_id") or payload.get("artifact_id") or ""
    ) != identifier:
        return None
    return value


def _substitution_dict(substitution: Substitution | None) -> dict[str, str] | None:
    """A substitution as a plain mapping, so reports stay JSON-serialisable."""
    if substitution is None:
        return None
    return {"kind": substitution.kind, "detail": substitution.detail,
            "evidence": substitution.evidence}


def find_substitution(artifact: Mapping[str, Any], *,
                      lexicon: Mapping[str, Any] | None = None,
                      experiences: Iterable[Mapping[str, Any]] = (),
                      memory_lines: Iterable[Mapping[str, Any]] = (),
                      protected: Iterable[str] = ()) -> Substitution | None:
    """Where forgetting this artifact costs nothing, or None.

    Order matters: a concrete substitute beats a category-level rule, because
    "something covers it" is a weaker claim than "this specific thing takes over
    its job".
    """
    lexicon = lexicon or {}
    name = _normalise(artifact.get("name") or artifact.get("artifact"))
    category = str(artifact.get("category") or artifact.get("artifact_type") or "").lower()

    # (a) a substitute artifact with a superseding record
    if name:
        for other in lexicon.get("concepts", []) or []:
            if not isinstance(other, Mapping):
                continue
            if _normalise(other.get("name")) != name:
                continue
            if str(other.get("id")) == str(artifact.get("id") or artifact.get("artifact_id")):
                continue
            if other.get("superseded_by") or other.get("supersedes"):
                return Substitution(
                    "substitute",
                    "a superseding artifact carries the same name",
                    f"{other.get('id')}:{other.get('superseded_by') or other.get('supersedes')}")

    # (b) a structured rule covering the same category
    for line in memory_lines or []:
        if not isinstance(line, Mapping):
            continue
        scope = _normalise(line.get("category") or line.get("scope"))
        if scope and category and scope == category:
            return Substitution(
                "structured",
                "a MemoryLine covers this category, so the detail is redundant",
                str(line.get("id") or line.get("name") or "memory_line"))

    # (c) absorbed by a later artifact that cites this one
    target = str(artifact.get("id") or artifact.get("experience_id") or artifact.get("artifact_id") or "")
    if target:
        for later in experiences:
            if not isinstance(later, Mapping):
                continue
            if str(later.get("experience_id") or later.get("id") or "") == target:
                continue
            if target in [str(r) for r in (later.get("related") or []) + (later.get("cites") or [])]:
                return Substitution(
                    "absorbed",
                    "a later artifact already carries this one forward",
                    str(later.get("experience_id") or later.get("id") or "unknown"))

    # (d) protected by lineage
    if any(target and str(p) == target for p in protected):
        return Substitution("never", "protected by a MemoryLine", str(target))

    return None


def assess(artifact: Mapping[str, Any], *, pollution_score: float,
           lexicon: Mapping[str, Any] | None = None,
           experiences: Iterable[Mapping[str, Any]] = (),
           memory_lines: Iterable[Mapping[str, Any]] = (),
           protected: Iterable[str] = ()) -> Assessment:
    """Forgettable only when dirty AND substitutable.

    Both conditions, deliberately. A dirty artifact with nothing to replace it
    creates a hole; a clean-but-substituted artifact has no reason to be
    forgotten. The first is the failure that makes forgetting dangerous, and
    the reason substitution is a gate rather than a tiebreaker.
    """
    artifact_id = str(artifact.get("id") or artifact.get("experience_id")
                      or artifact.get("artifact_id") or "")
    if pollution_score <= 0:
        return Assessment(artifact_id, False,
                          "not polluted: nothing to forget", None, pollution_score)

    substitution = find_substitution(
        artifact, lexicon=lexicon, experiences=experiences,
        memory_lines=memory_lines, protected=protected)

    category = str(artifact.get("category") or artifact.get("artifact_type") or "").lower()
    experience_type = str(artifact.get("experience_type") or "").lower()
    epistemic_status = str(artifact.get("epistemic_status") or "").upper()
    if experience_type in {"axiom", "constraint"} or epistemic_status in {
        "VERIFIED_FACT", "RULE"
    }:
        return Assessment(artifact_id, False,
                          "long-term governed experience: never forgettable",
                          None, pollution_score)
    if any(word in category for word in ("core", "principle", "axiom",
                                         "constraint", "invariant", "identity")):
        return Assessment(artifact_id, False,
                          "core-typed: never forgettable", None, pollution_score)
    if substitution is not None and substitution.kind == "never":
        return Assessment(artifact_id, False,
                         "protected by a MemoryLine", substitution, pollution_score)
    if substitution is None:
        return Assessment(
            artifact_id, False,
            "no substitution found: forgetting this would remove what no "
            "other artifact can replace", None, pollution_score)
    return Assessment(artifact_id, True,
                     f"substitutable via {substitution.kind}: {substitution.detail}",
                     substitution, pollution_score)


class MengpoRuntime:
    """Forget for real: remove, record, keep the tombstone, stay bounded."""

    def __init__(self, workspace_root: str | Path,
                 *, records_path: str | Path | None = None,
                 graveyard_path: str | Path | None = None,
                 state_path: str | Path | None = None,
                 protected: Iterable[str] = ()) -> None:
        self.root = Path(workspace_root).resolve()
        self.records_path = Path(records_path or
                                self.root / "08_GOVERNANCE" / "decisions"
                                / "mengpo_records.jsonl")
        self.graveyard_path = Path(graveyard_path or
                                  self.root / "08_GOVERNANCE" / "civilization"
                                  / "graveyard" / "runtime")
        self.state_path = Path(state_path or self.root / STATE_FILE)
        self._store_lock_path = self.root / "08_GOVERNANCE" / "decisions" / ".mengpo-runtime.lock"
        self._transaction_path = self.root / "08_GOVERNANCE" / "decisions" / ".mengpo-runtime-transaction.json"
        self.protected = list(protected)
        for directory in (self.records_path.parent, self.graveyard_path,
                           self.state_path.parent):
            directory.mkdir(parents=True, exist_ok=True)

    def _store_paths(self) -> tuple[Path, Path]:
        root = self.root.resolve()
        lexicon_path = root / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
        experiences_path = root / "09_KNOWLEDGE" / "experiences.json"
        for path in (lexicon_path, experiences_path):
            resolved = path.resolve(strict=False)
            if not resolved.is_relative_to(root):
                raise ValueError(f"Mengpo store path escapes workspace root: {path}")
        return lexicon_path, experiences_path

    @staticmethod
    def _validate_input_shapes(
        lexicon: Mapping[str, Any],
        experiences: list[Mapping[str, Any]],
        memory_lines: list[Mapping[str, Any]],
        pollution_scores: Mapping[str, float] | None,
    ) -> None:
        if not isinstance(lexicon, Mapping):
            raise TypeError("lexicon input must be an object")
        concepts = lexicon.get("concepts")
        if not isinstance(concepts, list):
            raise TypeError("unsupported lexicon concepts shape")
        for concept in concepts:
            if not isinstance(concept, Mapping):
                raise TypeError("lexicon candidate must be an object")
            identity = concept.get("id") or concept.get("name")
            if not isinstance(identity, str) or not identity.strip():
                raise ValueError("lexicon candidate has no stable identity")
        for experience in experiences:
            if not isinstance(experience, Mapping):
                raise TypeError("experience candidate must be an object")
            identity = experience.get("experience_id") or experience.get("id")
            if not isinstance(identity, str) or not identity.strip():
                raise ValueError("experience candidate has no stable identity")
        for line in memory_lines:
            if not isinstance(line, Mapping):
                raise TypeError("memory line must be an object")
        if pollution_scores is not None:
            if not isinstance(pollution_scores, Mapping):
                raise TypeError("pollution scores must be an object")
            for value in pollution_scores.values():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise TypeError("pollution score must be numeric")
                numeric_value = float(value)
                if not math.isfinite(numeric_value) or not 0.0 <= numeric_value <= 1.0:
                    raise ValueError("pollution score must be finite and between zero and one")

    @staticmethod
    def _read_json_store(path: Path, *, label: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"required Mengpo store is missing: {label}") from exc
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"required Mengpo store is unreadable: {label}") from exc
        if not isinstance(value, dict):
            raise TypeError(f"required Mengpo store has invalid shape: {label}")
        return value

    def _read_current_stores(
        self, lexicon_path: Path, experiences_path: Path
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        lexicon = self._read_json_store(lexicon_path, label="lexicon")
        concepts = lexicon.get("concepts")
        if not isinstance(concepts, list):
            raise TypeError("required Mengpo store has unsupported lexicon concepts shape")
        lexicon_ids: set[str] = set()
        for concept in concepts:
            if not isinstance(concept, Mapping):
                raise TypeError("required Mengpo store has invalid lexicon concept")
            identifier = concept.get("id") or concept.get("name")
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError("required Mengpo store has lexicon concept without identity")
            if identifier in lexicon_ids:
                raise ValueError("required Mengpo store has duplicate lexicon identity")
            lexicon_ids.add(identifier)

        experience_store = {"experiences": []}
        if experiences_path.exists():
            experience_store = self._read_json_store(
                experiences_path, label="legacy experience store"
            )
        items = experience_store.get("experiences")
        if not isinstance(items, list):
            raise TypeError("required Mengpo store has unsupported experience shape")
        experience_ids: set[str] = set()
        for experience in items:
            if not isinstance(experience, Mapping):
                raise TypeError("required Mengpo store has invalid experience record")
            identifier = experience.get("experience_id") or experience.get("id")
            if not isinstance(identifier, str) or not identifier.strip():
                raise ValueError("required Mengpo store has experience without identity")
            if identifier in experience_ids:
                raise ValueError("required Mengpo store has duplicate experience identity")
            experience_ids.add(identifier)
        if lexicon_ids & experience_ids:
            raise ValueError("artifact identities collide across Mengpo stores")
        return lexicon, experience_store

    def _recover_transaction(self) -> None:
        try:
            journal = json.loads(self._transaction_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise RuntimeError("Mengpo recovery journal is corrupt") from exc
        if not isinstance(journal, dict) or journal.get("version") != 1:
            raise RuntimeError("Mengpo recovery journal has unsupported shape")
        entries = journal.get("entries")
        if not isinstance(entries, list):
            raise TypeError("Mengpo recovery journal entries are invalid")
        root = self.root.resolve()
        restored: list[tuple[Path, bytes | None]] = []
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != {"path", "existed", "data"}:
                raise RuntimeError("Mengpo recovery journal entry is invalid")
            path = Path(entry["path"]).resolve(strict=False)
            if not path.is_relative_to(root):
                raise RuntimeError("Mengpo recovery journal path escapes workspace")
            if not isinstance(entry["existed"], bool):
                raise TypeError("Mengpo recovery journal existence flag is invalid")
            encoded = entry["data"]
            if entry["existed"]:
                if not isinstance(encoded, str):
                    raise RuntimeError("Mengpo recovery journal bytes are missing")
                try:
                    data = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise RuntimeError("Mengpo recovery journal bytes are invalid") from exc
            else:
                if encoded is not None:
                    raise RuntimeError("Mengpo recovery journal absence marker is invalid")
                data = None
            restored.append((path, data))
        for path, data in reversed(restored):
            if data is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write_bytes(path, data)
        self._transaction_path.unlink(missing_ok=True)

    def _begin_transaction(self, paths: Iterable[Path]) -> None:
        root = self.root.resolve()
        entries = []
        for path in dict.fromkeys(Path(item).resolve(strict=False) for item in paths):
            if not path.is_relative_to(root):
                raise ValueError(f"Mengpo transaction path escapes workspace: {path}")
            existed = path.exists()
            entries.append({
                "path": str(path),
                "existed": existed,
                "data": base64.b64encode(path.read_bytes()).decode("ascii") if existed else None,
            })
        _atomic_write_json(self._transaction_path, {"version": 1, "entries": entries})

    def _finish_transaction(self) -> None:
        self._transaction_path.unlink(missing_ok=True)

    @contextmanager
    def _exclusive_lock(self):
        """Serialize same-workspace runs across threads and processes."""
        lock_key = str(self._store_lock_path.resolve())
        with _THREAD_LOCKS_GUARD:
            thread_lock = _THREAD_LOCKS.setdefault(lock_key, threading.Lock())
        with thread_lock:
            lock_created = not self._store_lock_path.exists()
            handle = self._store_lock_path.open("a+b")
            if lock_created:
                os.chmod(self._store_lock_path, stat.S_IRUSR | stat.S_IWUSR)
            locked = False
            try:
                if os.name == "nt":
                    import msvcrt

                    handle.seek(0, os.SEEK_END)
                    if handle.tell() == 0:
                        handle.write(b"0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                locked = True
                self._recover_transaction()
                yield
            finally:
                try:
                    if locked:
                        if os.name == "nt":
                            import msvcrt

                            handle.seek(0)
                            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                        else:
                            import fcntl

                            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                finally:
                    handle.close()

    # ------------------------------------------------------------------ state

    def _load_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"runs": {}, "last_run_at": None, "last_run_result": None}
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"invalid Mengpo runtime state: {self.state_path}") from exc
        if not isinstance(state, dict):
            raise TypeError("Mengpo runtime state must be an object")
        unknown_fields = set(state) - {"runs", "last_run_at", "last_run_result"}
        if unknown_fields:
            raise ValueError("Mengpo runtime state has unsupported fields")
        runs = state.get("runs", {})
        if not isinstance(runs, dict):
            raise TypeError("Mengpo runtime state runs must be an object")
        for day, count in runs.items():
            try:
                date.fromisoformat(str(day))
            except (TypeError, ValueError) as exc:
                raise ValueError("Mengpo runtime state has an invalid run date") from exc
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise ValueError("Mengpo runtime state has an invalid run count")
        last_run_at = state.get("last_run_at")
        if last_run_at is not None:
            if not isinstance(last_run_at, str):
                raise ValueError("Mengpo runtime state last_run_at must be a string")
            try:
                parsed = datetime.fromisoformat(last_run_at)
            except ValueError as exc:
                raise ValueError("Mengpo runtime state last_run_at is invalid") from exc
            if parsed.tzinfo is None:
                raise ValueError("Mengpo runtime state last_run_at must be timezone-aware")
        last_result = state.get("last_run_result")
        if last_result is not None:
            if not isinstance(last_result, dict) or set(last_result) != {"forgotten", "skipped"}:
                raise ValueError("Mengpo runtime state last_run_result is invalid")
            for count in last_result.values():
                if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                    raise ValueError("Mengpo runtime state last_run_result is invalid")
        return {
            "runs": dict(runs),
            "last_run_at": last_run_at,
            "last_run_result": state.get("last_run_result"),
        }

    def _due(self, state: Mapping[str, Any]) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()
        runs = state["runs"]
        today_runs = runs.get(today, 0)
        if today_runs >= MAX_RUNS_PER_DAY:
            return False, f"daily run cap reached ({today_runs}/{MAX_RUNS_PER_DAY})"
        last = state["last_run_at"]
        if last:
            gap = (now - datetime.fromisoformat(last)).total_seconds() / 3600.0
            if gap < MIN_RUN_INTERVAL_HOURS:
                return False, f"cooldown: {gap:.1f}h since last run"
        return True, "due"

    def _record_run(self, forgotten: int, skipped: int) -> None:
        state = self._load_state()
        today = datetime.now(timezone.utc).date().isoformat()
        runs = state["runs"]
        runs[today] = int(runs.get(today) or 0) + 1
        state["last_run_at"] = datetime.now(timezone.utc).isoformat()
        state["last_run_result"] = {"forgotten": forgotten, "skipped": skipped}
        _atomic_write_json(self.state_path, state, sort_keys=True)

    # ------------------------------------------------------------------- run

    def run(self, *, lexicon: Mapping[str, Any],
            experiences: Iterable[Mapping[str, Any]] = (),
            memory_lines: Iterable[Mapping[str, Any]] = (),
            pollution_scores: Mapping[str, float] | None = None,
            dry_run: bool = False) -> dict[str, Any]:
        with self._exclusive_lock():
            return self._run_locked(
                lexicon=lexicon,
                experiences=experiences,
                memory_lines=memory_lines,
                pollution_scores=pollution_scores,
                dry_run=dry_run,
            )

    def _run_locked(self, *, lexicon: Mapping[str, Any],
                    experiences: Iterable[Mapping[str, Any]] = (),
                    memory_lines: Iterable[Mapping[str, Any]] = (),
                    pollution_scores: Mapping[str, float] | None = None,
                    dry_run: bool = False) -> dict[str, Any]:
        """Forget the substitutable-and-polluted, in one bounded run.

        Returns what it forgot, what it refused, and why. A refusal is a result:
        the runtime's whole value is that it declines to delete what it cannot
        replace.
        """
        try:
            experiences = list(experiences)
            memory_lines = list(memory_lines)
        except TypeError:
            return {
                "status": "UNSUPPORTED_INPUT",
                "reason": "experiences and memory_lines must be iterable collections",
                "contract_version": CONTRACT_VERSION,
                "forgotten": [],
                "refused": [],
                "counts": {"forgotten": 0, "refused": 0},
            }
        try:
            lexicon_path, experiences_path = self._store_paths()
            state = self._load_state()
            due, why = self._due(state)
        except (OSError, TypeError, ValueError) as exc:
            status = "INVALID_STORE" if "store" in str(exc).lower() else "STATE_CORRUPT"
            return {
                "status": status,
                "reason": str(exc),
                "contract_version": CONTRACT_VERSION,
                "forgotten": [],
                "refused": [],
                "counts": {"forgotten": 0, "refused": 0},
            }
        if not due:
            return {"status": "NOT_DUE", "reason": why,
                    "contract_version": CONTRACT_VERSION,
                    "forgotten": [], "refused": []}
        try:
            self._validate_input_shapes(lexicon, experiences, memory_lines, pollution_scores)
            lexicon_ids = {
                str(item.get("id") or item.get("name"))
                for item in lexicon["concepts"]
            }
            supplied_experience_ids = {
                str(item.get("experience_id") or item.get("id"))
                for item in experiences
            }
            store_lexicon, store_experiences = self._read_current_stores(
                lexicon_path, experiences_path
            )
            stored_lexicon_records = {
                str(item.get("id") or item.get("name")): item
                for item in store_lexicon["concepts"]
            }
            supplied_lexicon_records = {
                str(item.get("id") or item.get("name")): item
                for item in lexicon["concepts"]
            }
            if any(
                identity in stored_lexicon_records
                and not _same_payload(stored_lexicon_records[identity], supplied)
                for identity, supplied in supplied_lexicon_records.items()
                if identity in (pollution_scores or {})
            ):
                raise ValueError("lexicon candidates differ from canonical store records")
            supplied_experience_records = {
                str(item.get("experience_id") or item.get("id")): item
                for item in experiences
            }
            stored_experience_records = {
                str(item.get("experience_id") or item.get("id")): item
                for item in store_experiences["experiences"]
            }
            if any(
                identity in stored_experience_records
                and not _same_payload(stored_experience_records[identity], supplied)
                for identity, supplied in supplied_experience_records.items()
                if identity in (pollution_scores or {})
            ):
                raise ValueError("experience candidates differ from approved store records")
            stored_experience_ids = {
                str(item.get("experience_id") or item.get("id"))
                for item in store_experiences["experiences"]
            }
            scored_experience_ids = supplied_experience_ids & set(pollution_scores or {})
            if not scored_experience_ids.issubset(stored_experience_ids):
                raise ValueError("experience candidates are not present in an approved store")
            if set(pollution_scores or {}) - lexicon_ids - supplied_experience_ids:
                raise ValueError("pollution score references an unknown artifact identity")
        except (OSError, TypeError, ValueError) as exc:
            status = "INVALID_STORE" if "required mengpo store" in str(exc).lower() else "UNSUPPORTED_INPUT"
            return {
                "status": status,
                "reason": str(exc),
                "contract_version": CONTRACT_VERSION,
                "forgotten": [],
                "refused": [],
                "counts": {"forgotten": 0, "refused": 0},
            }

        pollution_scores = pollution_scores or {}

        forgotten: list[dict[str, Any]] = []
        refused: list[dict[str, Any]] = []

        pool: list[tuple[Mapping[str, Any], float]] = []
        for concept in lexicon.get("concepts") or []:
            if not isinstance(concept, Mapping):
                continue
            identifier = str(concept.get("id") or concept.get("name") or "")
            pool.append((concept, float(pollution_scores.get(identifier, 0.0))))
        for experience in experiences:
            identifier = str(experience.get("experience_id")
                             or experience.get("id") or "")
            pool.append((experience, float(pollution_scores.get(identifier, 0.0))))

        pool.sort(key=lambda item: item[1], reverse=True)
        planned: list[tuple[Mapping[str, Any], Assessment]] = []
        seen_ids: set[str] = set()
        for artifact, score in pool:
            verdict = assess(
                artifact, pollution_score=score,
                lexicon=lexicon, experiences=experiences,
                memory_lines=memory_lines, protected=self.protected)
            if not verdict.forgettable:
                refused.append({"artifact_id": verdict.artifact_id,
                                "reason": verdict.reason,
                                "pollution_score": score})
                continue
            identifier = verdict.artifact_id
            if identifier in seen_ids:
                refused.append({
                    "artifact_id": identifier,
                    "reason": "duplicate candidate identity in request",
                    "pollution_score": score,
                })
                continue
            seen_ids.add(identifier)
            if len(planned) >= MAX_PER_RUN:
                continue
            planned.append((artifact, verdict))

        if dry_run:
            for artifact, verdict in planned:
                forgotten.append({
                    "artifact_id": verdict.artifact_id,
                    "reason": verdict.reason,
                    "substitution": _substitution_dict(verdict.substitution),
                    "applied": False,
                })
        elif planned:
            accepted = []
            tombstone_paths = []
            for artifact, verdict in planned:
                safe_id = _safe_artifact_id(verdict.artifact_id or "")
                target = self.graveyard_path / f"{safe_id}.json"
                if target.exists():
                    refused.append({
                        "artifact_id": verdict.artifact_id,
                        "reason": "tombstone already exists; ID reuse requires reviewed recovery",
                        "pollution_score": verdict.pollution_score,
                    })
                    continue
                accepted.append((artifact, verdict))
                tombstone_paths.append(target)
            if accepted:
                transaction_paths = [
                    lexicon_path,
                    experiences_path,
                    self.records_path,
                    self.state_path,
                    *tombstone_paths,
                    *(
                        path.with_suffix(path.suffix + ".mengpo-backup")
                        for path in (lexicon_path, experiences_path)
                    ),
                ]
                self._begin_transaction(transaction_paths)
                try:
                    for artifact, verdict in accepted:
                        if not self._forget(artifact, verdict):
                            refused.append({
                                "artifact_id": verdict.artifact_id,
                                "reason": "candidate changed during transaction",
                                "pollution_score": verdict.pollution_score,
                            })
                            continue
                        forgotten.append({
                            "artifact_id": verdict.artifact_id,
                            "reason": verdict.reason,
                            "substitution": _substitution_dict(verdict.substitution),
                            "applied": True,
                        })
                    if forgotten:
                        self._record_run(len(forgotten), len(refused))
                    self._finish_transaction()
                except BaseException:
                    self._recover_transaction()
                    raise
        else:
            self._record_run(0, len(refused))
        applied_count = sum(1 for item in forgotten if item.get("applied"))
        if dry_run:
            status = "DRY_RUN"
        elif applied_count:
            status = "APPLIED"
        elif refused:
            status = "REFUSED"
        else:
            status = "NO_OP"
        reported_forgotten_count = len(forgotten) if dry_run else applied_count
        return {
            "status": status,
            "contract_version": CONTRACT_VERSION,
            "forgotten": forgotten,
            "refused": refused,
            "counts": {
                "forgotten": reported_forgotten_count,
                "refused": len(refused),
            },
        }

    # --------------------------------------------------------------- forgetting

    def _forget(self, artifact: Mapping[str, Any], verdict: Assessment) -> bool:
        """Remove for real, in every store, and leave a reversible tombstone."""
        payload = json.loads(json.dumps(artifact, ensure_ascii=False, default=str))
        identifier = verdict.artifact_id or "unknown"

        tombstone = {
            "contract_version": CONTRACT_VERSION,
            "id": identifier,
            "payload": payload,
            "forgotten_at": datetime.now(timezone.utc).isoformat(),
            "forgotten_reason": verdict.reason,
            "substitution": (verdict.substitution.__dict__
                             if verdict.substitution else None),
            "pollution_score": verdict.pollution_score,
            "recoverable_by": "restore payload from this tombstone into the store",
        }
        try:
            safe_identifier = _safe_artifact_id(identifier)
        except ValueError as exc:
            raise ValueError("unsafe artifact identifier; refusing forget") from exc
        target = self.graveyard_path / f"{safe_identifier}.json"
        lexicon_path, experiences_path = self._store_paths()
        lexicon, experience_store = self._read_current_stores(
            lexicon_path, experiences_path
        )
        target_matches = [
            item for item in lexicon["concepts"]
            if str(item.get("id") or item.get("name") or "") == identifier
        ]
        target_matches += [
            item for item in experience_store["experiences"]
            if str(item.get("experience_id") or item.get("id") or "") == identifier
        ]
        if len(target_matches) != 1 or not _same_payload(target_matches[0], payload):
            return False

        if target.exists():
            return False
        _atomic_write_json(target, tombstone)
        removed = self._remove_from_store(identifier, payload)
        if len(removed) != 1:
            raise RuntimeError("deletion did not change exactly one store record")

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "forget",
            "artifact_id": identifier,
            "artifact_type": str(artifact.get("category")
                                  or artifact.get("artifact_type") or "unknown"),
            "reason": verdict.reason,
            "pollution_score": verdict.pollution_score,
            "affected_items": removed,
            "substitution": (verdict.substitution.__dict__
                             if verdict.substitution else None),
            "tombstone": str(target),
            "contract_version": CONTRACT_VERSION,
        }
        _append_jsonl_record(self.records_path, record)
        return bool(removed)

    def _remove_from_store(self, identifier: str, payload: Mapping[str, Any]) -> list[str]:
        """Remove from the lexicon and the experience store. Returns what it hit.

        The removal is real. This is the part the original forget() was missing,
        and it is the difference between a tombstone and a deletion.
        """
        _safe_artifact_id(identifier)
        lexicon_path, experiences_path = self._store_paths()
        lexicon, experience_store = self._read_current_stores(
            lexicon_path, experiences_path
        )
        concept_items = lexicon["concepts"]
        experience_items = experience_store["experiences"]
        lexicon_matches = [
            item for item in concept_items
            if str(item.get("id") or item.get("name") or "") == identifier
        ]
        experience_matches = [
            item for item in experience_items
            if str(item.get("experience_id") or item.get("id") or "") == identifier
        ]
        payload_id = str(
            payload.get("id") or payload.get("experience_id") or payload.get("artifact_id") or ""
        )
        if payload_id != identifier:
            raise ValueError("artifact payload identity does not match deletion target")
        if bool(lexicon_matches) == bool(experience_matches):
            raise ValueError("artifact must resolve to exactly one authorized store target")
        if lexicon_matches and not _same_payload(lexicon_matches[0], payload):
            raise ValueError("candidate payload differs from current canonical lexicon record")
        if experience_matches and not _same_payload(experience_matches[0], payload):
            raise ValueError("candidate payload differs from current experience record")

        if lexicon_matches:
            lexicon["concepts"] = [item for item in concept_items if item not in lexicon_matches]
            backup = lexicon_path.with_suffix(".json.mengpo-backup")
            shutil.copy2(lexicon_path, backup)
            _atomic_write_json(lexicon_path, lexicon)
            return [f"lexicon:{identifier}"]

        experience_store["experiences"] = [
            item for item in experience_items if item not in experience_matches
        ]
        backup = experiences_path.with_suffix(".json.mengpo-backup")
        shutil.copy2(experiences_path, backup)
        _atomic_write_json(experiences_path, experience_store)

        return [f"experiences:{identifier}"]