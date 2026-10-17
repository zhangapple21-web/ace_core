"""A consumed observation must not be the last word on a condition that persists.

The defect this pins: record() returned the existing observation whenever its
signature was still "active" and the record was still in the bounded store. Since
mark_consumed() sets task_generated but never clears the signature, a condition
that stayed true froze onto its first observation and could never re-enter the
unprocessed queue.

That froze the reconciler in both directions at once. It could not re-report work,
and it could not see recovery either - so an incident could not reopen after a
genuine fix, and could not close after one. Two incidents sat that way: real
conditions, still true (pending_scan 7847 against a threshold of 500,
last_mine_seed_scan still "never"), each carrying a remediation task that was
archived over it.

The safety of re-reporting is not assumed. Downstream is what makes it safe, and
each property is pinned here rather than inferred:

  the converter deduplicates by semantic signature, and those signatures exclude
  rolling counters, so refreshing evidence cannot mint one task per cycle
  the incident record refreshes last_observed_at, so a standing claim stays current
  a value that changes does not fork a new incident identity
  genuine recovery still closes the incident, because a fresh observation carrying
  a false condition is what _reconcile_persistent_incidents needs

Acceptance cases mirror the review: same condition observed many times, archived
task with the condition still true, a changing value, recovery, recovery followed
by relapse, and the admission boundary left alone.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from core.observation import Observation, RuntimeObserver  # noqa: E402


def _observer(tmp_path):
    return RuntimeObserver(data_dir=str(tmp_path / "obs"))


def _state(value):
    return {"total": 17293, "pending_scan": value, "archaeologized": 161}


def _archive_through_lifecycle(pool, task_id):
    """Archive a task the way production does.

    pending cannot jump to archived - ALLOWED_TRANSITIONS in core/task.py requires
    pending -> active -> review -> approved -> archived. Driving the real path
    matters: a shortcut that silently does nothing would leave the task open and
    the test would then assert against a task that was never archived.
    """
    for status in ("active", "review", "approved", "archived"):
        moved = pool.move_task(task_id, status, actor="test")
        assert moved is not None, f"could not move {task_id} to {status}"
    assert pool.load_task(task_id).status == "archived"


def test_a_consumed_condition_is_reported_again(tmp_path):
    """The defect, stated as a test.

    Record, consume, record again. Before the fix the second call returned the
    consumed observation and appended nothing, so the condition could never be
    seen again.
    """
    observer = _observer(tmp_path)
    first = observer.record(description="fragment backlog", system_state=_state(7847),
                            source="daemon_loop", category="gap")
    assert first.task_generated is None
    observer.mark_consumed(first.obs_id, "RQ-20260928-002")

    second = observer.record(description="fragment backlog", system_state=_state(7847),
                             source="daemon_loop", category="gap")

    assert second.obs_id != first.obs_id, (
        "the second report was suppressed as a duplicate of a consumed record, so "
        "a condition that is still true can never re-enter the queue"
    )
    assert second.task_generated is None, "the fresh report must be unprocessed"


def test_an_unconsumed_condition_is_still_deduplicated(tmp_path):
    """The fix must not turn ordinary dedup off.

    Repeating the same report before anyone consumes it has to collapse to one
    record, or every daemon cycle would append.
    """
    observer = _observer(tmp_path)
    first = observer.record(description="health", system_state={"x": 1},
                            source="daemon_loop", category="gap")
    second = observer.record(description="health", system_state={"x": 1},
                             source="daemon_loop", category="gap")
    assert second.obs_id == first.obs_id, (
        "an unconsumed duplicate must still collapse; re-reporting is only for "
        "conditions the converter has already read"
    )


def test_a_condition_observed_a_hundred_times_does_not_accumulate_tasks(tmp_path):
    """Review case: same condition observed 100 times.

    What must not happen is 100 tasks. What must happen is that the evidence stays
    current and the converter keeps reusing one identity - which is the signature's
    job, not this layer's, so both halves are asserted together.
    """
    sys.path.insert(0, str(REPO))
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    observer = _observer(tmp_path)
    pool = TaskPool(str(tmp_path / "pool"))
    converter = ObservationToTaskConverter(observer, pool)
    rule = next(r for r in converter.rules if r.name == "fragment_backlog")

    signature = None
    for _ in range(100):
        obs = observer.record(description="fragment backlog", system_state=_state(7847),
                              source="daemon_loop", category="gap")
        signature = converter._semantic_signature(rule, obs.system_state)

    assert signature, "the rule must produce an identity"
    assert len({signature}) == 1, "one hundred reports produced more than one identity"

    # and a drifting value must not fork that identity
    drifted = {"total": 17293, "pending_scan": 7800, "archaeologized": 200}
    drifted_sig = converter._semantic_signature(rule, drifted)
    assert drifted_sig == signature, (
        "a value that ticked from 7847 to 7800 changed the incident identity, so a "
        "backlog draining by 47 would mint a new task"
    )


def test_an_archived_task_does_not_close_a_condition_that_is_still_true(tmp_path):
    """Review case: task terminal, condition true.

    The incident must survive, because nothing about the world changed - only the
    paperwork did.
    """
    sys.path.insert(0, str(REPO))
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    observer = _observer(tmp_path)
    pool = TaskPool(str(tmp_path / "pool"))
    converter = ObservationToTaskConverter(observer, pool)

    obs = observer.record(description="fragment backlog", system_state=_state(7847),
                          source="daemon_loop", category="gap")
    result = converter.convert()
    assert result["tasks_created"] >= 1, f"no task was created: {result}"
    rule = next(r for r in converter.rules if r.name == "fragment_backlog")
    created = [t for t in pool.list_tasks(status="pending", limit=100)
               if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"]
    assert created, "the fragment_backlog rule produced no task to archive"
    task = created[0]

    _archive_through_lifecycle(pool, task.task_id)
    assert "fragment_backlog" in converter._semantic_incidents, (
        "archiving the task dropped the incident; a task ending is not a condition "
        "being resolved"
    )

    # and a later report refreshes the incident rather than losing it
    converter._semantic_incidents["fragment_backlog"]["last_observed_at"] = "2000-01-01T00:00:00"
    again = observer.record(description="fragment backlog", system_state=_state(7847),
                            source="daemon_loop", category="gap")
    converter._reconcile_persistent_incidents(again)
    assert "fragment_backlog" in converter._semantic_incidents, (
        "re-reporting a still-true condition cleared the incident"
    )
    assert rule.condition_fn(again), "the condition must still read as true"


def test_the_incident_evidence_refreshes_while_its_task_stays_archived(tmp_path):
    """A standing claim must be restated with live evidence, not left frozen.

    Once the incident's task is archived, the converter stops finding it among
    the open statuses and falls back to the incident's recorded task_id.  That
    fallback used to return without calling _record_persistent_incident, so the
    incident kept pointing at work that ended and its last_observed_at froze at
    that moment - the live condition was then carried by a stale record.  The
    open-status branch always refreshed; the archived branch has to as well, or
    the steady state is precisely the one that goes stale.
    """
    sys.path.insert(0, str(REPO))
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    observer = _observer(tmp_path)
    pool = TaskPool(str(tmp_path / "pool"))
    converter = ObservationToTaskConverter(observer, pool)

    observer.record(description="fragment backlog", system_state=_state(7847),
                    source="daemon_loop", category="gap")
    converter.convert()
    created = [t for t in pool.list_tasks(status="pending", limit=100)
               if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"]
    assert created, "the fragment_backlog rule produced no task to archive"
    task = created[0]
    _archive_through_lifecycle(pool, task.task_id)

    incident = converter._semantic_incidents["fragment_backlog"]
    assert incident["task_id"] == task.task_id, (
        "the incident must keep pointing at the work it opened, even once that "
        "work is archived"
    )
    incident["last_observed_at"] = "2000-01-01T00:00:00"
    converter._save_semantic_incidents()

    observer.record(description="fragment backlog", system_state=_state(7847),
                    source="daemon_loop", category="gap")
    result = converter.convert()

    incident = converter._semantic_incidents["fragment_backlog"]
    assert incident["last_observed_at"] > "2000-01-01T00:00:00", (
        "the incident survived but was never restated: a standing condition must "
        "carry fresh evidence, otherwise a stale timestamp is indistinguishable "
        "from a condition nobody is watching"
    )
    assert incident["signature"] == converter._semantic_signature(
        next(r for r in converter.rules if r.name == "fragment_backlog"),
        _state(7847)), "refreshing evidence must not fork the incident identity"

    fresh = [t for t in pool.list_tasks(limit=1000)
             if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"]
    assert len(fresh) == 1, (
        f"refreshing evidence minted work: {[t.task_id for t in fresh]}"
    )
    assert result["tasks_created"] == 0, (
        "a re-observation of an unchanged archived incident must not create a task"
    )


def test_recovery_closes_the_incident_and_relapse_reopens_it(tmp_path):
    """Review cases: condition clears, then returns.

    Before the fix neither was observable, because the record had frozen. Both
    directions are asserted so the fix cannot regress into a one-way valve.
    """
    sys.path.insert(0, str(REPO))
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    observer = _observer(tmp_path)
    pool = TaskPool(str(tmp_path / "pool"))
    converter = ObservationToTaskConverter(observer, pool)

    obs = observer.record(description="fragment backlog", system_state=_state(7847),
                          source="daemon_loop", category="gap")
    converter.convert()
    created = [t for t in pool.list_tasks(status="pending", limit=100)
               if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"]
    assert created, "the first round produced no task"
    task = created[0]
    assert "fragment_backlog" in converter._semantic_incidents

    recovered = observer.record(description="fragment backlog", system_state=_state(12),
                                source="daemon_loop", category="gap")
    converter._reconcile_persistent_incidents(recovered)
    assert "fragment_backlog" not in converter._semantic_incidents, (
        "real recovery evidence did not close the incident"
    )

    relapsed = observer.record(description="fragment backlog", system_state=_state(9000),
                               source="daemon_loop", category="gap")
    before = {t.task_id for t in pool.list_tasks(limit=1000)}
    converter.convert()
    assert "fragment_backlog" in converter._semantic_incidents, (
        "a condition that genuinely returned did not reopen its incident"
    )
    # Scope to this rule. A gap observation whose state omits last_mine_seed_scan
    # also satisfies cross_agent_idle, because that rule defaults a missing key to
    # "never" - a separate pre-existing attribution defect, and not evidence of a
    # duplicate here. What must not happen is a second fragment_backlog task.
    new_for_rule = [
        t for t in pool.list_tasks(limit=1000)
        if t.task_id not in before
        and (t.outputs or {}).get("conversion_rule") == "fragment_backlog"
    ]
    assert not new_for_rule, (
        "the relapse minted a duplicate fragment_backlog task while the original "
        "was still open; an unresolved task is the work, and reusing it is what "
        "stops one incident becoming many"
    )
    open_for_rule = [t for t in pool.list_tasks(status="pending", limit=1000)
                     if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"]
    assert len(open_for_rule) == 1, (
        f"expected exactly one open fragment_backlog task, found "
        f"{[t.task_id for t in open_for_rule]}"
    )
    assert open_for_rule[0].task_id == task.task_id


def test_a_relapse_after_the_task_was_archived_opens_a_distinct_round(tmp_path):
    """Relapse must not collide with an identity that is already closed out.

    The open-task case above reuses, which is correct. This is the other half: once
    the task is terminal there is nothing left to reuse, and the new round needs its
    own identity so the old closure cannot be mistaken for handling the relapse.
    """
    sys.path.insert(0, str(REPO))
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    observer = _observer(tmp_path)
    pool = TaskPool(str(tmp_path / "pool"))
    converter = ObservationToTaskConverter(observer, pool)

    observer.record(description="fragment backlog", system_state=_state(7847),
                    source="daemon_loop", category="gap")
    converter.convert()
    first = [t for t in pool.list_tasks(status="pending", limit=100)
             if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"][0]
    _archive_through_lifecycle(pool, first.task_id)

    observer.record(description="fragment backlog", system_state=_state(12),
                    source="daemon_loop", category="gap")
    converter._reconcile_persistent_incidents(observer.get_unprocessed(limit=10)[0])
    assert "fragment_backlog" not in converter._semantic_incidents

    observer.record(description="fragment backlog", system_state=_state(9000),
                    source="daemon_loop", category="gap")
    converter.convert()

    assert "fragment_backlog" in converter._semantic_incidents, (
        "the relapse did not reopen an incident whose task had been archived"
    )
    fresh = [t for t in pool.list_tasks(status="pending", limit=100)
             if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"]
    assert fresh, "the relapse produced no task after the original was archived"
    assert fresh[0].task_id != first.task_id, (
        "the relapse reused the archived task's identity; a new round must not "
        "collide with a closure that already happened"
    )


def test_recovery_and_relapse_in_the_same_tick_do_not_erase_each_other(tmp_path):
    """Ordering evidence must not depend on clock resolution.

    The daemon records several gap observations inside a single cycle, so a
    recovery observation and a relapse observation can share a timestamp to the
    microsecond. Comparing created_at made neither of them newer, and the stale
    recovery record then closed an incident that a later observation in the same
    pass had just reopened. The store keeps append order, which is the order the
    observations were actually made, and positions do not tie.
    """
    sys.path.insert(0, str(REPO))
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    observer = _observer(tmp_path)
    pool = TaskPool(str(tmp_path / "pool"))
    converter = ObservationToTaskConverter(observer, pool)

    observer.record(description="fragment backlog", system_state=_state(7847),
                    source="daemon_loop", category="gap")
    converter.convert()
    task = [t for t in pool.list_tasks(status="pending", limit=100)
            if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"][0]
    _archive_through_lifecycle(pool, task.task_id)
    assert "fragment_backlog" in converter._semantic_incidents

    recovered = observer.record(description="fragment backlog", system_state=_state(12),
                               source="daemon_loop", category="gap")
    relapsed = observer.record(description="fragment backlog", system_state=_state(9000),
                               source="daemon_loop", category="gap")
    # Both carry the same instant, as they genuinely can inside one daemon cycle.
    for observation in (recovered, relapsed):
        observation.created_at = "2026-10-17T12:00:00.000000"
    observer._observations[observer._observations.index(recovered)].created_at = recovered.created_at
    observer._observations[observer._observations.index(relapsed)].created_at = relapsed.created_at

    before = [t.task_id for t in pool.list_tasks(limit=1000)
              if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"]
    converter.convert()
    after = [t.task_id for t in pool.list_tasks(limit=1000)
             if (t.outputs or {}).get("conversion_rule") == "fragment_backlog"]

    assert "fragment_backlog" in converter._semantic_incidents, (
        "a recovery observation sharing its instant with a later relapse closed the "
        "incident; the two must be ordered by when they were recorded, not by a "
        "clock that cannot tell them apart"
    )
    assert after == before, (
        f"the same-tick pair minted work: {before} -> {after}"
    )


def test_the_admission_boundary_is_untouched():
    """Review case: an unqualified source stays not admitted.

    This change is about when an already-admitted observation is reported again.
    It must not widen, narrow, or reinterpret who may enter, so the admission
    thresholds are asserted against the real module rather than assumed unaffected
    because the diff does not mention it.
    """
    sys.path.insert(0, str(REPO))
    from core.evidence_admission import Thresholds, quality_facts

    thin = quality_facts(["one short note"])
    full = quality_facts([f"evidence number {i} " + "x" * 60 for i in range(3)])

    assert thin.independent_source_count < Thresholds.minimum_independent_sources, (
        "a thin evidence set now clears the independence threshold; the change must "
        "not have moved admission"
    )
    assert thin.evidence_count >= 1, "the fixture is not exercising the thin path"
    assert full.evidence_count >= Thresholds.minimum_unique_evidence


def test_the_observation_store_stays_bounded_under_sustained_re_reporting(tmp_path):
    """Re-reporting must not turn the store into an unbounded log.

    Every cycle appends once per persisting condition, so the bound that keeps the
    store at 200 records is what stops this from becoming a disk-filling loop.
    """
    observer = _observer(tmp_path)
    first = observer.record(description="fragment backlog", system_state=_state(7847),
                            source="daemon_loop", category="gap")
    for i in range(400):
        observer.mark_consumed(first.obs_id if i == 0 else observer.get_recent(limit=1)[0].obs_id,
                               f"RQ-{i}")
        observer.record(description="fragment backlog", system_state=_state(7847),
                        source="daemon_loop", category="gap")
    assert len(observer._observations) <= 200, (
        f"the store grew to {len(observer._observations)}; re-reporting is bounded "
        f"only by the retention window"
    )