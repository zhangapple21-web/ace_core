from core.outcome_receipt import OutcomeReceiptRecorder
from core.task import Task


def _task():
    return Task(
        task_id="RQ-OUTCOME-1",
        title="Independent recheck",
        hypothesis="A bounded result can be independently verified.",
        evidence=[
            {"source": "fixture://source-a"},
            {"source": "fixture://source-b"},
        ],
        result={"finding": "pending verification"},
        outputs={"admission": {"expected_result": "A bounded finding", "verification_method": "Recheck two sources"}},
    )


def test_archival_stage_is_pending_and_not_a_verified_outcome():
    task = _task()
    receipt = OutcomeReceiptRecorder().stage(task)

    assert receipt["status"] == "PENDING_EXTERNAL_VERIFICATION"
    assert receipt["result_present"] is True
    assert "verified_outcome_receipt" not in task.outputs


def test_verified_receipt_requires_independent_refs_and_groups():
    task = _task()
    recorder = OutcomeReceiptRecorder()
    receipt = recorder.verify(
        task,
        result_ref="fixture://result",
        verification_ref="fixture://verification",
        evidence_refs=["fixture://source-a", "fixture://source-b"],
        independent_evidence_groups=2,
        verifier="independent_rechecker",
        verified_at="2026-09-01T12:00:00",
    )

    assert receipt["status"] == "VERIFIED"
    assert task.outputs["verified_outcome_receipt"] == receipt
