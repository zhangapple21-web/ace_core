from core.daily_shift import DailyShift
from core.task import TaskPool


def test_daily_shift_is_evidence_only(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"))
    task = pool.create_task("completed", creator="test")
    task.audit_log.append({"event": "transition", "from": "pending", "to": "active", "reason": "lease_claimed", "at": "2026-08-25T09:00:00"})
    task.audit_log.append({"event": "transition", "from": "active", "to": "review", "actor": "researcher", "at": "2026-08-25T09:01:00"})
    task.audit_log.append({"event": "transition", "from": "review", "to": "approved", "actor": "validator", "at": "2026-08-25T09:02:00"})
    task.audit_log.append({"event": "transition", "from": "approved", "to": "archived", "at": "2026-08-25T09:03:00"})
    pool.update_task(task)
    report = DailyShift(pool, str(tmp_path / "data")).build("2026-08-25")
    assert report["no_synthetic_work"] is True
    assert report["taskpool"]["lifecycle_transitions"]["claim"] == 1
    assert report["taskpool"]["lifecycle_transitions"]["validation"] == 1
    assert len(pool.list_tasks()) == 1
