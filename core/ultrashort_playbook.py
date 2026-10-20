"""老手式 A 股超短线研究契约。

This module turns the user-supplied ultra-short playbook into small,
auditable helpers.  It is deliberately research-only: it classifies market
conditions, setup shapes, volume/price observations and a *research ceiling*
for risk sizing, but it never emits an order or a recommendation.
"""

from __future__ import annotations

import math
from typing import Any, Mapping


CONTRACT_VERSION = "ace.ultrashort_playbook.v1"
RESEARCH_STATUS = "RESEARCH_ONLY"

MARKET_REGIMES = ("ATTACK", "RANGE", "RISK_OFF", "UNKNOWN")
SETUP_TYPES = (
    "BREAKOUT",
    "DIVERGENCE_TO_CONSISTENCY",
    "TREND_PULLBACK",
    "SECTOR_FOLLOW_THROUGH",
    "EARLY_IDENTIFICATION",
)

_REGIME_FIELDS = (
    "breadth_ratio",
    "limit_up_count",
    "limit_down_count",
    "break_rate",
    "turnover_ratio_vs_average",
    "sector_breadth_ratio",
    "high_level_continuity_ratio",
)


def _finite(value: Any, field: str, *, minimum: float | None = None, maximum: float | None = None) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field}_must_be_finite_number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_must_be_finite_number") from exc
    if not math.isfinite(number):
        raise ValueError(f"{field}_must_be_finite_number")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field}_below_minimum")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field}_above_maximum")
    return number


def _known_bool(value: Any, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"{field}_must_be_bool_or_none")
    return value


def classify_market_regime(metrics: Mapping[str, Any]) -> dict[str, Any]:
    """Classify the day as attack, range or risk-off without filling gaps.

    Ratios are research conventions, not calibrated thresholds.  Counts are
    retained verbatim so the record remains auditable.  Missing inputs produce
    ``UNKNOWN`` rather than an optimistic default.
    """

    if not isinstance(metrics, Mapping):
        raise ValueError("market_metrics_must_be_mapping")
    missing = [field for field in _REGIME_FIELDS if metrics.get(field) is None]
    if missing:
        return {
            "contract_version": CONTRACT_VERSION,
            "research_status": RESEARCH_STATUS,
            "regime": "UNKNOWN",
            "status": "INCOMPLETE",
            "missing_fields": missing,
            "criteria": {},
        }

    breadth = _finite(metrics["breadth_ratio"], "breadth_ratio", minimum=0.0, maximum=1.0)
    limit_up = _finite(metrics["limit_up_count"], "limit_up_count", minimum=0.0)
    limit_down = _finite(metrics["limit_down_count"], "limit_down_count", minimum=0.0)
    break_rate = _finite(metrics["break_rate"], "break_rate", minimum=0.0, maximum=1.0)
    turnover = _finite(metrics["turnover_ratio_vs_average"], "turnover_ratio_vs_average", minimum=0.0)
    sector_breadth = _finite(metrics["sector_breadth_ratio"], "sector_breadth_ratio", minimum=0.0, maximum=1.0)
    high_level = _finite(metrics["high_level_continuity_ratio"], "high_level_continuity_ratio", minimum=0.0, maximum=1.0)

    criteria = {
        "breadth_supportive": breadth >= 0.60,
        "turnover_supportive": turnover >= 1.00,
        "sector_breadth_supportive": sector_breadth >= 0.50,
        "high_level_supportive": high_level >= 0.50,
        "break_rate_stable": break_rate <= 0.35,
        "risk_off_breadth": breadth < 0.40,
        "risk_off_break_rate": break_rate > 0.50,
        "risk_off_high_level": high_level < 0.30,
        "risk_off_limit_balance": limit_down > limit_up,
    }
    attack_votes = sum(criteria[key] for key in (
        "breadth_supportive", "turnover_supportive", "sector_breadth_supportive",
        "high_level_supportive", "break_rate_stable",
    ))
    risk_votes = sum(criteria[key] for key in (
        "risk_off_breadth", "risk_off_break_rate", "risk_off_high_level",
        "risk_off_limit_balance",
    ))
    if risk_votes >= 2:
        regime = "RISK_OFF"
    elif attack_votes >= 4:
        regime = "ATTACK"
    else:
        regime = "RANGE"
    return {
        "contract_version": CONTRACT_VERSION,
        "research_status": RESEARCH_STATUS,
        "regime": regime,
        "status": "COMPLETE",
        "missing_fields": [],
        "inputs": {
            "breadth_ratio": breadth,
            "limit_up_count": limit_up,
            "limit_down_count": limit_down,
            "break_rate": break_rate,
            "turnover_ratio_vs_average": turnover,
            "sector_breadth_ratio": sector_breadth,
            "high_level_continuity_ratio": high_level,
        },
        "criteria": criteria,
        "semantics": "research_regime_label; not_a_trade_signal",
    }


def assess_volume_price(
    *,
    price_change_pct: float,
    volume_ratio_vs_average: float,
    close_location: float | None = None,
    prior_breakout_failed: bool = False,
    high_position: bool = False,
) -> dict[str, Any]:
    """Describe volume/price behaviour without calling it institutional flow."""

    change = _finite(price_change_pct, "price_change_pct")
    volume = _finite(volume_ratio_vs_average, "volume_ratio_vs_average", minimum=0.0)
    close = None if close_location is None else _finite(close_location, "close_location", minimum=0.0, maximum=1.0)
    failed = _known_bool(prior_breakout_failed, "prior_breakout_failed")
    high = _known_bool(high_position, "high_position")
    if failed:
        signal = "BREAKOUT_FAILURE_RISK"
    elif high and volume >= 1.20 and close is not None and close < 0.40:
        signal = "HIGH_LEVEL_DISTRIBUTION_RISK"
    elif change > 0 and volume >= 1.20:
        signal = "UP_VOLUME_CONFIRMATION"
    elif change > 0 and volume < 0.80:
        signal = "UP_THIN_PARTICIPATION"
    elif change < 0 and volume >= 1.20:
        signal = "DOWN_SELLING_PRESSURE"
    elif change < 0 and volume < 0.80:
        signal = "DOWN_SELLING_PRESSURE_EASING"
    else:
        signal = "MIXED_OR_NEUTRAL"
    return {
        "contract_version": CONTRACT_VERSION,
        "research_status": RESEARCH_STATUS,
        "signal": signal,
        "inputs": {
            "price_change_pct": change,
            "volume_ratio_vs_average": volume,
            "close_location": close,
            "prior_breakout_failed": failed,
            "high_position": high,
        },
        "warning": "volume_is_not_equal_to_main_force_buying; every_trade_has_a_buyer_and_a_seller",
    }


def classify_setup(observation: Mapping[str, Any]) -> dict[str, Any]:
    """Check one of the five user-supplied setup shapes.

    Unknown conditions are retained as blockers.  A setup is never considered
    actionable merely because a few booleans are true.
    """

    if not isinstance(observation, Mapping):
        raise ValueError("setup_observation_must_be_mapping")
    setup = str(observation.get("setup_type", "")).strip().upper()
    if setup not in SETUP_TYPES:
        raise ValueError("setup_type_invalid")

    def flag(name: str) -> bool | None:
        return _known_bool(observation.get(name), name)

    sector_sync = observation.get("sector_sync_count")
    if sector_sync is None:
        sector_count: int | None = None
    else:
        sector_count = int(_finite(sector_sync, "sector_sync_count", minimum=0.0))

    common = {
        "sector_sync_at_least_two": None if sector_count is None else sector_count >= 2,
        "not_late_acceleration": None if flag("late_acceleration") is None else not flag("late_acceleration"),
        "not_near_limit_up": None if flag("near_limit_up") is None else not flag("near_limit_up"),
        "pressure_distance_executable": None if observation.get("pressure_distance_pct") is None else _finite(observation["pressure_distance_pct"], "pressure_distance_pct", minimum=0.0) >= 2.0,
        "invalidation_distance_executable": None if observation.get("invalidation_distance_pct") is None else _finite(observation["invalidation_distance_pct"], "invalidation_distance_pct", minimum=0.0) >= 1.0,
    }
    requirements: dict[str, tuple[str, ...]] = {
        "BREAKOUT": ("price_breaks_pressure", "volume_confirms", "sector_sync_at_least_two"),
        "DIVERGENCE_TO_CONSISTENCY": ("prior_divergence", "core_support", "volume_confirms", "sector_sync_at_least_two"),
        "TREND_PULLBACK": ("trend_intact", "pullback_volume_contracted", "support_active", "reclaim_confirmed"),
        "SECTOR_FOLLOW_THROUGH": ("sector_core_confirmed", "candidate_not_overheated", "sector_sync_at_least_two"),
        "EARLY_IDENTIFICATION": ("platform_or_contraction", "relative_strength_before_sector_expansion", "opening_support", "volume_progression"),
    }
    checks: dict[str, bool | None] = dict(common)
    for name in requirements[setup]:
        if name == "sector_sync_at_least_two":
            continue
        checks[name] = flag(name)
    missing = [name for name in requirements[setup] if checks.get(name) is None]
    failed = [name for name in requirements[setup] if checks.get(name) is False]
    for name in ("not_late_acceleration", "not_near_limit_up", "pressure_distance_executable", "invalidation_distance_executable"):
        if checks[name] is None:
            missing.append(name)
        elif checks[name] is False:
            failed.append(name)
    eligible = not missing and not failed
    return {
        "contract_version": CONTRACT_VERSION,
        "research_status": RESEARCH_STATUS,
        "setup_type": setup,
        "eligible_for_research": eligible,
        "status": "PASS" if eligible else "INCOMPLETE" if missing else "REJECT",
        "checks": checks,
        "missing_conditions": sorted(set(missing)),
        "failed_conditions": sorted(set(failed)),
        "sector_sync_count": sector_count,
        "semantics": "setup_classification_only; no_order_authority",
    }


def assess_risk_reward(*, entry_price: float, invalidation_price: float, pressure_price: float | None = None) -> dict[str, Any]:
    """Return an ex-ante risk/reward check, never a target or guarantee."""

    entry = _finite(entry_price, "entry_price", minimum=0.0)
    invalidation = _finite(invalidation_price, "invalidation_price", minimum=0.0)
    if invalidation >= entry:
        raise ValueError("invalidation_price_must_be_below_entry_price")
    risk = entry - invalidation
    upside = None
    ratio = None
    if pressure_price is not None:
        pressure = _finite(pressure_price, "pressure_price", minimum=0.0)
        upside = pressure - entry
        ratio = round(upside / risk, 6)
    return {
        "contract_version": CONTRACT_VERSION,
        "research_status": RESEARCH_STATUS,
        "entry_price": entry,
        "invalidation_price": invalidation,
        "risk_per_share": round(risk, 6),
        "pressure_observation": pressure_price,
        "upside_to_pressure": None if upside is None else round(upside, 6),
        "risk_reward_ratio": ratio,
        "status": "CHECKED" if ratio is not None else "INCOMPLETE",
        "semantics": "technical_observation_not_profit_target",
    }


def research_position_ceiling(
    *,
    account_equity: float,
    max_loss_fraction: float,
    entry_price: float,
    invalidation_price: float,
    slippage_buffer_per_share: float = 0.0,
    fee_buffer_per_share: float = 0.0,
    lot_size: int = 100,
    max_position_fraction: float = 1.0,
) -> dict[str, Any]:
    """Calculate a bounded research position ceiling under T+1 constraints.

    This is deliberately not an order quantity.  It is a transparent ceiling
    for teacher review and must still account for gaps, limit moves and actual
    execution conditions.
    """

    equity = _finite(account_equity, "account_equity", minimum=0.0)
    loss_fraction = _finite(max_loss_fraction, "max_loss_fraction", minimum=0.0, maximum=1.0)
    entry = _finite(entry_price, "entry_price", minimum=0.0)
    invalidation = _finite(invalidation_price, "invalidation_price", minimum=0.0)
    slippage = _finite(slippage_buffer_per_share, "slippage_buffer_per_share", minimum=0.0)
    fees = _finite(fee_buffer_per_share, "fee_buffer_per_share", minimum=0.0)
    if invalidation >= entry:
        raise ValueError("invalidation_price_must_be_below_entry_price")
    if not isinstance(lot_size, int) or lot_size <= 0:
        raise ValueError("lot_size_must_be_positive_integer")
    max_fraction = _finite(max_position_fraction, "max_position_fraction", minimum=0.0, maximum=1.0)
    risk_per_share = (entry - invalidation) + slippage + fees
    budget = equity * loss_fraction
    raw_shares = math.floor(budget / risk_per_share) if risk_per_share > 0 else 0
    value_cap_shares = math.floor((equity * max_fraction) / entry) if entry > 0 else 0
    shares = min(raw_shares, value_cap_shares)
    lot_shares = (shares // lot_size) * lot_size
    return {
        "contract_version": CONTRACT_VERSION,
        "research_status": RESEARCH_STATUS,
        "status": "CEILING_ONLY" if lot_shares > 0 else "NOT_EXECUTABLE",
        "t_plus_one": True,
        "account_equity": equity,
        "max_loss_fraction": loss_fraction,
        "risk_budget": round(budget, 6),
        "risk_per_share_with_buffers": round(risk_per_share, 6),
        "raw_share_ceiling": raw_shares,
        "lot_size": lot_size,
        "research_share_ceiling": lot_shares,
        "value_cap_shares": value_cap_shares,
        "warnings": [
            "gap_and_limit_move_can_exceed_the_planned_loss",
            "t_plus_one_and_liquidity_can_delay_exit",
            "not_an_order_or_recommendation",
        ],
    }


def metadata() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "research_status": RESEARCH_STATUS,
        "market_regimes": list(MARKET_REGIMES),
        "setup_types": list(SETUP_TYPES),
        "sequence": [
            "market_environment",
            "sector_to_stock_to_setup",
            "volume_price_and_liquidity",
            "confirmation_and_invalidation",
            "risk_reward_and_t_plus_one",
            "post_close_review",
        ],
        "production_integration": False,
        "recommendation_authority": False,
        "no_chasing_or_averaging_down": True,
        "position_sizing_is_research_ceiling": True,
    }
