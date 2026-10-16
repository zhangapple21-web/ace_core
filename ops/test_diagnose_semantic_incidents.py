"""A stuck incident must be diagnosable, not just stale.

Two persistent semantic incidents were found stuck: fragment_backlog (18 days old)
and cross_agent_idle (7 days), and both remediation tasks had been archived within
minutes of creation. Both file a real complaint with a real mechanism behind it, and
neither could be answered by looking at the incident file alone - a pointer records
when a condition was last seen, never whether anything is still watching it.

The diagnosis this pins, stated as three distinguishable states so the answer to
"is it still real" is mechanical rather than a reading of tea leaves:

  MONITORED            the rule's category is present in the queue the converter
                       reads, so reconciliation can run.
  STALE_TASK_DONE      the remediation task is terminal but no fresh observation
                       has cleared the pointer yet.
  STUCK_NO_OBSERVATION no observation in that category exists, so nothing can
                       ever clear it. This is the state that is indistinguishable
                       from "still true" without looking at the queue.

It also pins the bound that makes it fragile: convert() reads a limited slice of
the unprocessed queue, and if the queue is larger than that slice, whether an
incident is reconciled can depend on queue order. That is worth failing on if it
regresses further, not silently accepting.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pytest  # noqa: E402

from ops.diagnose_semantic_incidents import diagnose  # noqa: E402

VERDICTS = {"MONITORED", "STALE_TASK_DONE", "STUCK_NO_OBSERVATION"}


def test_the_diagnosis_reaches_a_definite_verdict_for_every_incident():
    report = diagnose()
    assert report["incidents"], "no incidents to diagnose - is the file readable?"
    for row in report["incidents"]:
        assert row["verdict"] in VERDICTS, (
            f"{row['incident']} got verdict {row['verdict']!r}; every incident must "
            "resolve to one of the three states or the diagnosis is not answering "
            "the question"
        )
        assert row["explanation"], f"{row['incident']} has no explanation"


def test_an_incident_naming_a_finished_task_is_not_reported_as_live_work():
    """The specific harm this exists to prevent.

    A retired incident that keeps naming an archived task looks exactly like live
    work. Any reader - a human or the next window - would believe there is open
    work indefinitely. If such a pointer is ever reachable by the reconciler, the
    diagnosis must say so plainly.
    """
    report = diagnose()
    for row in report["incidents"]:
        if row["task_terminal"] and row["category_reachable_in_queue"]:
            assert row["verdict"] in {"STALE_TASK_DONE", "MONITORED"}, (
                f"{row['incident']} names a finished task and its category IS "
                f"reachable, yet it was called {row['verdict']!r}"
            )


def test_the_diagnosis_exposes_the_conversion_limit_and_the_queue_size():
    """Reconciliation is bounded by the slice convert() reads.

    convert() iterates observer.get_unprocessed(limit=100). If the queue holds
    more than that, an incident's fate depends on where its category's
    observations happen to sit - so the diagnosis must report both numbers rather
    than only the outcome.
    """
    report = diagnose()
    assert report["convert_limit"] == 100
    assert report["unprocessed_queue_size"] >= 0
    assert "queue_categories" in report
    assert isinstance(report["queue_categories"], dict)


def test_diagnosis_does_not_mutate_anything():
    """A diagnostic that records an observation would change what it measures."""
    from ops.diagnose_semantic_incidents import INCIDENTS

    before = INCIDENTS.stat().st_mtime if INCIDENTS.is_file() else None
    before_bytes = INCIDENTS.read_bytes() if INCIDENTS.is_file() else None
    diagnose()
    if before is not None:
        assert INCIDENTS.stat().st_mtime == before, "the incident file was rewritten"
        assert INCIDENTS.read_bytes() == before_bytes, "the incident file changed"