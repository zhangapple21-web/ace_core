"""What the runtime's own questions may and may not turn into work.

Recovered context, because it matters for reading this file
-----------------------------------------------------------
An audit cited `ops/test_observation_to_task_churn.py` as an existing test. The
source is not in the tree and no commit ever touched it, but its compiled artifact
(`ops/__pycache__/test_observation_to_task_churn.cpython-311-pytest-9.1.1.pyc`, written
14:02 on 2026-10-18) still holds it: five tests under `TensionQuestionChurnTest`, with
a `_FakeObserver` shim and a `_tension_obs` helper. What could be recovered from the
code objects - the assertion messages, the docstrings, the constants - is folded in
here. Two of its five contracts are stronger than what this repository currently
guarantees, and the gap is written down as a test rather than quietly dropped:

  recovered and adopted here
      same question after archival is absorbed, not re-filed (counts as a semantic
      duplicate and consumes the observation)
      distinct questions stay distinct work
  recovered and NOT implemented, named below
      a continuing condition must leave a durable record across archival

Why that last one is a named gap and not a change
-------------------------------------------------
The durable record for continuing conditions is `semantic_incidents.json`, and it is
keyed by *rule name*. `fragment_backlog` and `cross_agent_idle` are one condition per
rule, so the key is exact. `tension_question` is three conditions per rule - measured
live as three distinct `tension_key` values - so a rule-keyed record would flap
between them and end up naming a task for a question it is not about. Changing that
key is a change to a production field's schema, which the phase-2 audit explicitly
reserved for the owner ("do not modify production fields yet; the owner decides on
backfill, the rolling window, and whether admission evidence is the only durable
relation"). So the requirement is pinned as a strict xfail: it is a real gap, it is
visible, and it will announce itself the moment someone closes it.

What is durable today, and what is not
--------------------------------------
Durable: the closed task keeps the question's `semantic_signature` and its admission
evidence copy, and every re-ask is marked consumed against that task - so the trail
"this question was asked and serviced" survives the observation store's ~200-row
rewind. Not durable: any statement that the question is *still* being asked, which
today lives only inside that window.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

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


def _ask(observer, question: str, description: str = "runtime asks: it files a question"):
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


def _archive_only_task(pool) -> str:
    """The runtime files, services and archives a question in one cycle."""
    tasks = _tasks(pool)
    assert len(tasks) == 1, f"expected exactly one question task, saw {len(tasks)}"
    task_id = tasks[0].task_id
    for status in ("active", "review", "approved", "archived"):
        assert pool.move_task(task_id, status, actor="test") is not None
    assert pool.load_task(task_id).status == "archived"
    return task_id


# --- recovered: the first asking must create work -------------------------------

def test_the_first_asking_of_a_question_creates_work(tmp_path):
    observer, pool, converter = _converter(tmp_path)

    _ask(observer, "thinking_drought", "runtime asks: observe again")
    result = converter.convert()

    assert result["tasks_created"] == 1, f"the first asking must create work: {result}"
    assert len(_tasks(pool)) == 1


# --- recovered: absorption after archival, not re-filing -------------------------

def test_same_question_after_archival_is_absorbed_not_refiled(tmp_path):
    """A question already asked and serviced must not mint another task.

    Recovered assertion intent from the compiled artifact, kept verbatim in spirit:
    the re-ask is counted as a semantic duplicate and the observation is consumed, so
    it neither becomes work nor is left looking unhandled.
    """
    observer, pool, converter = _converter(tmp_path)

    observer.record(description="runtime asks: observe again",
                    system_state={"tension_key": "thinking_drought",
                                  "evidence": ["observed without a name"]},
                    severity="medium", source="daemon_loop", category="anomaly")
    converter.convert()
    tasks = _tasks(pool)
    assert len(tasks) == 1
    first_task_id = tasks[0].task_id
    _archive_only_task(pool)

    observer.record(description="runtime asks: observe again",
                    system_state={"tension_key": "thinking_drought",
                                  "evidence": ["observed without a name"]},
                    severity="medium", source="daemon_loop", category="anomaly")
    result = converter.convert()

    assert result["tasks_created"] == 0, (
        f"a question already asked and serviced minted another task: {result}"
    )
    assert result["semantic_duplicates"] >= 1, (
        f"the re-ask was not counted as a duplicate: {result}"
    )
    assert observer.get_unprocessed() == [], "the re-ask was left unconsumed"
    archived = [task for task in pool.list_tasks(status="archived", limit=1000)
                if (task.outputs or {}).get("conversion_rule") == RULE]
    assert len(archived) == 1, "the closed task was disturbed by the re-ask"
    assert archived[0].task_id == first_task_id, (
        "the re-ask pointed at a different task than the one that carried it"
    )


# --- recovered: the dedup must not collapse genuinely different questions --------

def test_distinct_questions_still_each_get_one_task(tmp_path):
    """A different question is different work and must still be admitted."""
    observer, pool, converter = _converter(tmp_path)

    for question in ("thinking_drought", "learn_without_use", "fa_duty_gap"):
        _ask(observer, question)
        result = converter.convert()
        assert result["tasks_created"] == 1, (
            f"{question} was not admitted: {result}"
        )

    assert len(_tasks(pool)) == 3, f"three questions produced {len(_tasks(pool))} tasks"


# --- named gap: the durable record a continuing condition owes ------------------

@pytest.mark.xfail(
    strict=True,
    reason="semantic_incidents.json is keyed by rule name and this rule carries three "
           "distinct questions; re-keying it is a production schema change the "
           "phase-2 audit reserved for the owner. Closes the moment it is decided.",
)
def test_a_continuing_question_must_leave_a_record_beyond_the_observation_window(tmp_path):
    """A continuing condition must leave an incident record across archival.

    Recovered from the compiled artifact and NOT implemented on purpose: the durable
    record is `semantic_incidents.json`, keyed by rule name, and this rule carries
    three distinct questions, so a rule-keyed entry would name a task for a question
    it is not about. Re-keying that file is a production schema change reserved for
    the owner by the phase-2 audit, so this is pinned as a strict xfail: it stays
    visible, and it will fail loudly the moment the gap is closed rather than being
    quietly forgotten.
    """
    observer, pool, converter = _converter(tmp_path)
    _ask(observer, "thinking_drought")
    converter.convert()
    _archive_only_task(pool)
    _ask(observer, "thinking_drought")
    converter.convert()

    incidents = json_incidents(converter)
    assert RULE in incidents, (
        f"a question that keeps being asked left no incident record: {incidents}"
    )
    assert incidents[RULE].get("task_id"), (
        f"the incident record names no task: {incidents[RULE]}"
    )


def json_incidents(converter):
    path = Path(converter.observer.data_dir) / "semantic_incidents.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


# --- the ceiling: suppression must not become muting -----------------------------

def test_a_new_question_after_one_closed_still_gets_its_own_task(tmp_path):
    """If closing one task silenced every question, this would be a quieter bug."""
    observer, pool, converter = _converter(tmp_path)

    _ask(observer, "fa_duty_gap")
    converter.convert()
    closed = _archive_only_task(pool)

    _ask(observer, "model_call_starvation")
    converter.convert()

    tasks = _tasks(pool)
    assert len(tasks) == 1, (
        f"a never-asked question was suppressed along with the repeat: {len(tasks)}"
    )
    assert tasks[0].task_id != closed