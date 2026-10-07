"""Expectation violations, stated as questions.

The daemon already sees the world (heartbeat, TaskPool, graveyard) and it
already proves things (Researcher, Validator) and files work (Admission,
TaskPool). What it lacked was the middle: noticing that something does not
match what was expected, and saying so out loud as a checkable question.

A surprise is not a task and not a verdict. It becomes an ``anomaly``
observation with a stable dedup identity, and the existing
observation-to-task converter decides whether it is worth working on. The
same incident never files twice; a new incident always files once.

Each check is a pure function of (current, previous) snapshots so the whole
thing is unit-testable without a daemon. Thresholds live here, next to the
reason they were chosen, not scattered through the daemon.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# A heartbeat older than this is not "a little late", it is a stopped heart.
HEARTBEAT_STALE_MINUTES = 15

# More blocked tasks appearing in one cycle than this is a flood, not drift.
BLOCKED_FLOOD_PER_CYCLE = 5

# Since the probe fix, a cycle should add ~0 probe files. Anything above
# this is the old disease returning, not noise.
PROBE_JUMP_PER_CYCLE = 3


def _parse_ts(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def _age_minutes(last_beat: Any, now: datetime) -> Optional[float]:
    moment = _parse_ts(last_beat)
    if moment is None:
        return None
    return (now - moment).total_seconds() / 60.0


def check_surprises(
    current: Dict[str, Any],
    previous: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    """Compare one runtime snapshot against expectations and the last one.

    ``current`` keys used: last_beat, pid, run_id, pending, blocked,
    archived, probes. Missing keys mean "unknown", never "fine": a check
    that cannot see reports nothing rather than reporting all-clear.
    ``previous`` may be None on the first run; only absolute checks apply.
    """
    moment = now or datetime.now(timezone.utc)
    previous = previous or {}
    surprises: List[Dict[str, Any]] = []

    age = _age_minutes(current.get("last_beat"), moment)
    if age is None:
        surprises.append(
            {
                "key": "heartbeat_unreadable",
                "question": "The heartbeat timestamp cannot be parsed. "
                "Is the heartbeat writer still alive, or is the file corrupt?",
                "severity": "high",
                "evidence": {"last_beat": current.get("last_beat")},
            }
        )
    elif age > HEARTBEAT_STALE_MINUTES:
        surprises.append(
            {
                "key": "heartbeat_stale",
                "question": f"The last heartbeat is {age:.0f} minutes old. "
                "Did the daemon stall between cycles, or did the writer die?",
                "severity": "critical",
                "evidence": {
                    "last_beat": current.get("last_beat"),
                    "age_minutes": round(age, 1),
                },
            }
        )

    if current.get("pid") is not None and previous.get("pid") is not None:
        if current.get("pid") != previous.get("pid"):
            if current.get("run_id") != previous.get("run_id"):
                # A restart is lifecycle, not surprise. It is recorded by
                # the continuity audit, so this layer stays silent.
                pass
            else:
                surprises.append(
                    {
                        "key": "pid_changed_same_run",
                        "question": "The process id changed but the run id did not. "
                        "Did the daemon actually restart, or is something else "
                        "writing heartbeat records?",
                        "severity": "critical",
                        "evidence": {
                            "pid": current.get("pid"),
                            "previous_pid": previous.get("pid"),
                            "run_id": current.get("run_id"),
                        },
                    }
                )

    if isinstance(current.get("blocked"), int) and isinstance(previous.get("blocked"), int):
        flood = current["blocked"] - previous["blocked"]
        if flood > BLOCKED_FLOOD_PER_CYCLE:
            surprises.append(
                {
                    "key": "blocked_flood",
                    "question": f"{flood} tasks entered blocked in one cycle. "
                    "Is one validator decision parking everything, or did a "
                    "whole family of evidence go stale at once?",
                    "severity": "high",
                    "evidence": {
                        "blocked_before": previous["blocked"],
                        "blocked_now": current["blocked"],
                    },
                }
            )

    if isinstance(current.get("probes"), int) and isinstance(previous.get("probes"), int):
        jump = current["probes"] - previous["probes"]
        if jump > PROBE_JUMP_PER_CYCLE:
            surprises.append(
                {
                    "key": "probe_growth_returned",
                    "question": f"The graveyard grew by {jump} probe files in one cycle, "
                    "against an expectation of ~0 since the rolling-receipt fix. "
                    "Did the probe regress, or is a new per-cycle writer active?",
                    "severity": "high",
                    "evidence": {
                        "probes_before": previous["probes"],
                        "probes_now": current["probes"],
                    },
                }
            )

    return surprises


# --- Question Forge v1: tensions, not thresholds ---------------------------
#
# Learned expectations are deliberately NOT the first eye. Field proof from
# this machine: before the rolling-receipt fix, "+250 probe files a day"
# was the stable history. A learner would have enshrined the disease as
# normal. History-normal is not correct-state, so learned models arrive
# only as enhancers, after questions already exist.
#
# These checks ask from structure the system already owns: a working FA
# whose core duty never fires, and deposited experiences nobody reuses.
# No statistics, no covariance, no new entity types: a tension becomes an
# anomaly observation with a verification plan inside, and the existing
# converter decides whether it is worth working on.

# An FA that keeps observing while its core duty count stays here is asked
# about, not alarmed on: the answer may legitimately be "by design".
CURATOR_DUTY_ZERO_RUNS = 0

# Experiences younger than this that nobody referenced are "learned but
# unused" candidates. Older ones had their chance; counting only the young
# keeps the question about the current loop, not archaeology.
LEARN_WITHOUT_USE_DAYS = 7
LEARN_WITHOUT_USE_MIN_COUNT = 3


def check_tensions(field: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Ask from structure the system already owns.

    ``field`` keys used: curator_observing (bool), curator_runs
    (completed curation runs, int), recent_exp_unreferenced (int),
    recent_exp_total (int). Missing keys mean "unknown": report nothing
    rather than all-clear, same contract as check_surprises.
    """
    questions: List[Dict[str, Any]] = []

    observing = field.get("curator_observing")
    runs = field.get("curator_runs")
    if observing is True and isinstance(runs, int) and runs <= CURATOR_DUTY_ZERO_RUNS:
        questions.append(
            {
                "key": "fa_duty_gap",
                "question": "The curator keeps observing every cycle, yet its "
                "core duty count is zero. Is curation gated by design, broken "
                "at the entry, or waiting on a decision nobody made?",
                "severity": "medium",
                "evidence": {
                    "curator_observing": True,
                    "curator_runs": runs,
                },
                "verification_plan": [
                    "List who calls the curation entry besides tests.",
                    "Check whether the sync gate is open or fail-closed.",
                    "Conclude RESTORE, REWIRE, or RETIRE with receipts.",
                ],
            }
        )

    unreferenced = field.get("recent_exp_unreferenced")
    total = field.get("recent_exp_total")
    if (
        isinstance(unreferenced, int)
        and isinstance(total, int)
        and total > 0
        and unreferenced >= LEARN_WITHOUT_USE_MIN_COUNT
        and unreferenced == total
    ):
        questions.append(
            {
                "key": "learn_without_use",
                "question": f"{unreferenced} of {total} recent experiences were never "
                "referenced. Did the loop learn without using, and if so, "
                "is reuse broken or is there simply nothing worth reusing?",
                "severity": "medium",
                "evidence": {
                    "recent_exp_unreferenced": unreferenced,
                    "recent_exp_total": total,
                    "window_days": LEARN_WITHOUT_USE_DAYS,
                },
                "verification_plan": [
                    "Sample the unreferenced records for reuse value.",
                    "Check whether the reuse stage ran and what it matched.",
                    "Conclude BROKEN_REUSE, NOTHING_WORTH_REUSING, or TOO_EARLY.",
                ],
            }
        )

    return questions


__all__ = [
    "BLOCKED_FLOOD_PER_CYCLE",
    "HEARTBEAT_STALE_MINUTES",
    "LEARN_WITHOUT_USE_DAYS",
    "LEARN_WITHOUT_USE_MIN_COUNT",
    "PROBE_JUMP_PER_CYCLE",
    "check_surprises",
    "check_tensions",
]