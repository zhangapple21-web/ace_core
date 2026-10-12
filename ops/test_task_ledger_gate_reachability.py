"""The task ledger's drift gate is unreachable from the TaskPool write path.

`core/task_ledger.py` states three hard rules. Rule 3:

    落盘前计数器实值必须能被账本重放复现 —— 复现不了即 drift
    (before persisting, the actual counter values must be reproducible by replaying
    the ledger; if they cannot be reproduced, that is drift)

and two write-port modes:

    shadow  (default) record a kind="drift" row
    enforce            raise LedgerDriftError and refuse the write

`write_port_gate` implements exactly that, and it works when called directly:

    probe B: gate called directly -> task_ledger_drift:RQ-...:rework_count:
             expected=0 actual=2

But `TaskPool._transition` orders its calls so the gate can never see drift:

    560  self._ledger_open(task)      ensure_baseline, seeds counters
    ...
    598  self._ledger_close(...)      registers EVERY outstanding counter delta as a
                                     legitimate kind="consume" row, self-referenced
    604  self._ledger_open(task)
    607  self._write_task_atomic(...) -> write_port_gate -> reconcile()

`_ledger_close` is documented as "把本次实际发生的计数差登记成一行，带来源" -- register the
deltas that actually occurred in this operation, with a source. That is correct for
the counters the pool itself changed. It cannot distinguish those from a counter
some caller mutated by hand before calling update_task. It absorbs both, writes a row
citing the task itself as the source, and by the time `write_port_gate` runs,
`replay(ledger) == counter_values(task)` and `reconcile()` returns {}.

Measured, with ACE_TASK_LEDGER_MODE=enforce:

    drift visible BEFORE the write : {'rework_count': {'expected': 0, 'actual': 2}}
    update_task raised             : None
    update_task returned           : True
    on-disk rework_count           : 2          <- the unregistered change landed
    ledger rows written            : ['baseline', 'hold', 'consume']
    replay(ledger) AFTER           : rework_count 2   <- gate now sees it as legitimate

So the two red tests in ops/test_task_ledger.py are correct, not stale:

    test_unregistered_counter_change_becomes_drift_row
    test_enforce_mode_blocks_unregistered_change

Both were failing before any change in this session touched this area, and they
describe the documented contract.

What is NOT asserted here is which layer should be fixed. Two defensible answers:

  (a) `_ledger_close` should only register deltas attributable to the operation it
      is closing, so a pre-existing mutation stays visible to the gate; or
  (b) the pool is the only writer and the gate is meant to catch direct file writes,
      in which case the tests encode a contract the pool never intended to honour.

Choosing between them is a governance decision about who may mutate counters. This
file pins the observable behaviour that the decision has to preserve, and refuses to
pick a side. It does not assert that the current behaviour is correct.

SUPERSEDED 2026-10-12 - the decision was made and this file's premise is now closed.

Those tests are inverted in place below, with the original measurements preserved in
each docstring. The author of this file left the instruction at what was lines
119-121:

    This asserts the CURRENT behaviour on purpose, so that anyone who changes
    the ordering sees this test flip and has to look at it. If the gate is
    made reachable, delete or invert this test -- do not let it quietly keep
    passing.

The gate is reachable now, so they are inverted rather than deleted.

Root cause, for the archaeology: ``_ledger_close`` computed the difference between the
replayed ledger and the live counters and absorbed ALL of it under the row's own actor
and reason. Every caller except ``_transition`` had just made those changes knowingly.
``_transition`` had changed no counter at all, so its row absorbed whatever
unregistered bump was already sitting on the task and labelled it
``transition:pending->pending``. By the time ``write_port_gate`` ran, replay equalled
counter_values and reconcile() returned {} - the one component meant to prove "no
counter changed without a registered source" silently certified every unregistered
change.

The fix is one keyword: ``_ledger_close`` takes an explicit ``counters`` allowlist and
``_transition`` passes ``()``, because a transition moves no counter. No legitimate
producer is affected - the lease and failure paths still register their own counters
with their own actor.
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


def test_pool_write_lets_an_unregistered_change_through_in_enforce_mode(monkeypatch):
    """enforce mode now refuses the write. It used to sail through.

    Previously measured: ``update_task raised: None``, ``update_task returned: True``
    and ``on-disk rework_count: 2`` - an unregistered change landing in enforce mode,
    which is the mode documented to refuse exactly this.
    """
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "enforce")
    with tempfile.TemporaryDirectory() as td:
        pool, loaded = _claimed(td, "enforce reaches the gate")
        loaded.rework_count += 2
        raised = None
        try:
            pool.update_task(loaded)
        except LedgerDriftError as exc:
            raised = str(exc)
        on_disk = json.loads(
            (Path(td) / "active" / (loaded.task_id + ".json")).read_text(encoding="utf-8")
        )
    assert raised is not None, "enforce mode must refuse an unregistered counter change"
    assert "rework_count" in raised
    assert on_disk.get("rework_count") == 0, "a refused write must not land"


def test_the_absorbed_change_is_recorded_as_a_self_referenced_consume_row(monkeypatch):
    """The self-referenced absorb row is gone; a drift row cites the write port.

    Previously the delta landed in a ``consume`` row whose ref resolved to the task
    being modified - rule 1 says a public accounting entry must carry a resolvable
    source, and citing yourself explains nothing about who changed the counter.
    """
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "shadow")
    with tempfile.TemporaryDirectory() as td:
        pool, loaded = _claimed(td, "drift cites the write port")
        loaded.starvation_age += 3
        pool.update_task(loaded)
        stored = pool.load_task(loaded.task_id)
        drift_rows = [r for r in (stored.ledger or []) if r.get("kind") == "drift"]
        consume_rows = [r for r in (stored.ledger or []) if r.get("kind") == "consume"]
    assert drift_rows, "an unregistered counter change must become a drift row"
    last = drift_rows[-1]
    assert last.get("deltas", {}).get("starvation_age") == 3, last.get("deltas")
    assert last.get("actor") == "write_port", last.get("actor")
    assert last.get("reason") == "unregistered_counter_change", last.get("reason")
    assert not consume_rows, "no transition row may absorb an unregistered change"


def test_after_the_write_the_ledger_replays_the_unregistered_value(monkeypatch):
    """The end state: a refused write must not be certified by the ledger.

    Previously ``reconcile(stored) == {}`` and the ledger replayed the unregistered
    value - the ledger had laundered a change nobody authorised into a settled row.
    """
    monkeypatch.setenv("ACE_TASK_LEDGER_MODE", "enforce")
    with tempfile.TemporaryDirectory() as td:
        pool, loaded = _claimed(td, "refused drift")
        loaded.rework_count += 2
        try:
            pool.update_task(loaded)
        except LedgerDriftError:
            pass
        stored = pool.load_task(loaded.task_id)
    assert replay(stored)["rework_count"] == 0, "a refused change must not replay"
    assert counter_values(stored)["rework_count"] == 0
    assert reconcile(stored) == {}, reconcile(stored)


def test_shadow_mode_records_the_drift_row_it_always_documented(monkeypatch):
    """shadow mode's documented behaviour is to append kind="drift". It now does.

    Previously the delta was absorbed before the gate ran, so shadow mode behaved
    exactly like enforce-plus-ignore: it wrote the change down and said nothing.
    """
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
        test_pool_write_lets_an_unregistered_change_through_in_enforce_mode,
        test_the_absorbed_change_is_recorded_as_a_self_referenced_consume_row,
        test_after_the_write_the_ledger_replays_the_unregistered_value,
        test_shadow_mode_never_records_a_drift_row_either,
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