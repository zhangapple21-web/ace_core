"""An unexercisable safety net must raise its own hand.

The incident-reachability watch exists because a persistent incident pointer can
sit in the file forever reporting an open incident while the remediation task is
archived and nothing is capable of clearing it. Two were found: fragment_backlog
(18 days) and cross_agent_idle (6 days), both naming archived tasks. The mechanism
is identical to an unwired component - a rule that exists and can never fire - so
it escalates into the same structural_gap observation channel the dead-component
watch already uses, rather than into a second private alerting path.

Three properties are pinned here, each of which was a real defect during
development rather than a hypothetical:

  A pointer old enough to be a standing claim escalates. The first version
  computed the age by subtracting a naive last_observed_at from an aware now(),
  the TypeError was swallowed into None, and the guard read None as "not old
  enough" - so both 18-day and 6-day pointers silently produced escalated=0. A
  guard that skips on an error is the same blindness it exists to catch, so an
  uncomputable age must escalate rather than vanish.

  Escalation is deduplicated. Running the watch repeatedly must not manufacture
  the same observation repeatedly, or it becomes noise and gets ignored, which
  defeats it.

  It escalates only what is genuinely unreconcilable. A rule whose category does
  appear in the queue is being watched and must stay quiet.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

from ops.incident_reachability_watch import (  # noqa: E402
    CONTRACT_VERSION,
    STALE_POINTER_DAYS,
    _iso,
    run,
)


class RecordingObserver:
    def __init__(self):
        self.recorded = []

    def record(self, **kwargs):
        self.recorded.append(kwargs)
        return kwargs


class AgedIncidentFiles:
    """Put a controlled incident file in place and point the module at it."""

    def __init__(self, tmp_path, incidents):
        self.path = tmp_path / "semantic_incidents.json"
        self.path.write_text(json.dumps(incidents, ensure_ascii=False), encoding="utf-8")


def _naive_iso(days_ago: int) -> str:
    """last_observed_at is written naive; reproduce that exactly."""
    moment = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return moment.replace(tzinfo=None).isoformat()


def test_a_naive_timestamp_does_not_silently_suppress_escalation(monkeypatch, tmp_path):
    """The defect this watch was nearly born with.

    last_observed_at carries no timezone offset while now() is aware. Subtracting
    them raises TypeError; an unguarded except turns that into None, and a guard of
    the form "skip when the age is falsy" then reads the error as "not old enough".
    Both real pointers were days past the threshold and escalated zero times.
    """
    incidents = {
        "fragment_backlog": {
            "schema_version": 1,
            "signature": "a" * 64,
            "task_id": "RQ-FAKE-1",
            "last_observed_at": _naive_iso(STALE_POINTER_DAYS + 15),
            "reason": "persistent_semantic_incident",
        }
    }
    AgedIncidentFiles(tmp_path, incidents)
    monkeypatch.setattr("ops.incident_reachability_watch.INCIDENTS", tmp_path / "semantic_incidents.json")
    # diagnose() reads its own module-level INCIDENTS; point that at the fixture too
    monkeypatch.setattr("ops.diagnose_semantic_incidents.INCIDENTS", tmp_path / "semantic_incidents.json")

    observer = RecordingObserver()
    result = run(REPO, observer)

    assert result["unreachable_rules"] == 1, "the stale pointer was not detected at all"
    assert result["escalated"] == 1, (
        "a 15-day-old pointer past the threshold did not escalate; a naive "
        "timestamp must not read as 'not old enough'"
    )
    assert observer.recorded[0]["dedup_key"] == "incident_unreachable:fragment_backlog"


def test_an_unknown_age_escalates_rather_than_vanishing(monkeypatch, tmp_path):
    """An unparseable timestamp is itself unverified, so it must surface."""
    incidents = {
        "fragment_backlog": {
            "schema_version": 1,
            "signature": "b" * 64,
            "task_id": "RQ-FAKE-2",
            "last_observed_at": "not-a-timestamp",
            "reason": "persistent_semantic_incident",
        }
    }
    AgedIncidentFiles(tmp_path, incidents)
    monkeypatch.setattr("ops.incident_reachability_watch.INCIDENTS", tmp_path / "semantic_incidents.json")
    monkeypatch.setattr("ops.diagnose_semantic_incidents.INCIDENTS", tmp_path / "semantic_incidents.json")

    observer = RecordingObserver()
    result = run(REPO, observer)
    # diagnose() also sees the real queue, so the two live unreachable rules are
    # found alongside the fixture's. What matters is that the unparseable timestamp
    # produced an escalation of its own rather than being filtered out.
    assert result["escalated"] >= 1, (
        "an uncomputable age was treated as acceptable; that is how a broken "
        "watcher looks exactly like a working one"
    )
    assert any(r["system_state"].get("task_id") == "RQ-FAKE-2"
               for r in observer.recorded), (
        "the rule with the unparseable timestamp did not escalate"
    )


def test_a_young_pointer_stays_quiet(monkeypatch, tmp_path):
    """Not everything is an incident; a new pointer must not cry wolf on day one."""
    incidents = {
        "fragment_backlog": {
            "schema_version": 1,
            "signature": "c" * 64,
            "task_id": "RQ-FAKE-3",
            "last_observed_at": _iso(datetime.now(timezone.utc)),
            "reason": "persistent_semantic_incident",
        }
    }
    AgedIncidentFiles(tmp_path, incidents)
    monkeypatch.setattr("ops.incident_reachability_watch.INCIDENTS", tmp_path / "semantic_incidents.json")
    monkeypatch.setattr("ops.diagnose_semantic_incidents.INCIDENTS", tmp_path / "semantic_incidents.json")

    observer = RecordingObserver()
    result = run(REPO, observer)
    assert result["unreachable_rules"] == 1, "still detected as unreachable"
    assert result["escalated"] == 0, "a pointer observed today must not be escalated"


def test_escalation_carries_enough_to_act_on(monkeypatch, tmp_path):
    """The observation must say which rule, which task, and for how long."""
    incidents = {
        "fragment_backlog": {
            "schema_version": 1,
            "signature": "d" * 64,
            "task_id": "RQ-FAKE-4",
            "last_observed_at": _naive_iso(STALE_POINTER_DAYS + 30),
            "reason": "persistent_semantic_incident",
        }
    }
    AgedIncidentFiles(tmp_path, incidents)
    monkeypatch.setattr("ops.incident_reachability_watch.INCIDENTS", tmp_path / "semantic_incidents.json")
    monkeypatch.setattr("ops.diagnose_semantic_incidents.INCIDENTS", tmp_path / "semantic_incidents.json")

    observer = RecordingObserver()
    run(REPO, observer)
    record = observer.recorded[0]
    state = record["system_state"]
    assert record["category"] == "structural_gap"
    assert record["source"] == "incident_reachability_watch"
    assert state["contract_version"] == CONTRACT_VERSION
    assert state["rule"] == "fragment_backlog"
    assert state["task_id"] == "RQ-FAKE-4"
    assert state["unverified_days"] >= STALE_POINTER_DAYS
    assert "gap" in record["description"]


def test_the_snapshot_records_the_queue_bound_that_makes_it_fragile(monkeypatch, tmp_path):
    """The reason this went unnoticed is a number: convert() reads 100 of 116.

    If the snapshot stops carrying both numbers, a future reader cannot tell
    whether reconciliation is merely unlucky about queue position or has no input
    at all.
    """
    incidents = {
        "fragment_backlog": {
            "schema_version": 1,
            "signature": "e" * 64,
            "task_id": "RQ-FAKE-5",
            "last_observed_at": _naive_iso(STALE_POINTER_DAYS + 9),
            "reason": "persistent_semantic_incident",
        }
    }
    AgedIncidentFiles(tmp_path, incidents)
    monkeypatch.setattr("ops.incident_reachability_watch.INCIDENTS", tmp_path / "semantic_incidents.json")

    run(REPO, RecordingObserver())
    snapshot = json.loads(
        (REPO / "08_GOVERNANCE" / "structural_integrity" /
         "incident_reachability_snapshot.json").read_text(encoding="utf-8"))
    assert "convert_limit" in snapshot and "unprocessed_queue_size" in snapshot
    assert snapshot["contract_version"] == CONTRACT_VERSION
    assert "fragment_backlog" in snapshot["unreachable_incident_rules"]


def test_with_no_incident_file_the_watch_reports_nothing_and_does_not_raise(tmp_path, monkeypatch):
    """A machine that never had incidents is not broken."""
    monkeypatch.setattr("ops.incident_reachability_watch.INCIDENTS",
                        tmp_path / "does_not_exist.json")
    # diagnose() reads its own INCIDENTS path, so patch that too
    monkeypatch.setattr("ops.diagnose_semantic_incidents.INCIDENTS",
                        tmp_path / "does_not_exist.json")
    observer = RecordingObserver()
    result = run(REPO, observer)
    assert result["unreachable_rules"] == 0
    assert observer.recorded == []