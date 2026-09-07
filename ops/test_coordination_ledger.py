import json
from agent_team.coordination_ledger import reconcile_directory, reconcile_state

def _state():
    return {"threads": [{"thread_id": "thread-1", "status": "completed_pending_integration", "adopted": False, "ownership": "report.md", "acceptance_audit": "acceptance.md"}]}

def test_reconcile_requires_output_and_explicit_acceptance(tmp_path):
    state = _state()
    (tmp_path / "report.md").write_text("worker evidence", encoding="utf-8")
    (tmp_path / "acceptance.md").write_text("## Decision\n\nAccepted after RED/GREEN verification.\n", encoding="utf-8")
    result, changes = reconcile_state(state, tmp_path)
    assert result["threads"][0]["status"] == "completed_adopted"
    assert result["threads"][0]["adopted"] is True
    assert len(changes) == 1

def test_reconcile_does_not_auto_accept_rejection(tmp_path):
    state = _state()
    (tmp_path / "report.md").write_text("worker evidence", encoding="utf-8")
    (tmp_path / "acceptance.md").write_text("## Decision\n\nRejected pending evidence.\n", encoding="utf-8")
    result, changes = reconcile_state(state, tmp_path)
    assert result == state and changes == []

def test_reconcile_is_idempotent(tmp_path):
    (tmp_path / "report.md").write_text("worker evidence", encoding="utf-8")
    (tmp_path / "acceptance.md").write_text("## Decision\n\nAccepted after review.\n", encoding="utf-8")
    (tmp_path / "state.json").write_text(json.dumps(_state()), encoding="utf-8")
    assert len(reconcile_directory(tmp_path)) == 1
    assert reconcile_directory(tmp_path) == []

def test_reconcile_rejects_paths_outside_root(tmp_path):
    state = _state()
    state["threads"][0]["ownership"] = "../report.md"
    state["threads"][0]["acceptance_audit"] = "../acceptance.md"
    result, changes = reconcile_state(state, tmp_path)
    assert result == state and changes == []



