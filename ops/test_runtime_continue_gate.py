from pathlib import Path

from core.runtime_continue_gate import evaluate_daemon_boundary


def test_daemon_boundary_writes_receipt_when_context_is_stale(tmp_path: Path):
    result = evaluate_daemon_boundary(
        tmp_path,
        {"continuation_context_fresh": False, "continue_gate_failure_count": 0},
        {"runtime": {}},
        "run-1",
    )
    assert result["status"] == "CLOSE_AND_HANDOFF"
    receipt = Path(result["receipt_path"])
    assert receipt.is_file()
    assert "HANDOFF_REQUIRED" in receipt.read_text(encoding="utf-8")
    assert result["next_context_required"] is True
    assert result["prior_attempt_status"] == "PASS"


def test_new_daemon_context_can_continue(tmp_path: Path):
    result = evaluate_daemon_boundary(
        tmp_path,
        {"continuation_context_fresh": True},
        {"runtime": {}},
        "run-2",
    )
    assert result["status"] == "CONTINUE"
    assert result["context_id"] == "run-2"
    assert result["next_context_required"] is False


