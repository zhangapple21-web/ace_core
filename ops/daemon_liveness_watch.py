#!/usr/bin/env python3
"""The daemon was dead for nine and a half hours and three checks said so.

That is the whole reason this watch exists. On 2026-10-17 the runtime stopped at
02:53:48 and did not come back until it was started by hand at 12:24. During that
window the hourly checkup ran and recorded `daemon心跳存活` as an error three
times, and `heartbeat.json` even carries the trace: `last_exit_reason` is
`host_termination`, written at 03:47:01 - the checkup's own `:47` cadence. The
machine was thinking about the outage correctly the entire time.

So the missing part was never detection. It was disposition: an alert that ends in
a log line is not a safety net, and the previous window already established that
nothing reads those lines. This watch adds no detector. It reads the same verdict
the checkup reads, from the same component (`core.heartbeat.Heartbeat`), and does
the two things a verdict of "stopped" needs:

  it starts the daemon again, through the task that already exists for that
  purpose, and it says what happened

The action is not a new supervisor. `schtasks /run /tn ACE_Daemon_Boot` is the
same path the boot and daily triggers take, and it is the path that restored the
runtime by hand earlier today. Nothing here runs on its own schedule: this script
is one entry in the existing `WATCHES` registry, driven by the hourly tick that is
already registered as a SYSTEM task. Because the tick runs as SYSTEM it does not
share the daemon's fate, which is the one property that makes the check worth
anything.

Where an escalation goes depends on whether anyone can hear it
-------------------------------------------------------------
The repository's existing escalation channel is an observation with
`category="structural_gap"`, which the daemon's converter turns into work. That
channel is circular for this watch: a dead daemon cannot consume the observation
that says it is dead. So the disposition splits:

  daemon stopped   start it, then record the finding once it is alive to consume it
  daemon running   record the finding directly - the pipeline is up, so use it

Both branches end in the same durable place when the runtime is reachable. When it
is not, the snapshot and a non-zero exit are the record, and the next hourly run
tries again.

What it deliberately does not do
--------------------------------
It does not decide the daemon *should* be stopped. If the task has been disabled,
that is an operator decision and starting it would fight that decision, so the
recovery is suppressed and reported as suppressed. Idempotence covers the rest:
starting an already-running task is refused by the task's own `IgnoreNew` policy,
so a spurious attempt is harmless rather than a second runtime.

It never invents a new observation category. `structural_gap` is the category the
converter already sees; a fresh category would be a finding nobody can act on,
which is the failure this repository already has a name for.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.heartbeat import Heartbeat  # noqa: E402
from ops.health_check import _process_command_line  # noqa: E402

CONTRACT_VERSION = "ace.daemon_liveness_watch.v1"
SNAPSHOT = "08_GOVERNANCE/structural_integrity/daemon_liveness_snapshot.json"

TASK_NAME = "ACE_Daemon_Boot"
PS = Path(r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe")

# The daemon beats at every stage of a five-minute cycle, so six silent cycles is
# not a busy runtime, it is a stopped one. The checkup's own floor is one hour,
# which is why the outage was measured in hours; the watch that has to act cannot
# share that floor, or it waits an hour to notice something it is about to fix.
MAX_IDLE_SECONDS = 1800

# The same allowance for the evidence a persistent incident carries. One cycle of
# slack is not enough - a daily restart costs time - but five silent cycles is not
# a slow cycle, it is a pipeline that stopped refreshing its own claims.
EVIDENCE_MAX_MINUTES = 30

# A restarted daemon publishes a new run_id and a fresh last_start while it is
# still warming up, before its first stage beat. Waiting only for a beat would
# read a successful recovery as a failure.
RECOVERY_WAIT_SECONDS = 240


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _age_minutes(stamp: Any) -> Optional[float]:
    """Age of a timestamp that may be naive, aware, or unparseable.

    semantic_incidents.json writes naive local times while everything else here
    is timezone-aware. Treating that as "no age" would silently exempt the one
    field this check is about.
    """
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp))
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.astimezone()
    return (_now() - parsed.astimezone(timezone.utc)).total_seconds() / 60.0


def _heartbeat_path(root: Path) -> Path:
    return root / "06_RUNTIME" / "ace" / "data" / "memory" / "heartbeat.json"


def _task_state() -> Dict[str, Any]:
    """Whether the task that owns the daemon exists, and whether it is disabled.

    State is read from the scheduler's own object rather than from `schtasks`
    output, because this host reports in Chinese and parsing translated words is
    how a check becomes host-specific.
    """
    executable = str(PS) if PS.is_file() else "powershell"
    query = (f"(Get-ScheduledTask -TaskName '{TASK_NAME}' -ErrorAction SilentlyContinue)"
             ".State")
    try:
        result = subprocess.run([executable, "-NoProfile", "-Command", query],
                                capture_output=True, text=True, timeout=60,
                                encoding="utf-8", errors="replace")
        state = (result.stdout or "").strip()
    except (OSError, subprocess.SubprocessError) as error:
        return {"known": False, "detail": f"{type(error).__name__}: {error}"}
    if not state:
        return {"known": True, "state": "ABSENT", "disabled": True,
                "detail": "the scheduler knows no task by that name"}
    return {"known": True, "state": state, "disabled": state.lower() == "disabled"}


def measure_daemon(root: Path) -> Dict[str, Any]:
    """Read the existing verdict. Reuse `Heartbeat`; do not re-derive liveness."""
    heartbeat_file = _heartbeat_path(root)
    if not heartbeat_file.is_file():
        return {"heartbeat_available": False, "alive": False,
                "detail": f"no heartbeat at {heartbeat_file}",
                "verified": [], "unverified": ["daemon_liveness"]}

    status = Heartbeat(str(heartbeat_file.parent)).get_status(
        max_idle_seconds=MAX_IDLE_SECONDS)
    alive = bool(status.get("is_alive"))
    pid = status.get("pid")
    report: Dict[str, Any] = {
        "heartbeat_available": True,
        "alive": alive,
        "status": status.get("status"),
        "pid": pid,
        "run_id": status.get("run_id"),
        "last_beat": status.get("last_beat"),
        "last_start": status.get("last_start"),
        "seconds_since_last_beat": status.get("seconds_since_last_beat"),
        "max_idle_seconds": MAX_IDLE_SECONDS,
        "verified": [],
        "unverified": [],
    }

    # A live heartbeat whose pid belongs to some other process is the shape of a
    # reused pid, so confirm ownership when it can be measured. When it cannot,
    # say so instead of reading silence as a violation.
    if alive and isinstance(pid, int) and pid > 0:
        try:
            command_line = _process_command_line(pid)
        except (OSError, subprocess.SubprocessError):
            command_line = ""
        report["command_line"] = command_line
        if command_line:
            owned = ("ace_daemon.py" in command_line
                     or ("ace.py" in command_line and "daemon" in command_line))
            report["owns_pid"] = owned
            report["verified"].append("daemon_pid_ownership")
        else:
            report["owns_pid"] = None
            report["unverified"].append("daemon_pid_ownership")

    report["task"] = _task_state()
    return report


def measure_incident_evidence(root: Path) -> Dict[str, Any]:
    """How old the persistent incidents' own evidence is.

    An incident stays in semantic_incidents.json until an observation of its
    category proves recovery, and the daemon refreshes `last_observed_at` every
    cycle the condition is still true. So a frozen timestamp means the producer or
    the converter stopped, even while a heartbeat says the process is fine.
    """
    path = root / "06_RUNTIME" / "ace" / "data" / "observations" / "semantic_incidents.json"
    if not path.is_file():
        return {"present": False, "count": 0, "stale": [], "detail": "no incident file"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return {"present": True, "count": 0, "stale": [],
                "detail": f"unreadable: {type(error).__name__}: {error}",
                "unverified": ["incident_evidence"]}
    if not isinstance(payload, dict):
        return {"present": True, "count": 0, "stale": [],
                "detail": f"unexpected shape: {type(payload).__name__}"}

    stale: List[Dict[str, Any]] = []
    for rule, record in sorted(payload.items()):
        if not isinstance(record, dict):
            continue
        age = _age_minutes(record.get("last_observed_at"))
        if age is not None and age <= EVIDENCE_MAX_MINUTES:
            continue
        stale.append({
            "rule": rule,
            "task_id": record.get("task_id"),
            "last_observed_at": record.get("last_observed_at"),
            "age_minutes": None if age is None else round(age, 1),
            "detail": ("its evidence has not been refreshed inside "
                       f"{EVIDENCE_MAX_MINUTES} minutes"),
        })
    return {"present": True, "count": len(payload), "stale": stale,
            "max_age_minutes": EVIDENCE_MAX_MINUTES}


def start_task() -> Dict[str, Any]:
    """Start the daemon through the registered task - the sanctioned path."""
    started = time.time()
    try:
        result = subprocess.run(["schtasks", "/run", "/tn", TASK_NAME],
                                capture_output=True, text=True, timeout=120,
                                encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as error:
        return {"attempted": True, "returncode": None,
                "detail": f"{type(error).__name__}: {error}"}
    return {
        "attempted": True,
        "returncode": result.returncode,
        # The message is recorded verbatim because it is evidence, never parsed:
        # this host answers in Chinese and a decision must not depend on wording.
        "detail": ((result.stdout or "") + (result.stderr or "")).strip()[:300],
        "elapsed_seconds": round(time.time() - started, 1),
    }


def _recovered(before: Dict[str, Any], after: Dict[str, Any]) -> Optional[str]:
    """Which signal says the runtime is back, or None if none does."""
    if after.get("alive"):
        return "heartbeat_alive"
    before_run = before.get("run_id")
    after_run = after.get("run_id")
    if after_run and after_run != before_run:
        # A new run_id means a new process took the heartbeat, even if its first
        # stage beat has not landed yet.
        return "new_run_id"
    return None


def run(root: Path = ROOT, observer: Any = None, *,
        wait_seconds: int = RECOVERY_WAIT_SECONDS) -> Dict[str, Any]:
    before = measure_daemon(root)
    incidents = measure_incident_evidence(root)

    findings: List[Dict[str, Any]] = []
    if not before.get("heartbeat_available"):
        findings.append({
            "kind": "NO_HEARTBEAT_EVIDENCE",
            "severity": "medium",
            "detail": before.get("detail"),
        })
    elif not before.get("alive"):
        findings.append({
            "kind": "DAEMON_STOPPED",
            "severity": "high",
            "detail": (f"heartbeat status={before.get('status')} pid={before.get('pid')} "
                       f"last_beat={before.get('last_beat')} "
                       f"silent={before.get('seconds_since_last_beat')}s against a "
                       f"{MAX_IDLE_SECONDS}s allowance"),
        })
    elif before.get("owns_pid") is False:
        findings.append({
            "kind": "DAEMON_PID_NOT_OWNED",
            "severity": "high",
            "detail": (f"the heartbeat names pid {before.get('pid')} but that process is "
                       f"not the daemon: {before.get('command_line')!r}"),
        })

    for row in incidents.get("stale", []):
        findings.append({
            "kind": "INCIDENT_EVIDENCE_STALE",
            "severity": "medium",
            "rule": row["rule"],
            "task_id": row.get("task_id"),
            "detail": (f"incident {row['rule']} has not had its evidence refreshed "
                       f"for {row['age_minutes']} minutes while its condition remains "
                       f"on file"),
        })

    disposition: Dict[str, Any] = {"needed": bool(findings)}
    daemon_findings = [f for f in findings
                       if f["kind"] in {"DAEMON_STOPPED", "DAEMON_PID_NOT_OWNED"}]
    if daemon_findings:
        task = before.get("task") or {}
        if task.get("disabled"):
            disposition.update({
                "action": "none",
                "suppressed": "task is disabled, so starting it would fight an operator decision",
                "task_state": task.get("state"),
            })
        else:
            disposition["action"] = "start_task"
            disposition.update(start_task())
            deadline = time.time() + max(0, wait_seconds)
            after = measure_daemon(root)
            signal = _recovered(before, after)
            while signal is None and time.time() < deadline:
                time.sleep(10)
                after = measure_daemon(root)
                signal = _recovered(before, after)
            disposition["recovered_by"] = signal
            disposition["daemon_after"] = {
                "alive": after.get("alive"),
                "status": after.get("status"),
                "pid": after.get("pid"),
                "run_id": after.get("run_id"),
                "seconds_since_last_beat": after.get("seconds_since_last_beat"),
            }
            disposition["waited_seconds"] = round(
                max(0.0, time.time() - (deadline - max(0, wait_seconds))), 1)

    # Escalation goes through the existing channel, which only exists for a runtime
    # that is running: an observation recorded while nothing consumes it is the
    # same dead end as the alert nobody read.
    escalated = 0
    if findings and observer is not None:
        live = measure_daemon(root) if daemon_findings else before
        if live.get("alive"):
            for finding in findings:
                observer.record(
                    description=("daemon liveness watch: " + str(finding.get("detail"))),
                    system_state={
                        "kind": finding["kind"],
                        "severity": finding["severity"],
                        "rule": finding.get("rule"),
                        "task_id": finding.get("task_id"),
                        "disposition": disposition.get("action"),
                    },
                    severity=str(finding["severity"]),
                    source="daemon_liveness_watch",
                    category="structural_gap",
                    dedup_key=f"daemon_liveness:{finding['kind']}",
                )
                escalated += 1

    snapshot = {
        "contract_version": CONTRACT_VERSION,
        "at": _iso(_now()),
        "thresholds": {"max_idle_seconds": MAX_IDLE_SECONDS,
                       "evidence_max_minutes": EVIDENCE_MAX_MINUTES},
        "daemon": before,
        "incidents": incidents,
        "findings": findings,
        "disposition": disposition,
        "escalated": escalated,
    }

    snapshot_path = root / SNAPSHOT
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from core.window_write import write_window_artifact

        write_window_artifact(root, SNAPSHOT, payload, lane="governance-lane",
                              actor="daemon_liveness_watch")
    except Exception:
        snapshot_path.write_text(payload, encoding="utf-8")

    return {
        "status": "OK" if not findings else "FINDINGS",
        "contract_version": CONTRACT_VERSION,
        "findings": len(findings),
        "kinds": [f["kind"] for f in findings],
        "disposition": disposition.get("action"),
        "recovered_by": disposition.get("recovered_by"),
        "escalated": escalated,
        "snapshot": str(snapshot_path.relative_to(root)).replace("\\", "/"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--wait-seconds", type=int, default=RECOVERY_WAIT_SECONDS)
    args = parser.parse_args()

    observer = None
    try:
        from core.observation import RuntimeObserver

        observer = RuntimeObserver(
            data_dir=str(Path(args.root) / "06_RUNTIME" / "ace" / "data" / "observations"))
    except Exception:
        observer = None

    result = run(Path(args.root), observer, wait_seconds=args.wait_seconds)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"{result['status']:10s} findings={result['findings']} "
              f"disposition={result['disposition']} recovered_by={result['recovered_by']}")
        for kind in result["kinds"]:
            print(f"  {kind}")

    # A standing finding must be visible to the scheduler. The tick already reads
    # exit codes, and unlike the incident watch this one cannot rely on an
    # observation being consumed, because the consumer may be the thing that died.
    return 0 if result["status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
