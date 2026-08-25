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


def test_high_priority_work_does_not_hide_an_observed_internal_candidate(tmp_path):
    observed = candidate()
    loop = loop_for(
        tmp_path,
        [task("high-work")],
        [lambda: [(observed, [{"source": "a"}, {"source": "b"}])]],
    )
    mode, selection = loop._choose_candidate(allow_external=True)

    assert mode == "internal"
    assert selection[0].title == "Evidence-backed internal learning"
    assert loop._blocking_task().task_id == "high-work"


def test_blocked_or_approved_high_priority_work_does_not_consume_execution_capacity(tmp_path):
    loop = loop_for(
        tmp_path,
        [task("external-wait", status="blocked"), task("already-approved", status="approved")],
        [],
    )

    assert loop._blocking_task() is None


def test_blocked_execution_can_use_external_discovery_for_assessment(tmp_path):
    external_calls = []
    loop = loop_for(
        tmp_path,
        [task("high-work")],
        [lambda: []],
        external_discoverer=lambda objective, tiers: external_calls.append(True) or [],
    )

    result = loop.run("2026-08-31")

    assert result["reason"] == "no_evidence_backed_internal_candidate_or_external_candidate"
    assert result["outcome"] == "NO_VALID_LEARNING_TARGET"
    assert external_calls == [True]


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

    mode, selection = loop._choose_candidate(allow_external=True)

    assert mode == "internal"
    assert selection[0].title == "Recovered internal candidate"


def test_all_pre_fix_blocked_result_shapes_are_reassessed():
    for outcome, discovery_evaluated in (
        ("NO_VALID_LEARNING_TARGET", False),
        ("LEARNING_CANDIDATE_DEFERRED", True),
    ):
        assert DailyLearningLoop._is_legacy_blocked_result({
            "outcome": outcome,
            "reason": "learning_blocked_by_priority_task",
            "discovery_evaluated": discovery_evaluated,
            "no_side_effects": True,
        })

    assert not DailyLearningLoop._is_legacy_blocked_result({
        "outcome": "observe",
        "reason": "insufficient_independent_evidence",
    })
    assert not DailyLearningLoop._is_legacy_blocked_result({
        "outcome": "LEARNING_CANDIDATE_DEFERRED",
        "reason": "learning_blocked_by_priority_task",
        "task_id": "RQ-existing",
    })


def test_pre_expanded_scan_no_candidate_result_is_reassessed_only_once():
    legacy = {
        "outcome": "NO_VALID_LEARNING_TARGET",
        "reason": "no_evidence_backed_internal_candidate_or_external_candidate",
    }
    current = {**legacy, "candidate_scan_limit": 200}

    assert DailyLearningLoop._is_legacy_blocked_result(legacy)
    assert not DailyLearningLoop._is_legacy_blocked_result(current)


def test_source_independence_excludes_unobservable_and_unverified_lineage():
    loop = DailyLearningLoop.__new__(DailyLearningLoop)
    evidence = [
        {"metadata": {"independence_group": "direct_a", "lineage_observable": True}},
        {"metadata": {"independence_group": "direct_a", "lineage_observable": True}},
        {"metadata": {"independence_group": "UNVERIFIED_AGGREGATE", "lineage_observable": False}},
        {"metadata": {"independence_group": "UNVERIFIED", "lineage_observable": True}},
    ]

    result = loop._source_independence(evidence)

    assert result["independent_count"] == 1
    assert result["independence_groups"] == ["direct_a"]
    assert result["qualifying_evidence_count"] == 2
