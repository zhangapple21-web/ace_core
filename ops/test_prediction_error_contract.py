import json

import pytest

from core.prediction_error_contract import (
    append_prediction_receipt,
    build_prediction_receipt,
    compare_prediction,
    validate_prediction_receipt,
)


def _prediction(**overrides):
    value = {
        "subject": "短剧镜头表演",
        "expected_state": {
            "performance": {"hand_action": "raise_hand", "listener_reaction": "turn_head"},
            "sync": {"offset_ms": 0},
        },
        "success_observables": [
            {"name": "hand_action", "path": "performance.hand_action"},
            {"name": "listener_reaction", "path": "performance.listener_reaction", "severity": "critical"},
            {"name": "sync_offset", "path": "sync.offset_ms", "tolerance": 80},
        ],
        "observation_refs": ["test://render/001/readback"],
        "actual_observation": {
            "performance": {"hand_action": "raise_hand", "listener_reaction": "turn_head"},
            "sync": {"offset_ms": 40},
        },
        "resource_budget": {"max_retries": 1},
    }
    value.update(overrides)
    return value


def test_matching_prediction_is_keep_and_is_hash_verified():
    receipt = build_prediction_receipt(**_prediction())
    assert receipt["decision"] == "KEEP"
    assert receipt["mismatch"] is False
    assert receipt["execution_authorized"] is False
    assert validate_prediction_receipt(receipt)["prediction_id"] == receipt["prediction_id"]


def test_critical_mismatch_is_rollback():
    payload = _prediction()
    payload["actual_observation"]["performance"]["listener_reaction"] = "none"
    receipt = build_prediction_receipt(**payload)
    assert receipt["comparison"]["status"] == "MISMATCHED"
    assert receipt["decision"] == "ROLLBACK"
    assert receipt["learning_status"] == "PENDING"


def test_noncritical_mismatch_is_retry():
    payload = _prediction()
    payload["actual_observation"]["performance"]["hand_action"] = "none"
    receipt = build_prediction_receipt(**payload)
    assert receipt["decision"] == "RETRY"


def test_missing_observation_stays_unknown():
    payload = _prediction(actual_observation={"performance": {"hand_action": "raise_hand"}})
    receipt = build_prediction_receipt(**payload)
    assert receipt["decision"] == "UNKNOWN"
    assert receipt["comparison"]["unknown_count"] == 2


def test_unreferenced_readback_cannot_be_treated_as_real_success():
    payload = _prediction()
    payload.pop("observation_refs")
    receipt = build_prediction_receipt(**payload)
    assert receipt["comparison"]["status"] == "MATCHED"
    assert receipt["decision"] == "UNKNOWN"
    assert receipt["observation_verified"] is False


def test_tampering_with_comparison_or_authority_is_rejected():
    receipt = build_prediction_receipt(**_prediction())
    receipt["decision"] = "KEEP"
    receipt["execution_authorized"] = True
    with pytest.raises(ValueError, match="authority"):
        validate_prediction_receipt(receipt)

    receipt = build_prediction_receipt(**_prediction())
    receipt["comparison"]["status"] = "MISMATCHED"
    with pytest.raises(ValueError, match="comparison|hash"):
        validate_prediction_receipt(receipt)


def test_append_is_idempotent(tmp_path):
    receipt = build_prediction_receipt(**_prediction())
    out = tmp_path / "prediction_error_receipts.jsonl"
    assert append_prediction_receipt(receipt, out)["added"] == 1
    assert append_prediction_receipt(receipt, out)["added"] == 0
    lines = out.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["schema"] == "ace.prediction_error.v1"


def test_compare_prediction_does_not_treat_false_as_missing():
    comparison = compare_prediction(
        {"visible": False},
        {"visible": False},
        [{"name": "visible", "path": "visible"}],
    )
    assert comparison["status"] == "MATCHED"
