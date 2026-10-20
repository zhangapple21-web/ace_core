"""Regression tests for the blind re-injection path.

A consumed will must stay consumed, no matter how the state file and the live
pool disagree, and how many times the scheduler runs.
"""
import json

import pytest

import daily_intent_scheduler as s
from core.task import TaskPool
from ops.test_support import FixtureTaskPool


def _intent(intent_id="will_x", path="docs/WILL_X.md"):
    return {
        "intent_id": intent_id,
        "question": f"produce {path}",
        "why_now": "regression probe",
        "expected_result": path,
        "verification_method": "file_exists_nonempty",
        "delivery_path": path,
        "priority": "high",
        "domain": "analysis",
        "state": "candidate",
        "added_at": "2026-10-03",
        "tags": [],
    }


def _force_archive(pool, task):
    """Put a task in archived/ without the archive gate.

    move_task(active -> archived) is refused for delivery-scoped tasks without a
    verified release receipt, which is a real production gate. These tests are
    about reading terminal state, so write the archived record directly rather
    than weakening that gate.
    """
    task.status = "archived"
    pool._write_task_atomic(task, pool._task_path(task.task_id, "archived"))
    old = pool._task_path(task.task_id, "active")
    if old.exists():
        old.unlink()
    pool._update_index(task)
    return task


def _delivered_task(pool, intent_id="will_x", path="docs/WILL_X.md", suffix=""):
    task = pool.create_task(
        title=f"deliver {path} for {intent_id}{suffix}",
        hypothesis="the worker will write it",
        priority="high",
        tags=["intent:" + intent_id, "external_target", "delivery:physical"],
        outputs={"delivery": {"required_path": path, "success_metric": "file_exists_nonempty"}},
    )
    # mark it delivered and archived, exactly as the real loop would
    task.outputs.setdefault("delivery", {})["verification"] = {"satisfied": True}
    pool.update_task(task)
    pool.claim_task(task.task_id, owner="researcher", lease_seconds=300)
    return _force_archive(pool, pool.load_task(task.task_id))


def test_an_archived_delivered_intent_is_fulfilled_not_candidate(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    _delivered_task(pool)
    state = {"protocol": s.PROTOCOL, "intents": {}}
    resolved = s.derive_state(_intent(), pool, state)
    assert resolved["state"] == "fulfilled"
    assert resolved["reason"] == "task_archived"


def test_repeated_assess_never_reopens_a_consumed_intent(tmp_path):
    """Ten passes over the pool must not make a fulfilled will look eligible."""
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    _delivered_task(pool)
    state = {"protocol": s.PROTOCOL, "intents": {}}
    for _ in range(10):
        report = s.assess(pool, [_intent()], 3, state)
        decision = s.decide(report)
        assert decision["outcome"] == "NO_VALID_INTENT", decision
        s.record_observations(state, report)
        s.save_state(state, tmp_path / "state.json")
        reloaded = s.load_state(tmp_path / "state.json")
        assert reloaded["intents"]["will_x"]["state"] == "fulfilled"
        assert reloaded["intents"]["will_x"].get("task_id")


def test_a_stale_candidate_observation_cannot_demote_fulfilled(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    state = {"protocol": s.PROTOCOL, "intents": {"will_x": {"state": "fulfilled", "task_id": "RQ-1"}}}
    stale = {
        "evaluated": [
            {
                "intent_id": "will_x",
                "question": "produce docs/WILL_X.md",
                "state": "candidate",
                "state_reason": "no_task_created_yet",
                "task": None,
                "errors": None,
            }
        ]
    }
    s.record_observations(state, stale)
    assert state["intents"]["will_x"]["state"] == "fulfilled", "must not regress"
    assert state["intents"]["will_x"]["task_id"] == "RQ-1", "the only pointer must survive"
    rejected = [h for h in state["intents"]["will_x"]["history"] if h.get("rejected")]
    assert rejected, "the rejected observation must be recorded, not dropped silently"


def test_inject_selected_refuses_when_the_will_was_already_consumed(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    _delivered_task(pool)
    state = {"protocol": s.PROTOCOL, "intents": {}}
    out = s.inject_selected(_intent(), pool, state)
    assert out["outcome"] == "REFUSED_ALREADY_INJECTED"
    assert out["task"]["status"] == "archived"


def test_tag_scan_returns_the_newest_task_when_two_carry_the_intent(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    older = _delivered_task(pool, suffix=" v1")
    newer = _delivered_task(pool, suffix=" v2")
    found = s.find_intent_task(pool, "will_x")
    assert found is not None
    assert found["task_id"] in {older.task_id, newer.task_id}
    # the newest creation wins, not merely the first archived match
    assert found["task_id"] == newer.task_id


def test_recorded_task_id_wins_over_the_tag_scan(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    task = _delivered_task(pool)
    state = {"protocol": s.PROTOCOL, "intents": {"will_x": {"task_id": task.task_id}}}
    located = s.locate_intent_task(pool, "will_x", state)
    assert located["task_id"] == task.task_id
    assert located["delivery_verified"] is True


def test_task_id_order_is_numeric_not_lexicographic():
    """RQ-...-09 must sort below RQ-...-10, not above it as a string would."""
    assert s._task_id_order("RQ-20261003-09") < s._task_id_order("RQ-20261003-10")
    assert sorted(
        ["RQ-20261003-10", "RQ-20261003-09", "RQ-20261003-100"],
        key=s._task_id_order,
    ) == ["RQ-20261003-09", "RQ-20261003-10", "RQ-20261003-100"]


def test_archived_without_the_artifact_stays_open(tmp_path):
    """An archived task whose artifact is missing must not count as fulfilled."""
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    task = pool.create_task(
        title="deliver docs/GHOST.md for will_ghost",
        hypothesis="will write it",
        priority="high",
        tags=["intent:will_ghost", "external_target"],
        outputs={"delivery": {"required_path": "docs/GHOST.md", "success_metric": "file_exists_nonempty"}},
    )
    task.outputs["delivery"]["verification"] = {"satisfied": False}
    pool.update_task(task)
    pool.claim_task(task.task_id, owner="researcher", lease_seconds=300)
    _force_archive(pool, pool.load_task(task.task_id))
    resolved = s.derive_state(
        {
            "intent_id": "will_ghost",
            "question": "q",
            "verification_method": "file_exists_nonempty",
            "delivery_path": "docs/GHOST.md",
            "state": "candidate",
        },
        pool,
        {"protocol": s.PROTOCOL, "intents": {}},
    )
    assert resolved["state"] == "blocked"
    assert resolved["reason"] == "archived_without_delivery"