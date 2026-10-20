"""Regression for the rework-loop defect in execution_discipline.

Before this fix, 275 of 461 persisted envelopes carried `stage_regression`,
every worker submission was refused with "nothing was written", and the 13
blocked tasks were the same bug wearing a different label.

Three properties are pinned. The first two existed before and must survive; the
third is the defect itself. A fix that only satisfies the third is not a fix, it
is a gate that stopped working.
"""

from __future__ import annotations

import glob
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import execution_discipline as ed  # noqa: E402


class _Envelope(dict):
    """validate_execution_discipline only ever touches these attributes."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(name) from exc


class _FakeTask:
    """Minimal task stand-in: _get_envelope reads outputs.execution_discipline."""

    def __init__(self, envelope):
        self.outputs = {"execution_discipline": envelope}


def _validated(events, **envelope_kwargs):
    """Build an envelope-shaped payload for validate_execution_discipline()."""
    payload = {
        "protocol": ed.PROTOCOL_VERSION,
        "start_protocol": ed.START_PROTOCOL_VERSION,
        "complexity": "complex",
        "status": "in_progress",
        "events": events,
        "pipeline": {},
        "stop": {},
    }
    payload.update(envelope_kwargs)
    return _FakeTask(_Envelope(payload))


def _regressions(events):
    return [
        code
        for code in ed.validate_execution_discipline(_validated(events)).get("errors", [])
        if code.startswith("stage_regression")
    ]


def test_validated_and_reviewed_are_the_same_stage():
    """Reading then recording on one pass is not a backward step."""

    assert ed._EVENT_STAGE["reviewed"] == ed._EVENT_STAGE["validated"]


def test_single_pass_validator_order_is_accepted():
    assert _regressions([
        {"event": "prepared"},
        {"event": "researched"},
        {"event": "reviewed"},
        {"event": "validated", "outcome": "approved"},
    ]) == []


def test_real_rework_loop_is_not_a_regression():
    """The defect: research -> validate -> rework -> research is a loop."""

    assert _regressions([
        {"event": "prepared"},
        {"event": "researched"},
        {"event": "reviewed"},
        {"event": "validated", "outcome": "rework_pending"},
        {"event": "researched"},
        {"event": "reviewed"},
        {"event": "validated", "outcome": "approved"},
    ]) == []


def test_multiple_rework_rounds_are_not_regressions():
    assert _regressions([
        {"event": "prepared"}, {"event": "researched"},
        {"event": "reviewed"}, {"event": "validated", "outcome": "rework_pending"},
        {"event": "researched"}, {"event": "reviewed"},
        {"event": "validated", "outcome": "rework_pending"},
        {"event": "researched"}, {"event": "reviewed"},
        {"event": "validated", "outcome": "approved"},
    ]) == []


def test_terminal_verdict_after_stop_is_epilogue():
    """How the 13 blocked tasks were shaped."""

    assert _regressions([
        {"event": "prepared"},
        {"event": "researched"},
        {"event": "reviewed"},
        {"event": "validated", "outcome": "rework_pending"},
        {"event": "researched"},
        {"event": "reviewed"},
        {"event": "stop"},
        {"event": "validated", "outcome": "blocked_non_convergent"},
        {"event": "stop"},
    ]) == []


def test_genuine_out_of_order_within_one_attempt_is_still_caught():
    assert _regressions([
        {"event": "prepared"},
        {"event": "researched"},
        {"event": "validated", "outcome": "approved"},
        {"event": "prepared"},
    ]) != []


def test_genuine_rewind_within_one_attempt_is_still_caught():
    assert _regressions([
        {"event": "prepared"},
        {"event": "researched"},
        {"event": "reviewed"},
        {"event": "validated", "outcome": "approved"},
        {"event": "researched"},
    ]) != []


def test_early_stage_reappearing_after_stop_is_still_caught():
    assert _regressions([
        {"event": "prepared"},
        {"event": "researched"},
        {"event": "stop"},
        {"event": "researched"},
    ]) != []


def test_persisted_corpus_no_longer_regresses():
    """The population claim, checked against real files rather than fixtures."""

    pool = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "task_pool")
    if not os.path.isdir(pool):
        return
    live_bad, terminal_bad, checked = [], [], 0
    for path in glob.glob(os.path.join(pool, "*", "*.json")):
        try:
            data = json.load(io.open(path, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict) or "task_id" not in data:
            continue
        disc = (data.get("outputs") or {}).get("execution_discipline") or {}
        events = disc.get("events") if isinstance(disc, dict) else None
        if not events:
            continue
        checked += 1
        payload = {
            "protocol": ed.PROTOCOL_VERSION,
            "start_protocol": ed.START_PROTOCOL_VERSION,
            "complexity": disc.get("complexity") or "complex",
            "status": disc.get("status") or "in_progress",
            "events": events,
            "pipeline": disc.get("pipeline") or {},
            "stop": disc.get("stop") or {},
        }
        codes = [
            code
            for code in ed.validate_execution_discipline(
                _FakeTask(_Envelope(payload))
            ).get("errors", [])
            if code.startswith("stage_regression")
        ]
        if not codes:
            continue
        status = data.get("status")
        if status in {"pending", "active", "review", "blocked"}:
            live_bad.append((data["task_id"], status, codes))
        else:
            terminal_bad.append((data["task_id"], status, codes))

    print("checked=%d live_regressions=%d terminal_regressions=%d"
          % (checked, len(live_bad), len(terminal_bad)))
    for tid, status, codes in terminal_bad:
        print("  terminal (left flagged on purpose): %s %s %s" % (tid, status, codes))
    # No task that can still be worked may carry this defect.
    assert live_bad == [], "live tasks still regress: %r" % (live_bad,)


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except AssertionError as exc:
                failures += 1
                print("FAIL %s: %s" % (name, exc))
    print("failures=%d" % failures)
    sys.exit(1 if failures else 0)
