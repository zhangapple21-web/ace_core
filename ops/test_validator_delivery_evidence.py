"""A verified physical artifact must be able to satisfy the evidence heuristics."""
from core.task_roles import Validator, _has_verified_delivery
from ops.test_support import FixtureTaskPool
from core.task import Task


def _task(with_delivery_verification):
    outputs = {}
    if with_delivery_verification is not None:
        outputs["delivery"] = {
            "required_path": "docs/X.md",
            "success_metric": "file_exists_nonempty",
            "verification": {"satisfied": with_delivery_verification, "reason": "delivery_satisfied"},
        }
    return Task(task_id="RQ-TEST-V1", title="produce a document", hypothesis="h", evidence=[], outputs=outputs)


def test_helper_only_trusts_a_true_verdict():
    assert _has_verified_delivery(_task(True)) is True
    assert _has_verified_delivery(_task(False)) is False
    assert _has_verified_delivery(_task(None)) is False
    assert _has_verified_delivery(Task(task_id="RQ-TEST-V2", title="no delivery")) is False


def _validate(tmp_path, delivery_verified):
    pool = FixtureTaskPool(str(tmp_path / f"pool_{delivery_verified}"))
    created = pool.create_task(
        title="produce a document",
        hypothesis="the mapping will make the R1 lineage reviewable",
        priority="high",
    )
    stored = pool.load_task(created.task_id)
    if delivery_verified is not None:
        stored.outputs["delivery"] = {
            "required_path": "docs/X.md",
            "success_metric": "file_exists_nonempty",
            "verification": {"satisfied": delivery_verified, "reason": "delivery_satisfied"},
        }
    stored.evidence = [{"source": "admission", "content": "external_target_injection"}]
    pool.update_task(stored)
    pool.move_task(created.task_id, "review", actor="researcher")
    return Validator(pool).validate_task(pool.load_task(created.task_id))


def test_verified_delivery_replaces_the_sample_size_floor(tmp_path):
    result = _validate(tmp_path, True)
    assert result.get("passed") is True, result.get("verdict")
    assert result.get("hard_objections") == []


def test_without_a_verified_delivery_the_objections_are_unchanged(tmp_path):
    result = _validate(tmp_path, False)
    objections = list(result.get("objections", []))
    assert any("样本量不足" in item for item in objections), objections
    assert result.get("passed") is not True