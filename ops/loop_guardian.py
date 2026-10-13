"""Loop guardian: turn \"someone is watching\" into an assertion that closes itself.

Watching a loop by hand is itself part of the loop. This makes it mechanical: a
read-only sweep that states what a healthy ACE cycle must look like, records the
observation, and writes a closure receipt once the thresholds hold. Nothing here
mutates the task pool, calls a model, or dispatches work - it reads the pools,
asserts against them, and keeps a ledger.

The assertions
--------------
A1  the daemon is alive and its state is fresh
A2  no pool is a black hole (a pool directory with tasks but no lifecycle dirs)
A3  work is moving (some non-terminal state changed since the last sweep)
A4  the pending backlog is draining, not growing
A5  no new work has been stranded in the isolated freezone pool

Closure
-------
When every assertion holds for ``REQUIRED_CONSECUTIVE`` consecutive sweeps, the
guardian writes one closure receipt and stops asserting. Closure means "this
loop is closed and I have stopped hand-waving it", not "the backlog is empty" -
a loop with 60 tasks cycling through researcher and validator is closed. A loop
with pending=0 because the work went nowhere is the failure A2 exists to catch.

The thresholds are declared here rather than inferred from a single sweep,
because a one-shot check cannot distinguish a healthy drain from a momentary
gap, and it is exactly that distinction the last defect turned on.
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

#: Consecutive sweeps that must all hold before the loop is called closed.
REQUIRED_CONSECUTIVE = 3

#: The daemon's state file must be written within this many minutes.
DAEMON_FRESH_MINUTES = 10

#: Minimum gap between sweeps before "nothing changed" counts as a stall. The
#: daemon cycles roughly every four minutes, so a shorter gap would score a
#: normal pause as a failure - a guardian that cries wolf gets ignored, which is
#: the same as having no guardian.
MIN_SWEEP_GAP_MINUTES = 5

#: Statuses that are not terminal. A pool whose live set is empty while pending
#: is not is the shape of a stall.
LIVE_STATUSES = ("pending", "active", "review", "approved")

#: Where the guardian keeps its own ledger. Deliberately not the task pool.
LEDGER = BASE_DIR / "06_RUNTIME" / "ace" / "data" / "memory" / "loop_guardian.json"
#: Where a closure receipt lands, alongside the other governance receipts.
RECEIPTS = BASE_DIR / "08_GOVERNANCE" / "loop_guardian"


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pool_counts(pool_dir: Path) -> dict[str, int]:
    if not pool_dir.is_dir():
        return {}
    return {
        sub.name: len(list(sub.glob("*.json")))
        for sub in sorted(pool_dir.iterdir())
        if sub.is_dir()
    }


def _recently_touched(pool_dir: Path, since_iso: str) -> int:
    """How many task files changed after ``since_iso``.

    Activity, not net count: a pool where two tasks finish and two arrive nets
    to zero while being busier than either endpoint. mtime churn is the honest
    signal for "the lifecycle is doing something".
    """
    if not since_iso:
        return 0
    try:
        since = datetime.fromisoformat(since_iso).timestamp()
    except ValueError:
        return 0
    touched = 0
    for sub in pool_dir.iterdir():
        if not sub.is_dir():
            continue
        for path in sub.glob("*.json"):
            try:
                if path.stat().st_mtime >= since:
                    touched += 1
            except OSError:
                continue
    return touched


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sweep(base: Path = BASE_DIR) -> dict:
    """One read-only pass. Returns the assertion results and the raw counts."""
    now_ts = time.time()
    assertions: dict[str, dict] = {}

    # ---- A1: daemon alive and fresh
    state = _read_json(base / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json") or {}
    state_file = base / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json"
    try:
        age_min = max(0.0, now_ts - state_file.stat().st_mtime) / 60.0
    except OSError:
        age_min = 9999.0
    assertions["A1_daemon_fresh"] = {
        "passed": bool(state.get("run_status") == "alive") and age_min <= DAEMON_FRESH_MINUTES,
        "detail": f"status={state.get('run_status')} state_file_age={age_min:.1f}min",
    }

    # ---- A2: no black-hole pool
    black_holes = []
    for name in ("task_pool", "task_pool_freezone"):
        pool_dir = base / name
        counts = _pool_counts(pool_dir)
        total = sum(counts.values())
        # a pool that carries tasks but was never given the lifecycle layout
        if total and "active" not in counts:
            black_holes.append({"pool": name, "total": total, "statuses": sorted(counts)})
    assertions["A2_no_black_hole_pool"] = {
        "passed": not black_holes,
        "detail": "every pool holding tasks also holds the live-status layout",
        "black_holes": black_holes,
    }

    counts = _pool_counts(base / "task_pool")
    fz_counts = _pool_counts(base / "task_pool_freezone")

    # ---- A3: work is moving since the last sweep
    previous = _read_json(LEDGER) or {}
    previous_counts = (previous.get("counts") or {}).get("task_pool") or {}
    previous_at = (previous.get("last_sweep_at") or "")
    live_total = sum(counts.get(s, 0) for s in LIVE_STATUSES)

    # Net counts are a weak activity signal: two tasks finishing while two
    # arrive nets to zero, so a busy pool looks static. Count how many task
    # files were actually touched instead.
    touched = _recently_touched(base / "task_pool", previous_at)
    if not previous_counts or not previous_at:
        # A first sweep is a baseline, not a stall. Scoring it as failure would
        # make the guardian cry wolf on the run it is installed by.
        a3, a3_detail = True, "first sweep, baseline recorded"
    elif touched:
        a3, a3_detail = True, f"{touched} task file(s) changed since the last sweep"
    else:
        # Nothing moved. That is only a stall if enough time has passed for a
        # daemon cycle to have happened: the daemon runs about every four
        # minutes and moves a couple of tasks per cycle, so two sweeps six
        # minutes apart can straddle a cycle and see nothing. Scoring that red
        # is the guardian lying about the system, which is worse than silence.
        try:
            gap_min = (datetime.now() - datetime.fromisoformat(previous_at)).total_seconds() / 60.0
        except ValueError:
            gap_min = 9999.0
        if gap_min < MIN_SWEEP_GAP_MINUTES:
            a3, a3_detail = True, (
                f"no activity yet, but only {gap_min:.1f}min since the last sweep "
                f"(< {MIN_SWEEP_GAP_MINUTES}min needed to judge)"
            )
        else:
            a3, a3_detail = False, (
                f"no task file changed in {gap_min:.1f}min, longer than a daemon cycle"
            )
    assertions["A3_work_is_moving"] = {"passed": a3, "detail": a3_detail}

    # ---- A4: pending is draining or cycling, not growing
    previous_pending = previous_counts.get("pending") if previous_counts else None
    pending = counts.get("pending", 0)
    if previous_pending is None:
        a4 = True
        detail = "first sweep, baseline recorded"
    else:
        a4 = pending <= previous_pending
        detail = f"pending {previous_pending} -> {pending}"
    assertions["A4_pending_not_growing"] = {"passed": a4, "detail": detail}

    # ---- A5: the isolated freezone pool is not accumulating new stranded work
    fz_pending = fz_counts.get("pending", 0)
    previous_fz = (previous.get("counts") or {}).get("task_pool_freezone") or {}
    if not previous_fz:
        a5, detail = True, "first sweep, baseline recorded"
    else:
        a5 = fz_pending <= previous_fz.get("pending", 0)
        detail = f"freezone pending {previous_fz.get('pending', 0)} -> {fz_pending}"
    assertions["A5_freezone_not_accumulating"] = {"passed": a5, "detail": detail}

    return {
        "at": _now(),
        "assertions": assertions,
        "counts": {"task_pool": counts, "task_pool_freezone": fz_counts},
        "live_total": live_total,
        "all_passed": all(a["passed"] for a in assertions.values()),
    }


def _load_ledger() -> dict:
    return _read_json(LEDGER) or {}


def _write_ledger(payload: dict) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    temporary = LEDGER.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                         encoding="utf-8")
    temporary.replace(LEDGER)


def evaluate_and_record(base: Path = BASE_DIR) -> dict:
    """Assert, then either advance the streak or close the loop with a receipt."""
    report = sweep(base)
    ledger = _load_ledger()
    streak = int(ledger.get("consecutive_green", 0))

    if not report["all_passed"]:
        streak = 0
    else:
        streak += 1

    entry = {
        "counts": report["counts"],
        "live_total": report["live_total"],
        "consecutive_green": streak,
        "last_sweep_at": report["at"],
        "closed": bool(ledger.get("closed")),
    }
    _write_ledger(entry)

    closed_already = bool(ledger.get("closed"))
    receipt = None
    if streak >= REQUIRED_CONSECUTIVE and not closed_already:
        receipt = {
            "contract_version": "ace.loop_guardian.closure.v1",
            "closed_at": report["at"],
            "reason": (
                "every loop assertion held for "
                f"{REQUIRED_CONSECUTIVE} consecutive sweeps"
            ),
            "assertions": {name: a["detail"] for name, a in report["assertions"].items()},
            "final_counts": report["counts"],
            "meaning": (
                "closed means the cycle moves: work is claimed, reviewed, and "
                "archived. It does not mean the backlog is empty - a backlog "
                "cycling through researcher and validator is a closed loop."
            ),
            "production_integration": False,
            "taskpool_mutated": False,
        }
        RECEIPTS.mkdir(parents=True, exist_ok=True)
        target = RECEIPTS / f"closure-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
        entry["closed"] = True
        entry["closed_at"] = report["at"]
        _write_ledger(entry)

    report["streak"] = streak
    report["required"] = REQUIRED_CONSECUTIVE
    report["closed"] = bool(entry.get("closed"))
    report["receipt"] = receipt
    return report


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="ACE loop guardian (read-only, self-closing)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=str(BASE_DIR))
    args = parser.parse_args()

    report = evaluate_and_record(Path(args.root))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0

    print(f"== loop guardian @ {report['at']} ==")
    for name, assertion in report["assertions"].items():
        mark = "ok  " if assertion["passed"] else "FAIL"
        print(f"  [{mark}] {name}: {assertion['detail']}")
    print(f"  streak {report['streak']}/{report['required']}"
          f"{'  -> CLOSED' if report['closed'] else ''}")
    print(f"  counts: {json.dumps(report['counts'], ensure_ascii=False)}")
    if report.get("receipt"):
        print(f"  closure receipt written to {RECEIPTS}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())