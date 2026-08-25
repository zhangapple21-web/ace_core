from core.daily_shift import DailyShift
from core.task import TaskPool


def test_daily_shift_is_evidence_only(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"))
    task = pool.create_task("completed", creator="test")
    task.audit_log.append({"event": "transition", "from": "pending", "to": "active", "reason": "lease_claimed"})
    task.audit_log.append({"event": "transition", "from": "approved", "to": "archived"})
    pool.update_task(task)
    report = DailyShift(pool, str(tmp_path / "data")).build("2026-08-25")
    assert report["no_synthetic_work"] is True
    assert report["taskpool"]["lifecycle_transitions"]["claim"] == 1
    assert len(pool.list_tasks()) == 1
