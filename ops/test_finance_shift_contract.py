from core.finance_shift_contract import build_evaluation_slots, build_postmortem_status


def _record(**overrides):
    item = {
        "evaluation_only": True,
        "recommendation_id": "EVAL-1",
        "timestamp": "2026-08-27T09:45:00+08:00",
        "symbol": "000001",
        "reference_price": 10.2,
        "hypothesis": "research hypothesis",
        "invalidating_conditions": ["break condition"],
        "next_verification": "next session",
        "data_snapshot_hash": "hash",
        "source_refs": ["source-a", "source-b"],
        "data_quality_state": "DEGRADED",
        "feature_version": "v1",
        "advisor_version": "blocked",
        "risk_version": "not-ready",
    }
    item.update(overrides)
    return item


def test_slots_are_an_upper_bound_and_not_a_quota():
    report = build_evaluation_slots([], target=2)
    assert report["evaluation_pick_target"] == 2
    assert report["evaluation_pick_count"] == 0
    assert report["status"] == "NO_VALID_EVALUATION_PICK"
    assert report["publication_authority"] is False


def test_only_complete_explicit_paper_records_are_visible():
    report = build_evaluation_slots([_record(), _record(recommendation_id="EVAL-2")], target=2)
    assert report["evaluation_pick_count"] == 2
    assert report["status"] == "VALID"
    assert [item["recommendation_id"] for item in report["picks"]] == ["EVAL-1", "EVAL-2"]
    assert build_evaluation_slots([_record(source_refs=[])])["evaluation_pick_count"] == 0


def test_three_eligible_picks_are_explicitly_excess_not_silently_truncated():
    report = build_evaluation_slots(
        [_record(), _record(recommendation_id="EVAL-2"), _record(recommendation_id="EVAL-3")],
        target=2,
    )
    assert report["evaluation_pick_count"] == 3
    assert report["status"] == "INVALID_EXCESS_EVALUATION_PICK"
    assert report["publication_authority"] is False


def test_postmortem_refuses_to_review_untraceable_history():
    assert build_postmortem_status([])["status"] == "NO_ELIGIBLE_PRIOR_RECORD"
    assert build_postmortem_status([_record()])["status"] == "READY_FOR_REVIEW"


