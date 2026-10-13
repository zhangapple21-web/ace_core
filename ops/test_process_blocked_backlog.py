"""Blocked-backlog disposition: it must process, and it must refuse correctly.

68 held is a stall in the same way pending=0 is. This module's job is to give
each task the terminal disposition the system already implements, and to refuse
the ones that genuinely need a human - which is the same discipline as the
admissibility gate, pointed at the other end of the lifecycle.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import ops.process_blocked_backlog as pbb  # noqa: E402

BLOCKED_REASON = "相同证据集重复验证达到上限，等待人工或外部新证据"


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A pool, a knowledge store, and the report dir the gate reads."""
    for name in ("blocked", "graveyard", "pending", "active", "review", "archived"):
        (tmp_path / "task_pool" / name).mkdir(parents=True, exist_ok=True)
    (tmp_path / "09_KNOWLEDGE").mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pbb, "BASE_DIR", tmp_path)
    return tmp_path


def _task(root, task_id, *, unchanged=4, review=5, evidence=None):
    """A blocked task, built with the pool's own APIs and no hand-written index.

    The fixture must not patch task_index.json or move files by hand: the pool's
    load_task resolves a task through that index, and a fixture that disagrees
    with it produces a test that looks correct and tests nothing. The daemon
    reaches blocked through block_task, so the fixture uses the same call.
    """
    from core.task import TaskPool

    pool = TaskPool(str(root / "task_pool"))
    admission = {
        "source_type": "evidence",
        "source_ref": f"fixture:{task_id}",
        "why_now": "fixture blocked task for disposition testing",
        "evidence": [{"source": "test", "content": "fixture evidence"}],
        "expected_result": "the task is disposed or held with a stated reason",
        "verification_method": "assert the resulting state and the recorded reason",
        "risk": "low: sandbox fixture only",
        "estimated_scope": "small",
    }
    created = pool.create_task(
        title=f"patrol follow-up {task_id}",
        creator="observation_to_task",
        priority="high",
        admission=admission,
        outputs={"terminal_disposition": ""},
    )

    stored = pool.load_task(created.task_id)
    assert stored is not None, "fixture task was not loadable"
    stored.unchanged_review_count = unchanged
    stored.review_count = review
    stored.evidence = evidence if evidence is not None else [
        {"source": "runtime_observation:OBS-1", "content": "patrol returned error"},
        {"source": "runtime_observation:OBS-1", "content": "patrol returned error"},
    ]
    assert pool.update_task(stored), "fixture could not settle the blocked record"

    blocked = pool.block_task(created.task_id, BLOCKED_REASON,
                              actor="fixture", block_type="manual_gate_blocked")
    assert blocked is not None, "block_task refused: the fixture never reached blocked"

    on_disk = json.loads(
        (root / "task_pool" / "blocked" / f"{created.task_id}.json").read_text(encoding="utf-8"))
    assert BLOCKED_REASON in str(on_disk.get("blocked_reason")), (
        "fixture: the marker the gate filters on must be on disk"
    )
    return created.task_id


def _review(root, sweep, tasks, reviewer, verdict):
    directory = root / "07_SANDBOX" / "free_research" / "reports" / "external_review"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"EXP-EXTREVIEW-{sweep}.json").write_text(json.dumps({
        "tasks": tasks,
        "reviews": [{"reviewer": reviewer, "status": "REVIEWED",
                     "detail": f"INDEPENDENT: the evidence does not address the claim. VERDICT: {verdict}"}],
    }, ensure_ascii=False), encoding="utf-8")


# -------------------------------------------------------------- refusals

def test_a_task_below_the_ceiling_is_not_disposed(workspace):
    """Disposing work that still has research room would bury a live question."""
    tid = _task(workspace, "RQ-BELOW", unchanged=2, review=3)
    _review(workspace, "S1", [tid], "deepseek", "CANNOT_ASSESS")
    report = pbb.process(workspace)
    held = {e["task_id"]: e["reason"] for e in report["observed"]}
    assert tid in held
    assert "ceiling" in held[tid]


def test_a_contradicted_task_is_left_for_a_human(workspace):
    """A reader who disagreed is exactly the case a human must see."""
    tid = _task(workspace, "RQ-CONTRA", unchanged=4, review=5)
    _review(workspace, "S1", [tid], "deepseek", "CONTRADICTED")
    report = pbb.process(workspace)
    held = {e["task_id"]: e["reason"] for e in report["observed"]}
    assert tid in held
    assert "contradicted" in held[tid]


def test_a_task_no_one_reviewed_is_not_disposed_on_assumption(workspace):
    tid = _task(workspace, "RQ-UNREAD", unchanged=4, review=5)
    report = pbb.process(workspace)
    held = {e["task_id"]: e["reason"] for e in report["observed"]}
    assert tid in held
    assert "no outside reader" in held[tid]


def test_a_task_with_no_evidence_is_not_disposed(workspace):
    """An empty evidence array is not proof the work is finished."""
    tid = _task(workspace, "RQ-EMPTY", unchanged=4, review=5, evidence=[])
    _review(workspace, "S1", [tid], "deepseek", "CANNOT_ASSESS")
    report = pbb.process(workspace)
    assert tid not in {e["task_id"] for e in report["disposed"]}


# -------------------------------------------------------------- disposition

def test_a_spent_task_is_disposed_deposited_and_moved(workspace):
    """The full path: disposition, lesson, and the lifecycle transition."""
    tid = _task(workspace, "RQ-SPENT", unchanged=4, review=5)
    _review(workspace, "S1", [tid], "deepseek", "CANNOT_ASSESS")

    dry = pbb.process(workspace)
    assert dry["disposed_count"] == 1 and dry["apply"] is False

    applied = pbb.process(workspace, apply=True)
    assert applied["disposed_count"] == 1
    entry = applied["disposed"][0]
    assert entry["deposited_experience"], "the lesson must reach the knowledge store"
    assert (workspace / "task_pool" / "graveyard" / f"{tid}.json").exists()
    assert not (workspace / "task_pool" / "blocked" / f"{tid}.json").exists()

    stored = json.loads(
        (workspace / "task_pool" / "graveyard" / f"{tid}.json").read_text(encoding="utf-8"))
    assert stored["status"] == "graveyard"
    assert stored["outputs"]["terminal_disposition_reason"].startswith("ceiling reached")
    # a lesson, not a finding: nothing here was ever proven
    assert stored["guardian_decision"] == "discard"


def test_disposition_is_idempotent(workspace):
    tid = _task(workspace, "RQ-IDEM", unchanged=4, review=5)
    _review(workspace, "S1", [tid], "deepseek", "CANNOT_ASSESS")
    pbb.process(workspace, apply=True)
    again = pbb.process(workspace, apply=True)
    assert again["disposed_count"] == 0, "a disposed task is no longer in blocked"


def test_a_disposed_task_is_recoverable_by_the_existing_hatch(workspace):
    """Disposing is a statement that work finished, not a deletion.

    The audit trail and reopen_task both survive, so new evidence can still
    bring it back - which is what makes disposing safe to automate.
    """
    from core.task import TaskPool

    tid = _task(workspace, "RQ-RECOVER", unchanged=4, review=5)
    _review(workspace, "S1", [tid], "deepseek", "CANNOT_ASSESS")
    pbb.process(workspace, apply=True)

    stored = json.loads(
        (workspace / "task_pool" / "graveyard" / f"{tid}.json").read_text(encoding="utf-8"))
    reopened = any(e.get("event") == "transition" and e.get("to") == "graveyard"
                   for e in stored.get("audit_log") or [])
    assert reopened, "the transition must be in the audit log"

    pool = TaskPool(str(workspace / "task_pool"))
    task = pool.load_task(tid)
    assert task is not None and task.status == "graveyard"
