"""Canonical research profile for ACE's 1--2 day ultra-short workflow.

The profile is a ranking convention, not a trading signal or a probability
model.  It keeps the fast, observable parts of the workflow ahead of slower
background indicators while retaining hard gates for next-day path,
tradeability, evidence freshness, and explicit invalidation.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


PROFILE_ID = "ace.ultrashort.1-2d.v2"
PROFILE_VERSION = "ace.ultrashort_factor_profile.v2"

# These are relative ranking weights and intentionally sum to 1.0.  They have
# not been presented as backtested returns or win rates.
FACTOR_WEIGHTS: dict[str, float] = {
    "market_sentiment_index_environment": 0.20,
    "sector_strength_rotation": 0.20,
    "auction_opening_support": 0.20,
    "intraday_volume_price_turnover": 0.20,
    "flow_continuity_1_3d": 0.15,
    "next_day_path_exit": 0.05,
}

HARD_GATES = (
    "tradeability",
    "fresh_independent_evidence",
    "next_day_path",
    "invalidation_and_exit",
)

# These thresholds are a transparent research convention, not a calibrated
# probability model.  They deliberately separate opportunity conviction from
# execution risk: a high-risk, high-conviction setup may still be graded A/A+
# when its invalidation and tradeability gates are explicit.
GRADE_THRESHOLDS = {
    "A+": 4.20,
    "A": 3.70,
    "B": 3.00,
    "C": 2.25,
}

RISK_WEIGHTS = {
    "volatility": 0.25,
    "gap_and_overnight": 0.20,
    "liquidity_and_execution": 0.20,
    "event_and_announcement": 0.15,
    "structure_and_invalidation": 0.20,
}

# A 4--5% move is not a buy signal by itself.  This policy makes the
# distinction explicit so the anti-chasing guard cannot erase the very
# early, still-actionable part of a move.  It is metadata/decision guidance,
# not a calibrated probability model and it does not change the six-factor
# score.
EARLY_MOVE_POLICY: dict[str, Any] = {
    "policy_id": "ace.early_move_lane.v1",
    "status": "RESEARCH_ONLY",
    "four_to_five_pct_is_actionable": True,
    "allowed_when": [
        "first_leg_or_first_pullback_not_late_acceleration",
        "sector_breadth_has_at_least_two_confirming_names",
        "opening_or_intraday_support_is_active",
        "volume_price_progression_is_confirmed",
        "invalidation_distance_and_liquidity_are_acceptable",
    ],
    "forecast_definition": (
        "提前会涨 means identifying a pre-breakout or early-breakout setup "
        "before confirmation; it is a conditional forecast, not a guaranteed rise"
    ),
    "forecast_evidence": [
        "platform_or_first_pullback_position",
        "relative_strength_before_full_sector_expansion",
        "auction_or_first_five_minute_support",
        "pullback_volume_contraction_and_reclaim",
        "same_day_or_1_to_3d_flow_continuity",
    ],
    "reject_or_observe_when": [
        "late_acceleration_or_near_limit_up",
        "single_stock_pulse_without_sector_breadth",
        "volume_expansion_without_price_progression",
        "pressure_too_close_or_invalidation_not_executable",
    ],
    "no_guarantee": True,
}

_GRADE_ORDER = {"A+": 4, "A": 3, "B": 2, "C": 1, "D": 0}
_CONVICTION_ORDER = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field}_must_be_finite_number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_must_be_finite_number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field}_must_be_finite_number")
    if not 0.0 <= number <= 5.0:
        raise ValueError(f"{field}_must_be_between_0_and_5")
    return number


def score_factors(factors: Mapping[str, Any]) -> dict[str, Any]:
    """Score a complete six-factor observation without filling unknowns.

    Values are analyst/replay scores in the closed interval 0--5.  A missing
    factor returns ``score=None`` and an explicit list of missing fields; it
    is never silently treated as zero or as a pass.
    """

    if not isinstance(factors, Mapping):
        raise ValueError("factors_must_be_mapping")
    missing = [name for name in FACTOR_WEIGHTS if factors.get(name) is None]
    if missing:
        return {
            "profile_id": PROFILE_ID,
            "profile_version": PROFILE_VERSION,
            "score": None,
            "missing_factors": missing,
            "status": "INCOMPLETE",
        }
    normalized = {name: _number(factors[name], name) for name in FACTOR_WEIGHTS}
    score = sum(normalized[name] * weight for name, weight in FACTOR_WEIGHTS.items())
    return {
        "profile_id": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "score": round(score, 6),
        "factor_scores": normalized,
        "weights": dict(FACTOR_WEIGHTS),
        "missing_factors": [],
        "status": "COMPLETE",
        "semantics": "research_ranking_only; not_probability_or_return",
    }


def _gate_status(gates: Mapping[str, Any] | None) -> dict[str, bool | None]:
    """Normalize hard-gate values without treating unknown as pass."""

    if gates is None:
        return {name: None for name in HARD_GATES}
    if not isinstance(gates, Mapping):
        raise ValueError("gates_must_be_mapping")
    normalized: dict[str, bool | None] = {}
    for name in HARD_GATES:
        value = gates.get(name)
        if value is None:
            normalized[name] = None
        elif isinstance(value, bool):
            normalized[name] = value
        else:
            raise ValueError(f"{name}_gate_must_be_bool_or_none")
    return normalized


def _risk_level(risk_scores: Mapping[str, Any] | None) -> dict[str, Any]:
    """Score risk independently from opportunity conviction.

    Inputs use the same 0--5 scale, where 5 means more risk.  Unknown risk is
    preserved as ``UNKNOWN``; it is never silently treated as safe.
    """

    if risk_scores is None:
        return {"level": "UNKNOWN", "score": None, "missing": list(RISK_WEIGHTS)}
    if not isinstance(risk_scores, Mapping):
        raise ValueError("risk_scores_must_be_mapping")
    missing = [name for name in RISK_WEIGHTS if risk_scores.get(name) is None]
    if missing:
        return {"level": "UNKNOWN", "score": None, "missing": missing}
    normalized = {name: _number(risk_scores[name], name) for name in RISK_WEIGHTS}
    score = sum(normalized[name] * weight for name, weight in RISK_WEIGHTS.items())
    level = "LOW" if score < 1.75 else "MEDIUM" if score < 3.25 else "HIGH"
    return {
        "level": level,
        "score": round(score, 6),
        "scores": normalized,
        "missing": [],
    }


def classify_candidate(
    factors: Mapping[str, Any],
    *,
    gates: Mapping[str, Any] | None = None,
    risk_scores: Mapping[str, Any] | None = None,
    evidence_complete: bool | None = None,
    tn6_prior: Mapping[str, Any] | None = None,
    decision_discipline: Mapping[str, Any] | None = None,
    company_view: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Translate research factors into an explicit opportunity card.

    ``tn6_prior`` is retained as provenance only.  It can affect this result
    only when the caller supplies independently replayed evidence; a binary
    indicator name or hit count alone never changes the score.
    """

    scored = score_factors(factors)
    gate_state = _gate_status(gates)
    risk = _risk_level(risk_scores)
    discipline = None
    if decision_discipline is not None:
        from .decision_discipline import normalize_decision_discipline

        discipline = normalize_decision_discipline(decision_discipline)
    company_context = None
    if company_view is not None:
        from .company_view import normalize_company_view

        company_context = normalize_company_view(company_view)

    result: dict[str, Any] = {
        "profile_id": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "status": "RESEARCH_ONLY",
        "gates": gate_state,
        "risk": risk,
        "risk_level": risk["level"],
        "tn6_prior": dict(tn6_prior) if isinstance(tn6_prior, Mapping) else None,
        "tn6_prior_used_for_score": False,
        "semantics": "opportunity_conviction_and_risk_are_separate; research_only",
        "early_move_policy": dict(EARLY_MOVE_POLICY),
        "decision_discipline": discipline,
        "company_view": company_context,
    }
    result.update({"score": scored.get("score"), "factor_scores": scored.get("factor_scores")})

    if scored.get("score") is None:
        result.update({"attack_grade": "D", "conviction": "LOW", "decision_endpoint": "WAIT_FOR_EVIDENCE"})
        return result

    failed_gates = [name for name, value in gate_state.items() if value is False]
    unknown_gates = [name for name, value in gate_state.items() if value is None]
    score = float(scored["score"])
    if evidence_complete is False or failed_gates:
        conviction = "LOW"
    elif evidence_complete is None or unknown_gates:
        conviction = "MEDIUM"
    elif score >= GRADE_THRESHOLDS["A"]:
        conviction = "HIGH"
    else:
        conviction = "MEDIUM"

    if failed_gates or score < GRADE_THRESHOLDS["C"]:
        grade = "D"
    elif score >= GRADE_THRESHOLDS["A+"] and conviction == "HIGH":
        grade = "A+"
    elif score >= GRADE_THRESHOLDS["A"] and conviction in {"HIGH", "MEDIUM"}:
        grade = "A"
    elif score >= GRADE_THRESHOLDS["B"]:
        grade = "B"
    else:
        grade = "C"

    # An unknown next-day path or invalidation is not promoted to an execution
    # endpoint even when the weighted score is attractive.
    if gate_state.get("next_day_path") is not True or gate_state.get("invalidation_and_exit") is not True:
        decision_endpoint = "WAIT_FOR_CONFIRMATION"
    elif discipline is not None and not discipline["decision_ready"]:
        # The discipline is an execution front door, not a scoring factor.
        decision_endpoint = "NO_ODDS_DO_NOT_ACT"
    elif grade in {"A+", "A"} and conviction == "HIGH":
        decision_endpoint = "EXECUTE_OR_VALIDATE"
    else:
        decision_endpoint = "MANUAL_REVIEW"

    result.update({
        "attack_grade": grade,
        "conviction": conviction,
        "decision_endpoint": decision_endpoint,
        "failed_gates": failed_gates,
        "unknown_gates": unknown_gates,
    })
    return result


def summarize_daily_opportunity(candidates: Any) -> dict[str, Any]:
    """Make the daily opportunity call without forcing a two-name shortlist.

    The function consumes already-classified research cards.  It deliberately
    does not recompute a score, downgrade a grade because risk is high, or
    manufacture a replacement candidate.  A day with only B/C/D cards is
    reported as ``NO_A_TODAY``; an empty pool is
    ``NO_SUITABLE_SETUP``.  This keeps the daily output honest while allowing
    a high-risk, high-conviction A/A+ card to remain visible.
    """

    if not isinstance(candidates, (list, tuple)):
        raise ValueError("candidates_must_be_sequence")

    normalized: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, Mapping):
            raise ValueError(f"candidate_{index}_must_be_mapping")
        grade = str(candidate.get("attack_grade", "")).strip().upper()
        if grade not in _GRADE_ORDER:
            raise ValueError(f"candidate_{index}_attack_grade_invalid")
        candidate_id = str(
            candidate.get("candidate_id", candidate.get("symbol", f"candidate-{index + 1}"))
        ).strip()
        if not candidate_id:
            raise ValueError(f"candidate_{index}_identity_missing")
        conviction = str(candidate.get("conviction", "UNKNOWN")).strip().upper()
        risk_level = str(candidate.get("risk_level", "UNKNOWN")).strip().upper()
        normalized.append({
            "candidate_id": candidate_id,
            "attack_grade": grade,
            "conviction": conviction,
            "risk_level": risk_level,
            "input_index": index,
        })

    if not normalized:
        return {
            "daily_signal": "NO_SUITABLE_SETUP",
            "a_grade_present": False,
            "best_candidate_id": None,
            "best_attack_grade": None,
            "best_conviction": None,
            "best_risk_level": None,
            "candidate_count": 0,
            "no_a_reason": "no_candidate_cards",
            "semantics": "daily_opportunity_truthful_no_force_two_names; research_only",
        }

    ranked = sorted(
        normalized,
        key=lambda item: (
            _GRADE_ORDER[item["attack_grade"]],
            _CONVICTION_ORDER.get(item["conviction"], -1),
            -item["input_index"],
        ),
        reverse=True,
    )
    best = ranked[0]
    best_grade = best["attack_grade"]
    if best_grade == "A+":
        signal = "A_PLUS_PRESENT"
    elif best_grade == "A":
        signal = "A_PRESENT"
    else:
        signal = "NO_A_TODAY"

    return {
        "daily_signal": signal,
        "a_grade_present": best_grade in {"A+", "A"},
        "best_candidate_id": best["candidate_id"],
        "best_attack_grade": best_grade,
        "best_conviction": best["conviction"],
        "best_risk_level": best["risk_level"],
        "candidate_count": len(normalized),
        "no_a_reason": None if best_grade in {"A+", "A"} else "best_candidate_below_A_threshold",
        "ranked_candidates": ranked,
        "semantics": "daily_opportunity_truthful_no_force_two_names; research_only",
    }


def profile_metadata() -> dict[str, Any]:
    """Return a serializable profile declaration for research records."""

    from .decision_discipline import metadata as decision_discipline_metadata
    from .company_view import metadata as company_view_metadata

    return {
        "profile_id": PROFILE_ID,
        "profile_version": PROFILE_VERSION,
        "horizon": "1-2 trading days; maximum observation 3-5 days",
        "factor_weights": dict(FACTOR_WEIGHTS),
        "hard_gates": list(HARD_GATES),
        "grade_thresholds": dict(GRADE_THRESHOLDS),
        "risk_weights": dict(RISK_WEIGHTS),
        "risk_conviction_separation": True,
        "daily_truthful_grade_call": True,
        "no_a_output": "NO_A_TODAY",
        "tn6_role": "prior_provenance_only_until_point_in_time_replay",
        "status": "RESEARCH_ONLY",
        "historical_validation_required": True,
        "production_integration": False,
        "recommendation_authority": False,
        "early_move_policy": dict(EARLY_MOVE_POLICY),
        "decision_discipline": decision_discipline_metadata(),
        "company_view": company_view_metadata(),
    }
