#!/usr/bin/env python3
"""Focused tests for the roster receipt: the diff, the quality, the alarm discipline.

The roster and the role table are injected rather than probed, so these tests are
offline and deterministic. That is the right seam here for a specific reason: the
probe itself belongs to `free_model_discovery` and is tested beside it in
`ops/test_free_model_discovery.py`, while the logic that can *lie* lives in this
file - what counts as a change, what a failed probe is forbidden to claim, and
whether a steady roster stays silent. The live path is exercised by running the
component, which the hourly tick does; a receipt whose tests all stub the probe
proves nothing about the probe, and this file does not pretend otherwise.

Run: py -3 ops/test_opencode_roster_receipt.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ops.opencode_roster_receipt import (  # noqa: E402
    RECEIPT_RELPATH,
    STATUS_DEGRADED,
    STATUS_FRESH,
    STATUS_PROBE_FAILED,
    build_receipt,
    record_change,
    write_receipt,
)

T1 = 1_700_000_000.0
T2 = T1 + 3600.0
T3 = T2 + 3600.0
MODEL_A = "opencode/beam-free"
MODEL_B = "opencode/fledge-alpha-free"


class CapturingObserver:
    """Stands in for RuntimeObserver so the recorded payload can be asserted."""

    def __init__(self) -> None:
        self.calls = []

    def record(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


def roster(live, *, error=None, available=True):
    return {
        "available": available,
        "module_error": None if available else "ImportError",
        "live": list(live),
        "cache": {
            "source": "cli", "error": error, "checked_at": T1,
            "age_seconds": 0.1, "model_count": len(live), "ttl_seconds": 900,
        },
    }


def roles(selection, *, candidates=None):
    return {
        "available": True,
        "module_error": None,
        "roles": {
            role: {"selected": chosen, "candidates": (candidates or {}).get(role, []),
                   "retired": []}
            for role, chosen in selection.items()
        },
        "flat_table": {role: chosen for role, chosen in selection.items() if chosen},
        "candidate_table": candidates or {},
    }


def test_a_first_receipt_states_there_was_nothing_to_compare():
    first = build_receipt(Path("."), roster=roster([MODEL_A]), roles=roles({"r": MODEL_A}),
                          previous={}, now=T1)
    assert first["status"] == STATUS_FRESH, first["status"]
    change = first["change"]
    assert change["changed"] is None, change
    assert change["appeared"] == [] and change["retired"] == [], change
    assert change["roster_changed_at"] is None, change
    assert change["roster_first_seen_at"] == first["written_at"], change


def test_a_retirement_is_dated():
    first = build_receipt(Path("."), roster=roster([MODEL_A, MODEL_B]),
                          roles=roles({"r": MODEL_A}), previous={}, now=T1)
    second = build_receipt(Path("."), roster=roster([MODEL_A]),
                           roles=roles({"r": MODEL_A}), previous=first, now=T2)
    change = second["change"]
    assert change["changed"] is True, change
    assert change["retired"] == [MODEL_B], change
    assert change["appeared"] == [], change
    assert change["roster_changed_at"] == second["written_at"], change
    assert change["roster_first_seen_at"] == second["written_at"], change


def test_a_steady_roster_carries_the_change_time_forward_and_stays_silent():
    first = build_receipt(Path("."), roster=roster([MODEL_A, MODEL_B]),
                          roles=roles({"r": MODEL_A}), previous={}, now=T1)
    moved = build_receipt(Path("."), roster=roster([MODEL_A]),
                          roles=roles({"r": MODEL_A}), previous=first, now=T2)
    steady = build_receipt(Path("."), roster=roster([MODEL_A]),
                           roles=roles({"r": MODEL_A}), previous=moved, now=T3)
    change = steady["change"]
    assert change["changed"] is False, change
    assert change["roster_changed_at"] == moved["change"]["roster_changed_at"], change
    assert change["roster_first_seen_at"] == moved["change"]["roster_first_seen_at"], change

    observer = CapturingObserver()
    outcome = record_change(Path("."), steady, observer=observer)
    assert outcome["recorded"] is False, outcome
    assert observer.calls == [], observer.calls


def test_a_failed_probe_does_not_fabricate_a_rotation_and_does_not_alarm():
    first = build_receipt(Path("."), roster=roster([MODEL_A, MODEL_B]),
                          roles=roles({"r": MODEL_A}), previous={}, now=T1)
    failed = build_receipt(Path("."), roster=roster([MODEL_A], error="cli_probe_failed"),
                           roles=roles({"r": MODEL_A}), previous=first, now=T2)
    assert failed["status"] == STATUS_PROBE_FAILED, failed["status"]
    change = failed["change"]
    assert change["changed"] is None, change
    assert change["appeared"] == [] and change["retired"] == [], change
    assert change["roster_changed_at"] == first["change"]["roster_changed_at"], change

    observer = CapturingObserver()
    outcome = record_change(Path("."), failed, observer=observer)
    assert outcome["recorded"] is False, outcome
    assert observer.calls == [], observer.calls


def test_an_empty_tier_is_a_roster_of_zero_and_degrades():
    first = build_receipt(Path("."), roster=roster([MODEL_A, MODEL_B]),
                          roles=roles({"r": MODEL_A}), previous={}, now=T1)
    empty = build_receipt(Path("."), roster=roster([], error="no_free_models_offered"),
                          roles=roles({"r": None}), previous=first, now=T2)
    assert empty["status"] == STATUS_DEGRADED, empty["status"]
    assert empty["quality"] == "empty_tier", empty["quality"]
    change = empty["change"]
    assert change["changed"] is True, change
    assert change["retired"] == sorted([MODEL_A, MODEL_B]), change


def test_a_starved_role_degrades_and_raises_the_severity():
    first = build_receipt(Path("."), roster=roster([MODEL_A]),
                          roles=roles({"writer": MODEL_A}), previous={}, now=T1)
    starved = build_receipt(
        Path("."), roster=roster([MODEL_A]),
        roles=roles({"writer": None}, candidates={"writer": [MODEL_B]}),
        previous=first, now=T2)
    assert starved["status"] == STATUS_DEGRADED, starved["status"]
    assert starved["roles"]["starved"] == ["writer"], starved["roles"]

    observer = CapturingObserver()
    outcome = record_change(Path("."), starved, observer=observer)
    assert outcome["recorded"] is True, outcome
    assert len(observer.calls) == 1, observer.calls
    call = observer.calls[0]
    assert call["severity"] == "high", call
    assert call["category"] == "environment_change", call
    assert call["system_state"]["starved"] == ["writer"], call


def test_the_dedup_key_identifies_the_change_not_the_moment():
    first = build_receipt(Path("."), roster=roster([MODEL_A, MODEL_B]),
                          roles=roles({"r": MODEL_A}), previous={}, now=T1)
    second = build_receipt(Path("."), roster=roster([MODEL_A]),
                           roles=roles({"r": MODEL_A}), previous=first, now=T2)
    observer = CapturingObserver()
    record_change(Path("."), second, observer=observer)
    record_change(Path("."), second, observer=observer)
    assert observer.calls[0]["dedup_key"] == observer.calls[1]["dedup_key"], observer.calls

    third = build_receipt(Path("."), roster=roster([]), roles=roles({"r": None}),
                          previous=second, now=T3)
    record_change(Path("."), third, observer=observer)
    assert observer.calls[2]["dedup_key"] != observer.calls[0]["dedup_key"], observer.calls


def test_the_receipt_is_written_atomically_and_parses_back():
    workdir = Path(tempfile.mkdtemp(prefix="ace_roster_receipt_"))
    try:
        receipt = build_receipt(workdir, roster=roster([MODEL_A]),
                                roles=roles({"r": MODEL_A}), previous={}, now=T1)
        receipt["change"]["observation"] = {"recorded": False, "reason": "test"}
        path = write_receipt(workdir, receipt)
        assert path == workdir.resolve() / RECEIPT_RELPATH, path
        readback = json.loads(path.read_text(encoding="utf-8"))
        assert readback["schema"] == "ace.opencode_roster_receipt.v1", readback
        assert readback["roster"]["live"] == [MODEL_A], readback
        leftovers = sorted(p.name for p in path.parent.iterdir() if p.name.endswith(".tmp"))
        assert leftovers == [], leftovers
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


def test_a_bom_prefixed_previous_receipt_still_compares():
    """The counterexample that found the silent reset: a BOM must not hide a roster."""
    workdir = Path(tempfile.mkdtemp(prefix="ace_roster_bom_"))
    try:
        previous = build_receipt(workdir, roster=roster([MODEL_A, MODEL_B]),
                                 roles=roles({"r": MODEL_A}), previous={}, now=T1)
        previous_path = workdir.resolve() / RECEIPT_RELPATH
        previous_path.parent.mkdir(parents=True, exist_ok=True)
        previous_path.write_text("\ufeff" + json.dumps(previous, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
        now = build_receipt(workdir, roster=roster([MODEL_A]),
                            roles=roles({"r": MODEL_A}), now=T2)
        change = now["change"]
        assert change["comparison_state"] == "ok", change
        assert change["changed"] is True, change
        assert change["retired"] == [MODEL_B], change
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


def test_an_unreadable_previous_receipt_is_named_not_treated_as_first():
    workdir = Path(tempfile.mkdtemp(prefix="ace_roster_bad_"))
    try:
        path = workdir.resolve() / RECEIPT_RELPATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not json at all", encoding="utf-8")
        now = build_receipt(workdir, roster=roster([MODEL_A]),
                            roles=roles({"r": MODEL_A}), now=T2)
        change = now["change"]
        assert change["comparison_state"] == "unreadable", change
        assert change["changed"] is None, change
        assert "unusable" in change["compared_to"], change
        assert "first receipt" not in change["compared_to"], change
    finally:
        import shutil
        shutil.rmtree(workdir, ignore_errors=True)


def main() -> int:
    tests = [(name, value) for name, value in sorted(globals().items())
             if name.startswith("test_") and callable(value)]
    failures = []
    for name, test in tests:
        try:
            test()
        except AssertionError as exc:
            failures.append(name)
            print(f"FAIL {name}: {exc}")
        else:
            print(f"ok   {name}")
    print(f"{len(tests) - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
