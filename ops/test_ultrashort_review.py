import pytest

from core.ultrashort_review import (
    freeze_opportunity_snapshot,
    metadata,
    record_opportunity_outcome,
    record_teacher_decision,
)


def _call():
    return {
        "daily_signal": "A_PRESENT",
        "candidate_count": 1,
        "best_candidate_id": "candidate-001",
        "best_attack_grade": "A",
        "best_conviction": "HIGH",
        "best_risk_level": "MEDIUM",
    }


def _snapshot():
    return freeze_opportunity_snapshot(
        _call(),
        snapshot_id="snap-001",
        as_of="2026-09-24T09:40:00+08:00",
        source_refs=["evidence://snapshot/001"],
    )


def test_snapshot_is_as_of_and_outcome_cannot_backfill_it():
    snapshot = _snapshot()
    assert snapshot["snapshot_scope"] == "AS_OF_NOT_FINAL_DAY_GRADE"
    assert snapshot["outcome_status"] == "PENDING_REVIEW"
    outcome = record_opportunity_outcome(
        snapshot,
        outcome="INVALIDATED",
        reviewed_at="2026-09-25T15:10:00+08:00",
        source_refs=["evidence://d1/001"],
        details={"reason": "support_failed"},
    )
    assert outcome["snapshot_as_of"] == snapshot["snapshot_as_of"]
    assert outcome["source_snapshot_hash"] == snapshot["snapshot_hash"]
    assert outcome["snapshot_unchanged"] is True
    assert outcome["daily_call_backfilled"] is False
    assert snapshot["daily_call"]["best_attack_grade"] == "A"


def test_rejected_teacher_candidate_stays_in_sample_and_counterfactual_replay():
    decision = record_teacher_decision(
        _snapshot(),
        decision="REJECTED",
        decided_at="2026-09-24T09:45:00+08:00",
        rationale="板块同步不足，老师否决。",
    )
    policy = decision["sample_policy"]
    assert policy["selection_sample_included"] is True
    assert policy["outcome_replay_eligible"] is True
    assert policy["counterfactual_replay"] is True
    assert policy["executed_trade_claim"] is False
    assert decision["manual_judgement_policy"]["changes_permanent_weights"] is False


def test_approved_candidate_needs_fill_evidence_for_execution_replay():
    decision = record_teacher_decision(
        _snapshot(),
        decision="APPROVED",
        decided_at="2026-09-24T09:45:00+08:00",
        rationale="条件满足，进入人工观察。",
    )
    policy = decision["sample_policy"]
    assert policy["outcome_replay_eligible"] is True
    assert policy["counterfactual_replay"] is False
    assert policy["execution_replay_requires_separate_fill_evidence"] is True
    assert policy["executed_trade_claim"] is False


def test_boundary_rejects_outcome_without_independent_source_refs():
    with pytest.raises(ValueError, match="outcome_source_refs_required"):
        record_opportunity_outcome(
            _snapshot(),
            outcome="VALIDATED",
            reviewed_at="2026-09-25T15:10:00+08:00",
            source_refs=[],
        )


def test_metadata_makes_rule_pollution_boundary_explicit():
    data = metadata()
    assert data["outcome_is_separate_record"] is True
    assert data["teacher_rejected_kept_in_selection_sample"] is True
    assert data["teacher_approved_replay_requires_fill_evidence"] is True
    assert data["manual_judgement_changes_rules"] is False
