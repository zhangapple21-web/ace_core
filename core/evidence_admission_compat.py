"""Shadow-only compatibility and reporting for evidence admission.

Nothing in this module writes TaskPool state or changes producer behavior.  It
is intentionally an offline/read-only layer for migrating historical Validator
signatures to the current canonical evidence signature (version 2).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

from .evidence_admission import evaluate_candidate, evidence_signature


CURRENT_SIGNATURE_VERSION = 2
TERMINAL_STATUSES = {"archived", "graveyard", "rejected"}


def signature_state(task: Mapping[str, Any]) -> str:
    """Classify persisted signature metadata without changing it.

    ``current`` means version 2 exists and matches a fresh canonical signature;
    ``legacy`` means a signature exists without the current version marker;
    ``unavailable`` means there is no usable signature or the metadata conflicts.
    """
    outputs = task.get("outputs", {}) or {}
    stored = outputs.get("last_validated_evidence_signature")
    version = outputs.get("evidence_signature_version")
    computed = evidence_signature(task.get("evidence", []))
    if not stored:
        return "unavailable"
    if version == CURRENT_SIGNATURE_VERSION and computed and stored == computed:
        return "current"
    if version != CURRENT_SIGNATURE_VERSION:
        return "legacy"
    return "unavailable"


def load_snapshot(pool_dir: str | Path) -> tuple[dict[str, Any], ...]:
    """Read a deterministic JSON snapshot in memory; never writes or moves files."""
    tasks = []
    for path in sorted(Path(pool_dir).glob("RQ-*.json")):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(task, dict):
            tasks.append(task)
    return tuple(tasks)


def _candidate(task: Mapping[str, Any]) -> dict[str, Any]:
    outputs = task.get("outputs", {}) or {}
    return {
        "admission": outputs.get("admission"),
        "evidence": task.get("evidence", []),
        "model_task_admission": outputs.get("model_task_admission"),
    }


def shadow_report(tasks: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Return would-be decisions and compatibility facts for an in-memory snapshot."""
    materialized = tuple(tasks)
    decisions = Counter()
    reasons = Counter()
    signature_states = Counter(signature_state(task) for task in materialized)
    records = []
    for task in materialized:
        existing = tuple(
            other for other in materialized
            if other.get("task_id") != task.get("task_id")
            and other.get("status") not in TERMINAL_STATUSES
        )
        decision = evaluate_candidate(_candidate(task), existing)
        decisions[decision.decision] += 1
        reasons[decision.reason] += 1
        records.append({
            "task_id": task.get("task_id", ""),
            "would_decision": decision.decision,
            "would_reason": decision.reason,
            "signature_state": signature_state(task),
            "evidence_signature": decision.evidence_signature,
            "duplicate_task_ids": list(decision.duplicate_task_ids),
            "quality": decision.to_dict()["quality"],
        })
    return {
        "mode": "shadow_only",
        "signature_version": CURRENT_SIGNATURE_VERSION,
        "task_count": len(materialized),
        "decisions": dict(decisions),
        "reasons": dict(reasons),
        "signature_states": dict(signature_states),
        "records": records,
    }
