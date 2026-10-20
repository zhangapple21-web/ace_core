"""Validator obligations and counterexamples must remain distinct."""

from __future__ import annotations

import json
import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.task_roles import Guardian, Validator
from ops.test_support import FixtureTaskPool


def _admission(source_ref: str) -> dict:
    return {
        "source_type": "system_observation",
        "source_ref": source_ref,
        "why_now": "Verify separation of review obligations from falsifying observations.",
        "evidence": [{"source_ref": source_ref, "description": "Test fixture only."}],
        "expected_result": "Generic advice and hard gate failures remain auditable without fabricating counterexamples.",
        "verification_method": "Run this focused test.",
        "risk": "Test-only data.",
        "estimated_scope": "one task",
    }


def _ready_for_review(pool, *, suffix: str, evidence_count: int = 5, priority: str = "high"):
    task = pool.create_task(
        f"review semantics {suffix}",
        hypothesis="The bounded fixture satisfies the local validation gate.",
        creator="test",
        priority=priority,
        tags=["long_term_rule", "task_type:reasoning"],
        admission=_admission(f"test:{suffix}"),
        outputs={
            "discovery": {"task_type": "reasoning"},
            "protocol_purpose": "long_term_rule",
            "responsibility_packet": {
                "learning_return": "Document this validation disposition.",
                "next_action": "Continue existing review and verification path.",
                "unknowns": ["Test scope only."],
            },
        },
    )
    task.result = "Five separately sourced fixture observations were reviewed locally."
    task.evidence = [
        {"source": f"{suffix}-{i}", "content": f"Independent evidence {i} for fixture {suffix}. " * 5}
        for i in range(evidence_count)
    ]
    assert pool.update_task(task)
    claimed = pool.claim_task(task.task_id, "researcher")
    assert claimed is not None
    reviewed = pool.move_task(task.task_id, "review", actor="researcher", task=claimed)
    assert reviewed is not None
    return reviewed


def _structured_validator_router(*, counter_examples=()):
    class Router:
        def chat(self, **_kwargs):
            return {
                "success": True,
                "content": json.dumps({
                    "facts": ["Fixture was reviewed."],
                    "evidence": ["Only local test fixture."],
                    "inference": ["No external claim is established."],
                    "unknowns": ["The test says nothing about runtime."],
                    "objections": ["The fixture must not be generalized."],
                    "symbolic_claims": [],
                    "next_verification": ["Run the local regression."],
                    "stop_condition": ["Stop at test boundary."],
                    "hard_objections": [],
                    "advisory_objections": [],
                    "counter_examples": list(counter_examples),
                }),
                "provider": "glm",
                "model": "glm-4-flash",
                "latency_ms": 1,
                "tried_models": ["glm:glm-4-flash"],
            }

    return Router()


def test_advisory_only_validator_result_does_not_add_a_counterexample(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    reviewed = _ready_for_review(pool, suffix="advisory-only")

    result = Validator(pool).validate_task(pool.load_task(reviewed.task_id))
    stored = pool.load_task(reviewed.task_id)

    assert result["passed"] is True
    assert stored is not None
    assert result["hard_objections"] == []
    assert result["counter_examples"] == 0
    assert "未主动寻找反例，存在确认偏误风险" in result["advisory_objections"]
    assert Validator._unique_counter_examples(stored) == set()

    approved = pool.move_task(stored.task_id, "approved", actor="validator", task=stored)
    assert approved is not None
    decision = Guardian(pool).judge(pool.load_task(stored.task_id))
    assert decision["verdict"] == "axiom"
    assert decision["promoted"] is True


def test_hard_sample_obligation_blocks_without_fabricating_counterexample(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    reviewed = _ready_for_review(pool, suffix="hard-obligation", evidence_count=2)

    result = Validator(pool).validate_task(pool.load_task(reviewed.task_id))
    stored = pool.load_task(reviewed.task_id)

    assert result["passed"] is False
    assert stored is not None
    assert any("样本量不足" in item for item in result["hard_objections"])
    assert result["counter_examples"] == 0
    assert Validator._unique_counter_examples(stored) == set()
    assert any("样本量不足" in item["content"] for item in stored.validation_notes)


def test_model_counterexample_is_recorded_as_a_nonblocking_finding(tmp_path):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    reviewed = _ready_for_review(pool, suffix="explicit-counterexample")
    counterexample = "The proposed rule fails in the independently repeated edge case."

    result = Validator(pool, llm_router=_structured_validator_router(
        counter_examples=[counterexample]
    )).validate_task(pool.load_task(reviewed.task_id))
    stored = pool.load_task(reviewed.task_id)

    assert result["passed"] is True
    assert result["counter_examples"] == 1
    assert counterexample in Validator._unique_counter_examples(stored)
    assert counterexample in result["objections"]
    assert counterexample in result["advisory_objections"]
    assert counterexample not in result["hard_objections"]


@pytest.mark.parametrize("priority", ["high", "critical"])
def test_guardian_does_not_promote_constraint_with_recorded_counterexample(tmp_path, priority):
    pool = FixtureTaskPool(str(tmp_path / "pool"))
    reviewed = _ready_for_review(
        pool,
        suffix=f"known-counterexample-{priority}",
        evidence_count=3,
        priority=priority,
    )
    counterexample = "The proposed constraint fails in a recorded independent edge case."
    reviewed.add_counter_example(counterexample, source="validator")
    assert pool.update_task(reviewed)

    approved = pool.move_task(
        reviewed.task_id,
        "approved",
        actor="validator",
        task=pool.load_task(reviewed.task_id),
    )
    assert approved is not None

    decision = Guardian(pool).judge(pool.load_task(reviewed.task_id))

    assert decision["verdict"] == "experience"
    assert decision["promoted"] is False
    assert "反例" in decision["reason"]
