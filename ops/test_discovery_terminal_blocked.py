# Regression: terminally blocked tasks must not suppress discovery.
#
# _has_viable_work used to treat any blocked task as viable work, so 25
# terminal dead-ends (all waiting on external evidence that may never come)
# kept DiscoveryMode switched off indefinitely. A fresh blocked task without
# the terminal flag still suppresses, which the pre-existing contract in
# test_discovery_mode.py pins and this suite does not touch.
from core.discovery import DiscoveryMode
from core.observation import RuntimeObserver
from core.task import TaskPool


def _discovery(pool, tmp_path):
    observer = RuntimeObserver(data_dir=str(tmp_path / "obs"))
    return DiscoveryMode(
        task_pool=pool,
        observer=observer,
        base_dir=str(tmp_path),
        candidate_sources=[lambda: []],
    )


def _admission():
    return {
        "source_type": "maintenance",
        "source_ref": "ops/test_discovery_terminal_blocked.py",
        "why_now": "regression fixture",
        "evidence": ["terminal blocked tasks must not suppress discovery"],
        "expected_result": "discovery proceeds past terminal dead ends",
        "verification_method": "pytest",
        "risk": "low: test fixture",
        "estimated_scope": "single-test",
    }


def test_terminal_blocked_does_not_suppress_discovery(tmp_path):
    pool = TaskPool(str(tmp_path / "pool"))
    task = pool.create_task(title="dead end", hypothesis="h", admission=_admission())
    pool.block_task(task.task_id, "waiting on evidence that never comes", actor="test")
    stored = pool.load_task(task.task_id)
    stored.outputs["terminal_non_convergent"] = True
    assert pool.update_task(stored)

    assert DiscoveryMode  # contract import guard
    discovery = _discovery(pool, tmp_path)
    assert discovery._has_viable_work() is False


def test_fresh_blocked_still_suppresses_discovery(tmp_path):
    pool = TaskPool(str(tmp_path / "pool"))
    task = pool.create_task(title="live wait", hypothesis="h", admission=_admission())
    pool.block_task(task.task_id, "waiting on a human", actor="test")

    discovery = _discovery(pool, tmp_path)
    assert discovery._has_viable_work() is True