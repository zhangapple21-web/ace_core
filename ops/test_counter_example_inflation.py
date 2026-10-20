"""Counter-example inflation in the review path.

Companion to test_research_evidence_inflation.py, which pins the same disease on
the evidence side. Measured on all 67 non-convergent blocked tasks (2026-10-11):

- every one stored 12-16 counter_examples holding only 2-4 distinct texts
  (mean 14.4 stored -> 3.7 distinct)
- every one asked exactly one distinct objection, three times

core/task_roles.py::Validator.validate_task calls `task.add_counter_example(...)`
for every genuine objection on every review pass, and `add_counter_example`
appends without comparing against what the task already carries. So each
rework cycle re-deposits the same handful of texts.

Unlike the evidence side, this was never made measurable: the reader saw
`counter_examples: 11` and had no way to tell it from eleven distinct
objections. That misreading is what let a one-objection review present itself
as three rounds of deliberation.

This fix publishes the ratio. It deliberately does NOT rewrite the stored list:
the stored evidence path chose measurement over mutation, and history is
append-only.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ops.test_support import FixtureTaskPool as TaskPool
from core.task import Task  # noqa: E402
from core.task_roles import Validator  # noqa: E402


def _task_with_repeated_objections():
    task = Task(task_id="RQ-TEST-CE-001", title="验证重复反例", hypothesis="反例会重复沉淀")
    for _ in range(4):
        task.add_counter_example("仅2条证据，样本量不足", source="validator")
        task.add_counter_example("核心关键词在词库中无对应概念，研究背景薄弱", source="validator")
    return task


def test_distinct_counter_examples_collapses_repetition():
    task = _task_with_repeated_objections()
    assert len(task.counter_examples) == 8
    assert len(Validator._unique_counter_examples(task)) == 2


def test_blank_counter_examples_are_not_counted_as_distinct():
    task = Task(task_id="RQ-TEST-CE-002", title="空反例", hypothesis="空文本不算异议")
    task.add_counter_example("   ", source="validator")
    task.add_counter_example("", source="validator")
    assert len(Validator._unique_counter_examples(task)) == 0


def test_validator_publishes_counter_example_inflation():
    """The record must let a reader tell 8 objections from 2 objections heard 4x.

    The validator appends its own genuine objections during this pass, so the
    stored count grows again on top of the 8 prepared duplicates. The invariant
    under test is therefore the relationship, not an exact total.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("counter-example inflation", creator="test", priority="low")
        task.hypothesis = "repeated objections must not read as breadth"
        task.evidence = [
            {"source": "test", "content": "first detailed evidence record " * 8},
            {"source": "test", "content": "second detailed evidence record " * 8},
        ]
        for _ in range(4):
            task.add_counter_example("仅2条证据，样本量不足", source="validator")
            task.add_counter_example("核心关键词在词库中无对应概念，研究背景薄弱", source="validator")
        pool.update_task(task)

        claimed = pool.claim_task(task.task_id, "researcher", lease_seconds=60)
        assert claimed is not None
        assert pool.move_task(task.task_id, "review", actor="researcher", task=claimed) is not None

        Validator(pool).validate_task(pool.load_task(task.task_id))
        stored = pool.load_task(task.task_id)
        record = (stored.outputs or {}).get("last_validator_result") or {}

        stored_count = record.get("stored_counter_example_count")
        distinct_count = record.get("distinct_counter_example_count")
        ratio = record.get("counter_example_inflation_ratio")

        assert isinstance(stored_count, int)
        assert isinstance(distinct_count, int)
        assert stored_count >= 8, "the prepared duplicates must all still be stored"
        assert distinct_count >= 2, "both prepared objections must be counted as distinct"
        assert stored_count > distinct_count, "this task is exactly the inflated case"
        assert ratio == round(stored_count / distinct_count, 2)
