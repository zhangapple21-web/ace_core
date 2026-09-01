"""Fail-closed, portable continuity evidence for the ACE motherplate.

This is deliberately an auditor, not a recovery engine.  It observes the
existing runtime, governance roots, task ledger and Free Zone boundary, then
records a small hash-chained receipt.  It never starts a daemon, replays work,
creates a task, invokes a model, or promotes research.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


SCHEMA_VERSION = 1
REQUIRED_ANCHORS = (
    "AGENTS.md",
    "ace_config.json",
    "README.md",
    "00_ROOT/PRINCIPLES.md",
    "00_ROOT/ARCHITECTURE.md",
    "ace_daemon.py",
    "core/task.py",
    "core/daily_shift.py",
    "core/free_research_sandbox.py",
    "core/free_zone_reality_bridge.py",
    "core/free_zone_model_research.py",
    "core/free_zone_model_shift.py",
    "core/meaning_line.py",
    "core/stock_data_reliability.py",
    "core/data_admission_recovery.py",
    "core/continuity_audit.py",
)
OPTIONAL_FOOTPRINTS = (
    "06_RUNTIME/ace/data/memory/daemon_state.json",
    "06_RUNTIME/ace/data/memory/heartbeat.json",
    "06_RUNTIME/ace/data/daily_shift_latest.json",
    "06_RUNTIME/ace/data/daily_growth_latest.json",
    "06_RUNTIME/ace/data/hourly_task_service_latest.json",
    "06_RUNTIME/ace/data/stock_data_evidence/data_admission_recovery_latest.json",
    "07_SANDBOX/free_research/autonomy_state.json",
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical(value).encode("utf-8"))


class ContinuityAuditor:
    """Read and write hash-bound continuity receipts for one ACE checkout."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.data_dir = self.root / "06_RUNTIME" / "ace" / "data" / "memory"
        self.continuity_dir = self.data_dir / "continuity"
        self.ledger_path = self.continuity_dir / "ledger.jsonl"
        self.latest_path = self.continuity_dir / "continuity_latest.json"

    @staticmethod
    def _host_id() -> str:
        # The receipt only needs to distinguish hosts.  Persisting a digest
        # avoids turning a machine name into application memory.
        return _sha256_bytes(platform.node().encode("utf-8"))[:24]

    @staticmethod
    def _atomic_write(path: Path, value: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _anchors(self) -> Tuple[Dict[str, str], List[str]]:
        anchors: Dict[str, str] = {}
        reasons: List[str] = []
        for relative in REQUIRED_ANCHORS:
            path = self.root / relative
            if not path.is_file():
                reasons.append(f"MISSING_REQUIRED_ANCHOR:{relative}")
                continue
            try:
                anchors[relative] = _sha256_bytes(path.read_bytes())
            except OSError:
                reasons.append(f"UNREADABLE_REQUIRED_ANCHOR:{relative}")
        return anchors, reasons

    def current_anchor_snapshot(self) -> Dict[str, Any]:
        """Return the disk motherplate identity a new daemon would load.

        This is intentionally a read-only snapshot.  Capturing it at daemon
        startup lets a later audit distinguish the current files from the
        Python modules an already-running process actually began with.
        """
        anchors, reasons = self._anchors()
        return {
            "anchor_set_sha256": _sha256_json(anchors),
            "anchor_count": len(anchors),
            "reason_codes": reasons,
        }

    def _git_identity(self) -> Dict[str, Any]:
        if not (self.root / ".git").exists():
            return {"available": False}
        try:
            head = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=3, check=False,
            ).stdout.strip()
            status = subprocess.run(
                ["git", "-C", str(self.root), "status", "--porcelain=v1"],
                capture_output=True, text=True, timeout=3, check=False,
            ).stdout.splitlines()
            return {"available": bool(head), "head": head or None, "dirty_path_count": len(status)}
        except (OSError, subprocess.SubprocessError):
            return {"available": False, "error": "git_identity_unavailable"}

    def _runtime_footprint(self, *, current_anchor_set_sha256: str) -> Dict[str, Any]:
        artifacts: Dict[str, Dict[str, Any]] = {}
        for relative in OPTIONAL_FOOTPRINTS:
            path = self.root / relative
            if path.is_file():
                try:
                    artifacts[relative] = {"present": True, "sha256": _sha256_bytes(path.read_bytes())}
                except OSError:
                    artifacts[relative] = {"present": False, "reason": "unreadable"}
            else:
                artifacts[relative] = {"present": False}

        state = self._read_json(self.root / "06_RUNTIME/ace/data/memory/daemon_state.json")
        heartbeat = self._read_json(self.root / "06_RUNTIME/ace/data/memory/heartbeat.json")
        run_started_at = state.get("run_started_at")
        last_exit_at = state.get("last_exit_time")
        last_exit_scope = "not_recorded"
        if last_exit_at:
            last_exit_scope = "current_or_unknown"
            if run_started_at and str(last_exit_at) < str(run_started_at):
                last_exit_scope = "prior_run"
        if isinstance(state.get("previous_run_exit"), dict):
            last_exit_scope = "prior_run_archived"
        task_pool = self.root / "task_pool"
        task_files = sum(1 for _ in task_pool.glob("*.json")) if task_pool.is_dir() else 0
        loaded_anchor_set_sha256 = state.get("loaded_anchor_set_sha256")
        if not isinstance(loaded_anchor_set_sha256, str) or not loaded_anchor_set_sha256:
            runtime_adoption = {
                "status": "DAEMON_LOADED_VERSION_UNATTESTED",
                "loaded_anchor_set_sha256": None,
                "current_anchor_set_sha256": current_anchor_set_sha256,
                "reason": "daemon_state_has_no_startup_anchor_snapshot",
            }
        elif loaded_anchor_set_sha256 != current_anchor_set_sha256:
            runtime_adoption = {
                "status": "DAEMON_RESTART_REQUIRED_FOR_CURRENT_ANCHORS",
                "loaded_anchor_set_sha256": loaded_anchor_set_sha256,
                "current_anchor_set_sha256": current_anchor_set_sha256,
                "reason": "disk_motherplate_changed_after_daemon_startup",
            }
        else:
            runtime_adoption = {
                "status": "DAEMON_LOADED_CURRENT_ANCHORS",
                "loaded_anchor_set_sha256": loaded_anchor_set_sha256,
                "current_anchor_set_sha256": current_anchor_set_sha256,
                "reason": "startup_snapshot_matches_current_motherplate",
            }
        return {
            "artifacts": artifacts,
            "daemon_identity": {
                "run_id_present": bool(state.get("run_id")),
                "pid_present": isinstance(state.get("pid"), int),
                "run_status": state.get("run_status"),
                "cycle_status": (state.get("cycle_progress") or {}).get("cycle_status"),
                "heartbeat_run_id_matches": bool(state.get("run_id")) and state.get("run_id") == heartbeat.get("run_id"),
                "last_exit_record_scope": last_exit_scope,
            },
            "runtime_adoption": runtime_adoption,
            "taskpool": {"directory_present": task_pool.is_dir(), "task_file_count": task_files},
            "free_zone": {
                "boundary_artifact_present": (self.root / "07_SANDBOX/free_research").is_dir(),
                "production_integration": False,
            },
        }

    def _load_ledger(self) -> Tuple[List[Dict[str, Any]], List[str]]:
        if not self.ledger_path.exists():
            return [], []
        entries: List[Dict[str, Any]] = []
        reasons: List[str] = []
        try:
            lines = self.ledger_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return [], ["LEDGER_UNREADABLE"]
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                reasons.append(f"LEDGER_MALFORMED_LINE:{number}")
                continue
            if not isinstance(entry, dict):
                reasons.append(f"LEDGER_INVALID_ENTRY:{number}")
                continue
            entries.append(entry)
        previous_hash: Optional[str] = None
        for number, entry in enumerate(entries, start=1):
            entry_hash = entry.get("entry_hash")
            without_hash = {key: value for key, value in entry.items() if key != "entry_hash"}
            if not isinstance(entry_hash, str) or entry_hash != _sha256_json(without_hash):
                reasons.append("LEDGER_HASH_INVALID")
            if entry.get("previous_entry_hash") != previous_hash:
                reasons.append("LEDGER_CHAIN_BREAK")
            previous_hash = entry_hash if isinstance(entry_hash, str) else None
        return entries, list(dict.fromkeys(reasons))

    def audit(
        self,
        *,
        record: bool = True,
        host_id: Optional[str] = None,
        runtime_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build one truthful continuity conclusion and optionally record it."""
        host = host_id or self._host_id()
        anchors, reasons = self._anchors()
        entries, ledger_reasons = self._load_ledger()
        reasons.extend(ledger_reasons)
        prior = entries[-1] if entries else None
        prior_anchors = prior.get("anchors", {}) if isinstance(prior, dict) else {}
        prior_anchors = prior_anchors if isinstance(prior_anchors, dict) else {}
        anchor_changes = {
            "added": sorted(set(anchors) - set(prior_anchors)),
            "removed": sorted(set(prior_anchors) - set(anchors)),
            "modified": sorted(
                key for key in set(anchors).intersection(prior_anchors)
                if anchors[key] != prior_anchors[key]
            ),
        }
        anchors_changed = any(anchor_changes.values())
        if prior and anchors_changed:
            reasons.append("ANCHOR_SET_CHANGED")
        migration = {
            "detected": bool(prior and prior.get("host_id") != host),
            "previous_host_id": prior.get("host_id") if prior else None,
            "current_host_id": host,
        }
        chain_valid = not ledger_reasons
        if any(reason.startswith(("MISSING_", "UNREADABLE_", "LEDGER_")) for reason in reasons):
            status, level = "CONTINUITY_DEGRADED", "NO_CONTINUITY_CLAIM"
        elif not prior:
            status, level = "CONTINUITY_ESTABLISHED", "BASELINE_ONLY"
        elif anchors_changed:
            # A preserved chain proves the historical transition happened, but
            # it cannot infer whether a changed root was intended.  Record the
            # first changed receipt honestly; a later identical receipt can
            # verify that this new motherplate persisted across a boundary.
            status, level = "CONTINUITY_CHANGED_UNATTESTED", "HASH_CHAIN_WITH_CHANGE_DISCLOSURE"
        elif migration["detected"]:
            status, level = "CONTINUITY_VERIFIED_AFTER_MIGRATION", "HASH_CHAIN_AND_ANCHORS"
        else:
            status, level = "CONTINUITY_VERIFIED", "HASH_CHAIN_AND_ANCHORS"

        recorded_at = datetime.now(timezone.utc).isoformat()
        report: Dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "recorded_at": recorded_at,
            "continuity_status": status,
            "claim_level": level,
            "reason_codes": list(dict.fromkeys(reasons)),
            "anchors": anchors,
            "anchor_set_sha256": _sha256_json(anchors),
            "anchor_changes_since_previous_receipt": anchor_changes,
            "repository": self._git_identity(),
            "runtime_footprint": self._runtime_footprint(
                current_anchor_set_sha256=_sha256_json(anchors)
            ),
            "runtime_context": runtime_context or {},
            "migration": migration,
            "ledger": {
                "path": str(self.ledger_path.relative_to(self.root)),
                "entry_count_before": len(entries),
                "chain_valid": chain_valid,
                "previous_entry_hash": prior.get("entry_hash") if prior else None,
            },
            "scope": ["motherplate_anchors", "governed_runtime", "taskpool_presence", "free_zone_boundary", "local_cloud_research_path"],
            "non_claims": [
                "does_not_prove_a_daemon_is_currently_running",
                "does_not_prove_a_running_daemon_loaded_current_anchors_without_matching_startup_snapshot",
                "does_not_prove_a_natural_cycle_completed",
                "does_not_promote_free_zone_or_change_admission",
            ],
            "side_effects": {"taskpool_mutated": False, "model_called": False, "production_changed": False},
        }
        if record:
            entry = {
                "schema_version": SCHEMA_VERSION,
                "recorded_at": recorded_at,
                "host_id": host,
                "continuity_status": status,
                "claim_level": level,
                "anchor_set_sha256": report["anchor_set_sha256"],
                "anchors": anchors,
                "runtime_footprint_sha256": _sha256_json(report["runtime_footprint"]),
                "previous_entry_hash": prior.get("entry_hash") if prior else None,
            }
            entry["entry_hash"] = _sha256_json(entry)
            self.continuity_dir.mkdir(parents=True, exist_ok=True)
            with self.ledger_path.open("a", encoding="utf-8") as handle:
                handle.write(_canonical(entry) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            report["ledger"]["entry_hash"] = entry["entry_hash"]
            report["ledger"]["entry_count_after"] = len(entries) + 1
            self._atomic_write(self.latest_path, json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return report
