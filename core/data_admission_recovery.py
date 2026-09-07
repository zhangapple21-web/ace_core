"""Durable diagnosis and recovery routing for data-admission blockers.

This module neither relaxes Phase Two nor performs network work.  It turns a
current capability matrix into a bounded, source-specific recovery contract
so a recurring ``NOT_ADMITTED`` state is not mistaken for progress.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REQUIRED_OPERATIONS = ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index")
RESEARCH_CANDIDATE_SOURCES = {
    "quote": ("sina_direct", "tencent_direct"),
    "daily_kline": ("tencent_direct", "baostock"),
    "minute_kline_1m": ("sina_direct", "tencent_direct"),
    "minute_kline_5m": ("tencent_direct", "baostock"),
    "index": ("sina_direct", "tencent_direct"),
}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class DataAdmissionRecovery:
    """Single-writer, evidence-only recovery ledger under the existing data dir."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "stock_data_evidence" / "data_admission_recovery_latest.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _write(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def build(self, matrix: Mapping[str, Any], *, observed_at: str | None = None) -> dict[str, Any]:
        admission = matrix.get("phase_two_admission", {}) if isinstance(matrix, Mapping) else {}
        operations = admission.get("core_operations", {}) if isinstance(admission, Mapping) else {}
        operation_rows: dict[str, Any] = {}
        unresolved: list[str] = []
        for operation in REQUIRED_OPERATIONS:
            detail = operations.get(operation, {}) if isinstance(operations, Mapping) else {}
            detail = detail if isinstance(detail, Mapping) else {}
            sources = sorted(str(item) for item in detail.get("production_sources", []) if str(item))
            groups = sorted(set(str(item) for item in detail.get("independence_groups", []) if str(item)))
            cross_validated = detail.get("has_independent_cross_validation") is True
            blockers: list[str] = []
            if not sources:
                blockers.append("NO_QUALIFIED_PRODUCTION_SOURCE")
            if len(groups) < 2 or not cross_validated:
                blockers.append("INDEPENDENT_CROSS_VALIDATION_MISSING")
            status = "READY" if not blockers else "BLOCKED"
            if blockers:
                unresolved.append(operation)
            operation_rows[operation] = {
                "status": status,
                "blockers": blockers,
                "qualified_sources": sources,
                "independence_groups": groups,
                "research_candidate_sources": list(RESEARCH_CANDIDATE_SOURCES[operation]),
                "verification": "a candidate source needs isolated evidence and a fresh admission review before it can enter the existing open-validation refresh",
            }
        blocker_fingerprint = _digest({name: row["blockers"] for name, row in operation_rows.items()})
        prior = self._read(self.path)
        repeated = prior.get("blocker_fingerprint") == blocker_fingerprint
        consecutive = int(prior.get("consecutive_unchanged_observations", 0)) + 1 if repeated else 1
        state = "RECOVERY_VERIFICATION_DUE" if unresolved and consecutive >= 3 else ("RECOVERY_IN_PROGRESS" if unresolved else "ADMISSION_READY")
        report = {
            "contract_version": "ace.data_admission_recovery.v1",
            "recorded_at": observed_at or datetime.now(timezone.utc).isoformat(),
            "phase_two_status": admission.get("status", "NOT_RECORDED") if isinstance(admission, Mapping) else "NOT_RECORDED",
            "recovery_status": state,
            "unresolved_operations": unresolved,
            "operations": operation_rows,
            "blocker_fingerprint": blocker_fingerprint,
            "consecutive_unchanged_observations": consecutive,
            "next_action": "research_candidate_source_evidence_without_changing_the_existing_refresh_or_admission" if unresolved else "keep_existing_admission_gate_and_revalidate_candidates",
            "side_effects": {"network_called": False, "taskpool_mutated": False, "admission_changed": False, "recommendation_created": False},
            "semantics": "This ledger explains and routes evidence repair; it never treats a planned probe or recovery status as data admission.",
        }
        self._write(self.path, report)
        return report
