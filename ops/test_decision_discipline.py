import pytest

from core.decision_discipline import (
    CHAT_PROTOCOL_VERSION,
    CONTRACT_VERSION,
    PRINCIPLE,
    STAGES,
    attach_decision_discipline,
    chat_protocol_prompt,
    metadata,
    normalize_decision_discipline,
)
from core.ultrashort_factor_profile import classify_candidate, profile_metadata


def _record(odds="结构确认后仍有空间，失效距离可执行"):
    return {
        "facts": ["板块有两个代表同步"],
        "structure": ["平台突破后的第一次回踩"],
        "position_price_expectation": ["未脱离观察区，预期差尚在"],
        "confirmation": ["放量突破并保持承接"],
        "invalidation": ["跌回平台且板块掉队"],
        "odds": odds,
    }


def test_contract_preserves_principle_and_indicator_boundary():
    result = normalize_decision_discipline(_record())
    assert result["contract_version"] == CONTRACT_VERSION
    assert result["principle"] == PRINCIPLE
    assert tuple(result["stages"]) == STAGES
    assert result["status"] == "READY_FOR_CONFIRMATION"
    assert result["indicator_role"] == "context_only"
    assert result["score_contribution"] == 0.0
    assert result["can_consume_as_market_signal"] is False


def test_missing_odds_is_explicit_stop():
    result = normalize_decision_discipline(_record(odds=""))
    assert result["status"] == "NO_ODDS_DO_NOT_ACT"
    assert result["decision_ready"] is False


def test_attach_preserves_existing_axes():
    candidate = {"score": 4.3, "attack_grade": "A+", "conviction": "HIGH", "risk_level": "HIGH"}
    attached = attach_decision_discipline(candidate, _record())
    for field in ("score", "attack_grade", "conviction", "risk_level"):
        assert attached[field] == candidate[field]
    assert attached["decision_discipline"]["decision_ready"] is True


def test_classifier_uses_discipline_as_execution_front_door_only():
    factors = {"market_sentiment_index_environment": 5,
               "sector_strength_rotation": 5,
               "auction_opening_support": 5,
               "intraday_volume_price_turnover": 5,
               "flow_continuity_1_3d": 5,
               "next_day_path_exit": 5}
    gates = {"tradeability": True, "fresh_independent_evidence": True,
             "next_day_path": True, "invalidation_and_exit": True}
    result = classify_candidate(factors, gates=gates, evidence_complete=True,
                                decision_discipline=_record(odds=""))
    assert result["attack_grade"] == "A+"
    assert result["decision_endpoint"] == "NO_ODDS_DO_NOT_ACT"


def test_metadata_declares_no_odds_and_context_only():
    value = metadata()
    assert value["no_odds_action"] == "NO_ODDS_DO_NOT_ACT"
    assert value["indicator_role"] == "context_only"
    assert profile_metadata()["decision_discipline"]["contract_version"] == CONTRACT_VERSION
    assert profile_metadata()["decision_discipline"]["chat_protocol_version"] == CHAT_PROTOCOL_VERSION
    assert CHAT_PROTOCOL_VERSION in chat_protocol_prompt()


def test_company_view_is_context_only_and_does_not_change_axes():
    from core.ultrashort_factor_profile import FACTOR_WEIGHTS

    factors = {name: 5 for name in FACTOR_WEIGHTS}
    result = classify_candidate(
        factors,
        gates={name: True for name in ("tradeability", "fresh_independent_evidence", "next_day_path", "invalidation_and_exit")},
        evidence_complete=True,
        company_view={
            "business_thesis": "板块景气预期的短线交易",
            "why_now": "板块刚扩散且仍有预期差",
            "price_and_odds": "未脱离观察区，失效距离可执行",
            "execution_quality": "需要开盘承接验证",
            "time_window": "1-2 个交易日",
            "counterfactual_company_test": "PASS",
            "evidence_refs": ["evidence://company-view"],
        },
    )
    assert result["attack_grade"] == "A+"
    assert result["conviction"] == "HIGH"
    assert result["company_view"]["status"] == "COMPLETE_RESEARCH_CONTEXT"
    assert result["company_view"]["score_contribution"] == 0.0


def test_invalid_discipline_is_not_filled_in():
    with pytest.raises(ValueError, match="facts"):
        normalize_decision_discipline(_record() | {"facts": []})
