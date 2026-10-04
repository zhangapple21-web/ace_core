import pytest

from core.task import TaskPool
from ops.test_support import FixtureTaskPool as Pool


def _pool(tmp_path):
    return Pool(str(tmp_path / "task_pool"))


def test_reopen_requires_a_reason(tmp_path):
    pool = _pool(tmp_path)
    task = pool.create_task(title="delivery held hostage")
    pool.block_task(task.task_id, reason="delivery_not_produced:docs/x.md", actor="delivery_executor",
                    block_type="external_condition_blocked")
    with pytest.raises(ValueError):
        pool.reopen_task(task.task_id, reason="   ", actor="ops")
    assert pool.load_task(task.task_id).status == "blocked"


def test_reopen_clears_the_non_convergent_flag_and_returns_to_pending(tmp_path):
    pool = _pool(tmp_path)
    task = pool.create_task(title="duplicate evidence ceiling")
    pool.block_task(task.task_id, reason="相同证据集重复验证达到上限，等待人工或外部新证据",
                    actor="validator", block_type="manual_gate_blocked")
    stored = pool.load_task(task.task_id)
    stored.outputs["terminal_non_convergent"] = True
    pool.update_task(stored)

    assert pool.unblock_task(task.task_id, actor="ops") is None, "unblock must stay closed"
    reopened = pool.reopen_task(task.task_id, reason="artifact was delivered", actor="ops")
    assert reopened.status == "pending"
    assert "terminal_non_convergent" not in pool.load_task(task.task_id).outputs
    assert pool.load_task(task.task_id).blocked_reason == ""


def test_reopen_records_its_own_audit_event_and_keeps_history(tmp_path):
    pool = _pool(tmp_path)
    task = pool.create_task(title="auditable reopen")
    pool.block_task(task.task_id, reason="ceiling", actor="validator", block_type="manual_gate_blocked")
    pool.reopen_task(task.task_id, reason="new artifact", actor="ops", new_evidence=[{"content": "file"}])

    reopened = pool.load_task(task.task_id)
    events = [entry.get("event") for entry in reopened.audit_log]
    assert "reopened" in events
    assert "transition" in events, "the original blocked transition must survive"
    entry = next(e for e in reopened.audit_log if e.get("event") == "reopened")
    assert entry["actor"] == "ops"
    assert entry["evidence_added"] == 1
    assert len(reopened.evidence) == 1


def test_reopen_only_applies_to_blocked_tasks(tmp_path):
    pool = _pool(tmp_path)
    task = pool.create_task(title="still pending")
    assert pool.reopen_task(task.task_id, reason="nothing was blocked", actor="ops") is None
    assert pool.load_task(task.task_id).status == "pending"


def test_reopen_persists_through_index_reload(tmp_path):
    pool = _pool(tmp_path)
    task = pool.create_task(title="index visibility")
    pool.block_task(task.task_id, reason="ceiling", actor="validator", block_type="manual_gate_blocked")
    pool.reopen_task(task.task_id, reason="escape hatch", actor="ops")

    reopened = TaskPool(str(tmp_path / "task_pool")).load_task(task.task_id)
    assert reopened.status == "pending"
    assert TaskPool(str(tmp_path / "task_pool")).list_tasks(status="pending", limit=50)