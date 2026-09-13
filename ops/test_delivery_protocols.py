import tempfile

from core.delivery_protocols import (
    EVIDENCE_PACKET_PROTOCOL,
    RELEASE_RECEIPT_PROTOCOL,
    WORK_CONTRACT_PROTOCOL,
    validate_release_receipt,
)
from core.task import TaskPool
from core.task_roles import Guardian, Validator


def _admission(source_ref="test-protocol:1"):
    return {
        "source_type": "maintenance",
        "source_ref": source_ref,
        "why_now": "A bounded protocol integration test is actionable.",
        "evidence": [{"source": source_ref, "detail": "Observed test signal."}],
        "expected_result": "The protocol boundary is exercised.",
        "verification_method": "Run the focused pytest case.",
        "risk": "Test-only; no external side effect.",
        "estimated_scope": "one bounded test",
    }


def _approved_task(pool, *, tags=None, source_ref="test-protocol:1"):
    task = pool.create_task(
        "protocol integration task",
        hypothesis="The protocol boundary can be exercised without replacing the lifecycle owner.",
        creator="test",
        tags=tags or [],
        admission=_admission(source_ref),
    )
    task = pool.claim_task(task.task_id, "researcher", lease_seconds=60)
    assert task is not None
    task.evidence = [
        {"content": f"evidence-{index}", "source": f"source-{index}"}
        for index in range(1, 6)
    ]
    assert pool.update_task(task)
    assert pool.move_task(task.task_id, "review", actor="researcher", task=task) is not None
    review = pool.load_task(task.task_id)
    assert review is not None
    assert pool.move_task(review.task_id, "approved", actor="validator", task=review) is not None
    return pool.load_task(task.task_id)


def test_lightweight_task_does_not_materialize_key_node_protocols():
    with tempfile.TemporaryDirectory() as temp_dir:
        task = TaskPool(temp_dir).create_task(
            "ordinary observation",
            creator="test",
            admission=_admission("test-protocol:ordinary"),
        )

        assert "work_contract" not in task.outputs
        assert "evidence_packet" not in task.outputs
        assert "release_receipt" not in task.outputs


def test_task_pool_materializes_and_persists_protocol_templates_for_production():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task(
            "production change",
            creator="test",
            tags=["production"],
            admission=_admission("test-protocol:production"),
        )
        stored = pool.load_task(task.task_id)

        assert stored is not None
        assert stored.outputs["protocols_required"] is True
        assert stored.outputs["work_contract"]["protocol"] == WORK_CONTRACT_PROTOCOL
        assert stored.outputs["evidence_packet"]["protocol"] == EVIDENCE_PACKET_PROTOCOL
        assert stored.outputs["release_receipt"]["protocol"] == RELEASE_RECEIPT_PROTOCOL
        assert stored.outputs["evidence_packet"]["completeness"] == "INCOMPLETE_GAPS"


def test_validator_consumes_evidence_packet_at_review_boundary():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task(
            "production validation",
            hypothesis="The protocol boundary can be validated with source-backed evidence.",
            creator="test",
            tags=["production"],
            admission=_admission("test-protocol:validator"),
        )
        claimed = pool.claim_task(task.task_id, "researcher", lease_seconds=60)
        assert claimed is not None
        claimed.evidence = [
            {"content": f"evidence-{index}", "source": f"source-{index}"}
            for index in range(1, 4)
        ]
        assert pool.update_task(claimed)
        assert pool.move_task(claimed.task_id, "review", actor="researcher", task=claimed) is not None

        result = Validator(pool).validate_task(pool.load_task(claimed.task_id))
        stored = pool.load_task(claimed.task_id)

        assert result["passed"] is True
        assert stored is not None
        assert stored.outputs["evidence_packet"]["status"] == "PASS"
        assert stored.outputs["delivery_protocol_checks"]["checked_by"] == "validator"


def test_guardian_does_not_promote_long_term_rule_without_protocols():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = _approved_task(pool, tags=["long_term_rule"], source_ref="test-protocol:guardian")
        task.outputs["work_contract"]["status"] = "BROKEN"
        assert pool.update_task(task) is False

        decision = Guardian(pool).judge(task)
        stored = pool.load_task(task.task_id)

        assert decision["verdict"] == "experience"
        assert decision["promoted"] is False
        assert "关键节点协议未通过" in decision["reason"]
        assert stored is not None
        assert task.outputs["delivery_protocol_checks"]["checked_by"] == "guardian"


def test_task_pool_blocks_external_delivery_archive_until_verified_receipt():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = _approved_task(pool, tags=["external_delivery"], source_ref="test-protocol:delivery")

        assert pool.move_task(task.task_id, "archived", actor="archivist", task=task) is None
        stored = pool.load_task(task.task_id)

        assert stored is not None
        assert stored.status == "approved"
        assert stored.outputs["delivery_protocol_checks"]["checked_by"] == "task_pool"
        assert validate_release_receipt(
            stored.outputs["release_receipt"],
            stored.task_id,
            require_verified=True,
        )["valid"] is False




def test_task_pool_archives_external_delivery_after_verified_receipt():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = _approved_task(pool, tags=["external_delivery"], source_ref="test-protocol:verified-delivery")
        task.outputs["release_receipt"] = {
            "protocol": RELEASE_RECEIPT_PROTOCOL,
            "work_id": task.task_id,
            "status": "VERIFIED",
            "reason": "真实入口冒烟通过。",
            "artifact": {"path": "dist/app.zip", "sha256": "a" * 64},
            "entrypoint": "https://example.invalid/app",
            "smoke_checks": [{"name": "health", "passed": True}],
            "rollback": {"ready": True, "method": "restore previous artifact"},
            "verified_at": "2026-09-12T00:00:00+00:00",
            "origin": "test",
        }
        assert pool.update_task(task)
        archived = pool.move_task(task.task_id, "archived", actor="archivist", task=task)

        assert archived is not None
        assert archived.status == "archived"
