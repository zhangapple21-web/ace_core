# Regression: a dead patrol and a deaf converter must both be caught.
#
# Field evidence: ops/run_checkup.py had no trigger for 22 days while the
# daemon filed 186 identical "巡检超过 N 小时未执行" observations, and the
# scheduled_task_inactive rule required task_never_run=True while the daemon
# always writes False. The scream was structurally inaudible.
import json
import tempfile
from pathlib import Path

from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.task import TaskPool


def _stack(tmp_path):
    pool = TaskPool(str(tmp_path / "pool"))
    observer = RuntimeObserver(data_dir=str(tmp_path / "obs"))
    converter = ObservationToTaskConverter(observer=observer, task_pool=pool)
    return pool, observer, converter


def test_stale_patrol_converts_despite_never_run_false(tmp_path):
    pool, observer, converter = _stack(tmp_path)
    observer.record(
        description="计划任务超过 544 小时未执行，自动巡检可能中断。",
        system_state={
            "task_never_run": False,
            "last_checkup": "2026-09-15T17:29:48",
            "hours_since": 544.1,
        },
        severity="medium",
        source="daemon_loop",
        category="improvement",
        auto_generated=True,
    )

    result = converter.convert()

    assert result["tasks_created"] == 1, f"converter result: {result}"
    tasks = pool.list_tasks(status="pending", limit=10)
    assert len(tasks) == 1
    assert tasks[0].priority == "medium"


def test_fresh_patrol_converts_nothing(tmp_path):
    pool, observer, converter = _stack(tmp_path)
    observer.record(
        description="计划任务超过 3 小时未执行，自动巡检可能中断。",
        system_state={
            "task_never_run": False,
            "last_checkup": "2026-10-08T06:00:00",
            "hours_since": 3.0,
        },
        severity="medium",
        source="daemon_loop",
        category="improvement",
        auto_generated=True,
    )

    result = converter.convert()

    assert result["tasks_created"] == 0
    assert pool.get_stats()["total"] == 0


def test_checkup_error_snapshot_converts(tmp_path):
    pool, observer, converter = _stack(tmp_path)
    observer.record(
        description="巡检结果为 error，已捕获探针诊断。",
        system_state={
            "checkup_path": "ops/logs/checkup_history.jsonl",
            "checkup_snapshot": {"overall": "error", "errors": 1},
        },
        severity="high",
        source="checkup_history",
        category="health",
        auto_generated=True,
    )

    result = converter.convert()

    assert result["tasks_created"] == 1, f"converter result: {result}"
    tasks = pool.list_tasks(status="pending", limit=10)
    assert len(tasks) == 1
    assert tasks[0].priority == "high"


def test_checkup_ok_snapshot_converts_nothing(tmp_path):
    pool, observer, converter = _stack(tmp_path)
    observer.record(
        description="巡检结果为 ok。",
        system_state={
            "checkup_path": "ops/logs/checkup_history.jsonl",
            "checkup_snapshot": {"overall": "ok", "errors": 0},
        },
        severity="medium",
        source="checkup_history",
        category="health",
        auto_generated=True,
    )

    result = converter.convert()

    assert result["tasks_created"] == 0
