import json

from core.reality_gap_relay import RealityGapRelay
from core.free_zone_autonomy import FreeZoneAutonomy
from core.free_zone_reality_bridge import FreeZoneRealityBridge
from core.free_zone_reflection_relay import FreeZoneReflectionRelay
from core.free_zone_loop_status import FreeZoneLoopStatus


def _write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def _runtime(root, *, serviced=False):
    runtime = root / "06_RUNTIME" / "ace" / "data"
    _write(runtime / "hourly_task_service_latest.json", {
        "hour": "2026-08-31T12:00Z",
        "pending_observed": 0 if serviced else 2,
        "service_status": "NO_PENDING_WORK" if serviced else "ELIGIBLE_WORK_NOT_SERVICED",
        "execution_evidence": {"status": "DAEMON_CONTEXT_BOUND"},
    })
    _write(runtime / "memory" / "daemon_state.json", {"run_id": "run-one", "cycles": 3})


def test_relay_releases_only_an_attributed_unserviced_backlog(tmp_path):
    _runtime(tmp_path)
    result = RealityGapRelay(tmp_path).scan_and_release()
    assert result["status"] == "RELEASED_TO_FREE_ZONE"
    assert result["task_created"] is False
    assert result["receipt"]["disposition"]["production_runtime_mutation"] is False


def test_relay_is_quiet_without_a_real_runtime_gap(tmp_path):
    _runtime(tmp_path, serviced=True)
    result = RealityGapRelay(tmp_path).scan_and_release()
    assert result["status"] == "NO_ELIGIBLE_REALITY_GAP"
    assert not (tmp_path / "08_GOVERNANCE" / "free_zone_exchange").exists()


def test_qualified_gap_can_make_the_full_nonproduction_round_trip(tmp_path):
    _runtime(tmp_path)
    released = RealityGapRelay(tmp_path).scan_and_release()["receipt"]
    root = tmp_path / "07_SANDBOX" / "free_research"
    autonomy = FreeZoneAutonomy(root, git_observer=lambda: {"status": "NO_SAFE_GIT_FOOD"})
    candidate = autonomy._inbox_candidates({})[0]
    execution = autonomy._execute(candidate, {})
    assert execution["outcome"] == "INCONCLUSIVE"
    record = autonomy.sandbox.record_experiment(
        experiment_id="EXP-FULL-ROUND-TRIP",
        hypothesis=candidate["hypothesis"],
        method=candidate["method"],
        outcome=execution["outcome"],
        evidence=execution["evidence"],
        metadata={"source_kind": candidate["source_kind"], "ace_reality_gap_origin": candidate["payload"]["origin"]},
    )
    autonomy.sandbox.distill(record["experiment_id"])
    source = root / "distillations" / "EXP-FULL-ROUND-TRIP.json"
    reflection = FreeZoneReflectionRelay(tmp_path, sandbox_root=root).reflect_available()
    assert reflection["status"] == "REFLECTIONS_RECORDED"
    assert reflection["reflected_count"] == 1
    assert reflection["reflections"][0]["origin_exchange_id"] == released["exchange_id"]
    assert reflection["reflections"][0]["status"] == "MAPPED_SHADOW"
    assert reflection["task_created"] is False
    assert reflection["production_runtime_mutation"] is False
    status = FreeZoneLoopStatus(tmp_path).build(relay_result={"status": "RELEASED_TO_FREE_ZONE"})
    assert status["counts"] == {"released": 1, "consumed": 1, "distilled": 1, "reflected": 1}
    assert status["exchanges"][0]["state"] == "REFLECTED"


def test_status_never_counts_an_unlinked_historical_bridge_as_a_closed_loop(tmp_path):
    bridge = tmp_path / "08_GOVERNANCE" / "free_zone_bridge" / "receipts" / "BRIDGE-OLD.json"
    _write(bridge, {"bridge_id": "BRIDGE-OLD", "source": {}, "disposition": {"status": "ACCEPTED_REALITY_RESEARCH"}})
    status = FreeZoneLoopStatus(tmp_path).build(relay_result={"status": "NO_ELIGIBLE_REALITY_GAP", "reason": "no_signal"})
    assert status["counts"] == {"released": 0, "consumed": 0, "distilled": 0, "reflected": 0}
    assert status["runtime_signal"]["eligibility_reason"] == "no_signal"


def test_four_round_replay_is_idempotent_and_exposes_each_real_breakpoint(tmp_path):
    # Round 1: no verified ACE gap means no release and an empty loop.
    _runtime(tmp_path, serviced=True)
    relay = RealityGapRelay(tmp_path)
    assert relay.scan_and_release()["status"] == "NO_ELIGIBLE_REALITY_GAP"
    assert FreeZoneLoopStatus(tmp_path).build()["counts"] == {
        "released": 0, "consumed": 0, "distilled": 0, "reflected": 0
    }

    # Round 2: the same real gap can be released twice without duplicate food.
    _runtime(tmp_path, serviced=False)
    first = relay.scan_and_release()["receipt"]
    second = relay.scan_and_release()["receipt"]
    assert first["exchange_id"] == second["exchange_id"]
    inbox = tmp_path / "07_SANDBOX" / "free_research" / "inbox"
    assert len(list(inbox.glob("EXCHANGE-*.json"))) == 1

    # Round 3: a linked experiment/distillation is counted as consumed but not
    # reflected until the reflection relay actually records the shadow receipt.
    root = tmp_path / "07_SANDBOX" / "free_research"
    autonomy = FreeZoneAutonomy(root, git_observer=lambda: {"status": "NO_SAFE_GIT_FOOD"})
    candidate = autonomy._inbox_candidates({})[0]
    execution = autonomy._execute(candidate, {})
    record = autonomy.sandbox.record_experiment(
        experiment_id="EXP-FOUR-ROUND",
        hypothesis=candidate["hypothesis"], method=candidate["method"], outcome=execution["outcome"],
        evidence=execution["evidence"],
        metadata={"source_kind": candidate["source_kind"], "ace_reality_gap_origin": candidate["payload"]["origin"]},
    )
    autonomy.sandbox.distill(record["experiment_id"])
    before_reflection = FreeZoneLoopStatus(tmp_path).build()
    assert before_reflection["counts"] == {"released": 1, "consumed": 1, "distilled": 1, "reflected": 0}

    # Round 4: a broken historical origin cannot block the valid reflection,
    # and a second reflection pass remains idempotent.
    _write(root / "distillations" / "EXP-BROKEN.json", {
        "experiment_id": "EXP-BROKEN", "origin": {"exchange_id": "EXCHANGE-MISSING", "receipt_sha256": "x"}
    })
    reflector = FreeZoneReflectionRelay(tmp_path, sandbox_root=root)
    first_reflection = reflector.reflect_available()
    second_reflection = reflector.reflect_available()
    assert first_reflection["reflected_count"] == 1
    assert first_reflection["skipped_count"] >= 1
    assert second_reflection["reflected_count"] == 1
    final = FreeZoneLoopStatus(tmp_path).build()
    assert final["counts"] == {"released": 1, "consumed": 1, "distilled": 1, "reflected": 1}
    assert final["exchanges"][0]["state"] == "REFLECTED"


def _bridge_mapping(root):
    evidence = root / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "bridge-a.md").write_text("a\n", encoding="utf-8")
    (evidence / "bridge-b.md").write_text("b\n", encoding="utf-8")
    return {
        "mapping_id": "ROUND-TRIP-ONE",
        "epistemic_status": "INFERENCE",
        "observation": "A Free Zone result retains its ACE-origin gap identity.",
        "learning": "A result can reflect back only through an independent ACE review.",
        "reality_scope": "ACE task lifecycle",
        "research_question": "Does the bridge preserve both directions of lineage?",
        "expected_result": "A research receipt includes the original ACE gap and no production authority.",
        "verification_method": "Verify source, origin, evidence, and receipt hashes.",
        "constraints": ["no task creation", "no production mutation"],
        "evidence_refs": [
            {"ref": "evidence/bridge-a.md", "independence_group": "a", "kind": "audit"},
            {"ref": "evidence/bridge-b.md", "independence_group": "b", "kind": "runtime"},
        ],
        "ace_review": {"decision": "ACCEPT_FOR_RESEARCH", "reviewer": "main_steward", "review_basis": ["lineage", "evidence"]},
    }


