import json

from core.delivery_execution import (
    REASON_BAD_JSON,
    REASON_EMPTY,
    REASON_EXTERNAL,
    REASON_MISSING,
    REASON_OK,
    REASON_OUT_OF_BOUNDS,
    DeliveryExecutor,
    declares_delivery,
    delivery_contract,
    verify_delivery,
    worker_verdict,
)
from core.task import Task


def _delivery_task(required_path="docs/DELIVERY_PROBE.md", metric="file_exists_nonempty"):
    return Task(
        task_id="RQ-TEST-001",
        title="delivery probe",
        hypothesis="h",
        priority="medium",
        tags=["external_target"],
        outputs={
            "delivery": {
                "required_path": required_path,
                "success_metric": metric,
                "domain": "document",
            }
        },
    )


def test_declares_delivery_only_for_wellformed_blocks():
    assert declares_delivery(_delivery_task()) is True
    assert declares_delivery(Task(task_id="RQ-TEST-002", title="no delivery")) is False


def test_contract_rejects_absolute_and_unknown_suffix(tmp_path):
    bad_path = delivery_contract(_delivery_task(required_path=str(tmp_path / "x.md")))
    assert "required_path_must_be_relative" in bad_path["errors"]
    bad_suffix = delivery_contract(_delivery_task(required_path="docs/x.exe"))
    assert "required_path_suffix_not_allowed" in bad_suffix["errors"]
    assert delivery_contract(_delivery_task())["valid"] is True


def test_missing_file_is_reported_as_missing_not_as_success(tmp_path):
    receipt = verify_delivery(_delivery_task(), tmp_path)
    assert receipt["satisfied"] is False
    assert receipt["reason"] == REASON_MISSING


def test_existing_nonempty_file_satisfies_delivery(tmp_path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "DELIVERY_PROBE.md").write_text("# real artifact\n", encoding="utf-8")
    receipt = verify_delivery(_delivery_task(), tmp_path)
    assert receipt["satisfied"] is True
    assert receipt["reason"] == REASON_OK
    assert receipt["size_bytes"] > 0


def test_empty_file_does_not_satisfy_delivery(tmp_path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "DELIVERY_PROBE.md").write_text("", encoding="utf-8")
    assert verify_delivery(_delivery_task(), tmp_path)["reason"] == REASON_EMPTY


def test_json_metric_requires_parsable_payload(tmp_path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "DELIVERY_PROBE.md").write_text("not json", encoding="utf-8")
    assert (
        verify_delivery(
            _delivery_task(metric="schema_valid_json"), tmp_path
        )["reason"]
        == REASON_BAD_JSON
    )
    (target / "DELIVERY_PROBE.md").write_text('{"ok": true}', encoding="utf-8")
    assert verify_delivery(_delivery_task(metric="schema_valid_json"), tmp_path)["satisfied"] is True


def test_external_metrics_stay_silent_instead_of_failing_closed(tmp_path):
    receipt = verify_delivery(_delivery_task(metric="user_accepted"), tmp_path)
    assert receipt["satisfied"] is None
    assert receipt["reason"] == REASON_EXTERNAL


def test_path_traversal_is_refused(tmp_path):
    receipt = verify_delivery(_delivery_task(required_path="docs/../../escape.md"), tmp_path)
    assert receipt["reason"] == REASON_OUT_OF_BOUNDS


def test_executor_fails_closed_without_worker_and_never_claims_delivery(tmp_path):
    result = DeliveryExecutor(tmp_path).execute(_delivery_task())
    assert result["status"] == "NO_WORKER_AVAILABLE"
    assert result["verification"]["satisfied"] is False


def test_executor_receipt_comes_from_disk_not_from_worker_claim(tmp_path):
    lying_worker = lambda **kwargs: {"ok": True}  # noqa: E731 - claims success, writes nothing
    result = DeliveryExecutor(tmp_path, worker_runner=lying_worker).execute(_delivery_task())
    assert result["status"] == "WORKER_FAILED"
    assert result["verification"]["reason"] == REASON_MISSING


def test_executor_reports_delivered_when_worker_really_writes_the_file(tmp_path):
    def real_worker(**kwargs):
        path = tmp_path / kwargs["required_path"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# produced by worker\n", encoding="utf-8")
        return {"ok": True}

    result = DeliveryExecutor(tmp_path, worker_runner=real_worker).execute(_delivery_task())
    assert result["status"] == "DELIVERED"
    assert result["verification"]["satisfied"] is True


def test_executor_skips_work_when_artifact_already_present(tmp_path):
    target = tmp_path / "docs"
    target.mkdir()
    (target / "DELIVERY_PROBE.md").write_text("already there\n", encoding="utf-8")
    calls = []

    def worker(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    result = DeliveryExecutor(tmp_path, worker_runner=worker).execute(_delivery_task())
    assert result["status"] == "ALREADY_DELIVERED"
    assert calls == []


def test_worker_verdict_reads_success_field_instead_of_mapping_truthiness():
    # bool({"success": False}) is True, so a failing OpenCodeWorker would
    # otherwise be recorded as ok: true -- a false claim inside a receipt.
    failed = worker_verdict({"success": False, "error": "opencode_all_models_failed"})
    assert failed["ok"] is False
    assert failed["error"] == "opencode_all_models_failed"
    assert worker_verdict({"success": True})["ok"] is True
    assert worker_verdict({"ok": True})["ok"] is True


def test_worker_verdict_marks_a_mapping_without_verdict_as_unverifiable():
    verdict = worker_verdict({"stdout": "something happened"})
    assert verdict["claim"] == "unverifiable_no_verdict_field"


def test_executor_attempt_does_not_claim_ok_when_real_worker_reports_failure(tmp_path):
    def failing_worker(**_kwargs):
        return {"success": False, "error": "opencode_all_models_failed", "attempts": []}

    result = DeliveryExecutor(tmp_path, worker_runner=failing_worker).execute(_delivery_task())
    assert result["status"] == "WORKER_FAILED"
    assert result["attempts"][0]["ok"] is False


def test_contract_payload_is_json_serialisable_for_task_storage(tmp_path):
    json.dumps(delivery_contract(_delivery_task()), ensure_ascii=False)
    json.dumps(verify_delivery(_delivery_task(), tmp_path), ensure_ascii=False)