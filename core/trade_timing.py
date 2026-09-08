"""Point-in-time client actionability checks for short-term stock research.

This is a presentation/readiness contract, not a signal or a score.  It exists
to prevent a valid observation from becoming a stale client message after the
entry window has already disappeared (for example, after a near-limit move or
an unfillable limit-up).  Missing evidence stays UNKNOWN.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


CONTRACT_VERSION = "ace.trade_timing.v1"
LATE_MOVE_PCT = 9.0
EARLY_MOVE_MIN_PCT = 4.0
EARLY_MOVE_MAX_PCT = 8.0
MAX_SNAPSHOT_AGE = timedelta(minutes=10)


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"trade_timing_{field}_must_be_iso_timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"trade_timing_{field}_must_include_timezone")
    return parsed


def assess_trade_window(
    *,
    observed_at: str,
    as_of: str,
    change_pct: float | int | None,
    is_limit_up: bool = False,
    confirmation_available: bool | None = None,
) -> dict[str, Any]:
    """Classify whether a point-in-time observation is still client-actionable."""

    observed = _timestamp(observed_at, "observed_at")
    current = _timestamp(as_of, "as_of")
    if current < observed:
        raise ValueError("trade_timing_as_of_before_observed_at")

    age = current - observed
    if change_pct is None:
        return {
            "contract_version": CONTRACT_VERSION,
            "status": "UNKNOWN_DATA",
            "message_window": "DO_NOT_SEND_ENTRY_LANGUAGE",
            "snapshot_age_seconds": int(age.total_seconds()),
            "reason": "change_pct_unverified",
            "score_contribution": 0.0,
            "changes_candidate_grade": False,
        }

    try:
        move = float(change_pct)
    except (TypeError, ValueError) as exc:
        raise ValueError("trade_timing_change_pct_must_be_numeric") from exc

    if age > MAX_SNAPSHOT_AGE:
        status = "STALE_SNAPSHOT"
        window = "REFRESH_BEFORE_CLIENT_MESSAGE"
        reason = "snapshot_older_than_10_minutes"
    elif is_limit_up:
        status = "WINDOW_MISSED"
        window = "WAIT_FOR_REOPEN_OR_NEXT_SETUP"
        reason = "limit_up_or_unfillable_state"
    elif move >= LATE_MOVE_PCT:
        status = "LATE_HIGH_MOVE"
        window = "WAIT_FOR_PULLBACK_OR_NEXT_SETUP"
        reason = "move_at_or_above_9_percent"
    elif EARLY_MOVE_MIN_PCT <= move <= EARLY_MOVE_MAX_PCT:
        status = "EARLY_MOVE_CONFIRMABLE"
        window = "CONFIRM_THEN_CONSIDER"
        reason = "early_move_range_requires_confirmation"
    else:
        status = "CONDITIONAL"
        window = "OBSERVE_CONFIRMATION"
        reason = "no_automatic_entry_window"

    if status == "EARLY_MOVE_CONFIRMABLE" and confirmation_available is False:
        status = "WAIT_FOR_CONFIRMATION"
        window = "DO_NOT_SEND_ENTRY_LANGUAGE"
        reason = "early_move_without_confirmation"

    return {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "message_window": window,
        "snapshot_age_seconds": int(age.total_seconds()),
        "change_pct": move,
        "reason": reason,
        "score_contribution": 0.0,
        "changes_candidate_grade": False,
    }


def metadata() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "late_move_pct": LATE_MOVE_PCT,
        "early_move_range_pct": [EARLY_MOVE_MIN_PCT, EARLY_MOVE_MAX_PCT],
        "max_snapshot_age_minutes": int(MAX_SNAPSHOT_AGE.total_seconds() // 60),
        "research_status": "RESEARCH_ONLY",
        "production_integration": True,
        "recommendation_authority": False,
        "purpose": "prevent_stale_or_unfillable_client_entry_language",
    }
