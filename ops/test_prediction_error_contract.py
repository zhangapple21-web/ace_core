import json
import hashlib

import pytest

from core.prediction_error_contract import (
    append_prediction_receipt,
    build_prediction_receipt,
    compare_prediction,
    validate_prediction_receipt,
)


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _evidence(tmp_path, actual, name="readback.json"):
    envelope = {
        "actual_observation": actual,
        "observation_sha256": hashlib.sha256(_canonical(actual)).hexdigest(),
    }
    path = tmp_path / name
    path.write_text(json.dumps(envelope, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return [{
        "ref": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "verification_method": "test_runner",
        "producer_role": "test_runner",
    }]


def _prediction(tmp_path=None, **overrides):
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
        "actual_observation": {
            "performance": {"hand_action": "raise_hand", "listener_reaction": "turn_head"},
            "sync": {"offset_ms": 40},
        },
        "resource_budget": {"max_retries": 1},
    }
    if tmp_path is not None:
        value["observation_refs"] = _evidence(tmp_path, value["actual_observation"])
    value.update(overrides)
    if tmp_path is not None and "actual_observation" in overrides and "observation_refs" not in overrides:
        value["observation_refs"] = _evidence(tmp_path, value["actual_observation"], "override-readback.json")
    return value


def test_matching_prediction_is_keep_and_is_hash_verified(tmp_path):
    receipt = build_prediction_receipt(**_prediction(tmp_path))
    assert receipt["decision"] == "KEEP"
    assert receipt["mismatch"] is False
    assert receipt["execution_authorized"] is False
    assert validate_prediction_receipt(receipt)["prediction_id"] == receipt["prediction_id"]


def test_critical_mismatch_is_rollback(tmp_path):
    payload = _prediction(tmp_path)
    payload["actual_observation"]["performance"]["listener_reaction"] = "none"
    payload["observation_refs"] = _evidence(tmp_path, payload["actual_observation"], "critical-readback.json")
    receipt = build_prediction_receipt(**payload)
    assert receipt["comparison"]["status"] == "MISMATCHED"
    assert receipt["decision"] == "ROLLBACK"
    assert receipt["learning_status"] == "PENDING"


def test_noncritical_mismatch_is_retry(tmp_path):
    payload = _prediction(tmp_path)
    payload["actual_observation"]["performance"]["hand_action"] = "none"
    payload["observation_refs"] = _evidence(tmp_path, payload["actual_observation"], "retry-readback.json")
    receipt = build_prediction_receipt(**payload)
    assert receipt["decision"] == "RETRY"


def test_missing_observation_stays_unknown(tmp_path):
    payload = _prediction(tmp_path, actual_observation={"performance": {"hand_action": "raise_hand"}})
    receipt = build_prediction_receipt(**payload)
    assert receipt["decision"] == "UNKNOWN"
    assert receipt["comparison"]["unknown_count"] == 2


def test_unreferenced_readback_cannot_be_treated_as_real_success(tmp_path):
    payload = _prediction(tmp_path)
    payload.pop("observation_refs")
    receipt = build_prediction_receipt(**payload)
    assert receipt["comparison"]["status"] == "MATCHED"
    assert receipt["decision"] == "UNKNOWN"
    assert receipt["observation_verified"] is False


def test_model_assertion_never_closes_observation_gap(tmp_path):
    actual = _prediction()["actual_observation"]
    refs = _evidence(tmp_path, actual, "model-claimed.json")
    refs[0]["producer_role"] = "model_output"
    payload = _prediction(tmp_path, observation_refs=refs)
    receipt = build_prediction_receipt(**payload)
    assert receipt["observation_verification"]["status"] == "UNVERIFIED"
    assert receipt["decision"] == "UNKNOWN"


def test_verified_artifact_can_supply_actual_observation(tmp_path):
    expected = {"render": {"motion": "visible"}}
    refs = _evidence(tmp_path, expected, "artifact-only.json")
    receipt = build_prediction_receipt(
        subject="artifact readback",
        expected_state=expected,
        success_observables=[{"name": "motion", "path": "render.motion"}],
        actual_observation=None,
        observation_refs=refs,
    )
    assert receipt["observation_verification"]["status"] == "VERIFIED"
    assert receipt["actual_observation"] == expected
    assert receipt["decision"] == "KEEP"


def test_changed_evidence_file_cannot_validate_old_keep_receipt(tmp_path):
    receipt = build_prediction_receipt(**_prediction(tmp_path))
    evidence_path = tmp_path / "readback.json"
    evidence_path.write_text('{"actual_observation":{"tampered":true}}', encoding="utf-8")
    with pytest.raises(ValueError, match="decision|verification|hash"):
        validate_prediction_receipt(receipt)


def test_tampering_with_comparison_or_authority_is_rejected(tmp_path):
    receipt = build_prediction_receipt(**_prediction(tmp_path))
    receipt["decision"] = "KEEP"
    receipt["execution_authorized"] = True
    with pytest.raises(ValueError, match="authority"):
        validate_prediction_receipt(receipt)

    receipt = build_prediction_receipt(**_prediction(tmp_path))
    receipt["comparison"]["status"] = "MISMATCHED"
    with pytest.raises(ValueError, match="comparison|hash"):
        validate_prediction_receipt(receipt)


def test_append_is_idempotent(tmp_path):
    receipt = build_prediction_receipt(**_prediction(tmp_path))
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
