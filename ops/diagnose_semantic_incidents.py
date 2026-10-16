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
        if not reachable:
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