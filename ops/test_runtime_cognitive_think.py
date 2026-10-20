from pathlib import Path

from core.cognitive_think_gate import CHARTER, CONTRACT_VERSION, COGNITIVE_HUB, THINK
from core.runtime_cognitive_think import evaluate_daemon_cognitive_think


def test_daemon_cognitive_think_writes_runtime_state(tmp_path: Path):
    result = evaluate_daemon_cognitive_think(
        tmp_path,
        {},
        {"runtime": {}},
        "run-think-1",
        continue_status="CONTINUE",
    )
    assert result["status"] == THINK
    assert result["actor_role"] == COGNITIVE_HUB
    assert result["thinking_permitted"] is True
    assert result["thinking_grants_execution"] is False
    assert result["execution_permitted"] is False
    assert result["continue_status"] == "CONTINUE"
    path = Path(result["runtime_state_path"])
    assert path == tmp_path / "runtime" / "cognitive_think_runtime_state.json"
    text = path.read_text(encoding="utf-8")
    assert CONTRACT_VERSION in text
    assert CHARTER in text
    assert "run-think-1" in text


def test_continue_closed_does_not_authorize_execution(tmp_path: Path):
    result = evaluate_daemon_cognitive_think(
        tmp_path,
        {"cognitive_execution_requested": True},
        {"runtime": {}},
        "run-think-2",
        continue_status="CLOSE_AND_HANDOFF",
    )
    assert result["execution_permitted"] is False
    assert result["thinking_grants_execution"] is False
    assert "EXECUTION_DENIED_BY_THINK_GATE" in result["reason_codes"]
