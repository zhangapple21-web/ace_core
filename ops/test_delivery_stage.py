"""Lifecycle-level tests for the delivery execution stage inside AceDaemon."""
import json

import pytest

from ace_daemon import AceDaemon
from core.task import TaskPool
from ops.test_support import FixtureTaskPool


def _delivery_task(pool, required_path="docs/DELIVERY_STAGE_PROBE.md"):
    # Title must vary per path: FixtureTaskPool derives its admission source_ref
    # from the title, and an identical one dedupes into the existing task.
    return pool.create_task(
        title=f"deliver {required_path}",
        hypothesis=f"a worker will write {required_path}",
        priority="high",
        tags=["external_target", "delivery:physical"],
        outputs={
            "delivery": {
                "required_path": required_path,
                "success_metric": "file_exists_nonempty",
                "domain": "document",
            }
        },
    )


class _StubDaemon(AceDaemon):
    """Only the delivery stage, without the whole runtime bootstrap."""

    def __init__(self, pool, base_dir, worker_runner=None):
        self.task_pool = pool
        self.base_dir = base_dir
        self.state = {"errors": []}
        self._delivery_runner_cache = worker_runner if worker_runner is not None else "unavailable"
        self._logged = []

    def _log_error(self, module, error, *args):
        self._logged.append((module, error))

    _task_production_policy = lambda self: {}


@pytest.fixture()
def stage(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    (tmp_path / "docs").mkdir()
    return _StubDaemon(pool, tmp_path), pool, tmp_path


def _put_in_review(pool, task):
    claimed = pool.claim_task(task.task_id, owner="researcher", lease_seconds=300)
    pool.move_task(claimed.task_id, "review", actor="researcher", claim_id=claimed.claim_id)
    return pool.load_task(task.task_id)


def test_missing_artifact_is_blocked_once_with_the_real_reason(stage):
    daemon, pool, _tmp = stage
    task = _put_in_review(pool, _delivery_task(pool))
    result = {}

    daemon._run_declared_deliveries(result)

    assert result["delivery_execution"] == {
        "review_seen": 1, "checked": 1, "delivered": 0, "not_produced": 1, "external_receipt": 0,
        "deferred": 0,
    }
    stored = pool.load_task(task.task_id)
    assert stored.status == "blocked"
    assert stored.blocked_reason == "delivery_not_produced:docs/DELIVERY_STAGE_PROBE.md"
    assert stored.outputs.get("terminal_non_convergent") is None, "must not burn the convergence ceiling"


def test_produced_artifact_is_verified_and_never_blocked(stage):
    daemon, pool, tmp = stage
    task = _put_in_review(pool, _delivery_task(pool))
    (tmp / "docs" / "DELIVERY_STAGE_PROBE.md").write_text("# done\n", encoding="utf-8")
    result = {}

    daemon._run_declared_deliveries(result)

    assert result["delivery_execution"]["delivered"] == 1
    stored = pool.load_task(task.task_id)
    assert stored.status == "review"
    verification = stored.outputs["delivery"]["verification"]
    assert verification["satisfied"] is True
    assert verification["reason"] == "delivery_satisfied"
    assert verification["content_sha256"]


def test_only_one_worker_invoking_delivery_runs_per_cycle(stage):
    """A measured `opencode run` costs ~98s, so the stage must not serialise
    several deliveries into one cycle. The rest stay in review for the next."""
    daemon, pool, _tmp = stage
    calls = []

    def worker(**kwargs):
        calls.append(kwargs["required_path"])
        return {"success": True}

    daemon._delivery_runner_cache = worker
    _put_in_review(pool, _delivery_task(pool, "docs/PROBE_A.md"))
    _put_in_review(pool, _delivery_task(pool, "docs/PROBE_B.md"))
    result = {}

    daemon._run_declared_deliveries(result)

    summary = result["delivery_execution"]
    assert calls == ["docs/PROBE_A.md"], "only one worker invocation per cycle"
    assert summary["checked"] == 1
    assert summary["deferred"] == 1


def test_without_a_worker_every_review_task_is_still_checked(stage):
    """The per-cycle budget exists to bound model time, not to starve the cheap
    pure-disk path. With no worker there is nothing to bound."""
    daemon, pool, tmp = stage
    _put_in_review(pool, _delivery_task(pool, "docs/PRESENT_A.md"))
    _put_in_review(pool, _delivery_task(pool, "docs/PRESENT_B.md"))
    (tmp / "docs" / "PRESENT_A.md").write_text("# a\n", encoding="utf-8")
    (tmp / "docs" / "PRESENT_B.md").write_text("# b\n", encoding="utf-8")
    result = {}

    daemon._run_declared_deliveries(result)

    assert result["delivery_execution"]["checked"] == 2
    assert result["delivery_execution"]["deferred"] == 0
    assert result["delivery_execution"]["delivered"] == 2


def test_a_raising_annotation_cannot_lose_the_receipt(stage):
    """Regression: add_research_note raised once in a real run and aborted the
    stage before update_task, discarding an already-verified delivery."""
    daemon, pool, tmp = stage
    task = _put_in_review(pool, _delivery_task(pool))
    (tmp / "docs" / "DELIVERY_STAGE_PROBE.md").write_text("# done\n", encoding="utf-8")

    def boom(*_args, **_kwargs):
        raise AttributeError("'TaskPool' object has no attribute 'add_research_note'")

    daemon.task_pool.__class__.add_research_note = boom
    try:
        daemon._run_declared_deliveries({})
    finally:
        del daemon.task_pool.__class__.add_research_note

    stored = pool.load_task(task.task_id)
    assert stored.outputs["delivery"]["verification"]["satisfied"] is True, "receipt must survive"
    assert any(e.get("source") == "delivery_verification" for e in stored.evidence)


def test_verified_artifact_enters_the_evidence_set_before_persisting(stage):
    """Regression: evidence written after update_task never reaches disk, so the
    validator kept seeing an unchanged signature and re-blocking a real file."""
    daemon, pool, tmp = stage
    task = _put_in_review(pool, _delivery_task(pool))
    (tmp / "docs" / "DELIVERY_STAGE_PROBE.md").write_text("# done\n", encoding="utf-8")

    daemon._run_declared_deliveries({})

    reloaded = TaskPool(str(tmp / "task_pool")).load_task(task.task_id)
    sources = [e.get("source") for e in reloaded.evidence if isinstance(e, dict)]
    assert "delivery_verification" in sources


def test_delivery_evidence_is_idempotent_but_content_sensitive(stage):
    daemon, pool, tmp = stage
    task = _put_in_review(pool, _delivery_task(pool))
    artifact = tmp / "docs" / "DELIVERY_STAGE_PROBE.md"
    artifact.write_text("# v1\n", encoding="utf-8")

    daemon._run_declared_deliveries({})
    first = TaskPool(str(tmp / "task_pool")).load_task(task.task_id).evidence
    daemon._run_declared_deliveries({})
    second = TaskPool(str(tmp / "task_pool")).load_task(task.task_id).evidence
    assert len(first) == len(second), "re-verifying an unchanged file must add nothing"

    artifact.write_text("# v2 changed\n", encoding="utf-8")
    daemon._run_declared_deliveries({})
    third = TaskPool(str(tmp / "task_pool")).load_task(task.task_id).evidence
    assert len(third) == len(second) + 1


def test_tasks_without_a_delivery_block_are_untouched(stage):
    daemon, pool, _tmp = stage
    plain = pool.create_task(title="plain research task")
    _put_in_review(pool, plain)
    result = {}

    daemon._run_declared_deliveries(result)

    assert result["delivery_execution"]["checked"] == 0
    assert pool.load_task(plain.task_id).status == "review"


def test_external_metric_stays_silent_instead_of_blocking(stage):
    daemon, pool, _tmp = stage
    task = _delivery_task(pool, required_path="docs/NEEDS_HUMAN.md")
    _put_in_review(pool, task)
    stored = pool.load_task(task.task_id)
    stored.outputs["delivery"]["success_metric"] = "user_accepted"
    pool.update_task(stored)
    result = {}

    daemon._run_declared_deliveries(result)

    assert result["delivery_execution"]["external_receipt"] == 1
    assert result["delivery_execution"]["not_produced"] == 0
    assert pool.load_task(task.task_id).status == "review"


def test_worker_that_cannot_run_fails_closed_without_touching_the_task(stage):
    """A broken worker is contained inside the executor, not reported as delivered."""
    daemon, pool, _tmp = stage
    task = _put_in_review(pool, _delivery_task(pool))

    def boom(**_kwargs):
        raise RuntimeError("worker exploded")

    daemon._delivery_runner_cache = boom
    result = {}
    daemon._run_declared_deliveries(result)

    assert result["delivery_execution"]["not_produced"] == 1
    stored = pool.load_task(task.task_id)
    assert stored.status == "blocked"
    assert stored.blocked_reason == "delivery_not_produced:docs/DELIVERY_STAGE_PROBE.md"
    assert daemon._logged == []


def test_stage_failure_is_contained_and_reported(stage):
    daemon, pool, _tmp = stage
    _put_in_review(pool, _delivery_task(pool))

    def boom(*_args, **_kwargs):
        raise RuntimeError("pool exploded")

    pool.list_tasks = boom
    result = {}

    daemon._run_declared_deliveries(result)

    assert result["delivery_execution"]["status"] == "ERROR"
    assert daemon._logged[0][0] == "delivery_execution"


def test_receipt_is_json_serialisable_for_the_task_record(stage):
    daemon, pool, tmp = stage
    task = _put_in_review(pool, _delivery_task(pool))
    (tmp / "docs" / "DELIVERY_STAGE_PROBE.md").write_text("x", encoding="utf-8")
    daemon._run_declared_deliveries({})
    stored = pool.load_task(task.task_id)
    json.dumps(stored.outputs["delivery"], ensure_ascii=False)