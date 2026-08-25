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
    assert report["taskpool"]["lifecycle_transitions"]["approved"] == 1
    assert len(pool.list_tasks()) == 1


def test_daily_shift_surfaces_shadow_model_performance(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "daily_growth_latest.json").write_text(
        '{"model_performance_ledger":{"shadow_only":true,"group_count":1}}',
        encoding="utf-8",
    )

    report = DailyShift(TaskPool(str(tmp_path / "task_pool")), str(data)).build(
        "2026-08-25"
    )

    assert report["model_performance"] == {
        "shadow_only": True,
        "group_count": 1,
    }
    assert "Model performance: `1` groups" in (data / "daily_shift_latest.md").read_text(
        encoding="utf-8"
    )
