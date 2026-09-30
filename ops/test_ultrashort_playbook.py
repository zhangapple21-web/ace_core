import pytest

from core.ultrashort_playbook import (
    assess_risk_reward,
    assess_volume_price,
    classify_market_regime,
    classify_setup,
    metadata,
    research_position_ceiling,
)


def _regime_metrics(**overrides):
    value = {
        "breadth_ratio": 0.70,
        "limit_up_count": 80,
        "limit_down_count": 12,
        "break_rate": 0.20,
        "turnover_ratio_vs_average": 1.10,
        "sector_breadth_ratio": 0.65,
        "high_level_continuity_ratio": 0.60,
    }
    value.update(overrides)
    return value


def test_market_regime_never_fills_missing_inputs():
    result = classify_market_regime({"breadth_ratio": 0.7})
    assert result["regime"] == "UNKNOWN"
    assert result["status"] == "INCOMPLETE"
    assert "break_rate" in result["missing_fields"]


def test_market_regime_distinguishes_attack_and_risk_off():
    assert classify_market_regime(_regime_metrics())["regime"] == "ATTACK"
    risk_off = classify_market_regime(_regime_metrics(
        breadth_ratio=0.25,
        limit_up_count=10,
        limit_down_count=60,
        break_rate=0.65,
        high_level_continuity_ratio=0.15,
    ))
    assert risk_off["regime"] == "RISK_OFF"


def test_volume_price_does_not_equate_volume_with_main_force_buying():
    result = assess_volume_price(
        price_change_pct=4.2,
        volume_ratio_vs_average=1.6,
    )
    assert result["signal"] == "UP_VOLUME_CONFIRMATION"
    assert "not_equal_to_main_force_buying" in result["warning"]


def test_setup_requires_sector_sync_and_exit_distance():
    observation = {
        "setup_type": "BREAKOUT",
        "price_breaks_pressure": True,
        "volume_confirms": True,
        "sector_sync_count": 1,
        "late_acceleration": False,
        "near_limit_up": False,
        "pressure_distance_pct": 4,
        "invalidation_distance_pct": 2,
    }
    result = classify_setup(observation)
    assert result["status"] == "REJECT"
    assert "sector_sync_at_least_two" in result["failed_conditions"]


def test_setup_pass_is_still_research_only():
    result = classify_setup({
        "setup_type": "TREND_PULLBACK",
        "trend_intact": True,
        "pullback_volume_contracted": True,
        "support_active": True,
        "reclaim_confirmed": True,
        "sector_sync_count": 2,
        "late_acceleration": False,
        "near_limit_up": False,
        "pressure_distance_pct": 3,
        "invalidation_distance_pct": 1.5,
    })
    assert result["status"] == "PASS"
    assert result["eligible_for_research"] is True
    assert result["semantics"].endswith("no_order_authority")


def test_risk_reward_and_position_ceiling_are_not_targets_or_orders():
    rr = assess_risk_reward(entry_price=10, invalidation_price=9, pressure_price=13)
    assert rr["risk_reward_ratio"] == pytest.approx(3.0)
    ceiling = research_position_ceiling(
        account_equity=100_000,
        max_loss_fraction=0.005,
        entry_price=10,
        invalidation_price=9,
        slippage_buffer_per_share=0.05,
        fee_buffer_per_share=0.01,
    )
    assert ceiling["research_status"] == "RESEARCH_ONLY"
    assert ceiling["research_share_ceiling"] == 400
    assert ceiling["t_plus_one"] is True
    assert ceiling["status"] == "CEILING_ONLY"
    assert "not_an_order" in " ".join(ceiling["warnings"])


def test_playbook_metadata_declares_no_production_authority():
    data = metadata()
    assert data["research_status"] == "RESEARCH_ONLY"
    assert data["production_integration"] is False
    assert data["recommendation_authority"] is False
    assert data["no_chasing_or_averaging_down"] is True
