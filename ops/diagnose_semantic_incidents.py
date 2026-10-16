#!/usr/bin/env python3
"""Diagnose why persistent semantic incidents cannot be reconciled.

A `persistent_semantic_incident` in semantic_incidents.json is supposed to be
forgotten once an observation of the same category proves recovery. If a pointer
stays there forever, one of three things is true and they need different responses:

  1. the condition still holds and nothing clears it,
  2. the category is no longer observed, so nothing can ever clear it, or
  3. the observation that would clear it never reaches the reconciling loop.

This diagnoses which, without changing anything. It exists because two pointers
were found stuck - fragment_backlog (18 days) and cross_agent_idle (7 days) - and
their remediation tasks had both been archived within minutes of creation. A
retired incident that keeps naming a finished task looks like live work forever, so
"is it still real" is a question worth being able to answer mechanically.

Read-only. It records no observation and creates no task.

Usage:
    py -3 ops/diagnose_semantic_incidents.py [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

INCIDENTS = ROOT / "06_RUNTIME" / "ace" / "data" / "observations" / "semantic_incidents.json"
TERMINAL = {"archived", "graveyard", "rejected", "completed", "failed", "done"}


def _find_task(task_id: str):
    for pool in ("task_pool", "task_pool_freezone"):
        base = ROOT / pool
        if not base.is_dir():
            continue
        for status_dir in sorted(base.iterdir()):
            if not status_dir.is_dir():
                continue
            path = status_dir / f"{task_id}.json"
            if path.is_file():
                try:
                    return pool, status_dir.name, json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    return pool, status_dir.name, None
    return None


def _live_condition(rule: str) -> dict:
    """Read the state the rule is about, from the source the daemon reads.

    This session diagnosed both incidents as unreachable: no `gap` observation
    reaches the converter, so the pointer can never be cleared. That was true
    and it was beside the point. A grep scoped to core/*.py found no producer,
    because the producer is ace_daemon.py at the repository root - lines 3295,
    3317 and 3333 record exactly these categories, and 55 such observations
    exist, all consumed into the two tasks now sitting archived.

    The conditions those observations carried are still true:
      fragment_backlog   pending_scan 7847 of 17293, threshold 500
      cross_agent_idle   last_mine_seed_scan == "never"

    So the incidents were never stuck. The work was closed on paper while the
    condition persisted. A diagnosis that stops at the queue cannot tell those
    apart, and reports a broken safety net when the real finding is unfixed work
    wearing a closed task's name.
    """
    if rule == "fragment_backlog":
        index_dir = ROOT / "02_FRAGMENT_INDEX"
        if not index_dir.is_dir():
            return {"readable": False, "detail": f"{index_dir} absent"}
        try:
            from core.fragment_index import FragmentIndex

            stats = FragmentIndex(str(index_dir)).get_stats()
        except Exception as exc:  # noqa: BLE001 - diagnosis must not raise
            return {"readable": False, "detail": f"{type(exc).__name__}: {exc}"}
        pending = stats.get("by_status", {}).get("pending_scan", 0)
        return {
            "readable": True,
            "state_key": "pending_scan",
            "value": pending,
            "threshold": 500,
            "source": str(index_dir / "fragment_index.json").replace("\\", "/"),
            "still_true": pending > 500,
            "total": stats.get("total"),
            "archaeologized": stats.get("by_status", {}).get("archaeologized"),
        }

    if rule == "cross_agent_idle":
        state_path = ROOT / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json"
        if not state_path.is_file():
            return {"readable": False, "detail": f"{state_path} absent"}
        try:
            value = json.loads(state_path.read_text(encoding="utf-8")).get(
                "last_mine_seed_scan", "never")
        except (OSError, ValueError) as exc:
            return {"readable": False, "detail": str(exc)}
        return {
            "readable": True,
            "state_key": "last_mine_seed_scan",
            "value": value,
            "threshold": "never",
            "source": str(state_path).replace("\\", "/"),
            "still_true": value == "never",
        }

    return {"readable": False, "detail": "no condition is defined for this rule"}


def diagnose() -> dict:
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool
    import tempfile

    if not INCIDENTS.is_file():
        return {"status": "NO_INCIDENT_FILE", "incidents": []}

    incidents = json.loads(INCIDENTS.read_text(encoding="utf-8"))
    file_age_h = (datetime.now().timestamp() - INCIDENTS.stat().st_mtime) / 3600

    # What the reconciler can actually see. It runs inside convert()'s loop over
    # get_unprocessed(limit=100), so both the queue contents and the limit bound
    # what is reachable this cycle.
    observer = RuntimeObserver(data_dir=str(INCIDENTS.parent))
    queue = observer.get_unprocessed(limit=500)
    queue_categories = {}
    for obs in queue:
        queue_categories[str(getattr(obs, "category", "?"))] = \
            queue_categories.get(str(getattr(obs, "category", "?")), 0) + 1

    tmp = Path(tempfile.mkdtemp())
    converter = ObservationToTaskConverter(
        RuntimeObserver(data_dir=str(tmp / "o")), TaskPool(str(tmp / "p")))
    persistent_rules = set(getattr(converter, "_PERSISTENT_INCIDENT_RULES", ()))
    rule_categories = {rule.name: rule.category for rule in converter.rules}

    rows = []
    for name, entry in incidents.items():
        task_id = str(entry.get("task_id") or "")
        found = _find_task(task_id)
        task_status = found[1] if found else None
        category = rule_categories.get(name, "gap")
        needed_key = ("pending_scan" if name == "fragment_backlog"
                      else "last_mine_seed_scan" if name == "cross_agent_idle"
                      else None)
        reachable = category in queue_categories
        condition = _live_condition(name)
        still_true = bool(condition.get("still_true"))

        # Order matters. A condition that is still true is the finding, whatever
        # the queue looks like: the work exists, and a terminal task claiming to
        # have handled it does not make it disappear. Reporting this as an
        # unreachable rule would blame the safety net for the closure decision.
        if still_true:
            verdict = "CONDITION_STILL_TRUE"
            if condition["threshold"] == "never":
                breach = (f"{condition['state_key']} is still {condition['value']!r}, "
                          f"which is the state this rule exists to catch")
            else:
                breach = (f"{condition['state_key']}={condition['value']!r} still "
                          f"breaches {condition['threshold']!r}")
            explanation = (
                f"{breach}, so the underlying condition persists; the incident is "
                f"open work, not an unreachable rule"
                + (f", while task {task_id} is {task_status}" if task_status else "")
            )
        elif not reachable:
            verdict = "STUCK_NO_OBSERVATION"
            explanation = (f"no unprocessed observation in category {category!r}, so "
                           f"_reconcile_persistent_incidents never sees one for this rule")
        elif found and task_status in TERMINAL:
            verdict = "STALE_TASK_DONE"
            explanation = "the remediation task is terminal but a fresh observation has not cleared it yet"
        else:
            verdict = "MONITORED"
            explanation = "the category is present in the queue; reconciliation can run"
        rows.append({
            "incident": name,
            "task_id": task_id,
            "last_observed_at": entry.get("last_observed_at"),
            "category": category,
            "requires_state_key": needed_key,
            "task_found_in": f"{found[0]}/{found[1]}" if found else None,
            "task_terminal": (task_status in TERMINAL) if task_status else None,
            "category_reachable_in_queue": reachable,
            "live_condition": condition,
            "verdict": verdict,
            "explanation": explanation,
        })

    return {
        "incident_file_age_hours": round(file_age_h, 1),
        "unprocessed_queue_size": len(queue),
        "convert_limit": 100,
        "entries_beyond_convert_limit": max(0, len(queue) - 100),
        "queue_categories": queue_categories,
        "persistent_rules": sorted(persistent_rules),
        "incidents": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = diagnose()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    print("=== persistent semantic incident diagnosis ===")
    print(f"  incident file age : {report['incident_file_age_hours']} h")
    print(f"  unprocessed queue : {report['unprocessed_queue_size']} "
          f"(convert() reads {report['convert_limit']}, "
          f"{report['entries_beyond_convert_limit']} beyond)")
    print(f"  queue categories  : {report['queue_categories']}")
    print(f"  persistent rules  : {report['persistent_rules']}")
    print()
    for row in report["incidents"]:
        print(f"  {row['incident']} -> {row['verdict']}")
        print(f"      task {row['task_id']} in {row['task_found_in']} "
              f"(terminal={row['task_terminal']})")
        print(f"      category {row['category']!r} reachable in queue: "
              f"{row['category_reachable_in_queue']}")
        print(f"      {row['explanation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())