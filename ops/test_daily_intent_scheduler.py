"""The intent pool is a granary, not a feeder: it must be able to do nothing."""
import json

import daily_intent_scheduler as sched
from ops.test_support import FixtureTaskPool


def _intent(intent_id="will_a", **overrides):
    payload = {
        "intent_id": intent_id,
        "question": "produce the missing mapping",
        "why_now": "the diagnosis showed a gap nobody closed",
        "expected_result": "docs/WILL_A.md",
        "verification_method": "file_exists_nonempty",
        "delivery_path": "docs/WILL_A.md",
        "priority": "high",
        "domain": "document",
        "state": "candidate",
        "added_at": "2026-10-03",
    }
    payload.update(overrides)
    return payload


def _pool(tmp_path):
    return FixtureTaskPool(str(tmp_path / "task_pool"))


def _archive(pool, task_id):
    """Walk the real lifecycle; pending cannot jump straight to archived."""
    claimed = pool.claim_task(task_id, owner="researcher", lease_seconds=300)
    pool.move_task(claimed.task_id, "review", actor="researcher", claim_id=claimed.claim_id)
    pool.move_task(task_id, "approved", actor="validator")
    pool.move_task(task_id, "archived", actor="archivist")
    assert pool.load_task(task_id).status == "archived"


# --- validation -----------------------------------------------------------


def test_minimal_required_fields_are_enforced(tmp_path):
    assert sched.validate_intent(_intent()) == []
    assert "question_required" in sched.validate_intent({})
    assert "why_now_required" in sched.validate_intent(_intent(why_now=""))


def test_deliverable_metric_without_a_path_is_rejected():
    errors = sched.validate_intent(_intent(delivery_path=""))
    assert "delivery_path_required_for_deliverable_verification" in errors


def test_unknown_metric_and_unknown_state_are_rejected():
    assert "verification_method_not_deliverable" in sched.validate_intent(
        _intent(verification_method="vibes")
    )
    assert "state_unknown" in sched.validate_intent(_intent(state="whatever"))


def test_queue_survives_blank_lines_and_bad_json(tmp_path):
    path = tmp_path / "q.jsonl"
    path.write_text(
        json.dumps(_intent("a"), ensure_ascii=False) + "\n\n// comment\nnot json\n",
        encoding="utf-8",
    )
    loaded = sched.load_queue(path)
    assert [item["intent_id"] for item in loaded] == ["a"]


def test_missing_queue_file_is_an_empty_queue_not_a_crash(tmp_path):
    assert sched.load_queue(tmp_path / "absent.jsonl") == []


# --- capacity gate: the granary may stay shut -----------------------------


def test_full_external_backlog_yields_healthy_idle(tmp_path):
    pool = _pool(tmp_path)
    pool.create_task(
        title="external work already running",
        priority="high",
        outputs={"delivery": {"required_path": "docs/OTHER.md", "success_metric": "file_exists_nonempty"}},
    )
    report = sched.assess(pool, [_intent()], capacity=0, state={})

    decision = sched.decide(report)
    assert decision["outcome"] == "HEALTHY_IDLE"
    assert decision["reason"] == "external_backlog_at_capacity"


def test_internal_noise_does_not_consume_external_capacity(tmp_path):
    """Self-observation tasks occupy pending but can never deliver anything."""
    pool = _pool(tmp_path)
    for index in range(5):
        pool.create_task(title=f"self observation {index}", priority="high", tags=["from_obs"])

    report = sched.assess(pool, [_intent()], capacity=3, state={})

    assert report["pool"]["in_flight"] == 5
    assert report["pool"]["external_in_flight"] == 0
    assert sched.decide(report)["outcome"] == "INJECT"


def test_no_candidate_intent_returns_no_valid_intent(tmp_path):
    pool = _pool(tmp_path)
    report = sched.assess(pool, [_intent(state="fulfilled")], capacity=3, state={})

    decision = sched.decide(report)
    assert decision["outcome"] == "NO_VALID_INTENT"
    assert decision["reason"] == "no_intent_in_candidate_state"


def test_empty_queue_returns_no_valid_intent(tmp_path):
    decision = sched.decide(sched.assess(_pool(tmp_path), [], capacity=3, state={}))
    assert decision["outcome"] == "NO_VALID_INTENT"


# --- lifecycle ------------------------------------------------------------


def test_an_archived_delivery_task_retires_the_intent(tmp_path):
    pool = _pool(tmp_path)
    created = pool.create_task(
        title=_intent()["question"],
        priority="high",
        tags=[sched.intent_tag("will_a"), "external_target"],
        outputs={"delivery": {"required_path": "docs/WILL_A.md", "success_metric": "file_exists_nonempty"}},
    )
    stored = pool.load_task(created.task_id)
    stored.outputs["delivery"]["verification"] = {"satisfied": True, "reason": "delivery_satisfied"}
    pool.update_task(stored)
    _archive(pool, created.task_id)

    report = sched.assess(pool, [_intent()], capacity=3, state={})
    record = report["evaluated"][0]

    assert record["state"] == "fulfilled"
    assert record["state_reason"] == "task_archived"
    assert record["eligible"] is False
    assert sched.decide(report)["outcome"] == "NO_VALID_INTENT"


def test_archived_without_the_artifact_does_not_count_as_fulfilled(tmp_path):
    pool = _pool(tmp_path)
    created = pool.create_task(
        title=_intent()["question"],
        priority="high",
        tags=[sched.intent_tag("will_a")],
        outputs={"delivery": {"required_path": "docs/WILL_A.md", "success_metric": "file_exists_nonempty"}},
    )
    stored = pool.load_task(created.task_id)
    stored.outputs["delivery"]["verification"] = {"satisfied": False, "reason": "delivery_file_missing"}
    pool.update_task(stored)
    _archive(pool, created.task_id)

    record = sched.assess(pool, [_intent()], capacity=3, state={})["evaluated"][0]
    assert record["state"] == "blocked"
    assert record["state_reason"] == "archived_without_delivery"


def test_a_blocked_intent_is_never_silently_reinjected(tmp_path):
    pool = _pool(tmp_path)
    created = pool.create_task(
        title=_intent()["question"],
        priority="high",
        tags=[sched.intent_tag("will_a")],
        outputs={"delivery": {"required_path": "docs/WILL_A.md", "success_metric": "file_exists_nonempty"}},
    )
    pool.block_task(created.task_id, "delivery_not_produced:docs/WILL_A.md", actor="delivery_executor",
                    block_type="external_condition_blocked")

    report = sched.assess(pool, [_intent()], capacity=3, state={})
    assert report["evaluated"][0]["state"] == "blocked"
    assert sched.decide(report)["outcome"] == "NO_VALID_INTENT"


def test_state_file_task_id_wins_over_a_tag_scan(tmp_path):
    pool = _pool(tmp_path)
    created = pool.create_task(title="no tag at all", priority="high")
    state = {"intents": {"will_a": {"task_id": created.task_id}}}

    found = sched.locate_intent_task(pool, "will_a", state)
    assert found["task_id"] == created.task_id


def test_history_accumulates_only_on_change(tmp_path):
    pool = _pool(tmp_path)
    state = {"intents": {}}
    report = {"evaluated": [{"intent_id": "will_a", "question": "q", "state": "candidate",
                             "state_reason": "no_task_created_yet", "task": None, "eligible": True}]}

    sched.record_observations(state, report)
    sched.record_observations(state, report)

    assert [entry["state"] for entry in state["intents"]["will_a"]["history"]] == ["candidate"]


# --- ranking --------------------------------------------------------------


def test_priority_then_age_decides_which_will_runs_today():
    ranked = sched.rank_candidates([
        {"intent": _intent("low_one", priority="low")},
        {"intent": _intent("high_late", priority="high", added_at="2026-10-03")},
        {"intent": _intent("high_early", priority="high", added_at="2026-09-01")},
        {"intent": _intent("medium_one", priority="medium")},
    ])
    assert [item["intent"]["intent_id"] for item in ranked] == [
        "high_early", "high_late", "medium_one", "low_one",
    ]


def test_injection_refuses_when_a_task_already_carries_the_intent(tmp_path, monkeypatch):
    """Even a caller that bypasses assess() cannot create a twin task."""
    pool = _pool(tmp_path)
    existing = pool.create_task(title="already here", priority="high",
                                tags=[sched.intent_tag("will_a")])

    called = []
    monkeypatch.setattr(sched, "inject", lambda target: called.append(target) or {"task_id": "X"})

    result = sched.inject_selected(_intent(), pool, {})

    assert result["outcome"] == "REFUSED_ALREADY_INJECTED"
    assert result["task"]["task_id"] == existing.task_id
    assert called == []


def test_target_payload_carries_the_intent_tag_and_contract():
    target = sched.build_target(_intent())
    assert sched.intent_tag("will_a") in target["tags"]
    assert target["protocol"] == "ace.target.inject.v1"
    assert target["expected_output"] == "docs/WILL_A.md"
    assert target["success_metric"] == "file_exists_nonempty"
    assert sched.validate_target(target) == []


def test_state_file_round_trips_and_survives_corruption(tmp_path):
    path = tmp_path / "state.json"
    path.write_text("{not json", encoding="utf-8")
    assert sched.load_state(path) == {"protocol": sched.PROTOCOL, "intents": {}}

    sched.save_state({"protocol": sched.PROTOCOL, "intents": {"a": {"state": "injected"}}}, path)
    assert sched.load_state(path)["intents"]["a"]["state"] == "injected"