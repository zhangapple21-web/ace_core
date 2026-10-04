"""inject_target is the only injection entry point in ACE.

These tests cover the part that matters for safety: an injected task must carry
a real delivery contract, and it must land in the pool the caller passed in.
"""
import json

import pytest

from core.task import TaskPool
from ops.inject_target import inject, validate_target
from ops.test_support import FixtureTaskPool


def _payload(**overrides):
    payload = {
        "protocol": "ace.target.inject.v1",
        "title": "write the proof document",
        "hypothesis": "the writer will produce it",
        "expected_output": "docs/INJECT_PROOF.md",
        "success_metric": "file_exists_nonempty",
        "priority": "high",
        "domain": "analysis",
        "why_now": "the pool must be able to deliver",
    }
    payload.update(overrides)
    return payload


def test_a_valid_payload_passes_validation():
    assert validate_target(_payload()) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"title": "   "},
        {"success_metric": "vibes"},
        {"expected_output": "/etc/passwd"},
        {"expected_output": "docs/x.exe"},
        {"tags": "not-a-list"},
    ],
)
def test_bad_payloads_are_refused_with_a_reason(overrides):
    assert validate_target(_payload(**overrides))


def test_injected_task_carries_a_delivery_contract(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    receipt = inject(_payload(), pool=pool)

    task = pool.load_task(receipt["task_id"])
    assert task is not None
    delivery = task.outputs["delivery"]
    assert delivery["required_path"] == "docs/INJECT_PROOF.md"
    assert delivery["success_metric"] == "file_exists_nonempty"
    assert delivery["domain"] == "analysis"
    # The delivery tags are what the scheduler's capacity count and the
    # Researcher's delivery-first ordering both key on.
    assert "external_target" in task.tags
    assert "delivery:physical" in task.tags
    assert task.outputs["admission"]["source_type"] == "external_target"


def test_injection_lands_in_the_caller_pool_not_the_production_one(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    receipt = inject(_payload(), pool=pool)
    assert pool.load_task(receipt["task_id"]) is not None

    # Task ids are date+counter based, so an isolated pool reuses the same
    # "RQ-<today>-001" name. Identity must therefore be checked by content:
    # this exact injection must not exist anywhere in the production pool.
    marker = "write the proof document"
    prod = TaskPool("task_pool")
    for status in ("pending", "active", "review", "approved", "blocked",
                   "archived", "rejected", "graveyard"):
        for task in prod.list_tasks(status=status, limit=100000):
            assert task.title.strip() != marker, "injection escaped into production"


def test_receipt_is_json_serialisable_for_logging(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "task_pool"))
    receipt = inject(_payload(), pool=pool)
    assert json.loads(json.dumps(receipt))["task_id"] == receipt["task_id"]