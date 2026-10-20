"""The execution discipline status machine was a no-op.

`core/execution_discipline._get_envelope` converts the stored dict into an
`ExecutionDiscipline` dataclass and returns it, but never writes it back.
`record_event` then assigned scalar fields on that detached copy:

    envelope.last_event = event
    envelope.status = "stopped"       # event == "stop"
    envelope.status = "in_progress"   # lifecycle_transition -> active
    envelope.status = "stopped"       # -> blocked/rejected/archived/graveyard
    envelope.status = event           # verified/approved/archived
    envelope.status = "in_progress"   # started/researched/validated/reviewed

Every one of those assignments was silently discarded.

Nested containers survived, because `from_legacy_dict` hands `from_dict` the live
dict and the nested `events` list / `pipeline` dict / `stop` dict are the same
objects, so in-place mutation reached the stored envelope. Only scalar rebinding was
lost. That is why the failure looked partial: `stop.reason` arrived, `status` did
not.

This was introduced by the dict -> dataclass refactor. The dict-based code mutated in
place and worked. Three tests in ops/test_execution_discipline.py have been failing
since then; two report `TypeError: 'ExecutionDiscipline' object is not subscriptable`
because they still subscript the return value, and the third asserts that blocking a
task marks the envelope stopped, which this bug silently prevented.

Scope note: `record_checkpoint` and `add_evidence_ledger_entry` also mutate through
`_get_envelope`, but they only touch nested containers, so they persist by accident.
They are not changed here; asserting they keep working is the point of
test_container_mutations_still_persist.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.execution_discipline import (  # noqa: E402
    PROTOCOL_VERSION,
    START_PROTOCOL_VERSION,
    add_evidence_ledger_entry,
    build_execution_discipline,
    ensure_execution_discipline,
    record_checkpoint,
    record_event,
)
from core.task import Task  # noqa: E402
from ops.test_support import FixtureTaskPool  # noqa: E402


def _task():
    t = Task(task_id="RQ-ST-001", title="架构集成任务", hypothesis="保留边界", outputs={})
    ensure_execution_discipline(t)
    return t


def test_record_event_persists_last_event_through_the_dict_round_trip():
    task = _task()
    record_event(task, "started", actor="test")
    stored = task.outputs["execution_discipline"]
    assert isinstance(stored, dict), "envelope must stay JSON-serialisable"
    assert stored["last_event"] == "started", (
        "last_event assignment was discarded: stored=%r" % (stored.get("last_event"),)
    )


def test_stop_event_persists_status():
    task = _task()
    record_event(task, "started", actor="test")
    record_event(task, "stop", actor="test", reason="evidence_gap")
    stored = task.outputs["execution_discipline"]
    assert stored["status"] == "stopped", (
        "status assignment was discarded: stored=%r" % (stored.get("status"),)
    )
    assert stored["stop"]["reason"] == "evidence_gap"


def test_blocking_a_task_marks_the_envelope_stopped():
    """The production symptom: move to blocked, envelope stays prepared."""
    with tempfile.TemporaryDirectory() as td:
        pool = FixtureTaskPool(os.path.join(td, "tasks"))
        created = pool.create_task(
            "架构集成任务", hypothesis="保留边界", creator="test", tags=["complexity:complex"]
        )
        pool.move_task(created.task_id, "blocked", actor="test", reason="evidence_gap")
        saved = pool.load_task(created.task_id)
        envelope = saved.outputs["execution_discipline"]

    assert envelope["status"] == "stopped", (
        "blocking a task must stop its envelope, got %r (this is the bug that "
        "'prepared' was reported instead)" % (envelope.get("status"),)
    )
    assert envelope["stop"]["reason"] == "evidence_gap"


def test_activating_a_task_marks_the_envelope_in_progress():
    with tempfile.TemporaryDirectory() as td:
        pool = FixtureTaskPool(os.path.join(td, "tasks"))
        created = pool.create_task("startable", creator="test")
        pool.move_task(created.task_id, "active", actor="test")
        envelope = pool.load_task(created.task_id).outputs["execution_discipline"]
    assert envelope["status"] == "in_progress", envelope.get("status")


def test_archived_task_ends_stopped_with_a_reason_not_status_archived():
    """Why an archived task's envelope status is "stopped", not "archived".

    core/task.py::_transition records, in this order for approved -> archived:
        1. lifecycle_transition(to_status=archived)  -> status = "stopped"
        2. archived                                   -> status = "archived"
        3. stop                                       -> status = "stopped"

    Step 2 is always clobbered by step 3. That ordering is load-bearing, not an
    accident: validate_execution_discipline recognises only "stopped" and
    {"prepared","in_progress","verified","reviewed","approved"}. A status of
    "archived" falls through both branches, so the stopped-without-reason check
    would silently stop applying to archived tasks.

    So the correct invariant is: an archived task's envelope is stopped, and it
    carries a stop reason. Asserted here so the invariant is deliberate rather than
    an accident nobody is watching.
    """
    with tempfile.TemporaryDirectory() as td:
        pool = FixtureTaskPool(os.path.join(td, "tasks"))
        created = pool.create_task("completable", creator="test")
        # pending -> archived and active -> archived are both illegal; the only route
        # is approved -> archived. The refusals are correct fail-closed behaviour.
        assert pool.move_task(created.task_id, "archived", reason="done") is None
        pool.move_task(created.task_id, "active", actor="test")
        assert pool.move_task(created.task_id, "archived", reason="done") is None
        pool.move_task(created.task_id, "review", actor="test")
        pool.move_task(created.task_id, "approved", actor="test")
        pool.move_task(created.task_id, "archived", actor="test", reason="done")
        envelope = pool.load_task(created.task_id).outputs["execution_discipline"]

    assert envelope["status"] == "stopped", envelope.get("status")
    assert envelope["stop"]["reason"] == "done", envelope.get("stop")
    # The `archived` event is still recorded, so the lifecycle stays auditable even
    # though the status it would have set is superseded.
    assert "archived" in [e["event"] for e in envelope["events"]], envelope["events"]


def test_container_mutations_still_persist():
    """Regression guard: the write-back must not lose what already worked."""
    task = _task()
    record_event(task, "started", actor="test")
    record_checkpoint(task, "preflight", actor="test", evidence=["manifest"])
    add_evidence_ledger_entry(task, "runtime", {"status": "observed"})
    stored = task.outputs["execution_discipline"]

    assert [e["event"] for e in stored["events"]] == ["prepared", "started"], stored["events"]
    assert stored["checkpoints"][0]["name"] == "preflight"
    assert stored["evidence_ledger"]["runtime"] == [{"status": "observed"}]
    # "started" maps to the execute stage, not a stage named "start".
    assert stored["pipeline"]["execute"]["last_event"] == "started", stored["pipeline"]


def test_write_back_is_lossless_for_every_declared_field():
    """_set_envelope serialises via asdict(); a field absent from the dataclass
    would be dropped on every event. Assert the round trip is complete."""
    task = _task()
    before = dict(task.outputs["execution_discipline"])
    record_event(task, "started", actor="test")
    after = task.outputs["execution_discipline"]

    assert set(before) == set(after), "fields lost across write-back: %r" % (
        set(before) ^ set(after),
    )
    assert after["protocol"] == PROTOCOL_VERSION, after.get("protocol")
    assert after["start_protocol"] == START_PROTOCOL_VERSION, after.get("start_protocol")
    # Every scalar the dataclass declares must still be present and equal.
    for field in ("status", "last_event", "complexity", "mode", "source", "created_at"):
        assert field in after, "%s disappeared across write-back" % field


def test_build_execution_discipline_returns_a_typed_object_not_a_dict():
    """Why two of the three pre-existing failures report TypeError instead of an
    assertion error: the return type changed and the tests were never updated."""
    envelope = build_execution_discipline(
        title="架构集成审计", hypothesis="验证现有边界", priority="high",
        tags=["integration"], admission={"evidence": [{"source": "f", "content": "k"}]},
    )
    assert not hasattr(envelope, "__getitem__"), (
        "if this now returns a dict, the two TypeError failures were a different bug"
    )
    assert envelope.protocol == PROTOCOL_VERSION
    assert envelope.complexity == "complex"
    assert envelope.to_dict()["protocol"] == PROTOCOL_VERSION


if __name__ == "__main__":
    failures = 0
    for fn in (
        test_record_event_persists_last_event_through_the_dict_round_trip,
        test_stop_event_persists_status,
        test_blocking_a_task_marks_the_envelope_stopped,
        test_activating_a_task_marks_the_envelope_in_progress,
        test_archived_task_ends_stopped_with_a_reason_not_status_archived,
        test_container_mutations_still_persist,
        test_write_back_is_lossless_for_every_declared_field,
        test_build_execution_discipline_returns_a_typed_object_not_a_dict,
    ):
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s\n      %s" % (fn.__name__, exc))
    print("failures=%d" % failures)
    raise SystemExit(1 if failures else 0)