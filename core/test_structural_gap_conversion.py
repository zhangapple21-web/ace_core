"""`structural_gap` was a category with producers and no consumer.

Four independent processes write it: the three structural watches, and the window
lane that refuses a write. Until the rule below existed the converter read each of
those observations, matched nothing, and left them unconsumed in the queue - not
even perception-only, which is reserved for `host_session`. So the escalations of
three watches piled up unread, which is indistinguishable from an escalation
channel that does not exist.

Three properties have to hold together, or this fix is worse than the defect:

  one incident, one task     a re-assertion reuses the open task instead of
                             minting one per hourly report
  one rule, many incidents   two different unreachable rules stay two tasks, so
                             the dedup does not paper over distinct problems
  no identity, no task       an observation that cannot be identified is left in
                             the queue rather than converted, because a task per
                             unidentified report is exactly what the signature
                             machinery exists to prevent
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RULE = "structural_gap_review"


def _converter(tmp_path):
    sys.path.insert(0, str(REPO))
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    observer = RuntimeObserver(data_dir=str(tmp_path / "obs"))
    pool = TaskPool(str(tmp_path / "pool"))
    return observer, pool, ObservationToTaskConverter(observer, pool)


def _liveness_state() -> dict:
    """The exact shape `ops/daemon_liveness_watch.py` records today."""
    return {"kind": "DAEMON_STOPPED", "severity": "high", "rule": None,
            "task_id": None, "disposition": "start_task"}


def _tasks(pool) -> list:
    found = []
    for status in ("pending", "active", "review", "approved", "blocked"):
        found += [task for task in pool.list_tasks(status=status, limit=1000)
                  if (task.outputs or {}).get("conversion_rule") == RULE]
    return found


def test_a_dead_runtime_finding_becomes_a_task(tmp_path):
    """The whole point of the rule, measured on the production producer's shape."""
    observer, pool, converter = _converter(tmp_path)

    obs = observer.record(description="daemon liveness watch: daemon is not running",
                          system_state=_liveness_state(), severity="high",
                          source="daemon_liveness_watch", category="structural_gap",
                          dedup_key="daemon_liveness:DAEMON_STOPPED")
    result = converter.convert()

    assert result["tasks_created"] == 1, f"the finding did not become work: {result}"
    tasks = _tasks(pool)
    assert len(tasks) == 1, f"one finding produced {len(tasks)} tasks"
    task = tasks[0]
    assert task.outputs["source_obs_id"] == obs.obs_id
    assert task.outputs["semantic_signature"], "the task carries no incident identity"
    # and the finding leaves the queue: converted, not merely read
    assert observer.get_unprocessed() == [], (
        "the converted observation stayed in the unprocessed queue"
    )


def test_the_same_finding_reported_hourly_reuses_one_task(tmp_path):
    """One hourly tick, five hours, one task.

    The watch re-asserts while the finding stands. Without signature dedup this is
    five tasks saying the same thing - the failure the other eight rules were given
    a `_semantic_signature` branch to prevent.
    """
    observer, pool, converter = _converter(tmp_path)

    for _ in range(5):
        observer.record(description="daemon liveness watch: daemon is not running",
                        system_state=_liveness_state(), severity="high",
                        source="daemon_liveness_watch", category="structural_gap",
                        dedup_key="daemon_liveness:DAEMON_STOPPED")
        converter.convert()

    assert len(_tasks(pool)) == 1, (
        "a recurring finding minted a new task per report"
    )


def test_two_different_unreachable_rules_stay_two_tasks(tmp_path):
    """Dedup must not become merging. Two rules, two problems, two tasks."""
    observer, pool, converter = _converter(tmp_path)

    for rule in ("fragment_backlog", "cross_agent_idle"):
        observer.record(
            description=f"incident rule {rule} can never be reconciled",
            system_state={"rule": rule, "verdict": "STUCK_NO_OBSERVATION",
                          "category": "gap", "task_id": f"RQ-{rule}",
                          "task_terminal": True, "unverified_days": 7},
            severity="high", source="incident_reachability_watch",
            category="structural_gap", dedup_key=f"incident_unreachable:{rule}")
        converter.convert()

    tasks = _tasks(pool)
    assert len(tasks) == 2, f"two incidents collapsed into {len(tasks)} tasks"
    assert len({task.title for task in tasks}) == 2


def test_a_gap_with_no_identifiable_incident_creates_nothing(tmp_path):
    """No identity means no dedup, and no dedup means one task per report."""
    observer, pool, converter = _converter(tmp_path)

    observer.record(description="a structural gap nobody can name",
                    system_state={"note": "no identity here"}, severity="high",
                    source="unattributed", category="structural_gap")
    result = converter.convert()

    assert result["tasks_created"] == 0
    assert _tasks(pool) == []
    assert len(observer.get_unprocessed()) == 1, (
        "an unconvertible observation was consumed anyway, so the finding would "
        "look handled while nothing carries it"
    )


def test_a_low_severity_gap_stays_out_of_the_pool(tmp_path):
    """`dead_component_watch` grades a never-referenced component `low`.

    Converting those would turn a design observation into work items on every
    review; the other eight rules draw the same line at `medium` and this one
    follows it rather than inventing a different threshold.
    """
    observer, pool, converter = _converter(tmp_path)

    observer.record(description="unwired component curator_dryrun",
                    system_state={"component": "curator_dryrun", "kind": "unwired",
                                  "file": "ops/curator_dryrun.py"},
                    severity="low", source="dead_component_watch",
                    category="structural_gap", dedup_key="unwired:curator_dryrun")
    converter.convert()

    assert _tasks(pool) == []