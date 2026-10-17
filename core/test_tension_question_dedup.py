"""A question asked every cycle is one piece of work, not one per asking.

`review_queue_bottleneck` and the recurring-error rules got signature-based dedup
because a condition that persists must not mint a task per cycle. `tension_question`
is the same shape with a clearer name - the runtime asks itself the same three
questions every cycle - and it was the one recurring rule left out. Measured on
2026-10-17: 78 observations, 3 distinct questions, 78 tasks.

These tests exist so the omission cannot come back quietly, and so the dedup cannot
overreach into merging genuinely different questions.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RULE = "tension_question"


def _converter(tmp_path):
    sys.path.insert(0, str(REPO))
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    observer = RuntimeObserver(data_dir=str(tmp_path / "obs"))
    pool = TaskPool(str(tmp_path / "pool"))
    return observer, pool, ObservationToTaskConverter(observer, pool)


def _ask(observer, question: str, description: str = "the runtime asked itself something"):
    return observer.record(
        description=description,
        system_state={"tension_key": question, "evidence": ["observed without a name"]},
        severity="medium", source="daemon_loop", category="anomaly",
        dedup_key=f"tension:{question}",
    )


def _tasks(pool) -> list:
    found = []
    for status in ("pending", "active", "review", "approved", "blocked"):
        found += [task for task in pool.list_tasks(status=status, limit=1000)
                  if (task.outputs or {}).get("conversion_rule") == RULE]
    return found


def test_the_same_question_asked_every_cycle_stays_one_task(tmp_path):
    observer, pool, converter = _converter(tmp_path)

    for _ in range(25):
        _ask(observer, "fa_duty_gap")
        converter.convert()

    tasks = _tasks(pool)
    assert len(tasks) == 1, f"one question asked 25 times produced {len(tasks)} tasks"
    assert tasks[0].outputs["semantic_signature"], "no identity was recorded on the task"


def test_the_three_recurring_questions_become_three_tasks(tmp_path):
    """Dedup is not merging: three different questions stay three tasks."""
    observer, pool, converter = _converter(tmp_path)

    for question in ("fa_duty_gap", "learn_without_use", "thinking_drought"):
        for _ in range(3):
            _ask(observer, question)
            converter.convert()

    assert len(_tasks(pool)) == 3, (
        f"three questions produced {len(_tasks(pool))} tasks"
    )


def test_a_new_question_after_the_first_one_closed_gets_its_own_task(tmp_path):
    """The identity ends with the work, not with the question's name.

    While a question's task is open the same question reuses it. Once that work is
    closed, the next asking is new work again - otherwise a question could be
    answered once and never re-raised.
    """
    observer, pool, converter = _converter(tmp_path)

    _ask(observer, "fa_duty_gap")
    converter.convert()
    first = _tasks(pool)
    assert len(first) == 1

    # close it the way production does: the real transition path, not a file move
    for status in ("active", "review", "approved", "archived"):
        assert pool.move_task(first[0].task_id, status, actor="test") is not None

    _ask(observer, "fa_duty_gap")
    result = converter.convert()

    remaining = _tasks(pool)
    assert len(remaining) == 1, (
        f"after that work closed, one re-asking left {len(remaining)} open tasks: "
        f"{result}"
    )
    assert remaining[0].task_id != first[0].task_id, (
        "the archived task was revived in place instead of new work being raised"
    )