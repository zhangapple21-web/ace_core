"""A non-production research lane for teacher review.

This lane answers the practical question "can we prepare two candidates for the
teacher today?" without changing ACE's strict production admission.  It accepts
either a fresh, traceable observation or a bounded multi-day evidence set.  The
result is always review-only and carries explicit staleness and missing-evidence
reasons; it never emits an order, price target, or delivery instruction.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.teacher_review_research.v1"
OPERATIONS = ("quote", "minute_kline_1m", "index")


def _time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("evidence timestamps require timezone")
    return parsed


def assess_teacher_review_lane(
    *,
    as_of: str,
    evidence_sessions: Sequence[Mapping[str, Any]],
    candidate_count: int = 2,
    live_max_age_minutes: int = 15,
    minimum_recent_sessions: int = 3,
) -> dict[str, Any]:
    """Assess whether a small teacher-review packet can be assembled.

    Each session has ``observed_at`` and an ``operations`` mapping.  An
    operation record must contain ``source_refs``, ``independence_groups``,
    ``lineage_observable``, ``coverage_complete``, ``fields_complete`` and
    ``cross_source_consistent``.  This is a research-quality completeness test,
    not the production Phase 2 admission predicate.
    """
    if candidate_count < 0 or candidate_count > 2:
        raise ValueError("candidate_count must be between 0 and 2")
    now = _time(as_of)
    sessions = []
    blockers: list[str] = []
    for raw in evidence_sessions:
        if not isinstance(raw, Mapping):
            raise ValueError("evidence session must be a mapping")
        observed = _time(raw.get("observed_at"))
        operations = raw.get("operations")
        if not isinstance(operations, Mapping):
            raise ValueError("evidence session operations must be a mapping")
        complete = True
        operation_results = {}
        for operation in OPERATIONS:
            item = operations.get(operation)
            if not isinstance(item, Mapping):
                complete = False
                operation_results[operation] = {"status": "MISSING"}
                continue
            groups = item.get("independence_groups", [])
            refs = item.get("source_refs", [])
            checks = {
                "source_refs": isinstance(refs, (list, tuple)) and bool(refs),
                "independence_groups": isinstance(groups, (list, tuple)) and bool(set(groups)),
                "lineage_observable": item.get("lineage_observable") is True,
                "coverage_complete": item.get("coverage_complete") is True,
                "fields_complete": item.get("fields_complete") is True,
                "cross_source_consistent": item.get("cross_source_consistent") is True,
            }
            status = "COMPLETE" if all(checks.values()) else "INCOMPLETE"
            complete = complete and status == "COMPLETE"
            operation_results[operation] = {"status": status, "checks": checks}
        sessions.append({
            "observed_at": observed.isoformat(),
            "age_minutes": max(0, int((now - observed).total_seconds() // 60)),
            "complete": complete,
            "operations": operation_results,
        })

    live = [item for item in sessions if item["complete"] and item["age_minutes"] <= live_max_age_minutes]
    recent = [item for item in sessions if item["complete"]]
    mode = "NONE"
    if live:
        mode = "LIVE_RESEARCH"
    elif len(recent) >= minimum_recent_sessions:
        mode = "RECENT_MULTI_DAY_RESEARCH"
    else:
        blockers.append("insufficient_fresh_or_multi_day_evidence")
    if candidate_count == 0:
        blockers.append("no_candidate_cards_requested")
    if mode == "NONE":
        blockers.append("teacher_review_lane_not_ready")
    return {
        "contract_version": CONTRACT_VERSION,
        "as_of": now.isoformat(),
        "research_status": "RESEARCH_ONLY",
        "lane": "TEACHER_REVIEW_RESEARCH",
        "mode": mode,
        "candidate_card_limit": candidate_count,
        "candidate_cards_authorized": candidate_count if mode != "NONE" else 0,
        "strict_production_admission_unchanged": True,
        "automatic_delivery": False,
        "sessions": sessions,
        "blockers": sorted(set(blockers)),
        "disclaimer": "Research candidates require teacher confirmation; no order, target price, guarantee, or automatic delivery is authorized.",
    }
