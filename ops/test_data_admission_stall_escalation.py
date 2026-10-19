"""Regression tests for stalled-blocker detection and action switching.

The defect these guard against: before this change the recovery ledger
saturated at ``RECOVERY_VERIFICATION_DUE`` after three unchanged observations,
so a blocker that repeated 5,421 times produced the identical ``next_action``
every window.  Status changed nothing, and nothing changed status.

A passing status assertion alone would not have caught that, so the
counterexample tests below assert on the *action* and on the observable side
effect (an admitted review task), not merely on the state string.
"""
import json
import pathlib

from core.data_admission_recovery import (
    STALL_ACTION,
    STALL_THRESHOLD,
    DataAdmissionRecovery,
)
from core.task import TaskPool

OPERATIONS = ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index")


def _blocked_matrix():
    rows = {
        name: {
            "production_sources": [],
            "independence_groups": [],
            "has_independent_cross_validation": False,
        }
        for name in OPERATIONS
    }
    return {"phase_two_admission": {"status": "NOT_ADMITTED", "core_operations": rows}}


def _drive(ledger, times, matrix=None):
    """Return the last report after building ``times`` identical observations."""
    matrix = matrix or _blocked_matrix()
    report = None
    for index in range(times):
        report = ledger.build(matrix, observed_at=f"2026-10-15T{index % 24:02d}:00:00+08:00")
    return report


def test_repeated_blocker_escalates_instead_of_repeating_the_research_action(tmp_path):
    ledger = DataAdmissionRecovery(tmp_path)
    report = _drive(ledger, STALL_THRESHOLD)

    assert report["recovery_status"] == "STALLED_NO_PROGRESS"
    assert report["stalled"] is True
    assert report["next_action"] == STALL_ACTION
    assert report["next_action"] != (
        "research_candidate_source_evidence_without_changing_the_existing_refresh_or_admission"
    )


def test_below_threshold_still_researches_so_the_band_is_real(tmp_path):
    """Counterexample: the stall band must not swallow ordinary repetition."""
    ledger = DataAdmissionRecovery(tmp_path)
    report = _drive(ledger, STALL_THRESHOLD - 1)

    assert report["stalled"] is False
    assert report["recovery_status"] == "RECOVERY_VERIFICATION_DUE"
    assert report["next_action"] == (
        "research_candidate_source_evidence_without_changing_the_existing_refresh_or_admission"
    )


def test_existing_three_observation_contract_is_preserved(tmp_path):
    """The pre-existing behaviour this change must not regress."""
    ledger = DataAdmissionRecovery(tmp_path)
    first = ledger.build(_blocked_matrix(), observed_at="2026-09-01T09:35:00+08:00")
    second = ledger.build(_blocked_matrix(), observed_at="2026-09-01T12:35:00+08:00")
    third = ledger.build(_blocked_matrix(), observed_at="2026-09-01T15:20:00+08:00")

    assert first["recovery_status"] == "RECOVERY_IN_PROGRESS"
    assert second["recovery_status"] == "RECOVERY_IN_PROGRESS"
    assert third["recovery_status"] == "RECOVERY_VERIFICATION_DUE"
    assert third["consecutive_unchanged_observations"] == 3


def test_escalation_admits_exactly_one_task_and_is_idempotent(tmp_path):
    pool = TaskPool(str(tmp_path / "pool"))
    ledger = DataAdmissionRecovery(tmp_path / "data")
    report = _drive(ledger, STALL_THRESHOLD)

    first = ledger.escalate(report, pool)
    assert first["attempted"] is True
    assert first["created"] is True
    assert first["task_id"]

    # Same stall cycle: repeated calls must not manufacture more work.
    second = ledger.escalate(report, pool)
    third = ledger.escalate(report, pool)
    assert second["created"] is False
    assert third["created"] is False
    assert second["task_id"] == first["task_id"] == third["task_id"]
    assert len(pool.list_tasks(limit=100)) == 1


def test_changed_fingerprint_opens_a_genuinely_new_cycle(tmp_path):
    """A real evidence change must not be folded into the old stall."""
    pool = TaskPool(str(tmp_path / "pool"))
    ledger = DataAdmissionRecovery(tmp_path / "data")
    stalled = _drive(ledger, STALL_THRESHOLD)
    first = ledger.escalate(stalled, pool)

    # Two operations now have sources, so only three stay blocked: the
    # fingerprint moves and this is a new, separately-actionable condition.
    matrix = _blocked_matrix()
    operations = matrix["phase_two_admission"]["core_operations"]
    for name in ("quote", "index"):
        operations[name] = {
            "production_sources": ["a", "b"],
            "independence_groups": ["a", "b"],
            "has_independent_cross_validation": True,
        }
    moved = ledger.build(matrix, observed_at="2026-10-16T09:00:00+08:00")
    assert moved["blocker_fingerprint"] != stalled["blocker_fingerprint"]

    recovered = _drive(ledger, STALL_THRESHOLD, matrix=matrix)
    assert recovered["blocker_fingerprint"] == moved["blocker_fingerprint"]
    second = ledger.escalate(recovered, pool)

    assert second["created"] is True
    assert second["task_id"] != first["task_id"]
    assert len(pool.list_tasks(limit=100)) == 2


def test_escalation_never_opens_the_gate_or_fabricates_progress(tmp_path):
    """The gate stays closed and no source is invented by escalating."""
    pool = TaskPool(str(tmp_path / "pool"))
    ledger = DataAdmissionRecovery(tmp_path / "data")
    report = _drive(ledger, STALL_THRESHOLD)
    ledger.escalate(report, pool)

    assert report["phase_two_status"] == "NOT_ADMITTED"
    assert report["side_effects"] == {
        "network_called": False,
        "taskpool_mutated": False,
        "admission_changed": False,
        "recommendation_created": False,
    }
    assert report["operations"]["quote"]["qualified_sources"] == []
    assert report["operations"]["quote"]["status"] == "BLOCKED"
    assert report["unresolved_operations"] == list(OPERATIONS)

    task = pool.list_tasks(limit=10)[0]
    assert task.outputs["admission"]["source_type"] == "system_observation"
    assert "must not open the admission gate" in task.outputs["admission"]["risk"].lower()


def test_a_spent_review_does_not_produce_an_identical_replacement(tmp_path):
    """Retrying must not mint a copy of the attempt it is retrying.

    This test used to require the opposite: that a generation-suffixed
    operation_intent let a corrected review through even after the previous one
    had circuit-broken. The worry was real - a spent review parked in `blocked`
    does match the same admission intent, so without distinguishing them every
    later escalation reuses the dead task.

    Measured on 2026-10-19, that allowance had produced the opposite failure.
    One blocker, one fingerprint, thirty-five tasks, gen1 through gen35, created
    every thirty minutes since 2026-10-16 - and all thirty-five carried an
    identical result payload. The only thing that varied was the stall counter
    climbing from 5533 to 6123. The "corrected review" the test was protecting
    the path for had never once produced a different finding.

    So the question is no longer "may a retry replace a spent task" but "does
    anything about the retry differ". If it does not, it must not be admitted:
    the circuit breaker's own method was producing the stall it was detecting.
    A genuinely new stall cycle has a new fingerprint and still gets its review.
    """
    pool = TaskPool(str(tmp_path / "pool"))
    ledger = DataAdmissionRecovery(tmp_path / "data")
    report = _drive(ledger, STALL_THRESHOLD)

    first = ledger.escalate(report, pool)
    assert first["created"] is True

    spent = pool.load_task(first["task_id"])
    spent.status = "blocked"
    spent.outputs["terminal_non_convergent"] = True
    spent.blocked_reason = "same evidence repeated to the limit"
    assert pool.update_task(spent) is True

    again = ledger.escalate(report, pool)
    assert again["created"] is False, (
        "a spent review of this fingerprint must not be replaced by an identical one"
    )
    assert again["task_id"] == first["task_id"]
    assert len(pool.list_tasks(limit=100)) == 1


def test_a_new_fingerprint_still_gets_its_own_review(tmp_path):
    """Suppression must be per-fingerprint, never global.

    This is the half that would be easy to break while stopping the retry loop:
    if identical retries are refused, a *different* stall must still be
    admitted, or the detector goes blind exactly when it finds something new.
    """
    pool = TaskPool(str(tmp_path / "pool"))
    ledger = DataAdmissionRecovery(tmp_path / "data")
    report = _drive(ledger, STALL_THRESHOLD)

    first = ledger.escalate(report, pool)
    assert first["created"] is True

    spent = pool.load_task(first["task_id"])
    spent.status = "blocked"
    spent.outputs["terminal_non_convergent"] = True
    assert pool.update_task(spent) is True

    other = _drive(ledger, STALL_THRESHOLD)
    other["blocker_fingerprint"] = "a-different-blocker"
    second = ledger.escalate(other, pool)
    assert second["created"] is True, "a different stall is different work"
    assert second["task_id"] != first["task_id"]


def test_the_retry_count_stays_visible_as_evidence(tmp_path):
    """Suppressing the retry must not suppress the fact that retries happened."""
    pool = TaskPool(str(tmp_path / "pool"))
    ledger = DataAdmissionRecovery(tmp_path / "data")
    report = _drive(ledger, STALL_THRESHOLD)

    first = ledger.escalate(report, pool)
    spent = pool.load_task(first["task_id"])
    spent.status = "blocked"
    spent.outputs["terminal_non_convergent"] = True
    assert pool.update_task(spent) is True

    again = ledger.escalate(report, pool)
    assert again["created"] is False
    # The ledger still counts what it refused, so the stall is not hidden.
    assert again.get("reason")
    live = pool.load_task(first["task_id"])
    evidence = live.outputs["admission"]["evidence"][0]
    assert "prior_circuit_broken_reviews" in evidence, (
        "the refusal must remain legible in the record"
    )


def test_escalation_reaches_a_model_route(tmp_path):
    """The escalation must not be born with every evidence route closed.

    ``task_roles._model_task_type`` resolves a task's profile from a
    ``task_type:`` tag.  Without one it returns ``''``, the profile has no
    ``model_enabled``, and ``_record_model_execution`` returns None before any
    model call.  RQ-20261016-001/-007 were admitted untagged, so the researcher
    ran with no model and no local artifact and reported "0 evidence" every
    cycle.  This pins the tag that gives the task a real route.
    """
    from core.miner_pool.task_profiles import get_task_profile
    from core.task_roles import _is_local_only_task, _model_task_type

    pool = TaskPool(str(tmp_path / "pool"))
    ledger = DataAdmissionRecovery(tmp_path / "data")
    report = _drive(ledger, STALL_THRESHOLD)
    outcome = ledger.escalate(report, pool)
    task = pool.load_task(outcome["task_id"])

    task_type = _model_task_type(task)
    assert task_type, "escalation must declare a task_type or it has no profile"
    profile = get_task_profile(task_type)
    assert profile.get("model_enabled") is True, (
        f"profile {task_type!r} cannot run a model, so research cannot converge"
    )
    assert _is_local_only_task(task) is False
    # A profile that permits a model is only useful if it also has local corpus
    # tags; this task has neither files nor prior memory hits, so the model is
    # the only remaining route.
    assert "task_type:reasoning" in task.tags


def test_escalation_carries_evidence_the_researcher_could_actually_reach(tmp_path):
    """Guard against shipping an escalation the researcher cannot use.

    Honest scope: this asserts *reachability of inputs*, not convergence.  An
    earlier version of this test claimed the external-object wording caused the
    lower non-convergence rate (43.2% vs 10.0% over 1,510 tasks).  That causal
    claim was not verified and is now known to be wrong for this path:
    ``task_roles.research_task`` never reads ``verification_method``, and
    RQ-20261016-007 still reported 0 evidence across two review cycles.  The
    correlation is real; the mechanism attributed to it was not.

    What is verifiable and worth pinning is narrower: the escalation must hand
    the researcher (a) a real external artifact path that exists, and (b) the
    concrete candidate sources for each unresolved operation, so a future
    wiring change has something to consume.
    """
    pool = TaskPool(str(tmp_path / "pool"))
    ledger = DataAdmissionRecovery(tmp_path / "data")
    report = _drive(ledger, STALL_THRESHOLD)
    ledger.escalate(report, pool)

    task = pool.list_tasks(limit=10)[0]
    admission = task.outputs["admission"]

    # (a) A real external artifact, not a self-reference.
    external = pathlib.Path(admission["external_evidence_ref"])
    assert external.name == "stock_data_benchmark_latest.json"
    # The instruction must send the researcher outward, not back to itself.
    assert "outside this task record" in admission["verification_method"].lower()

    # (b) Concrete per-operation targets, derived from the recovery report
    #     rather than invented at task-creation time.
    candidates = admission["evidence"][0]["research_candidate_sources"]
    assert set(candidates) == set(report["unresolved_operations"])
    for operation, sources in candidates.items():
        assert sources, f"{operation} must name at least one candidate source"
        assert all(isinstance(s, str) and s for s in sources)


def test_not_stalled_never_creates_a_task(tmp_path):
    """Counterexample: escalation is gated on the stall fact, not on being called."""
    pool = TaskPool(str(tmp_path / "pool"))
    ledger = DataAdmissionRecovery(tmp_path / "data")
    report = _drive(ledger, 3)

    outcome = ledger.escalate(report, pool)
    assert outcome == {"attempted": False, "created": False, "task_id": "", "reason": "not_stalled"}
    assert pool.list_tasks(limit=100) == []


def test_absent_pool_leaves_the_ledger_a_pure_observation(tmp_path):
    ledger = DataAdmissionRecovery(tmp_path)
    report = _drive(ledger, STALL_THRESHOLD)
    outcome = ledger.escalate(report, None)

    assert outcome["created"] is False
    assert outcome["reason"] == "no_task_pool_available"
    assert json.loads(ledger.path.read_text(encoding="utf-8"))["stalled"] is True
