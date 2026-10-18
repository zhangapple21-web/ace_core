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


def test_the_same_question_asked_again_after_its_task_closed_creates_nothing(tmp_path):
    """Superseded 2026-10-18, and the reason is the repository's own rule.

    This test used to require the opposite: that a question re-asked after its task
    closed would raise new work. That is the behaviour behind a measured production
    problem - 526 `fairness_yield`-era re-asks on one task, and roughly sixteen
    self-question tasks an hour in the live pool, each archived minutes after
    creation - and it contradicts what `core/observation_to_task.py` already says:

        "re-triggering is the watch and escalation layer's call, not the poll
        loop's"

    The converter is the poll loop. A question that was asked, worked, and closed is
    a question the civilization already answered once. Being asked again is a
    *question about the question*, and whether that deserves new work is a judgement
    for the escalation layer, not for every cycle of a loop that is only trying to be
    thorough.

    So the contract is: no new task, and the observation is marked consumed against
    the closed task that already carries this question. A genuinely new question
    still gets its own task - that is the test above, and it stays.
    """
    observer, pool, converter = _converter(tmp_path)

    _ask(observer, "fa_duty_gap")
    converter.convert()
    first = _tasks(pool)
    assert len(first) == 1
    task_id = first[0].task_id

    for status in ("active", "review", "approved", "archived"):
        assert pool.move_task(task_id, status, actor="test") is not None

    _ask(observer, "fa_duty_gap")
    converter.convert()

    assert len(_tasks(pool)) == 0, (
        "a question whose task already closed minted another task, which is how a "
        "self-ask becomes an endless supply of work"
    )
    re_ask = observer.get_unprocessed()
    assert re_ask == [], (
        f"the re-ask was left unconsumed as well as unconverted: {re_ask}"
    )
    reopened = pool.load_task(task_id)
    assert reopened is not None and reopened.status == "archived", (
        "the closed task was revived instead of the re-ask pointing at it"
    )


def test_a_new_question_still_gets_its_own_task(tmp_path):
    """The other half: suppression must not become muting.

    A question nobody has asked before is new information about the runtime, and the
    loop's job is to carry it. If closing one task silenced every question, this
    would be a quieter and much more expensive bug than the one it replaced.
    """
    observer, pool, converter = _converter(tmp_path)

    _ask(observer, "fa_duty_gap")
    converter.convert()
    first = _tasks(pool)
    for status in ("active", "review", "approved", "archived"):
        assert pool.move_task(first[0].task_id, status, actor="test") is not None

    _ask(observer, "model_call_starvation")
    result = converter.convert()

    assert len(_tasks(pool)) == 1, (
        f"a never-asked question was suppressed along with the repeat: {result}"
    )
    assert _tasks(pool)[0].task_id != first[0].task_id