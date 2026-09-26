from core.delivery_protocols import ensure_task_protocols, protocol_errors
from core.execution_contract import build_execution_system_prompt
from core.mirror_constitution import (
    CONTRACT_VERSION,
    RESPONSIBILITY_PROTOCOL,
    build_intent_envelope,
    build_responsibility_packet,
    validate_data_boundary,
    validate_intent_envelope,
    validate_responsibility_packet,
)
from core.task import Task
from core.task import TaskPool
from core.task_roles import Guardian
from tempfile import TemporaryDirectory


def _task():
    return Task(
        "RQ-mirror-001",
        "镜子宪法测试",
        hypothesis="验证责任包能投影既有生命周期",
        evidence=[{"source": "test:evidence", "content": "可复核证据"}],
        outputs={},
    )


def test_intent_envelope_is_candidate_only_and_cannot_grant_authority():
    envelope = build_intent_envelope(
        intent_kind="REQUEST",
        claim="补齐责任收口",
        source_refs=["user:2026-09-26"],
    )
    assert validate_intent_envelope(envelope)["valid"] is True
    envelope["authority"]["execution_authorized"] = True
    assert "intent_authority_execution_authorized_must_be_false" in validate_intent_envelope(envelope)["errors"]


def test_data_boundary_requires_sanitization_and_blocks_sensitive_egress():
    assert validate_data_boundary({"data_class": "PRIVATE"}, target="EXTERNAL")["valid"] is False
    assert validate_data_boundary({"data_class": "STRUCTURE"}, target="MODEL_CONTEXT")["valid"] is False
    assert validate_data_boundary(
        {"data_class": "STRUCTURE", "sanitized": True}, target="MODEL_CONTEXT"
    )["valid"] is True
    assert validate_data_boundary(
        {"data_class": "STRUCTURE", "sanitized": True}, target="PUBLIC"
    )["valid"] is True
    assert validate_data_boundary({"data_class": "UNKNOWN"}, target="INTERNAL")["valid"] is False


def test_responsibility_packet_projects_existing_task_without_execution_authority():
    packet = build_responsibility_packet(_task())
    assert packet["protocol"] == RESPONSIBILITY_PROTOCOL
    assert packet["contract_version"] == CONTRACT_VERSION
    assert packet["evidence_refs"] == ["test:evidence"]
    assert packet["authority"]["execution_authorized"] is False
    assert validate_responsibility_packet(packet, task_id="RQ-mirror-001")["valid"] is True
    assert validate_responsibility_packet(packet, task_id="RQ-mirror-001")["status"] == "COMPLETE_WITH_WARNINGS"
    assert validate_responsibility_packet(packet, task_id="RQ-mirror-001", strict=True)["valid"] is False

    packet["learning_return"] = "该协议可投影既有生命周期，不新增队列。"
    packet["acceptance_criteria"] = [{"description": "聚焦测试通过"}]
    packet["outcome"] = {"status": "verified"}
    assert validate_responsibility_packet(packet, task_id="RQ-mirror-001", strict=True)["valid"] is True


def test_production_protocol_materializes_responsibility_packet_but_light_task_does_not():
    task = _task()
    task.tags = ["production"]
    protocols = ensure_task_protocols(task)
    assert protocols["responsibility_packet"]["protocol"] == RESPONSIBILITY_PROTOCOL
    assert "responsibility" in protocols["checks"]
    assert protocol_errors(protocols, require_evidence=False) == []
    assert protocol_errors(protocols, require_responsibility=True)

    light = Task("RQ-mirror-light", "普通观察")
    assert ensure_task_protocols(light)["active"] is False
    assert "responsibility_packet" not in light.outputs


def test_execution_contract_includes_root_mirror_context():
    prompt = build_execution_system_prompt(
        role="researcher", task_type="reasoning", task_id="RQ-mirror-002"
    )
    assert "ACE-MIRROR-CONSTITUTION-1.0" in prompt
    assert "责任完成" in prompt


def test_legacy_execution_marker_is_idempotently_upgraded_with_mirror_context():
    from core.execution_contract import CONTRACT_VERSION, ensure_execution_contract

    legacy = f"[ACE_EXECUTION_CONTRACT version={CONTRACT_VERSION}]\nlegacy"
    upgraded = ensure_execution_contract(legacy)
    assert upgraded.count(CONTRACT_VERSION) == 1
    assert upgraded.count("ACE-MIRROR-CONSTITUTION-1.0") == 1


def test_guardian_does_not_promote_long_term_rule_without_learning_return():
    with TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task(
            "镜子宪法长期规则门",
            hypothesis="三条独立证据支持该规则",
            creator="test",
            tags=["long_term_rule"],
            admission={
                "source_type": "maintenance",
                "source_ref": "test:mirror-guardian",
                "why_now": "验证长期规则责任收口",
                "evidence": [{"source": "test:mirror-guardian", "detail": "测试证据"}],
                "expected_result": "无 learning_return 时不晋升",
                "verification_method": "运行本测试",
                "risk": "仅测试",
                "estimated_scope": "一个任务",
            },
        )
        claimed = pool.claim_task(task.task_id, "researcher", lease_seconds=60)
        assert claimed is not None
        claimed.evidence = [
            {"source": f"source-{index}", "content": f"evidence-{index}"}
            for index in range(1, 6)
        ]
        assert pool.update_task(claimed)
        assert pool.move_task(task.task_id, "review", actor="researcher", task=claimed) is not None
        reviewed = pool.load_task(task.task_id)
        assert reviewed is not None
        assert pool.move_task(task.task_id, "approved", actor="validator", task=reviewed) is not None

        decision = Guardian(pool).judge(pool.load_task(task.task_id))
        assert decision["verdict"] == "experience"
        assert decision["promoted"] is False
        assert "responsibility:responsibility_learning_return_missing" in decision["reason"]
