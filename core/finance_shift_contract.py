"""Read-only contracts for the finance section of an ACE Daily Shift.

This module deliberately does not discover, admit, rank, or publish a symbol.
It only classifies records already supplied by another governed component.
"""

from typing import Any, Dict, Iterable, List


EVALUATION_PICK_REQUIRED_FIELDS = (
    "recommendation_id",
    "timestamp",
    "symbol",
    "reference_price",
    "hypothesis",
    "invalidating_conditions",
    "next_verification",
    "data_snapshot_hash",
    "source_refs",
    "data_quality_state",
    "feature_version",
    "advisor_version",
    "risk_version",
)


def _non_empty(value: Any) -> bool:
    return value not in (None, "", [], {})


def is_eligible_evaluation_pick(candidate: Any) -> bool:
    """Return true only for a fully traceable, explicitly paper-only record."""
    if not isinstance(candidate, dict) or candidate.get("evaluation_only") is not True:
        return False
    return all(_non_empty(candidate.get(field)) for field in EVALUATION_PICK_REQUIRED_FIELDS)


def build_evaluation_slots(candidates: Iterable[Any], *, target: int = 2) -> Dict[str, Any]:
    """Represent an upper bound, never a quota, for governed paper picks."""
    target = max(0, int(target))
    eligible: List[Dict[str, Any]] = [
        item for item in candidates if is_eligible_evaluation_pick(item)
    ]
    # ``target`` is an upper bound, not a truncation instruction.  Silently
    # dropping the third eligible record would make an over-limit producer
    # look valid and would hide a possible duplicate/authority bug upstream.
    # Keep all supplied records for audit, but mark the set invalid and never
    # expose publication authority.
    if not eligible:
        status = "NO_VALID_EVALUATION_PICK"
    elif len(eligible) > target:
        status = "INVALID_EXCESS_EVALUATION_PICK"
    else:
        status = "VALID"
    return {
        "evaluation_pick_target": target,
        "evaluation_pick_count": len(eligible),
        "status": status,
        "picks": eligible,
        "publication_authority": False,
        "rule": "target_is_a_maximum_not_a_daily_quota",
    }


def build_postmortem_status(records: Iterable[Any]) -> Dict[str, Any]:
    """Expose whether supplied records are eligible for a later outcome review."""
    eligible = [item for item in records if is_eligible_evaluation_pick(item)]
    return {
        "status": "READY_FOR_REVIEW" if eligible else "NO_ELIGIBLE_PRIOR_RECORD",
        "eligible_record_count": len(eligible),
        "rule": "only_traceable_prior_evaluation_records_may_be_reviewed",
    }
