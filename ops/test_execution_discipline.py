import json

from core.execution_discipline import (
    PROTOCOL_VERSION,
    START_PROTOCOL_VERSION,
    add_evidence_ledger_entry,
    build_execution_discipline,
    classify_complexity,
    evaluate_route,
    execution_gate,
    record_checkpoint,
    record_event,
    ensure_execution_discipline,
    protocol_receipt,
    validate_execution_discipline,
)
from core.task import Task
from ops.test_support import FixtureTaskPool as TaskPool
from core.ace_start import ace_start


def test_complexity_classifier_keeps_simple_work_light():
    assert classify_complexity("读取当前计数", "", "low", []) == ("simple", "default_light_branch")
    assert classify_complexity("重构跨系统架构", "", "medium", []) == ("complex", "title_or_hypothesis")
    assert classify_complexity("普通研究", "", "medium", ["research"]) == ("medium", "bounded_heuristic")
    assert classify_complexity("anything", explicit="complex") == ("complex", "explicit")


def test_structured_envelope_preserves_unknowns_and_forbids_unsupported_mechanisms():
    envelope = build_execution_discipline(
        title="架构集成审计",
        hypothesis="验证现有边界",
        priority="high",
        tags=["integration"],
        admission={
            "evidence": [{"source": "fixture", "content": "known"}],
            "expected_result": "a bounded report",
            "verification_method": "re-read the source",
            "risk": "may be stale",
        },
    )
    assert envelope["protocol"] == PROTOCOL_VERSION
    assert envelope["complexity"] == "complex"
    assert envelope["minimal_plan"]["status"] == "required"
    assert envelope["constraints"]["parallelism"].startswith("refuse_by_default")
    assert envelope["verification"]["independent_reviewer"] == "not_proven_by_pilot"
    assert envelope["clarification"]["unknowns"]
    assert envelope["stop"]["required"] is True
    assert envelope["start_protocol"] == START_PROTOCOL_VERSION
    assert list(envelope["pipeline"]) == [
        "observe", "clarify", "plan", "route", "execute", "verify", "review", "stop"
    ]
    assert envelope["constraints"]["parallelism_decision"] == "serial_existing_lifecycle"


def test_task_pool_persists_protocol_and_lifecycle_events(tmp_path):
    pool = TaskPool(str(tmp_path / "tasks"))
    task = pool.create_task(
        "架构集成任务",
        hypothesis="保留边界",
        creator="test",
        tags=["complexity:complex"],
    )
    saved = pool.load_task(task.task_id)
    assert saved.outputs["execution_discipline"]["complexity"] == "complex"
    assert saved.outputs["execution_discipline"]["last_event"] == "prepared"

    moved = pool.move_task(task.task_id, "blocked", actor="test", reason="evidence_gap")
    assert moved is not None
    saved = pool.load_task(task.task_id)
    events = saved.outputs["execution_discipline"]["events"]
    assert any(event["event"] == "lifecycle_transition" for event in events)
    assert saved.outputs["execution_discipline"]["status"] == "stopped"
    assert saved.outputs["execution_discipline"]["stop"]["reason"] == "evidence_gap"


def test_legacy_task_backfill_is_deterministic():
    task = Task(task_id="RQ-legacy", title="读取状态", outputs={})
    envelope = ensure_execution_discipline(task)
    assert envelope["protocol"] == PROTOCOL_VERSION
    assert envelope["source"] == "legacy_task_backfill"
    json.dumps(task.to_dict(), ensure_ascii=False)


def test_execution_gate_rejects_malformed_structured_envelope():
    task = Task(
        task_id="RQ-malformed",
        title="complex task",
        outputs={
            "execution_discipline": {
                "protocol": PROTOCOL_VERSION,
                "complexity": "complex",
                "clarification": {},
                "minimal_plan": {"steps": []},
                "verification": {},
            }
        },
    )
    ready, reason = execution_gate(task)
    assert ready is False
    assert reason == "execution_discipline_missing_goal"


def test_route_refuses_shared_or_unproven_parallelism():
    route = evaluate_route(
        complexity="complex",
        depends_on=["RQ-parent"],
        shared_state=True,
        explicitly_independent=True,
    )
    assert route["decision"] == "serial_existing_lifecycle"
    assert route["parallelism"] == "refused"
    assert route["worker_runtime"] == "not_started"


def test_checkpoint_and_evidence_ledger_are_bounded_and_persisted():
    task = Task(task_id="RQ-ledger", title="structured task", outputs={})
    ensure_execution_discipline(task)
    record_checkpoint(task, "preflight", actor="test", evidence=["manifest"])
    add_evidence_ledger_entry(task, "runtime", {"status": "observed"})
    assert task.outputs["execution_discipline"]["checkpoints"][0]["name"] == "preflight"
    assert task.outputs["execution_discipline"]["evidence_ledger"]["runtime"] == [{"status": "observed"}]


def test_protocol_audit_and_receipt_are_deterministic_for_prepared_task():
    task = Task(task_id="RQ-receipt", title="架构集成任务", hypothesis="保留边界", outputs={})
    ensure_execution_discipline(task)
    audit = validate_execution_discipline(task)
    receipt = protocol_receipt(task)
    assert audit["valid"] is True
    assert audit["status"] == "prepared"
    assert receipt["receipt_version"] == "ACE-START-PROTOCOL-RECEIPT-1.0"
    assert receipt["task_id"] == "RQ-receipt"
    assert receipt["unknown_count"] >= 1


def test_protocol_audit_catches_stage_regression_and_missing_stop_reason():
    task = Task(task_id="RQ-regression", title="架构集成任务", outputs={})
    ensure_execution_discipline(task)
    record_event(task, "started", actor="test")
    record_event(task, "planned", actor="test")
    task.outputs["execution_discipline"]["status"] = "stopped"
    task.outputs["execution_discipline"]["stop"]["reason"] = ""
    audit = validate_execution_discipline(task)
    assert audit["valid"] is False
    assert "stage_regression:plan" in audit["errors"]
    assert "stopped_without_reason" in audit["errors"]


def test_start_entrypoint_is_fail_closed_for_missing_envelope(tmp_path):
    pool = TaskPool(str(tmp_path / "tasks"))
    task = pool.create_task("legacy start", creator="test")
    task_path = tmp_path / "tasks" / "pending" / f"{task.task_id}.json"
    payload = json.loads(task_path.read_text(encoding="utf-8"))
    payload["outputs"].pop("execution_discipline", None)
    task_path.write_text(json.dumps(payload), encoding="utf-8")
    result = ace_start(pool, task.task_id, "window-a")
    assert result["status"] == "REJECTED"
    assert result["reason"] == "execution_discipline_missing_envelope"
    assert pool.load_task(task.task_id).status == "pending"


def test_start_entrypoint_issues_owner_claim_and_fencing(tmp_path):
    pool = TaskPool(str(tmp_path / "tasks"))
    task = pool.create_task("startable", creator="test")
    result = ace_start(pool, task.task_id, "window-a", lease_seconds=60)
    assert result["status"] == "STARTED"
    assert result["owner"] == "window-a"
    stored = pool.load_task(task.task_id)
    assert stored.status == "active"
    assert stored.claim_id == result["claim_id"]
    assert stored.fencing_token == result["fencing_token"]



