import pytest

from core.paper_evaluation_journal import PaperEvaluationJournal


def _record(**overrides):
    value = {
        "evaluation_id": "EVAL-001", "mode": "EVALUATION_ONLY",
        "publication_authority": False, "not_a_recommendation": True,
        "recorded_at": "2026-08-28T10:00:00+08:00", "observation_at": "2026-08-28T09:35:00+08:00",
        "symbol": "600000", "reference_price": 10.2, "hypothesis": "test only",
        "invalidating_conditions": ["condition"], "data_snapshot_hash": "snapshot-hash",
        "source_refs": ["source-a", "source-b"], "data_quality_state": "DEGRADED",
        "feature_version": "v1", "strategy_id": "strategy-test", "strategy_version": "v1",
        "horizon_policy": {"version": "v1", "horizons": [7, 14, 30], "calendar": "explicit_upstream"},
        "micro_observation": {
            "contract_version": "ace.micro_observation.v1",
            "observation": "quote observed",
            "intent": "test a bounded hypothesis",
            "constraints": ["paper only"],
            "action": "record snapshot",
            "result": "recorded",
            "feedback": "await outcome",
            "next_question": "does the hypothesis survive D+7?",
            "evidence_refs": ["source-a"],
            "production_integration": False,
        },
    }
    value.update(overrides)
    return value


def test_degraded_but_complete_evaluation_record_is_persisted_without_publication(tmp_path):
    journal = PaperEvaluationJournal(str(tmp_path))
    assert journal.record(_record())["status"] == "RECORDED"
    assert journal.record(_record())["status"] == "ALREADY_RECORDED"
    assert journal.summary()["recorded_count"] == 1
    assert journal.summary()["publication_authority"] is False


def test_incomplete_record_is_rejected_without_writing_partial_ledger(tmp_path):
    journal = PaperEvaluationJournal(str(tmp_path))
    with pytest.raises(ValueError, match="incomplete_evaluation_record"):
        journal.record(_record(source_refs=[]))
    assert not journal.path.exists()


def test_outcome_receipt_requires_prior_record_and_enables_postmortem_only_with_evidence(tmp_path):
    journal = PaperEvaluationJournal(str(tmp_path))
    with pytest.raises(ValueError, match="evaluation_record_not_found"):
        journal.record_outcome({"evaluation_id": "missing", "horizon": "D+7", "observed_at": "2026-09-04T15:00:00+08:00", "result_snapshot_hash": "a" * 64, "source_refs": ["source"], "evaluation_rule_version": "v1"})
    journal.record(_record())
    assert journal.summary()["postmortem_status"] == "NO_ELIGIBLE_PRIOR_RECORD"
    receipt = {"evaluation_id": "EVAL-001", "horizon": "D+7", "observed_at": "2026-09-04T15:00:00+08:00", "result_snapshot_hash": "a" * 64, "source_refs": ["source"], "evaluation_rule_version": "v1"}
    assert journal.record_outcome(receipt)["status"] == "OUTCOME_RECORDED"
    assert journal.summary()["postmortem_status"] == "READY_FOR_REVIEW"


def test_outcome_rejects_malformed_evidence_and_horizon_outside_frozen_policy(tmp_path):
    journal = PaperEvaluationJournal(str(tmp_path))
    journal.record(_record())
    with pytest.raises(ValueError, match="outcome_evidence_malformed"):
        journal.record_outcome({"evaluation_id": "EVAL-001", "horizon": "D+7", "observed_at": "2026-09-04T15:00:00+08:00", "result_snapshot_hash": "result", "source_refs": "source", "evaluation_rule_version": "v1"})
    with pytest.raises(ValueError, match="horizon_not_in_frozen_policy"):
        journal.record_outcome({"evaluation_id": "EVAL-001", "horizon": "D+1", "observed_at": "2026-08-29T15:00:00+08:00", "result_snapshot_hash": "a" * 64, "source_refs": ["source"], "evaluation_rule_version": "v1"})
    assert journal.summary()["postmortem_status"] == "NO_ELIGIBLE_PRIOR_RECORD"


