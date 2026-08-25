from pathlib import Path
from types import SimpleNamespace

from core.daily_learning import DailyLearningLoop


class FakeTaskPool:
    def __init__(self, tasks):
        self.tasks = list(tasks)

    def list_tasks(self, status=None, priority=None, limit=100):
        matches = [
            task for task in self.tasks
            if (status is None or task.status == status)
            and (priority is None or task.priority == priority)
        ]
        return matches[:limit]


def loop_for(tmp_path: Path, tasks, internal_sources, external_discoverer=None):
    loop = DailyLearningLoop.__new__(DailyLearningLoop)
    loop.data_dir = tmp_path
    loop.results_dir = tmp_path / "daily_results"
    loop.results_dir.mkdir(parents=True)
    loop.task_pool = FakeTaskPool(tasks)
    loop.internal_candidate_sources = internal_sources
    loop.external_discoverer = external_discoverer
    return loop


def task(task_id, status="pending", priority="high", source_type="system_observation"):
    return SimpleNamespace(
        task_id=task_id,
        status=status,
        priority=priority,
        outputs={"admission": {"source_type": source_type}},
    )


def candidate(title="Evidence-backed internal learning"):
    return SimpleNamespace(title=title, fingerprint="learning-candidate")


def test_high_priority_work_defers_an_observed_internal_candidate_without_creating_task(tmp_path):
    observed = candidate()
    loop = loop_for(
        tmp_path,
        [task("high-work")],
        [lambda: [(observed, [{"source": "a"}, {"source": "b"}])]],
    )
    loop._create_task = lambda *args, **kwargs: (_ for _ in ()).throw(
        AssertionError("deferred candidate must not create a task")
    )

    result = loop.run("2026-08-30")

    assert result == {
        "date": "2026-08-30",
        "mode": "internal",
        "outcome": "LEARNING_CANDIDATE_DEFERRED",
        "reason": "learning_blocked_by_priority_task",
        "blocking_task_id": "high-work",
        "candidate": "Evidence-backed internal learning",
        "candidate_fingerprint": "learning-candidate",
        "discovery_evaluated": True,
        "no_side_effects": True,
    }


def test_blocked_or_approved_high_priority_work_does_not_consume_execution_capacity(tmp_path):
    loop = loop_for(
        tmp_path,
        [task("external-wait", status="blocked"), task("already-approved", status="approved")],
        [],
    )

    assert loop._blocking_task() is None


def test_blocked_execution_does_not_call_external_discovery(tmp_path):
    external_calls = []
    loop = loop_for(
        tmp_path,
        [task("high-work")],
        [lambda: []],
        external_discoverer=lambda objective, tiers: external_calls.append(True) or [],
    )

    result = loop.run("2026-08-31")

    assert result["reason"] == "learning_blocked_by_priority_task"
    assert result["outcome"] == "NO_VALID_LEARNING_TARGET"
    assert external_calls == []


def test_legacy_blocked_result_is_reassessed_once_with_candidate_visibility(tmp_path):
    observed = candidate("Recovered internal candidate")
    loop = loop_for(
        tmp_path,
        [task("high-work")],
        [lambda: [(observed, [{"source": "a"}, {"source": "b"}])]],
    )
    legacy = {
        "date": "2026-08-25",
        "mode": "none",
        "outcome": "NO_VALID_LEARNING_TARGET",
        "reason": "learning_blocked_by_priority_task",
        "blocking_task_id": "old-blocker",
        "no_side_effects": True,
    }
    loop._record_daily_result("2026-08-25", legacy)

    result = loop.run("2026-08-25")

    assert result["outcome"] == "LEARNING_CANDIDATE_DEFERRED"
    assert result["candidate"] == "Recovered internal candidate"
    assert loop.run("2026-08-25") == result
