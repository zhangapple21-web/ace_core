"""Build a bounded, non-production packet for teacher review.

The packet is intentionally separate from ``daily_research_brief``.  It is
useful when the production Phase-2 gate is blocked but a teacher still needs a
traceable shortlist based on fresh or recent multi-day evidence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence

from .teacher_review_research import assess_teacher_review_lane
from .ultrashort_factor_profile import summarize_daily_opportunity


CONTRACT_VERSION = "ace.teacher_review_packet.v1"


def _parse_time(value: Any) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("timestamps require timezone")
    return parsed


def build_teacher_review_packet(
    *,
    packet_id: str,
    as_of: str,
    evidence_sessions: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    minimum_recent_sessions: int = 3,
    live_max_age_minutes: int = 15,
) -> dict[str, Any]:
    """Return at most two evidence-linked cards, never a delivery command.

    Candidate data is copied only after the lane is authorized.  The function
    rejects missing provenance and rejects any attempt to smuggle order,
    target, guarantee, or delivery fields into a card.
    """
    lane = assess_teacher_review_lane(
        as_of=as_of,
        evidence_sessions=evidence_sessions,
        candidate_count=min(2, len(candidates)),
        live_max_age_minutes=live_max_age_minutes,
        minimum_recent_sessions=minimum_recent_sessions,
    )
    cards: list[dict[str, Any]] = []
    if lane["candidate_cards_authorized"]:
        seen: set[str] = set()
        for raw in candidates[:2]:
            if not isinstance(raw, Mapping):
                raise ValueError("candidate must be a mapping")
            required = {"symbol", "thesis", "trigger_conditions", "invalidation_conditions", "source_refs", "observed_at"}
            missing = sorted(required.difference(raw))
            if missing:
                raise ValueError(f"candidate missing: {', '.join(missing)}")
            symbol = str(raw["symbol"]).strip()
            if not symbol or symbol in seen:
                raise ValueError("candidate symbols must be non-empty and unique")
            seen.add(symbol)
            refs = raw["source_refs"]
            if not isinstance(refs, (list, tuple)) or not refs:
                raise ValueError("candidate source_refs must be non-empty")
            _parse_time(raw["observed_at"])
            forbidden = {"order", "orders", "buy", "sell", "target_price", "guarantee", "telegram", "auto_push"}
            present = forbidden.intersection(str(key).lower() for key in raw)
            if present:
                raise ValueError(f"candidate contains forbidden fields: {', '.join(sorted(present))}")
            cards.append({
                "symbol": symbol,
                "thesis": str(raw["thesis"]),
                "trigger_conditions": [str(x) for x in raw["trigger_conditions"]],
                "invalidation_conditions": [str(x) for x in raw["invalidation_conditions"]],
                "source_refs": [str(x) for x in refs],
                "observed_at": str(raw["observed_at"]),
            })
            # These three axes are optional for backwards-compatible packets,
            # but are preserved when the upstream classifier has supplied them.
            for field in ("attack_grade", "conviction", "risk_level"):
                if field in raw:
                    cards[-1][field] = str(raw[field]).strip().upper()
    graded_cards = [
        card for card in cards
        if all(field in card for field in ("attack_grade", "conviction", "risk_level"))
    ]
    if graded_cards == cards and cards:
        opportunity_call = summarize_daily_opportunity(cards)
    elif not cards:
        opportunity_call = summarize_daily_opportunity([])
    else:
        opportunity_call = {
            "daily_signal": "GRADE_CALL_UNAVAILABLE",
            "a_grade_present": None,
            "best_candidate_id": None,
            "best_attack_grade": None,
            "best_conviction": None,
            "best_risk_level": None,
            "candidate_count": len(cards),
            "no_a_reason": "candidate_grade_axes_missing",
            "semantics": "daily_opportunity_truthful_no_force_two_names; research_only",
        }
    return {
        "contract_version": CONTRACT_VERSION,
        "packet_id": str(packet_id),
        "as_of": _parse_time(as_of).isoformat(),
        "research_status": "RESEARCH_ONLY",
        "mode": lane["mode"],
        "lane_assessment": lane,
        "candidate_cards": cards,
        "opportunity_call": opportunity_call,
        "teacher_confirmation_required": True,
        "delivery": {"mode": "MANUAL_ONLY", "telegram_send_performed": False, "order_placed": False},
        "disclaimer": "仅供老师审阅；不构成投资建议，不含目标价、下单或收益保证。",
    }
