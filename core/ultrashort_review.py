"""Immutable snapshot, teacher-review, and outcome boundaries.

The daily A/A+ call answers only: "what was true at this snapshot time?"
Later invalidation is a separate outcome record.  Teacher decisions are also
recorded as labels and sampling metadata; they never rewrite the snapshot or
silently change permanent factors.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.ultrashort_review_boundary.v1"
TEACHER_DECISIONS = ("APPROVED", "REJECTED", "DEFERRED")
OUTCOMES = (
    "VALIDATED",
    "INVALIDATED",
    "DIRECTION_RIGHT_TIMING_WRONG",
    "EVIDENCE_INSUFFICIENT",
    "NOT_TRADED",
)


def _time(value: Any, field: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_must_be_iso_timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field}_requires_timezone")
    return parsed.isoformat()


def _hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _refs(value: Sequence[Any] | None) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError("source_refs_must_be_sequence")
    return [str(item) for item in value if str(item).strip()]


def freeze_opportunity_snapshot(
    call: Mapping[str, Any],
    *,
    snapshot_id: str,
    as_of: str,
    source_refs: Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Freeze a point-in-time daily call with a content hash."""

    if not isinstance(call, Mapping):
        raise ValueError("opportunity_call_must_be_mapping")
    if not str(snapshot_id).strip():
        raise ValueError("snapshot_id_must_be_non_empty")
    normalized_as_of = _time(as_of, "snapshot_as_of")
    required = ("daily_signal", "candidate_count", "best_candidate_id", "best_attack_grade")
    missing = [field for field in required if field not in call]
    if missing:
        raise ValueError(f"opportunity_call_missing: {', '.join(missing)}")
    payload = {
        "contract_version": CONTRACT_VERSION,
        "record_type": "OPPORTUNITY_SNAPSHOT",
        "snapshot_id": str(snapshot_id),
        "snapshot_as_of": normalized_as_of,
        "snapshot_scope": "AS_OF_NOT_FINAL_DAY_GRADE",
        "daily_call": json.loads(json.dumps(dict(call), ensure_ascii=False)),
        "source_refs": _refs(source_refs),
        "research_status": "RESEARCH_ONLY",
        "outcome_status": "PENDING_REVIEW",
        "outcome_may_not_backfill_daily_call": True,
        "teacher_decision": None,
        "rule_update_authorized": False,
    }
    payload["snapshot_hash"] = _hash(payload)
    return payload


def record_opportunity_outcome(
    snapshot: Mapping[str, Any],
    *,
    outcome: str,
    reviewed_at: str,
    source_refs: Sequence[Any],
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record D+1/D+2 evidence without mutating the original snapshot."""

    if not isinstance(snapshot, Mapping) or snapshot.get("record_type") != "OPPORTUNITY_SNAPSHOT":
        raise ValueError("snapshot_record_required")
    if outcome not in OUTCOMES:
        raise ValueError("outcome_invalid")
    refs = _refs(source_refs)
    if not refs:
        raise ValueError("outcome_source_refs_required")
    snapshot_hash = str(snapshot.get("snapshot_hash", "")).strip()
    if not snapshot_hash:
        raise ValueError("snapshot_hash_required")
    return {
        "contract_version": CONTRACT_VERSION,
        "record_type": "OPPORTUNITY_OUTCOME_REVIEW",
        "snapshot_id": str(snapshot.get("snapshot_id", "")),
        "source_snapshot_hash": snapshot_hash,
        "snapshot_as_of": str(snapshot.get("snapshot_as_of", "")),
        "outcome_reviewed_at": _time(reviewed_at, "outcome_reviewed_at"),
        "outcome": outcome,
        "details": dict(details or {}),
        "source_refs": refs,
        "research_status": "RESEARCH_ONLY",
        "snapshot_unchanged": True,
        "daily_call_backfilled": False,
        "rule_update_authorized": False,
    }


def record_teacher_decision(
    snapshot: Mapping[str, Any],
    *,
    decision: str,
    decided_at: str,
    rationale: str,
) -> dict[str, Any]:
    """Record teacher judgement without creating survivorship bias or rule drift.

    All reviewed candidates stay in the selection sample.  All are eligible
    for counterfactual outcome replay; only an approved candidate with separate
    execution evidence can later be labelled as actually traded.
    """

    if not isinstance(snapshot, Mapping) or snapshot.get("record_type") != "OPPORTUNITY_SNAPSHOT":
        raise ValueError("snapshot_record_required")
    choice = str(decision).strip().upper()
    if choice not in TEACHER_DECISIONS:
        raise ValueError("teacher_decision_invalid")
    if not str(rationale).strip():
        raise ValueError("teacher_rationale_required")
    return {
        "contract_version": CONTRACT_VERSION,
        "record_type": "TEACHER_DECISION",
        "snapshot_id": str(snapshot.get("snapshot_id", "")),
        "source_snapshot_hash": str(snapshot.get("snapshot_hash", "")),
        "snapshot_as_of": str(snapshot.get("snapshot_as_of", "")),
        "decided_at": _time(decided_at, "decided_at"),
        "decision": choice,
        "rationale": str(rationale).strip(),
        "research_status": "RESEARCH_ONLY",
        "sample_policy": {
            "selection_sample_included": True,
            "outcome_replay_eligible": True,
            "counterfactual_replay": choice != "APPROVED",
            "executed_trade_claim": False,
            "execution_replay_requires_separate_fill_evidence": True,
        },
        "manual_judgement_policy": {
            "stored_as_context_label": True,
            "changes_snapshot": False,
            "changes_factor_score": False,
            "changes_permanent_weights": False,
            "rule_update_authorized": False,
            "requires_independent_replay_before_any_rule_proposal": True,
        },
    }


def metadata() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "snapshot_semantics": "AS_OF_NOT_FINAL_DAY_GRADE",
        "outcome_is_separate_record": True,
        "teacher_rejected_kept_in_selection_sample": True,
        "teacher_approved_replay_requires_fill_evidence": True,
        "counterfactual_replay_includes_rejected": True,
        "manual_judgement_changes_rules": False,
        "production_integration": False,
        "recommendation_authority": False,
    }
