import pytest

from core.ultrashort_factor_profile import (
    FACTOR_WEIGHTS,
    classify_candidate,
    profile_metadata,
    score_factors,
    summarize_daily_opportunity,
)


def test_weights_are_canonical_and_sum_to_one():
    assert FACTOR_WEIGHTS["market_sentiment_index_environment"] == 0.20
    assert FACTOR_WEIGHTS["next_day_path_exit"] == 0.05
    assert sum(FACTOR_WEIGHTS.values()) == pytest.approx(1.0)
    assert profile_metadata()["status"] == "RESEARCH_ONLY"
    assert profile_metadata()["risk_conviction_separation"] is True
    assert profile_metadata()["daily_truthful_grade_call"] is True
    assert profile_metadata()["no_a_output"] == "NO_A_TODAY"
    assert profile_metadata()["tn6_role"].startswith("prior_provenance_only")
    policy = profile_metadata()["early_move_policy"]
    assert policy["four_to_five_pct_is_actionable"] is True
    assert policy["no_guarantee"] is True


def test_score_does_not_fill_missing_factor():
    result = score_factors({"market_sentiment_index_environment": 5})
    assert result["score"] is None
    assert result["status"] == "INCOMPLETE"
    assert "next_day_path_exit" in result["missing_factors"]


def test_complete_score_is_rank_only():
    result = score_factors({name: 5 for name in FACTOR_WEIGHTS})
    assert result["score"] == 5.0
    assert result["semantics"].startswith("research_ranking_only")
    with pytest.raises(ValueError, match="between_0_and_5"):
        score_factors({**{name: 1 for name in FACTOR_WEIGHTS}, "auction_opening_support": 6})


def _full_factors(value=5):
    return {name: value for name in FACTOR_WEIGHTS}


def _passed_gates():
    return {
        "tradeability": True,
        "fresh_independent_evidence": True,
        "next_day_path": True,
        "invalidation_and_exit": True,
    }


def _high_risk():
    return {
        "volatility": 5,
        "gap_and_overnight": 5,
        "liquidity_and_execution": 3,
        "event_and_announcement": 3,
        "structure_and_invalidation": 4,
    }


def test_conviction_and_risk_are_separate():
    result = classify_candidate(
        _full_factors(),
        gates=_passed_gates(),
        risk_scores=_high_risk(),
        evidence_complete=True,
    )
    assert result["attack_grade"] == "A+"
    assert result["conviction"] == "HIGH"
    assert result["risk_level"] == "HIGH"
    assert result["decision_endpoint"] == "EXECUTE_OR_VALIDATE"


def test_unknown_next_day_path_cannot_reach_execution_endpoint():
    gates = _passed_gates()
    gates["next_day_path"] = None
    result = classify_candidate(
        _full_factors(),
        gates=gates,
        risk_scores=_high_risk(),
        evidence_complete=True,
    )
    assert result["attack_grade"] == "A"
    assert result["decision_endpoint"] == "WAIT_FOR_CONFIRMATION"


def test_tn6_prior_is_provenance_only_without_replay():
    result = classify_candidate(
        _full_factors(1),
        gates=_passed_gates(),
        risk_scores=_high_risk(),
        evidence_complete=True,
        tn6_prior={"indicator_count": 100, "parse_status": "BINARY_FORMULA_UNPARSED"},
    )
    assert result["score"] == 1.0
    assert result["attack_grade"] == "D"
    assert result["tn6_prior_used_for_score"] is False


def test_early_move_lane_is_metadata_only_and_does_not_change_score():
    result = classify_candidate(
        _full_factors(4),
        gates=_passed_gates(),
        risk_scores=_high_risk(),
        evidence_complete=True,
    )
    assert result["score"] == 4.0
    assert result["early_move_policy"]["four_to_five_pct_is_actionable"] is True
    assert result["early_move_policy"]["no_guarantee"] is True


def test_daily_summary_reports_a_plus_even_when_risk_is_high():
    result = summarize_daily_opportunity([
        {"candidate_id": "aggressive", "attack_grade": "A+", "conviction": "HIGH", "risk_level": "HIGH"},
        {"candidate_id": "balanced", "attack_grade": "B", "conviction": "HIGH", "risk_level": "MEDIUM"},
    ])
    assert result["daily_signal"] == "A_PLUS_PRESENT"
    assert result["a_grade_present"] is True
    assert result["best_candidate_id"] == "aggressive"
    assert result["best_risk_level"] == "HIGH"


def test_daily_summary_says_no_a_instead_of_promoting_two_b_cards():
    result = summarize_daily_opportunity([
        {"candidate_id": "one", "attack_grade": "B", "conviction": "HIGH", "risk_level": "HIGH"},
        {"candidate_id": "two", "attack_grade": "B", "conviction": "MEDIUM", "risk_level": "MEDIUM"},
    ])
    assert result["daily_signal"] == "NO_A_TODAY"
    assert result["a_grade_present"] is False
    assert result["no_a_reason"] == "best_candidate_below_A_threshold"


def test_daily_summary_distinguishes_empty_pool_from_no_a():
    result = summarize_daily_opportunity([])
    assert result["daily_signal"] == "NO_SUITABLE_SETUP"
    assert result["no_a_reason"] == "no_candidate_cards"


