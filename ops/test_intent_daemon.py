"""The intent pool must fire on a real moment and stay silent otherwise.

Covers: waiting for the shift, once-per-day gate, healthy idle when the external
backlog is full, and one injection when a candidate exists.
"""
import json
from datetime import datetime
from pathlib import Path

import pytest

from ace_daemon import AceDaemon
from ops.test_support import FixtureTaskPool


class _Stub(AceDaemon):
    """Only the intent trigger, without the runtime bootstrap."""

    def __init__(self, pool, base_dir, capacity=3):
        self.task_pool = pool
        self.base_dir = base_dir
        self.state = {"errors": []}
        self.config = {"runtime": {"intent_pool_capacity": capacity}}
        self._logged = []
        self._saved = 0

    def _log_error(self, module, error, *args):
        self._logged.append((module, error))

    def _save_state(self):
        self._saved += 1


@pytest.fixture()
def rig(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    queue = tmp_path / "queue.jsonl"
    state = tmp_path / "state.json"
    return _Stub(pool, tmp_path), pool, queue, state


@pytest.fixture()
def evening(monkeypatch):
    """Put the test on the 18:30 dedicated shift, where the barn may act."""

    class _Evening(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 10, 3, 19, 0, 0)

    monkeypatch.setattr("ace_daemon.datetime", _Evening)
    return _Evening


def _write_queue(path, intents):
    path.write_text(
        "\n".join(json.dumps(i, ensure_ascii=False) for i in intents) + "\n", encoding="utf-8"
    )


def _intent(intent_id="will_one", path="docs/WILL_ONE.md"):
    return {
        "intent_id": intent_id,
        "question": f"produce {path}",
        "why_now": "the pool must deliver something",
        "expected_result": path,
        "verification_method": "file_exists_nonempty",
        "delivery_path": path,
        "priority": "high",
        "domain": "analysis",
        "state": "candidate",
        "added_at": "2026-10-03",
        "tags": ["probe"],
    }


def _run(daemon, queue, state):
    return daemon._run_intent_pool_if_due(queue_path=queue, state_path=state)


def test_empty_grain_barn_injects_nothing(rig, evening):
    daemon, _pool, queue, state = rig
    queue.write_text("", encoding="utf-8")
    out = _run(daemon, queue, state)
    assert out["status"] == "NO_VALID_INTENT"
    assert out["reason"] == "intent_queue_empty"


def test_missing_queue_file_is_not_an_error(rig, evening):
    daemon, _pool, queue, state = rig  # queue never written
    out = _run(daemon, queue, state)
    assert out["status"] == "NO_VALID_INTENT"


def test_already_run_today_is_a_noop(rig, evening):
    daemon, _pool, queue, state = rig
    _write_queue(queue, [_intent()])
    daemon.state["intent_pool_date"] = "2026-10-03"
    out = _run(daemon, queue, state)
    assert out["status"] == "ALREADY_RUN_TODAY"


def test_a_candidate_intent_is_injected_once_and_recorded(rig, evening):
    daemon, pool, queue, state = rig
    _write_queue(queue, [_intent()])

    out = _run(daemon, queue, state)

    assert out["status"] == "INJECTED", out
    assert out["intent_id"] == "will_one"
    assert out["injection"]["outcome"] == "INJECTED"
    task_id = out["injection"]["receipt"]["task_id"]
    stored = pool.load_task(task_id)
    assert stored is not None
    delivery = stored.outputs["delivery"]
    assert delivery["required_path"] == "docs/WILL_ONE.md"
    assert delivery["success_metric"] == "file_exists_nonempty"
    assert daemon.state["intent_pool_date"] == "2026-10-03"
    saved = json.loads(state.read_text(encoding="utf-8"))
    assert saved["intents"]["will_one"]["state"] == "injected"


def test_full_external_backlog_stays_healthy_idle(rig, evening):
    """Grain barn, not a feeder: capacity full must inject nothing."""
    daemon, pool, queue, state = rig
    _write_queue(queue, [_intent("will_one", "docs/W1.md"), _intent("will_two", "docs/W2.md")])

    for n in range(3):
        pool.create_task(
            title=f"occupy external slot {n}",
            hypothesis="hold the slot",
            priority="high",
            tags=["intent:occupier"],
        )

    out = _run(daemon, queue, state)
    assert out["status"] == "HEALTHY_IDLE"
    assert out["reason"] == "external_backlog_at_capacity"
    assert not [t for t in pool.list_tasks(limit=500) if "intent:will_one" in (t.tags or [])]


def test_second_call_same_day_does_not_create_a_twin_task(rig, evening):
    daemon, pool, queue, state = rig
    _write_queue(queue, [_intent()])

    first = _run(daemon, queue, state)
    second = _run(daemon, queue, state)
    assert first["status"] == "INJECTED"
    assert second["status"] == "ALREADY_RUN_TODAY"
    tagged = [t for t in pool.list_tasks(limit=500) if "intent:will_one" in (t.tags or [])]
    assert len(tagged) == 1, f"blind re-injection created {len(tagged)} tasks"


def test_before_the_shift_it_waits_and_injects_nothing(rig, monkeypatch):
    daemon, pool, queue, state = rig
    _write_queue(queue, [_intent()])

    class _Morning(datetime):
        @classmethod
        def now(cls):
            return datetime(2026, 10, 3, 6, 0, 0)

    monkeypatch.setattr("ace_daemon.datetime", _Morning)
    out = _run(daemon, queue, state)
    assert out["status"] == "WAITING_FOR_DEDICATED_SHIFT"
    assert not [t for t in pool.list_tasks(limit=500) if "intent:will_one" in (t.tags or [])]


def test_scheduler_imports_under_the_daemon_module_path(rig, evening):
    """Regression: the sys.path guard was one paired check, so when the repo root
    was already importable -- always true inside ace_daemon -- ops/ was never
    added and `from inject_target import ...` raised ModuleNotFoundError. Every
    evening turn failed with status=ERROR while the unit tests passed, because
    they ran the scheduler as a script."""
    import subprocess
    import sys

    code = (
        "import sys; sys.path.insert(0, r'%s');"
        "from ops import daily_intent_scheduler as s;"
        "print('IMPORT_OK', callable(s.assess), callable(s.inject_selected))"
        % str(Path(__file__).resolve().parents[1])
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert "IMPORT_OK True True" in proc.stdout, (
        f"scheduler must import as ops.daily_intent_scheduler: {proc.stderr[-800:]}"
    )


def test_injection_never_touches_the_production_pool(rig, evening, tmp_path):
    """Regression: inject() defaulted to the real task_pool, so exercising the
    scheduler wrote intent tasks into production."""
    daemon, pool, queue, state = rig
    _write_queue(queue, [_intent()])
    out = _run(daemon, queue, state)
    assert out["status"] == "INJECTED"
    tagged = [t for t in pool.list_tasks(limit=500) if "intent:will_one" in (t.tags or [])]
    assert len(tagged) == 1, "the task must land in the pool the daemon was given"


def test_no_task_pool_means_no_injection(rig, evening):
    daemon, _pool, queue, state = rig
    _write_queue(queue, [_intent()])
    daemon.task_pool = None
    out = _run(daemon, queue, state)
    assert out["status"] == "TASK_POOL_UNAVAILABLE"