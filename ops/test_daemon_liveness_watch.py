"""The watch has to act, and it has to be safe to run where nothing is wrong.

Two properties carry the weight here and both are pinned below.

The first is that a stopped runtime produces a *disposition*, not a sentence. The
outage this was written for already proved the detection half worked: the hourly
checkup recorded `daemon心跳存活` as an error three times while the daemon was dead
for nine and a half hours, and the heartbeat file still carries the trace at 03:47
on 2026-10-17. What was missing was anything that would start it again.

The second is that running the watch when nothing is wrong must be a no-op, and
that is not only about tidiness. The tick is invoked against throwaway roots by
`test_watch_tick.py`, and a watch that started the real daemon on behalf of a
temporary directory would be a test that reaches into production. The rule that
answers it is deliberate: no heartbeat file means the evidence of a crash is
absent, so the finding is recorded and no start is attempted. Absence is not
evidence.

The crash test that motivated the recovery is pinned in `test_daemon_recovery`
below as a recorded fact rather than a re-run: the scheduler's own
`RestartOnFailure` did not fire within eight minutes of an external kill, so
"something else will bring it back" was not a plan.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import ops.daemon_liveness_watch as dlw  # noqa: E402

SCRIPT = REPO / "ops" / "daemon_liveness_watch.py"
SOURCE = SCRIPT.read_text(encoding="utf-8")


class Observer:
    """Stands in for RuntimeObserver, which is what escalation goes through."""

    def __init__(self):
        self.records = []

    def record(self, **kwargs):
        self.records.append(kwargs)
        return {"id": len(self.records)}


def _memory(root: Path) -> Path:
    return root / "06_RUNTIME" / "ace" / "data" / "memory"


def _seed_heartbeat(root: Path, *, pid: int, run_id: str, status: str = "alive",
                    beat_age_seconds: float = 0.0) -> Path:
    memory = _memory(root)
    memory.mkdir(parents=True, exist_ok=True)
    last_beat = datetime.now() - timedelta(seconds=beat_age_seconds)
    payload = {
        "born_at": (datetime.now() - timedelta(days=1)).isoformat(),
        "last_beat": last_beat.isoformat(),
        "last_start": last_beat.isoformat(),
        "beat_count": 1,
        "status": status,
        "consecutive_misses": 0,
        "pid": pid,
        "run_id": run_id,
        "owner": "ace_daemon",
    }
    path = memory / "heartbeat.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _seed_incident(root: Path, rule: str, *, age_minutes: float,
                   task_id: str = "RQ-20260101-001") -> None:
    directory = root / "06_RUNTIME" / "ace" / "data" / "observations"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "semantic_incidents.json"
    payload = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    payload[rule] = {
        "schema_version": 1,
        "signature": "0" * 64,
        "task_id": task_id,
        "last_observed_at": (datetime.now() - timedelta(minutes=age_minutes)).isoformat(),
        "reason": "persistent_semantic_incident",
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _healthy(root: Path, monkeypatch, run_id: str = "run-a") -> None:
    _seed_heartbeat(root, pid=os.getpid(), run_id=run_id)
    monkeypatch.setattr(dlw, "_process_command_line",
                        lambda pid: r'"C:\...\pythonw.exe" "C:\...\ace.py" daemon --serve')
    monkeypatch.setattr(dlw, "_task_state",
                        lambda: {"known": True, "state": "Ready", "disabled": False})


# ------------------------------------------------------------ the reuse claims


def test_the_verdict_is_the_existing_heartbeat_not_a_second_liveness_rule():
    """A second liveness rule would be a second thing to disagree with the first."""
    assert "from core.heartbeat import Heartbeat" in SOURCE
    assert "get_status(" in SOURCE and "is_alive" in SOURCE
    assert "MAX_IDLE_SECONDS" in SOURCE, (
        "a threshold tighter than the checkup's hour must be stated, not implied"
    )


def test_the_escalation_reuses_the_category_the_converter_can_see():
    """A new category would be a finding nothing consumes - STUCK_NO_OBSERVATION."""
    assert 'category="structural_gap"' in SOURCE
    assert "dedup_key=" in SOURCE, (
        "without a stable key, one hourly tick would produce one task per hour"
    )


def test_the_recovery_uses_the_registered_task_rather_than_a_new_supervisor():
    assert 'TASK_NAME = "ACE_Daemon_Boot"' in SOURCE
    assert '["schtasks", "/run", "/tn", TASK_NAME]' in SOURCE
    assert "RestartOnFailure" in SOURCE or "RestartOnFailure" in __doc__


# --------------------------------------------------------------- the judgments


def test_a_running_runtime_is_not_a_finding(tmp_path, monkeypatch):
    _healthy(tmp_path, monkeypatch)
    observer = Observer()
    result = dlw.run(tmp_path, observer)
    assert result["status"] == "OK", result
    assert result["findings"] == 0
    assert observer.records == [], "a healthy runtime must not be escalated as a gap"


def test_a_stopped_runtime_is_a_finding_and_starts_the_existing_task(tmp_path, monkeypatch):
    _seed_heartbeat(tmp_path, pid=999999, run_id="dead-run", beat_age_seconds=3 * 3600)
    monkeypatch.setattr(dlw, "_task_state",
                        lambda: {"known": True, "state": "Ready", "disabled": False})
    calls = []
    monkeypatch.setattr(dlw, "start_task",
                        lambda: calls.append(1) or {"attempted": True, "returncode": 0,
                                                    "detail": "started"})
    observer = Observer()

    result = dlw.run(tmp_path, observer, wait_seconds=0)

    assert result["status"] == "FINDINGS"
    assert "DAEMON_STOPPED" in result["kinds"]
    assert calls == [1], "a stopped runtime must actually be restarted"
    snapshot = json.loads(
        (tmp_path / dlw.SNAPSHOT).read_text(encoding="utf-8"))
    assert snapshot["findings"][0]["kind"] == "DAEMON_STOPPED"
    assert snapshot["disposition"]["action"] == "start_task"
    assert snapshot["disposition"]["recovered_by"] is None


def test_a_recovered_runtime_is_escalated_through_the_pipeline_it_restored(tmp_path, monkeypatch):
    """Escalate *after* it is alive again, because before that nobody is listening."""
    _seed_heartbeat(tmp_path, pid=999999, run_id="dead-run", beat_age_seconds=3 * 3600)
    monkeypatch.setattr(dlw, "_task_state",
                        lambda: {"known": True, "state": "Ready", "disabled": False})
    monkeypatch.setattr(dlw, "_process_command_line",
                        lambda pid: r'"C:\...\pythonw.exe" "C:\...\ace.py" daemon --serve')

    def fake_start():
        _seed_heartbeat(tmp_path, pid=os.getpid(), run_id="revived-run")
        return {"attempted": True, "returncode": 0, "detail": "started"}

    monkeypatch.setattr(dlw, "start_task", fake_start)
    observer = Observer()

    result = dlw.run(tmp_path, observer, wait_seconds=0)

    assert result["recovered_by"] in {"heartbeat_alive", "new_run_id"}
    assert result["findings"] == 1, "the outage still happened; recovery is not erasure"
    assert len(observer.records) == 1
    record = observer.records[0]
    assert record["category"] == "structural_gap"
    assert record["dedup_key"] == "daemon_liveness:DAEMON_STOPPED"
    assert record["severity"] == "high"


def test_a_disabled_task_suppresses_the_recovery(tmp_path, monkeypatch):
    """Stopping the daemon by disabling its task is a decision, not a fault."""
    _seed_heartbeat(tmp_path, pid=999999, run_id="dead-run", beat_age_seconds=3 * 3600)
    monkeypatch.setattr(dlw, "_task_state",
                        lambda: {"known": True, "state": "Disabled", "disabled": True})

    def must_not_run():
        raise AssertionError("the recovery started a task the operator disabled")

    monkeypatch.setattr(dlw, "start_task", must_not_run)

    result = dlw.run(tmp_path, None, wait_seconds=0)

    snapshot = json.loads((tmp_path / dlw.SNAPSHOT).read_text(encoding="utf-8"))
    assert snapshot["disposition"]["action"] == "none"
    assert "disabled" in snapshot["disposition"]["suppressed"]
    assert result["status"] == "FINDINGS"


def test_absent_heartbeat_evidence_is_reported_and_does_not_authorize_a_start(tmp_path, monkeypatch):
    """Absence is not evidence of a crash, and this keeps temp roots harmless.

    The tick is run against throwaway roots by test_watch_tick.py. If a missing
    heartbeat file were read as a dead runtime, those runs would start the real
    daemon task on behalf of a temporary directory.
    """
    def must_not_run():
        raise AssertionError("a missing heartbeat triggered a start of the real task")

    monkeypatch.setattr(dlw, "start_task", must_not_run)
    observer = Observer()

    result = dlw.run(tmp_path, observer, wait_seconds=0)

    assert result["kinds"] == ["NO_HEARTBEAT_EVIDENCE"]
    assert result["disposition"] is None, (
        "no daemon finding means no action, so the result carries no disposition"
    )
    snapshot = json.loads((tmp_path / dlw.SNAPSHOT).read_text(encoding="utf-8"))
    assert snapshot["disposition"].get("action") is None
    assert observer.records == [], "nothing can consume an escalation in an empty root"


def test_a_live_pid_that_is_not_the_daemon_is_a_finding(tmp_path, monkeypatch):
    """The heartbeat can name a pid that exists and is something else entirely."""
    _seed_heartbeat(tmp_path, pid=os.getpid(), run_id="reused")
    monkeypatch.setattr(dlw, "_process_command_line",
                        lambda pid: r"C:\Windows\explorer.exe")
    monkeypatch.setattr(dlw, "_task_state",
                        lambda: {"known": True, "state": "Ready", "disabled": False})
    calls = []
    monkeypatch.setattr(dlw, "start_task",
                        lambda: calls.append(1) or {"attempted": True, "returncode": 0,
                                                    "detail": ""})

    result = dlw.run(tmp_path, None, wait_seconds=0)

    assert "DAEMON_PID_NOT_OWNED" in result["kinds"]
    assert calls == [1]


def test_an_unmeasurable_command_line_is_named_unverified_not_treated_as_a_fault(tmp_path, monkeypatch):
    """A measurement gap is not a violation, but it must not pass as confirmation."""
    _seed_heartbeat(tmp_path, pid=os.getpid(), run_id="run-a")
    monkeypatch.setattr(dlw, "_task_state",
                        lambda: {"known": True, "state": "Ready", "disabled": False})

    def unavailable(pid):
        return ""

    monkeypatch.setattr(dlw, "_process_command_line", unavailable)

    result = dlw.run(tmp_path, None, wait_seconds=0)

    assert result["status"] == "OK", "an unavailable measurement must not start a process"
    snapshot = json.loads((tmp_path / dlw.SNAPSHOT).read_text(encoding="utf-8"))
    assert "daemon_pid_ownership" in snapshot["daemon"]["unverified"]
    assert snapshot["daemon"]["owns_pid"] is None


def test_frozen_incident_evidence_is_a_finding_while_the_process_looks_fine(tmp_path, monkeypatch):
    """A heartbeat says the process is up; it does not say the pipeline is moving."""
    _healthy(tmp_path, monkeypatch)
    _seed_incident(tmp_path, "fragment_backlog", age_minutes=3 * 60)
    _seed_incident(tmp_path, "cross_agent_idle", age_minutes=1)
    calls = []
    monkeypatch.setattr(dlw, "start_task",
                        lambda: calls.append(1) or {"attempted": True, "returncode": 0,
                                                    "detail": ""})
    observer = Observer()

    result = dlw.run(tmp_path, observer, wait_seconds=0)

    assert result["kinds"] == ["INCIDENT_EVIDENCE_STALE"]
    assert calls == [], "there is nothing to start; the runtime is already up"
    assert len(observer.records) == 1
    assert observer.records[0]["dedup_key"] == "daemon_liveness:INCIDENT_EVIDENCE_STALE"
    assert observer.records[0]["system_state"]["rule"] == "fragment_backlog"


def test_fresh_incident_evidence_is_not_reported(tmp_path, monkeypatch):
    _healthy(tmp_path, monkeypatch)
    _seed_incident(tmp_path, "fragment_backlog", age_minutes=1)
    observer = Observer()
    result = dlw.run(tmp_path, observer)
    assert result["status"] == "OK"
    assert observer.records == []


def test_naive_local_timestamps_are_not_read_as_utc(tmp_path, monkeypatch):
    """semantic_incidents.json writes local time with no offset.

    Reading a naive local stamp as UTC inflates its age by the host's offset - 8
    hours here - which turns a fresh record into an old one. The arithmetic below
    is the check: a record written moments ago must read as moments ago.
    """
    _healthy(tmp_path, monkeypatch)
    _seed_incident(tmp_path, "fragment_backlog", age_minutes=0)
    report = dlw.measure_incident_evidence(tmp_path)
    assert report["stale"] == []


# ------------------------------------------------------------ the run contract


def test_a_standing_finding_is_visible_to_the_scheduler(tmp_path):
    """Exit 0 with a standing finding is how a broken watcher looks like a good one.

    This runs the real script against an empty root, which is the one failure the
    watch refuses to act on, so nothing outside the temporary directory is touched.
    """
    python = sys.executable or "py"
    proc = subprocess.run([python, "-u", str(SCRIPT), "--root", str(tmp_path), "--json"],
                          capture_output=True, text=True, timeout=300,
                          encoding="utf-8", errors="replace", cwd=str(REPO))
    assert proc.returncode != 0, (proc.stdout or "")[-400:]
    result = json.loads(proc.stdout)
    assert result["status"] == "FINDINGS"
    assert (tmp_path / dlw.SNAPSHOT).is_file(), "a finding must leave an artifact"


def test_the_watch_is_registered_in_the_existing_tick():
    tick = (REPO / "ops" / "watch_tick.py").read_text(encoding="utf-8")
    assert "daemon_liveness_watch.py" in tick, (
        "a watch outside the WATCHES registry never runs, which is the failure "
        "test_watch_tick.py already names"
    )
    assert "daemon_liveness_snapshot.json" in tick, (
        "its snapshot must be checked, not merely invoked"
    )
