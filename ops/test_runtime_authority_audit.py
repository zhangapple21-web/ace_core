"""Adversarial boundary checks for the runtime-authority audit.

All inputs below are untrusted records in a temporary directory.  The test
deliberately never calls a lifecycle mutation API on behalf of a report,
manifest, or model output.
"""

import json
from datetime import datetime, timedelta, timezone

from agent_team.active_work_manifest import READ_ONLY_MODE, access_mode
from core.finance_shift_contract import build_evaluation_slots
from core.task import TaskPool
from core.execution_discipline import protocol_receipt, validate_execution_discipline


def _admission(source_ref: str) -> dict:
    """Use the same explicit admission contract as production fixtures."""
    return {
        "source_type": "system_observation",
        "source_ref": source_ref,
        "why_now": "A boundary regression fixture must enter through Admission.",
        "evidence": [f"test://{source_ref}/evidence"],
        "expected_result": "The runtime boundary remains unchanged by derived records.",
        "verification_method": "Compare the persisted TaskPool record before and after the attack.",
        "risk": "test_only",
        "estimated_scope": "temporary fixture",
    }


def _create_fixture(pool: TaskPool, title: str):
    return pool.create_task(
        title,
        creator="authority_boundary_test",
        admission=_admission(title.replace(" ", "-")),
    )


def _paper_pick(number: int) -> dict:
    return {
        "evaluation_only": True,
        "recommendation_id": f"EVAL-{number}",
        "timestamp": "2026-09-05T09:45:00+08:00",
        "symbol": "000001",
        "reference_price": 10.2,
        "hypothesis": "paper-only hypothesis",
        "invalidating_conditions": ["break condition"],
        "next_verification": "next session",
        "data_snapshot_hash": "hash",
        "source_refs": ["source-a", "source-b"],
        "data_quality_state": "DEGRADED",
        "feature_version": "v1",
        "advisor_version": "blocked",
        "risk_version": "not-ready",
    }


def test_manifest_report_and_model_output_cannot_mutate_taskpool(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"), allow_test_creator_without_admission=True)
    task = _create_fixture(pool, "authority boundary fixture")
    before = pool.load_task(task.task_id).to_dict()

    # Attack 01: forged manifest completion; Attack 05: forged report approval;
    # Attack 06: model PASS.  These are only files and are never interpreted as
    # TaskPool commands.
    (tmp_path / "active_work_manifest.json").write_text(
        json.dumps({"task_id": task.task_id, "status": "COMPLETED", "owner": "other-window"}),
        encoding="utf-8",
    )
    (tmp_path / "report.json").write_text(
        json.dumps({"task_id": task.task_id, "delivery_approved": True}),
        encoding="utf-8",
    )
    (tmp_path / "model_output.json").write_text(
        json.dumps({"task_id": task.task_id, "decision": "PASS"}),
        encoding="utf-8",
    )

    assert pool.load_task(task.task_id).to_dict() == before
    assert pool.load_task(task.task_id).status == "pending"


def test_owner_missing_or_expired_is_read_only_without_implicit_takeover():
    now = datetime.now(timezone.utc)
    valid = {
        "work_id": "w1",
        "agent": "codex",
        "owner": "window-a",
        "mission": "audit",
        "workspace": "C:/tmp/ace_core",
        "scope": ["core"],
        "status": "active",
        "heartbeat_at": (now - timedelta(hours=2)).isoformat(),
        "ttl_seconds": 60,
        "production_integration": False,
        "taskpool_authority": False,
        "takeover_requires_new_declaration": True,
    }
    assert access_mode({**valid, "owner": ""}, "window-a") == READ_ONLY_MODE
    assert access_mode(valid, "window-a") == READ_ONLY_MODE
    assert valid["owner"] == "window-a"  # no mutation or takeover occurred


def test_finance_zero_one_two_three_contract_is_fail_closed():
    assert build_evaluation_slots([], target=2)["status"] == "NO_VALID_EVALUATION_PICK"
    assert build_evaluation_slots([_paper_pick(1)], target=2)["status"] == "VALID"
    assert build_evaluation_slots([_paper_pick(1), _paper_pick(2)], target=2)["status"] == "VALID"
    assert build_evaluation_slots(
        [_paper_pick(1), _paper_pick(2), _paper_pick(3)], target=2
    )["status"] == "INVALID_EXCESS_EVALUATION_PICK"


def test_move_to_active_materializes_owner_and_fencing_instead_of_unowned_state(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"), allow_test_creator_without_admission=True)
    task = _create_fixture(pool, "active transition fixture")

    moved = pool.move_task(task.task_id, "active", actor="window-a", task=task)

    assert moved is not None
    stored = pool.load_task(task.task_id)
    assert stored.status == "active"
    assert stored.lease_owner == "window-a"
    assert stored.assignee == "window-a"
    assert stored.claim_id
    assert stored.fencing_token == 1
    assert stored.lease_expires_at


def test_move_to_active_does_not_allow_a_stale_claim_to_reacquire(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"), allow_test_creator_without_admission=True)
    task = _create_fixture(pool, "stale transition fixture")
    claimed = pool.claim_task(task.task_id, "window-a", lease_seconds=60)
    assert claimed is not None

    stale = pool.load_task(task.task_id)
    stale.claim_id = ""
    assert pool.move_task(task.task_id, "active", actor="window-b", task=stale) is None
    current = pool.load_task(task.task_id)
    assert current.lease_owner == "window-a"


def test_orphaned_active_record_cannot_advance_without_recovery(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"), allow_test_creator_without_admission=True)
    task = _create_fixture(pool, "orphaned active fixture")
    task.status = "active"
    active_path = tmp_path / "task_pool" / "active" / f"{task.task_id}.json"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(json.dumps(task.to_dict()), encoding="utf-8")

    orphan = pool.load_task(task.task_id)
    assert orphan is not None and orphan.claim_id == ""
    orphan.status = "review"
    assert not pool.update_task(orphan)
    assert pool.move_task(task.task_id, "review", actor="window-a", task=orphan) is None
    assert pool.load_task(task.task_id).status == "active"


def test_duplicate_status_files_use_durable_timestamp_then_status_rank(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"), allow_test_creator_without_admission=True)
    task = _create_fixture(pool, "duplicate status tie fixture")
    active_path = tmp_path / "task_pool" / "active" / f"{task.task_id}.json"
    active_path.parent.mkdir(parents=True, exist_ok=True)
    active_path.write_text(json.dumps({**task.to_dict(), "status": "active"}), encoding="utf-8")

    loaded = pool.load_task(task.task_id)
    assert loaded is not None
    assert loaded.status == "active"


def test_taskpool_rejects_blank_owner_and_nonpositive_lease(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"), allow_test_creator_without_admission=True)
    task = _create_fixture(pool, "invalid lease fixture")
    assert pool.claim_task(task.task_id, "   ") is None
    assert pool.claim_task(task.task_id, "window-a", lease_seconds=0) is None
    assert pool.load_task(task.task_id).status == "pending"


def test_read_only_protocol_audit_does_not_repair_missing_envelope():
    from core.task import Task

    task = Task(task_id="RQ-damaged", title="damaged", outputs={})
    audit = validate_execution_discipline(task)
    receipt = protocol_receipt(task)
    assert audit["valid"] is False
    assert audit["errors"] == ["missing_execution_discipline_envelope"]
    assert receipt["valid"] is False
    assert "execution_discipline" not in task.outputs

