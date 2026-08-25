import copy
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.task import TaskPool
from core.task_roles import Researcher, Validator


def prepare_review_task(pool, title, priority="high", tags=None):
    task = pool.create_task(title, creator="test", priority=priority, tags=tags or [])
    task.hypothesis = "requires stronger evidence"
    task.evidence = [
        {"source": "test", "content": "first detailed evidence record " * 8},
        {"source": "test", "content": "second detailed evidence record " * 8},
    ]
    task.counter_examples = ["existing counterexample"]
    pool.update_task(task)
    claimed = pool.claim_task(task.task_id, "researcher", lease_seconds=60)
    assert claimed is not None
    assert pool.move_task(task.task_id, "review", actor="researcher", task=claimed) is not None
    return task.task_id


def requeue_for_review(pool, task_id):
    task = pool.load_task(task_id)
    task.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
    assert pool.update_task(task)
    claimed = pool.claim_task(task_id, "researcher", lease_seconds=60)
    assert claimed is not None
    assert pool.move_task(task_id, "review", actor="researcher", task=claimed) is not None


def test_same_stable_validation_tuple_blocks_on_fourth_review():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        validator = Validator(pool)
        task_id = prepare_review_task(pool, "stable non convergence")

        for _ in range(3):
            result = validator.validate_task(pool.load_task(task_id))
            stored = pool.load_task(task_id)
            assert not result["passed"]
            assert stored.status == "pending"
            assert stored.unchanged_review_count < validator.MAX_UNCHANGED_REVIEWS
            requeue_for_review(pool, task_id)

        result = validator.validate_task(pool.load_task(task_id))
        stored = pool.load_task(task_id)

        assert not result["passed"]
        assert stored.status == "blocked"
        assert stored.block_type == "manual_gate_blocked"
        assert stored.unchanged_review_count == validator.MAX_UNCHANGED_REVIEWS
        assert stored.outputs["validator_outcome_signature"]
        assert stored.outputs["objections_signature"]
        assert stored.retry_after == ""


def test_changed_validation_tuple_resets_unchanged_review_count():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        validator = Validator(pool)
        task_id = prepare_review_task(pool, "changed validation outcome")

        first = validator.validate_task(pool.load_task(task_id))
        assert not first["passed"]
        requeue_for_review(pool, task_id)
        task = pool.load_task(task_id)
        task.evidence.append({"source": "test", "content": "materially new evidence " * 8})
        task.hypothesis = ""
        task.counter_examples = []
        assert pool.update_task(task)

        second = validator.validate_task(pool.load_task(task_id))
        stored = pool.load_task(task_id)

        assert not second["passed"]
        assert stored.status == "pending"
        assert stored.unchanged_review_count == 1


def test_terminal_nonconvergent_tasks_cannot_be_claimed_after_retry_expiry():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        validator = Validator(pool)
        task_id = prepare_review_task(pool, "terminal claim guard")

        for _ in range(3):
            validator.validate_task(pool.load_task(task_id))
            requeue_for_review(pool, task_id)
        validator.validate_task(pool.load_task(task_id))

        stored = pool.load_task(task_id)
        stored.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
        assert pool.update_task(stored)
        assert pool.claim_task(task_id, "researcher") is None


def test_researcher_yields_after_two_consecutive_rework_claims():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        rework = pool.create_task("rework high", creator="test", priority="high")
        rework.rework_count = 1
        rework.consecutive_rework_claims = 2
        rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
        assert pool.update_task(rework)
        untouched_high = pool.create_task("untouched high", creator="test", priority="high")
        untouched_medium = pool.create_task("untouched medium", creator="test", priority="medium")

        claimed = researcher.pick_up_task(priority="any")

        assert claimed is not None
        assert claimed.task_id == untouched_high.task_id
        assert claimed.task_id != untouched_medium.task_id
        assert pool.load_task(rework.task_id).selection_trace[-1]["reason"] == "fairness_yield"


def test_rework_claim_preserves_lease_and_fencing_protection():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("lease rework", creator="test")
        first = pool.claim_task(task.task_id, "researcher-a", lease_seconds=1)
        assert first is not None
        stale_first = copy.deepcopy(first)
        assert pool.move_task(task.task_id, "review", actor="researcher-a", task=first) is not None
        review = pool.load_task(task.task_id)
        review.assignee = None
        review.retry_after = (datetime.now() - timedelta(seconds=1)).isoformat()
        assert pool.move_task(task.task_id, "pending", actor="validator", task=review) is not None

        second = pool.claim_task(task.task_id, "researcher-b", lease_seconds=60)

        assert second is not None
        assert second.claim_id != stale_first.claim_id
        assert second.fencing_token > stale_first.fencing_token
        stale_first.result = "stale overwrite"
        assert not pool.update_task(stale_first)
        assert pool.move_task(task.task_id, "review", actor="researcher-b", task=second) is not None


def test_medium_gets_a_bounded_yield_after_three_high_competitions():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        high_tasks = [
            pool.create_task(f"high backlog {index}", creator="test", priority="high")
            for index in range(4)
        ]
        medium = pool.create_task("starved medium", creator="test", priority="medium")

        claimed = [researcher.pick_up_task(priority="any") for _ in range(4)]

        assert all(task is not None for task in claimed)
        assert [task.task_id for task in claimed[:3]] == [task.task_id for task in high_tasks[:3]]
        assert claimed[3].task_id == medium.task_id
        assert pool.load_task(medium.task_id).starvation_age == 0


def test_critical_is_claimed_before_an_aged_medium():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        critical = pool.create_task("critical work", creator="test", priority="critical")
        pool.create_task("high backlog", creator="test", priority="high")
        medium = pool.create_task("aged medium", creator="test", priority="medium")
        medium.starvation_age = researcher.FAIRNESS_MEDIUM_AGE_LIMIT
        assert pool.update_task(medium)

        claimed = researcher.pick_up_task(priority="any")

        assert claimed is not None
        assert claimed.task_id == critical.task_id
        assert pool.load_task(medium.task_id).status == "pending"


def test_aging_yield_keeps_high_as_the_majority_across_eight_claims():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        high_tasks = [
            pool.create_task(f"high backlog {index}", creator="test", priority="high")
            for index in range(8)
        ]
        medium_tasks = [
            pool.create_task(f"medium backlog {index}", creator="test", priority="medium")
            for index in range(2)
        ]

        claimed = [researcher.pick_up_task(priority="any") for _ in range(8)]
        priorities = [task.priority for task in claimed if task is not None]

        assert priorities.count("medium") == 2
        assert priorities.count("high") == 6
        assert priorities.count("high") > priorities.count("medium")
        assert all(pool.load_task(task.task_id).starvation_age == 0 for task in medium_tasks)
        assert all(task.task_id in [claimed_task.task_id for claimed_task in claimed] for task in high_tasks[:6])


def test_active_high_does_not_create_aging_competition_for_pending_medium():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        active_high = pool.create_task("active high", creator="test", priority="high")
        medium = pool.create_task("pending medium", creator="test", priority="medium")
        assert pool.claim_task(active_high.task_id, "other-owner") is not None

        claimed = researcher.pick_up_task(priority="any")

        assert claimed is not None
        assert claimed.task_id == medium.task_id
        stored_medium = pool.load_task(medium.task_id)
        assert stored_medium.starvation_age == 0
        assert stored_medium.selection_trace == []


def test_claimable_active_high_does_not_consume_pending_high_aging_yield():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        active_high = pool.create_task("stale active high", creator="test", priority="high")
        pending_high = pool.create_task("pending high", creator="test", priority="high")
        medium = pool.create_task("aged medium", creator="test", priority="medium")
        claimed_active = pool.claim_task(active_high.task_id, "other-owner", lease_seconds=1)
        assert claimed_active is not None
        claimed_active.lease_expires_at = (datetime.now() - timedelta(seconds=1)).isoformat()
        assert pool.update_task(claimed_active)
        medium.starvation_age = researcher.FAIRNESS_MEDIUM_AGE_LIMIT
        assert pool.update_task(medium)

        claimed = researcher.pick_up_task(priority="any")

        assert claimed is not None
        assert claimed.task_id == active_high.task_id
        assert pool.load_task(medium.task_id).starvation_age == researcher.FAIRNESS_MEDIUM_AGE_LIMIT
        assert pool.load_task(medium.task_id).selection_trace == []
        assert pool.load_task(pending_high.task_id).selection_trace == []


def test_medium_claims_within_five_two_slot_cycles_under_continuous_high_backlog():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        high_tasks = [
            pool.create_task(f"high backlog {index}", creator="test", priority="high")
            for index in range(10)
        ]
        medium_tasks = [
            pool.create_task(f"medium backlog {index}", creator="test", priority="medium")
            for index in range(3)
        ]

        cycles = [
            [researcher.pick_up_task(priority="any") for _ in range(2)]
            for _ in range(5)
        ]
        claimed = [task for cycle in cycles for task in cycle if task is not None]
        priorities = [task.priority for task in claimed]

        assert all(len(cycle) == 2 for cycle in cycles)
        assert priorities.count("medium") == 2
        assert priorities.count("high") == 8
        assert priorities.count("high") > priorities.count("medium")
        assert all(pool.load_task(task.task_id).starvation_age == 0 for task in medium_tasks[:2])
        assert pool.load_task(medium_tasks[2].task_id).starvation_age == 2
        assert all(task.task_id in [claimed_task.task_id for claimed_task in claimed] for task in high_tasks[:8])


def test_aged_medium_yields_before_rework_fairness_untouched_high():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        for index in range(2):
            rework = pool.create_task(f"rework high {index}", creator="test", priority="high")
            rework.consecutive_rework_claims = researcher.FAIRNESS_REWORK_LIMIT
            rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
            assert pool.update_task(rework)
        untouched_high = [
            pool.create_task(f"untouched high {index}", creator="test", priority="high")
            for index in range(5)
        ]
        medium = pool.create_task("aged medium", creator="test", priority="medium")
        medium.starvation_age = researcher.FAIRNESS_MEDIUM_AGE_LIMIT
        assert pool.update_task(medium)

        claimed = researcher.pick_up_task(priority="any")

        assert claimed is not None
        assert claimed.task_id == medium.task_id
        assert pool.load_task(medium.task_id).starvation_age == 0
        assert pool.load_task(medium.task_id).selection_trace[-1]["reason"] == "aging_reset"
        assert pool.load_task(untouched_high[0].task_id).status == "pending"


def test_rework_yields_record_competition_before_medium_aging_yield():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        rework = pool.create_task("rework high", creator="test", priority="high")
        rework.consecutive_rework_claims = researcher.FAIRNESS_REWORK_LIMIT
        rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
        assert pool.update_task(rework)
        untouched_high = [
            pool.create_task(f"untouched high {index}", creator="test", priority="high")
            for index in range(4)
        ]
        medium = pool.create_task("starved medium", creator="test", priority="medium")

        claimed = [researcher.pick_up_task(priority="any") for _ in range(4)]
        stored_medium = pool.load_task(medium.task_id)

        assert all(task is not None for task in claimed)
        assert [task.task_id for task in claimed[:3]] == [task.task_id for task in untouched_high[:3]]
        assert claimed[3].task_id == medium.task_id
        assert [entry["reason"] for entry in stored_medium.selection_trace] == [
            "aging_competition",
            "aging_competition",
            "aging_competition",
            "aging_reset",
        ]
        assert stored_medium.starvation_age == 0


def test_aging_candidate_rotates_across_untouched_medium_backlog():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        researcher = Researcher(pool)
        high = pool.create_task("high backlog", creator="test", priority="high")
        medium_tasks = [
            pool.create_task(f"medium backlog {index}", creator="test", priority="medium")
            for index in range(3)
        ]

        first = researcher._aging_medium_candidate("any")
        assert first.task_id == medium_tasks[0].task_id
        claimed = pool.claim_task(first.task_id, "researcher")
        assert claimed is not None

        second = researcher._aging_medium_candidate("any")
        assert second is not None
        assert second.task_id == medium_tasks[1].task_id
        assert pool.load_task(high.task_id).status == "pending"


def test_graveyard_sweep_keeps_active_task_with_unexpired_lease():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("leased active task", creator="test")
        claimed = pool.claim_task(task.task_id, "researcher", lease_seconds=60)

        assert claimed is not None
        claimed.last_referenced_at = (datetime.now() - timedelta(days=31)).isoformat()
        assert pool.update_task(claimed)

        assert pool.check_graveyard() == []
        stored = pool.load_task(task.task_id)
        assert stored.status == "active"
        assert stored.lease_owner == "researcher"
        assert stored.claim_id == claimed.claim_id
        assert stored.fencing_token == claimed.fencing_token


def test_graveyard_sweep_moves_active_task_with_expired_lease():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("expired active task", creator="test")
        claimed = pool.claim_task(task.task_id, "researcher", lease_seconds=60)

        assert claimed is not None
        claimed.last_referenced_at = (datetime.now() - timedelta(days=31)).isoformat()
        claimed.lease_expires_at = (datetime.now() - timedelta(seconds=1)).isoformat()
        assert pool.update_task(claimed)

        moved = pool.check_graveyard()

        assert [task.task_id for task in moved] == [task.task_id]
        assert pool.load_task(task.task_id).status == "graveyard"


def test_graveyard_sweep_preserves_pending_review_and_rejected_behavior():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        pending = pool.create_task("stale pending", creator="test")
        review = pool.create_task("stale review", creator="test")
        rejected = pool.create_task("stale rejected", creator="test")

        claimed_review = pool.claim_task(review.task_id, "researcher", lease_seconds=60)
        assert claimed_review is not None
        assert pool.move_task(
            review.task_id,
            "review",
            actor="researcher",
            task=claimed_review,
        ) is not None
        assert pool.move_task(rejected.task_id, "rejected", actor="test") is not None
        for task in [pending, review, rejected]:
            stored = pool.load_task(task.task_id)
            stored.last_referenced_at = (datetime.now() - timedelta(days=31)).isoformat()
            assert pool.update_task(stored)

        moved = pool.check_graveyard()

        assert {task.task_id for task in moved} == {pending.task_id, review.task_id, rejected.task_id}
        assert all(pool.load_task(task.task_id).status == "graveyard" for task in [pending, review, rejected])


def test_validator_approves_evidence_qualified_task_with_advisory_objections():
    from core.task_roles import Validator

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("qualified evidence task", creator="test")
        task.status = "review"
        task.hypothesis = "the observed pattern is reproducible"
        task.evidence = [
            {"source": "a", "content": "short"},
            {"source": "b", "content": "independent evidence from source b " * 8},
            {"source": "c", "content": "independent evidence from source c " * 8},
        ]
        pool.update_task(task)
        pool.move_task(task.task_id, "review", task=task)

        first = Validator(pool).validate_task(pool.load_task(task.task_id))
        assert not first["passed"]
        assert first["advisory_objections"]
        stored = pool.load_task(task.task_id)
        stored.retry_after = ""
        stored.status = "review"
        pool.update_task(stored)
        pool.move_task(stored.task_id, "review", task=stored)

        second = Validator(pool).validate_task(pool.load_task(task.task_id))
        stored = pool.load_task(task.task_id)
        assert second["passed"]
        assert stored.status == "approved"
        assert stored.outputs["last_validator_result"]["hard_objections"] == []


def test_researcher_drops_empty_search_hits_before_persisting_evidence():
    from core.task_roles import Researcher

    class Memory:
        def search(self, keyword, limit=10):
            return [
                {"content": "", "source": "empty"},
                {
                    "summary": "substantive result for " + keyword,
                    "source": "memory",
                    "id": "memory-1",
                },
            ]

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("research evidence", creator="test")
        task.hypothesis = "a clear hypothesis"
        pool.update_task(task)
        claimed = pool.claim_task(task.task_id, "researcher")
        result = Researcher(pool, memory_index=Memory()).research_task(claimed)
        stored = pool.load_task(task.task_id)
        assert result["evidence_found"] >= 1
        assert stored.evidence
        assert all(item["content"].strip() for item in stored.evidence)


def test_researcher_does_not_promote_cycle_daily_summaries_to_research_evidence():
    from core.task_roles import Researcher

    class Memory:
        def search(self, keyword, limit=10):
            return [
                {
                    "summary": "generic daemon cycle summary",
                    "source": "ace_daemon",
                    "id": "daily-1",
                    "type": "daily_summary",
                },
                {
                    "summary": "specific independent finding for " + keyword,
                    "source": "archivist",
                    "id": "finding-1",
                    "type": "task_archive",
                },
            ]

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("research evidence", creator="test")
        task.hypothesis = "a clear hypothesis"
        pool.update_task(task)
        claimed = pool.claim_task(task.task_id, "researcher")

        Researcher(pool, memory_index=Memory()).research_task(claimed)

        stored = pool.load_task(task.task_id)
        assert any(item["source"].startswith("archivist") for item in stored.evidence)
        assert all(not item["source"].startswith("ace_daemon") for item in stored.evidence)


def test_fairness_yield_to_aging_medium_preserves_the_new_lease():
    from core.task_roles import Researcher

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        rework = pool.create_task(
            "high rework",
            creator="test",
            priority="high",
        )
        rework.outputs["last_validator_result"] = {"outcome": "rework_pending"}
        rework.consecutive_rework_claims = Researcher.FAIRNESS_REWORK_LIMIT
        pool.update_task(rework)
        medium = pool.create_task(
            "untouched medium",
            creator="test",
            priority="medium",
        )

        claimed = Researcher(pool).pick_up_task(priority="any")
        assert claimed.task_id == medium.task_id
        stored = pool.load_task(medium.task_id)
        assert stored.status == "active"
        assert stored.claim_id == claimed.claim_id
        assert stored.lease_owner == "researcher"
        assert pool.renew_lease(
            stored.task_id,
            "researcher",
            stored.claim_id,
        ) is not None


def test_evidence_qualified_medium_rework_gets_bounded_completion_service():
    from core.task_roles import Researcher

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        pool.create_task("competing high", creator="test", priority="high")
        untouched = pool.create_task(
            "untouched medium", creator="test", priority="medium"
        )
        qualified = pool.create_task(
            "qualified medium rework", creator="test", priority="medium"
        )
        qualified.hypothesis = "three independent records support this hypothesis"
        qualified.evidence = [
            {"source": "a", "content": "independent evidence a " * 5},
            {"source": "b", "content": "independent evidence b " * 5},
            {"source": "c", "content": "independent evidence c " * 5},
        ]
        qualified.outputs["last_validator_result"] = {
            "outcome": "rework_pending",
            "hard_objections": [],
        }
        pool.update_task(qualified)

        claimed = Researcher(pool).pick_up_task(priority="any")
        assert claimed.task_id == qualified.task_id
        assert pool.load_task(qualified.task_id).status == "active"
        assert pool.load_task(untouched.task_id).status == "pending"


def test_work_allocation_classifies_existing_work_without_creating_tasks():
    from core.autonomous_work_allocation import AutonomousWorkAllocation

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        local = pool.create_task("local work", creator="test")
        strategic = pool.create_task("strategic work", creator="test")
        strategic.outputs["discovery"] = {"task_type": "strategic"}
        pool.update_task(strategic)
        reasoning = pool.create_task("reasoning probe", creator="test")
        reasoning.tags = ["task_type:reasoning", "controlled_model_probe", "non_stock"]
        pool.update_task(reasoning)
        before = pool.get_stats()["total"]

        report = AutonomousWorkAllocation(pool).report({})

        assert report["outcome"] == "WORK_AVAILABLE"
        assert report["categories"]["LOCAL"]["count"] == 1
        assert report["categories"]["STRATEGIC"]["count"] == 1
        assert report["categories"]["REASONING"]["count"] == 1
        assert report["categories"]["FINANCIAL_RESEARCH"]["count"] == 0
        assert "no_synthetic_work" not in report
        assert report["allocation_mode"] == "read_only_existing_work"
        assert report["allocator_created_task_count"] == 0
        assert report["no_synthetic_work_by_allocator"] is True
        assert pool.get_stats()["total"] == before


if __name__ == "__main__":
    test_same_stable_validation_tuple_blocks_on_fourth_review()
    test_changed_validation_tuple_resets_unchanged_review_count()
    test_terminal_nonconvergent_tasks_cannot_be_claimed_after_retry_expiry()
    test_researcher_yields_after_two_consecutive_rework_claims()
    test_rework_claim_preserves_lease_and_fencing_protection()
    test_medium_gets_a_bounded_yield_after_three_high_competitions()
    print("taskpool nonconvergence checks passed")
