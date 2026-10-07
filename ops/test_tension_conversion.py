# Regression: tension observations must convert into verification tasks.
#
# The surprise/tension stage asks questions nobody assigned, but the
# converter only had rules for errors, bottlenecks, gaps and health. Without
# a tension rule the questions rotted as observations forever: asked, never
# answered. This pins the missing link between asking and working.
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


def _tension(pool_dir_unused, observer, key="fa_duty_gap"):
    return observer.record(
        description="Why does X never happen although Y keeps running?",
        system_state={"tension_key": key, "evidence": {"runs": 0}},
        severity="medium",
        source="tension_check",
        category="anomaly",
        auto_generated=True,
        dedup_key=("tension", key),
    )


def test_tension_observation_converts_to_task(tmp_path):
    pool, observer, converter = _stack(tmp_path)
    obs = _tension(None, observer)

    result = converter.convert()

    assert result["tasks_created"] == 1, f"converter result: {result}"
    refreshed = [o for o in observer.get_recent(limit=20) if o.obs_id == obs.obs_id][0]
    assert refreshed.task_generated, "observation must link its task"
    tasks = pool.list_tasks(status="pending", limit=10)
    assert len(tasks) == 1
    assert "question_forge" in tasks[0].tags


def test_same_tension_does_not_file_twice(tmp_path):
    pool, observer, converter = _stack(tmp_path)
    _tension(None, observer, key="learn_without_use")

    first = converter.convert()
    second = converter.convert()

    assert first["tasks_created"] == 1
    assert second["tasks_created"] == 0, f"second convert: {second}"


def test_ordinary_anomaly_without_tension_key_is_untouched(tmp_path):
    pool, observer, converter = _stack(tmp_path)
    observer.record(
        description="Something odd happened.",
        system_state={"note": "no tension key here"},
        severity="medium",
        source="surprise_check",
        category="anomaly",
        auto_generated=True,
        dedup_key=("surprise", "heartbeat_stale"),
    )

    result = converter.convert()

    assert result["tasks_created"] == 0
    assert pool.get_stats()["total"] == 0
