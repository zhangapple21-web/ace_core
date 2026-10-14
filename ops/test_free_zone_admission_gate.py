"""The admission gate: a Free Zone conclusion is not automatically work.

The defect it pins: `_create_followup_task` deduplicated on a source_ref
containing the distillation hash, so every new distillation was a new task
forever. Duplicates were structurally impossible; merit was never asked about.
These tests make the questions mandatory.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from core import free_zone_admission_gate as gate  # noqa: E402


def _distillation(experiment_id="EXP-1", pattern=None):
    return {
        "experiment_id": experiment_id,
        "pattern": pattern if pattern is not None else (
            "A bounded, checkable claim about how the gateway responds "
            "when the transport drops mid-stream, worth one independent check."),
        "outcome": "INCONCLUSIVE",
    }


def _task(experiment_id=None, source_ref=""):
    outputs = {}
    if experiment_id or source_ref:
        holder = {}
        admission = {}
        if experiment_id:
            holder["free_zone_reflection"] = {"experiment_id": experiment_id}
        if source_ref:
            admission["source_ref"] = source_ref
        outputs = {"free_zone_reflection": holder.get("free_zone_reflection"),
                   "admission": admission}
    return {"task_id": "RQ-x", "outputs": outputs}


@pytest.fixture()
def workspace(tmp_path):
    return tmp_path


# ------------------------------------------------------------------ receivable

def test_a_pattern_too_short_to_verify_is_not_receivable(workspace):
    ok, why = gate.is_receivable(_distillation(pattern="too short"))
    assert ok is False
    assert "too short" in why


def test_an_empty_record_is_not_receivable(workspace):
    ok, _ = gate.is_receivable({})
    assert ok is False


def test_a_substantive_pattern_is_receivable(workspace):
    ok, why = gate.is_receivable(_distillation())
    assert ok is True


# ------------------------------------------------------------------ unmet

def test_a_live_task_on_the_same_experiment_makes_it_unmet(workspace):
    ok, why = gate.is_unmet("EXP-1", _distillation(), [_task(experiment_id="EXP-1")])
    assert ok is False
    assert "already verifies" in why


def test_a_live_task_covering_it_by_admission_ref_is_unmet(workspace):
    ok, _ = gate.is_unmet("EXP-2", _distillation("EXP-2"),
                          [_task(source_ref="free_zone_reflection:EXP-2:hash")])
    assert ok is False


def test_an_experience_already_deposited_makes_it_met(workspace):
    ok, why = gate.is_unmet("EXP-3", _distillation("EXP-3"), [],
                            experiences=[{"experience_id": "E-1",
                                          "source_task_id": "EXP-3"}])
    assert ok is False
    assert "already deposited" in why


def test_an_uncovered_experiment_is_unmet(workspace):
    ok, _ = gate.is_unmet("EXP-4", _distillation("EXP-4"), [_task(experiment_id="OTHER")])
    assert ok is True


# ------------------------------------------------------------------ the cap

def test_within_cap_admits_until_the_daily_cap(workspace):
    state = {"admits": {"2026-01-01": gate.DAILY_ADMISSION_CAP - 1}}
    ok, why = gate.within_cap(state, "2026-01-01")
    assert ok is True
    state = {"admits": {"2026-01-01": gate.DAILY_ADMISSION_CAP}}
    ok, why = gate.within_cap(state, "2026-01-01")
    assert ok is False
    assert "cap" in why


def test_yesterdays_admissions_do_not_consume_today(workspace):
    state = {"admits": {"2026-01-01": 99}}
    ok, _ = gate.within_cap(state, "2026-01-02")
    assert ok is True


# ------------------------------------------------------------------ the gate

def test_admit_when_receivable_unmet_and_within_cap(workspace):
    admit, why, experiment_id = gate.should_admit(
        workspace, _distillation("EXP-A"), live_tasks=[], state={"admits": {}})
    assert admit is True
    assert experiment_id == "EXP-A"


def test_refuse_an_unverifiable_conclusion(workspace):
    admit, why, _ = gate.should_admit(
        workspace, _distillation("EXP-B", pattern="short"), live_tasks=[])
    assert admit is False
    assert "too short" in why


def test_refuse_what_is_already_covered(workspace):
    admit, why, _ = gate.should_admit(
        workspace, _distillation("EXP-C"),
        live_tasks=[_task(experiment_id="EXP-C")])
    assert admit is False
    assert "already" in why


def test_refuse_beyond_the_daily_cap(workspace):
    from datetime import date
    today = date.today().isoformat()
    admit, why, _ = gate.should_admit(
        workspace, _distillation("EXP-D"), live_tasks=[],
        state={"admits": {today: gate.DAILY_ADMISSION_CAP}})
    assert admit is False
    assert "cap" in why


def test_a_refusal_is_recorded_not_dropped(workspace):
    gate.record_refusal(workspace, "EXP-E", "too short to verify")
    log = workspace / "08_GOVERNANCE" / "free_zone_exchange" / \
        "relay_admission_refusals.jsonl"
    assert log.exists()
    entries = [json.loads(line) for line in
               log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert entries[-1]["experiment_id"] == "EXP-E"
    assert entries[-1]["reason"] == "too short to verify"


def test_admissions_are_counted_per_day(workspace):
    gate.record_admission(workspace, "EXP-F")
    gate.record_admission(workspace, "EXP-G")
    state = json.loads((workspace / gate.STATE_FILE).read_text(encoding="utf-8"))
    from datetime import date
    assert state["admits"][date.today().isoformat()] == 2


def test_the_cap_is_deliberately_small():
    """A cap that admits as much as it likes is not a cap.

    The unbounded linked path produced over a hundred tasks in a day, every one
    of which ran the same mould to the same non-convergence ceiling.
    """
    assert gate.DAILY_ADMISSION_CAP <= 3