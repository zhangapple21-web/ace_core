#!/usr/bin/env python3
"""Hourly structural-integrity watch tick.

Why this is Python and not PowerShell
-------------------------------------
The tick used to be watch_tick.ps1, launched through wscript and then through
powershell. On this host neither wrapper survives the scheduler's context:

  wscript.exe starts no child process at all - not cmd.exe, not powershell,
  nothing, with or without //B - and Task Scheduler still records exit 0. Every
  conclusion drawn from LastTaskResult on a wscript-launched job was therefore
  wrong: the job reported success having done nothing. The dead-component
  snapshot that this tick exists to refresh went 27 hours stale, and the two
  "it ran" confirmations that seemed to settle it had both run the Python entry
  point by hand rather than through the scheduler.

  Through cmd.exe the PowerShell tick starts, writes its first line, and then
  stops at whichever external command it reaches next. Each fix moved the failure
  one step further in, which is what a wrapper that cannot survive a hidden
  context looks like from the inside.

So the task runs the interpreter directly. A scheduled task has no interactive
window to hide, and pythonw allocates none, so there is nothing to hide and no
wrapper in the path to misbehave.

What it runs
------------
Entries, each judged independently so one failing cannot mask another:

  dead_component_watch         a component that exists and is referenced nowhere
  incident_reachability_watch  an incident rule that exists and can never fire
  daemon_liveness_watch        a runtime that is dead while its lock still claims it
  runtime_identity_receipt     what code was on disk while the runtime ran

incident_reachability_watch exists because of exactly this script's failure mode.
A persistent incident pointer sat in semantic_incidents.json for eighteen days
claiming open work while the task it named had been archived minutes after
creation, because the rule's category never produced an observation the
reconciler could see. A watch that is not run is not a watch.

The last entry is not a watch, and is listed here as what it is rather than
smuggled in as one: it detects nothing and can raise no finding. It records
identity - git HEAD and branch, the worktree-versus-HEAD blob hashes of the two
observation-lifecycle files, the OS view of the process, the registered task's
action and logon type, and the lock/heartbeat/anchor join - so that "what is
actually running" is a file anyone can read, instead of an answer reconstructed
by hand each time it is asked. It runs here because this tick already runs as
SYSTEM, the only identity that can see a Session 0 process and read its task
definition.

Judging rules
-------------
Exit code zero is not proof a watch looked; its snapshot on disk is. Each watch
has its own floor, because a watch that owns an interval (dead_component_watch
runs every twelve hours) legitimately leaves its snapshot hours old, while a
watch with no interval must refresh every tick. Using one freshness threshold for
both made this script fail on eleven of twelve hours - a watcher that cries wolf
is as blind as one that never speaks.

Read-only with respect to the substrate: it runs the watches, which record their
own observations, and judges them by exit code and snapshot age.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parent.parent

# name -> script, snapshot, and the oldest its snapshot may be while healthy.
# The floor is the watch's own cadence plus one tick of slack.
WATCHES: List[Dict[str, object]] = [
    {
        "name": "dead_component_watch",
        "script": "ops/dead_component_watch.py",
        "snapshot": "08_GOVERNANCE/structural_integrity/dead_components_snapshot.json",
        # MIN_INTERVAL_HOURS is 12, so a healthy snapshot is routinely two hours
        # old and a generic freshness threshold would fail eleven hours in twelve.
        "max_age_minutes": 13 * 60,
    },
    {
        "name": "incident_reachability_watch",
        "script": "ops/incident_reachability_watch.py",
        "snapshot": "08_GOVERNANCE/structural_integrity/incident_reachability_snapshot.json",
        # No interval of its own: every tick should refresh it.
        "max_age_minutes": 90,
    },
    {
        "name": "daemon_liveness_watch",
        "script": "ops/daemon_liveness_watch.py",
        "snapshot": "08_GOVERNANCE/structural_integrity/daemon_liveness_snapshot.json",
        # No interval of its own either, and the reason is different from the one
        # above: a stopped runtime is the condition this tick runs as SYSTEM to be
        # able to notice at all. Waiting twelve hours to look would restore the
        # nine-and-a-half-hour outage this watch exists to shorten.
        "max_age_minutes": 90,
    },
    {
        "name": "runtime_identity_receipt",
        "script": "ops/runtime_identity_receipt.py",
        # Not a watch: it observes no condition and can raise no finding. It is
        # here so the receipt is produced by a schedule rather than by whoever
        # remembers, and so a receipt that stops being refreshed is judged stale
        # like everything else. The path is git-ignored on purpose - a file that
        # recorded the dirty flag into a tracked path would make every later
        # receipt dirty and destroy the signal it exists to report.
        "snapshot": "06_RUNTIME/ace/data/memory/runtime_identity_receipt.json",
        "max_age_minutes": 90,
    },
]


def _age_minutes(path: Path):
    if not path.is_file():
        return None
    return (time.time() - path.stat().st_mtime) / 60.0


def run_watch(watch: Dict[str, object], root: Path, python: str) -> Dict[str, object]:
    script = root / str(watch["script"])
    if not script.is_file():
        return {"name": watch["name"], "status": "MISSING_SCRIPT", "detail": str(script)}

    started = time.time()
    # --force is deliberately NOT passed: each watch owns its interval, and forcing
    # it every tick would destroy the cadence evidence of when it last looked.
    proc = subprocess.run(
        [python, "-u", str(script), "--root", str(root), "--json"],
        capture_output=True, text=True, timeout=900,
        encoding="utf-8", errors="replace", cwd=str(root),
    )
    elapsed = round(time.time() - started, 1)

    snapshot = root / str(watch["snapshot"])
    age = _age_minutes(snapshot)

    result: Dict[str, object] = {
        "name": watch["name"],
        "returncode": proc.returncode,
        "elapsed_seconds": elapsed,
        "snapshot_exists": age is not None,
        "snapshot_age_minutes": None if age is None else round(age, 1),
    }

    if proc.returncode != 0:
        result["status"] = "EXITED_NONZERO"
        result["detail"] = ((proc.stderr or proc.stdout or "")[-400:])
        return result
    if age is None:
        result["status"] = "NO_SNAPSHOT"
        result["detail"] = f"exited 0 but wrote no snapshot at {watch['snapshot']}"
        return result
    if age > float(watch["max_age_minutes"]):  # type: ignore[arg-type]
        result["status"] = "STALE_SNAPSHOT"
        result["detail"] = (f"snapshot is {result['snapshot_age_minutes']} minutes old, "
                            f"past its {float(watch['max_age_minutes']) / 60:.1f}h floor")
        return result

    result["status"] = "OK"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--only", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    watches = [w for w in WATCHES if not args.only or w["name"] == args.only]
    if not watches:
        print(f"no watch named {args.only!r}", file=sys.stderr)
        return 1

    # sys.executable is python.exe under the console, pythonw.exe under the task.
    # Both are correct here; nothing is captured from stdout, so the window-less
    # build behaves the same as the console one.
    python = sys.executable or "py"
    results = [run_watch(watch, root, python) for watch in watches]
    failed = [r for r in results if r["status"] != "OK"]

    report = {
        "status": "OK" if not failed else "WATCH_FAILED",
        "python": python,
        "root": str(root),
        "watches": results,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    else:
        for entry in results:
            detail = entry.get("detail", "")
            print(f"{entry['status']:16s} {entry['name']:30s} "
                  f"rc={entry['returncode']} age={entry['snapshot_age_minutes']}m "
                  f"{detail}")
        print(report["status"])

    # A failing watch must be visible to the scheduler: exit non-zero so the task
    # stops reporting success it did not achieve.
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())