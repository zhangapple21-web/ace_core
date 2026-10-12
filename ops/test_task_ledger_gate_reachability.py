"""Regression guard: the task ledger's drift gate IS reachable from TaskPool writes.

`core/task_ledger.py` states three hard rules. Rule 3:

    落盘前计数器实值必须能被账本重放复现 —— 复现不了即 drift
    (before persisting, the actual counter values must be reproducible by replaying
    the ledger; if they cannot be reproduced, that is drift)

and two write-port modes:

    shadow  (default) record a kind="drift" row
    enforce            raise LedgerDriftError and refuse the write

These were RED before the fix. `TaskPool._transition` used to call
`_ledger_close(kind="consume", reason="transition:...")` unconditionally, even
though it never mutates a ledger counter itself (record_event/record_checkpoint
only touch outputs.execution_discipline). That close absorbed EVERY outstanding
counter delta -- including a counter some caller hand-mutated before
`update_task` -- into a single self-referenced consume row. By the time
`write_port_gate` ran, `replay(ledger) == counter_values(task)` and
`reconcile()` returned {}: the gate could never see drift, so shadow never
recorded a drift row and enforce never raised.

Fixed by removing that no-op close from `_transition`. This file now pins the
corrected behaviour so the bug cannot quietly come back. If someone re-adds an
absorbing `_ledger_close` to `_transition`, these tests fail again.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.task_ledger import (  # noqa: E402
    LedgerDriftError,
    counter_values,
    reconcile,
    replay,
    write_port_gate,
)
from ops.test_support import FixtureTaskPool  # noqa: E402


def _claimed(tmp, title):
    pool = FixtureTaskPool(tmp)
    task = pool.create_task(title)
    pool.claim_task(task.task_id, "researcher", lease_seconds=60)
    return pool, pool.load_task(task.task_id)


def test_the_gate_detects_drift_when_called_directly(monkeypatch):
    """The gate itself is correct. This is the control for the tests below."""
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "enforce")
    with tempfile.TemporaryDirectory() as td:
        pool, loaded = _claimed(td, "direct gate")
        loaded.rework_count += 2
        path = Path(td) / "active" / (loaded.task_id + ".json")
        raised = None
        try:
            write_port_gate(loaded, path, pool_dir=Path(td))
        except LedgerDriftError as exc:
            raised = str(exc)
    assert raised is not None, "write_port_gate failed to detect a direct mutation"
    assert "rework_count" in raised, raised


def test_drift_is_visible_before_the_pool_write(monkeypatch):
    """reconcile() must see the unregistered change while it is still visible."""
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "enforce")
    with tempfile.TemporaryDirectory() as td:
        pool, loaded = _claimed(td, "visible before write")
        loaded.rework_count += 2
        drift = reconcile(loaded)
    assert drift.get("rework_count") == {"expected": 0, "actual": 2}, drift


def test_pool_write_blocks_an_unregistered_change_in_enforce_mode(monkeypatch):
    """enforce mode must now refuse the write and leave disk unchanged.

    Before the fix this was the inverse assertion (the write slipped through).
    The bug was `_transition`'s absorbing `_ledger_close`; with it gone the gate
    sees drift and enforces. If this flips back to passing a write, the absorber
    has been reintroduced.
    """
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "enforce")
    with tempfile.TemporaryDirectory() as td:
        pool, loaded = _claimed(td, "enforce reachable")
        loaded.rework_count += 2
        before = json.loads(
            (Path(td) / "active" / (loaded.task_id + ".json")).read_text(encoding="utf-8")
        )
        raised = None
        try:
            pool.update_task(loaded)
        except LedgerDriftError as exc:
            raised = str(exc)
        on_disk = json.loads(
            (Path(td) / "active" / (loaded.task_id + ".json")).read_text(encoding="utf-8")
        )
    assert raised is not None, "enforce mode let an unregistered change through"
    assert "rework_count" in raised, raised
    assert on_disk.get("rework_count") == before.get("rework_count"), "drift landed on disk"


def test_unregistered_change_is_not_absorbed_as_a_self_referenced_consume_row(monkeypatch):
    """The absorber is gone: no consume row cites the task as its own source.

    This is the direct regression pin for the bug. Rule 1 forbids a self-ref
    consume row that explains nothing about who changed the counter; after the
    fix `_transition` no longer writes one.
    """
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "shadow")
    with tempfile.TemporaryDirectory() as td:
        pool, loaded = _claimed(td, "no absorber")
        loaded.starvation_age += 3
        pool.update_task(loaded)
        stored = pool.load_task(loaded.task_id)
        consumes = [r for r in (stored.ledger or []) if r.get("kind") == "consume"]
    absorbing = [
        row
        for row in consumes
        if row.get("deltas", {}).get("starvation_age") == 3
        and (row.get("ref") or {}).get("type") in ("self", "task")
    ]
    assert not absorbing, "an unregistered change was still absorbed into a consume row"


def test_after_the_write_the_unregistered_value_is_recorded_as_drift(monkeypatch):
    """shadow mode: the ledger now certifies the change via an explicit drift row.

    The ledger still replays to the actual value (self-consistent), but the row
    that carries it is kind="drift" with reason "unregistered_counter_change",
    not a silently legitimate consume row. That makes the change auditable.
    """
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "shadow")
    with tempfile.TemporaryDirectory() as td:
        pool, loaded = _claimed(td, "recorded drift")
        loaded.rework_count += 2
        pool.update_task(loaded)
        stored = pool.load_task(loaded.task_id)
        drift_rows = [
            r for r in (stored.ledger or [])
            if r.get("kind") == "drift" and (r.get("deltas") or {}).get("rework_count") == 2
        ]
    assert reconcile(stored) == {}, reconcile(stored)
    assert replay(stored)["rework_count"] == 2
    assert counter_values(stored)["rework_count"] == 2
    assert drift_rows, "expected a drift row recording the unregistered change"
    assert drift_rows[-1]["reason"] == "unregistered_counter_change", drift_rows[-1]["reason"]


def test_shadow_mode_records_a_drift_row_now(monkeypatch):
    """shadow mode's documented behaviour: append kind="drift". It now does."""
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "shadow")
    with tempfile.TemporaryDirectory() as td:
        pool, loaded = _claimed(td, "shadow drift")
        loaded.rework_count += 2
        pool.update_task(loaded)
        stored = pool.load_task(loaded.task_id)
        kinds = [r.get("kind") for r in (stored.ledger or [])]
    assert "drift" in kinds, kinds


if __name__ == "__main__":
    failures = 0
    for fn in (
        test_the_gate_detects_drift_when_called_directly,
        test_drift_is_visible_before_the_pool_write,
        test_pool_write_blocks_an_unregistered_change_in_enforce_mode,
        test_unregistered_change_is_not_absorbed_as_a_self_referenced_consume_row,
        test_after_the_write_the_unregistered_value_is_recorded_as_drift,
        test_shadow_mode_records_a_drift_row_now,
    ):
        class _MP:
            def __init__(self):
                self.saved = {}

            def setenv(self, k, v):
                self.saved[k] = os.environ.get(k)
                os.environ[k] = v

            def undo(self):
                for k, v in self.saved.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v

        mp = _MP()
        try:
            fn(mp)
            print("PASS %s" % fn.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s\n      %s" % (fn.__name__, exc))
        finally:
            mp.undo()
    print("failures=%d" % failures)
    raise SystemExit(1 if failures else 0)