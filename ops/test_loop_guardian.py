"""Loop guardian: the assertions must fail when they should.

A guardian that cannot fail is decoration. These tests build real pool states
on disk and check each assertion against them, including the failure modes the
last defect turned on: a pool nothing drives, and ``pending=0`` that means work
went nowhere rather than work finished.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import ops.loop_guardian as lg  # noqa: E402
from core.task import TaskPool  # noqa: E402


def _task(pool_dir, task_id, status="pending", **extra):
    from pathlib import Path

    path = Path(pool_dir) / status / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"task_id": task_id, "title": task_id, "status": status,
               "creator": "test", "priority": "medium"}
    payload.update(extra)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _move(pool_dir, task_id, to_status):
    """Move a task the way the lifecycle would, so counts genuinely change.

    A sweep whose counts equal the previous sweep is correctly scored red - work
    is not moving. Tests that want a green streak must move work, not just call
    the guardian again.
    """
    from pathlib import Path

    root = Path(pool_dir)
    for sub in root.iterdir():
        if sub.is_dir():
            path = sub / f"{task_id}.json"
            if path.exists():
                path.unlink()
    _task(root, task_id, status=to_status)


# ---------------------------------------------------------------- fixtures

@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    """A workspace with a live main pool and a fresh daemon state file."""
    import time

    main = TaskPool(str(tmp_path / "task_pool"))
    _task(tmp_path / "task_pool", "RQ-T-001")
    rt = tmp_path / "06_RUNTIME" / "ace" / "data" / "memory"
    rt.mkdir(parents=True, exist_ok=True)
    (rt / "daemon_state.json").write_text(json.dumps({
        "pid": 1, "run_status": "alive", "last_run": "recent",
    }), encoding="utf-8")
    monkeypatch.setattr(lg, "BASE_DIR", tmp_path)
    monkeypatch.setattr(lg, "LEDGER", tmp_path / "ledger.json")
    monkeypatch.setattr(lg, "RECEIPTS", tmp_path / "receipts")
    return tmp_path


def _sweep_with_ledger(tmp_path, previous_counts):
    """Seed the guardian's ledger as if a previous sweep had happened.

    The nesting matters: the guardian reads ``counts.task_pool`` internally, so a
    flat dict makes every comparison treat the run as a first sweep.
    """
    (tmp_path / "ledger.json").write_text(json.dumps({
        "counts": {"task_pool": previous_counts},
        "consecutive_green": 0,
    }), encoding="utf-8")


# ------------------------------------------------------------- assertions

def test_a_fresh_live_daemon_passes_a1(workspace):
    report = lg.sweep(workspace)
    assert report["assertions"]["A1_daemon_fresh"]["passed"]


def test_a_stale_or_dead_daemon_fails_a1(workspace):
    import time

    state = workspace / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json"
    state.write_text(json.dumps({"run_status": "stale"}), encoding="utf-8")
    assert not lg.sweep(workspace)["assertions"]["A1_daemon_fresh"]["passed"]

    # alive but the state file has not been written for half an hour
    old = time.time() - 3600
    os.utime(state, (old, old))
    state.write_text(json.dumps({"run_status": "alive"}), encoding="utf-8")
    os.utime(state, (old, old))
    assert not lg.sweep(workspace)["assertions"]["A1_daemon_fresh"]["passed"]


def test_a_pool_with_tasks_but_no_lifecycle_fails_a2(workspace):
    """This is exactly the defect: a pool nobody drives.

    ``task_pool_freezone`` held 67 tasks while its only directory was
    ``pending``. A pool with work but no active/review layout is a black hole,
    and pending=0 in the main pool must not hide it.
    """
    black = workspace / "task_pool_freezone"
    _task(black, "RQ-STRANDED-1")
    _task(black, "RQ-STRANDED-2")

    report = lg.sweep(workspace)
    assertion = report["assertions"]["A2_no_black_hole_pool"]
    assert assertion["passed"] is False
    names = [b["pool"] for b in assertion["black_holes"]]
    assert "task_pool_freezone" in names


def test_a_served_pool_passes_a2(workspace):
    """A pool with the full layout is fine even when empty."""
    TaskPool(str(workspace / "task_pool_freezone"))
    assert lg.sweep(workspace)["assertions"]["A2_no_black_hole_pool"]["passed"]


def _age_task_files(workspace: Path, minutes: float) -> None:
    """Backdate every task file so nothing appears touched recently.

    Backdating only the ledger boundary is not a stall: every file then looks
    like it changed after the boundary. A stall is a boundary that is recent
    enough to be meaningful while the files are older than it.
    """
    import os
    import time

    stamp = time.time() - minutes * 60
    for sub in (workspace / "task_pool").iterdir():
        if sub.is_dir():
            for path in sub.glob("*.json"):
                os.utime(path, (stamp, stamp))


def test_work_moving_passes_a3_and_stalled_fails(workspace):
    # the first evaluate records the baseline
    assert lg.evaluate_and_record(workspace)["streak"] == 1

    # the lifecycle advances the task: green, because a file was touched
    _move(workspace / "task_pool", "RQ-T-001", "review")
    assert lg.evaluate_and_record(workspace)["streak"] == 2

    # a real stall: files untouched, boundary recent enough to judge
    _age_task_files(workspace, lg.MIN_SWEEP_GAP_MINUTES + 5)
    ledger = json.loads((workspace / "ledger.json").read_text(encoding="utf-8"))
    ledger["last_sweep_at"] = (
        datetime.now() - timedelta(minutes=lg.MIN_SWEEP_GAP_MINUTES + 2)
    ).isoformat()
    (workspace / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    stalled = lg.evaluate_and_record(workspace)
    assert stalled["assertions"]["A3_work_is_moving"]["passed"] is False
    assert stalled["streak"] == 0, "a real stall must reset the streak"

    # now the lifecycle advances the task again: green returns
    _move(workspace / "task_pool", "RQ-T-001", "approved")
    assert lg.evaluate_and_record(workspace)["assertions"]["A3_work_is_moving"]["passed"]


def test_growing_pending_fails_a4_and_draining_passes(workspace):
    _sweep_with_ledger(workspace, {"pending": 2, "archived": 0})
    assert lg.sweep(workspace)["assertions"]["A4_pending_not_growing"]["passed"]  # 2 -> 1

    _task(workspace / "task_pool", "RQ-T-002")
    _sweep_with_ledger(workspace, {"pending": 1, "archived": 0})
    assertion = lg.sweep(workspace)["assertions"]["A4_pending_not_growing"]
    assert assertion["passed"] is False
    assert "1 -> 2" in assertion["detail"]


def test_a_first_sweep_records_a_baseline_without_failing(workspace):
    """A baseline must not be scored as a stall on its first appearance."""
    report = lg.sweep(workspace)
    assert report["assertions"]["A3_work_is_moving"]["passed"]
    assert "baseline" in report["assertions"]["A3_work_is_moving"]["detail"]


# ----------------------------------------------------------------- closure

def test_closure_requires_consecutive_green_sweeps(workspace, monkeypatch):
    """Three green sweeps in a row close the loop; one red resets it."""
    assert lg.REQUIRED_CONSECUTIVE == 3

    # sweep 1: baseline, green
    first = lg.evaluate_and_record(workspace)
    assert first["streak"] == 1 and not first["closed"]

    # sweep 2: counts changed, green
    (workspace / "task_pool" / "pending" / "RQ-T-001.json").unlink()
    _task(workspace / "task_pool", "RQ-T-001", status="review")
    second = lg.evaluate_and_record(workspace)
    assert second["streak"] == 2 and not second["closed"], (
        "closing on two sweeps would mistake a momentary gap for a closed loop"
    )

    # sweep 3: changed again, green -> closed
    (workspace / "task_pool" / "review" / "RQ-T-001.json").unlink()
    _task(workspace / "task_pool" / "task_pool" if False else workspace / "task_pool",
          "RQ-T-001", status="approved")
    third = lg.evaluate_and_record(workspace)
    assert third["streak"] == 3 and third["closed"]
    assert third["receipt"] is not None
    receipts = list((workspace / "receipts").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["contract_version"] == "ace.loop_guardian.closure.v1"
    assert receipt["taskpool_mutated"] is False


def test_a_red_sweep_resets_the_streak(workspace):
    # immediate re-sweep is green: the gap is shorter than a daemon cycle
    assert lg.evaluate_and_record(workspace)["streak"] == 1
    assert lg.evaluate_and_record(workspace)["streak"] == 2

    # a real stall: files untouched for longer than a daemon cycle
    _age_task_files(workspace, lg.MIN_SWEEP_GAP_MINUTES + 5)
    ledger = json.loads((workspace / "ledger.json").read_text(encoding="utf-8"))
    ledger["last_sweep_at"] = (
        datetime.now() - timedelta(minutes=lg.MIN_SWEEP_GAP_MINUTES + 2)
    ).isoformat()
    (workspace / "ledger.json").write_text(json.dumps(ledger), encoding="utf-8")
    stalled = lg.evaluate_and_record(workspace)
    assert stalled["streak"] == 0, "a real stall must reset the streak"
    assert stalled["closed"] is False

    # a black hole is red regardless of timing
    _task(workspace / "task_pool_freezone", "RQ-STRANDED")
    report = lg.evaluate_and_record(workspace)
    assert report["streak"] == 0
    assert report["closed"] is False
    assert not list((workspace / "receipts").glob("*.json"))


def test_closure_is_idempotent(workspace):
    for index in range(lg.REQUIRED_CONSECUTIVE):
        _move(workspace / "task_pool", "RQ-T-001",
              ["pending", "review", "approved"][index])
        report = lg.evaluate_and_record(workspace)
        assert report["closed"] is (index == lg.REQUIRED_CONSECUTIVE - 1)
    assert len(list((workspace / "receipts").glob("*.json"))) == 1, (
        "a second closure must not write a second receipt"
    )
    # and a later sweep does not close again
    _move(workspace / "task_pool", "RQ-T-001", "archived")
    assert lg.evaluate_and_record(workspace)["closed"]
    assert len(list((workspace / "receipts").glob("*.json"))) == 1


def test_the_guardian_never_writes_to_the_task_pool(workspace):
    """Read-only over work: its only writes are its ledger and its receipts."""
    before = {
        sub.name: sorted(p.name for p in sub.glob("*.json"))
        for sub in sorted((workspace / "task_pool").iterdir()) if sub.is_dir()
    }
    lg.evaluate_and_record(workspace)
    after = {
        sub.name: sorted(p.name for p in sub.glob("*.json"))
        for sub in sorted((workspace / "task_pool").iterdir()) if sub.is_dir()
    }
    assert before == after