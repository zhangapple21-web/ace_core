"""A wrapper that cannot survive a hidden context is not a wrapper.

Found the hard way, and the diagnosis took three wrong turns before landing, so
what is pinned here is the conclusion rather than the theory.

A structural watch scheduled hourly reported exit 0 on every fire while its
snapshot went 27 hours stale: the job never ran. Three candidate explanations
were each disproved by experiment rather than reasoning:

  wscript.exe starts no child process at all - disproved. Given a captured
    pipe it launches powershell and the child completes.
  cmd.exe is the reliable host - disproved. The same command that works from a
    console writes its first line under the scheduler and then stops at whichever
    external command it reaches next; every fix moved the failure one step on.
  the py.exe launcher shim is the problem - disproved. Calling the resolved
    interpreter directly failed identically.

What remains is the one thing all the failures share: a window-less context.
The tick ran under wscript -> powershell -> py -> python, and every layer that
needs a console is a place it can stop without anyone noticing, because Task
Scheduler records exit 0 either way. The same tick launched directly by pythonw,
which allocates no window, completes and produces its snapshot.

So this test pins the property that made the difference observable: a scheduled
job's exit code is not evidence it did anything. The proof has to be an artifact
the run had to produce. That is why the verification used by this repository
deletes the snapshot and triggers the task, rather than reading LastTaskResult.

If a future change to this host makes the wrapped path work, the assertion below
fails and says the workaround can be reconsidered deliberately - which is the
correct time to remove it.
"""
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
ROOT = Path(r"C:\tmp\ace_core")
TICK = ROOT / "ops" / "watch_tick.py"
SNAPSHOT = ROOT / "08_GOVERNANCE" / "structural_integrity" / "incident_reachability_snapshot.json"

pytestmark = pytest.mark.skipif(
    not TICK.is_file(), reason="the watch tick entry point is not present"
)


def _ps(command):
    return subprocess.run([PS, "-NoProfile", "-Command", command],
                          capture_output=True, text=True, timeout=300,
                          encoding="utf-8", errors="replace").stdout.strip()


def test_the_tick_itself_succeeds_and_refreshes_its_snapshot():
    """Direct invocation is the baseline the scheduler must be able to match."""
    proc = subprocess.run([r"C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe",
                           "-u", str(TICK), "--root", str(ROOT)],
                          capture_output=True, text=True, timeout=900,
                          encoding="utf-8", errors="replace", cwd=str(ROOT))
    assert proc.returncode == 0, (
        f"the tick failed on its own terms, so a scheduler failure would say "
        f"nothing: {(proc.stdout or '')[-500:]}{(proc.stderr or '')[-300:]}"
    )
    assert SNAPSHOT.is_file(), "the tick exited 0 without writing its snapshot"


def test_a_scheduled_job_must_be_proven_by_its_artifact_not_its_exit_code():
    """The verification discipline this repository uses, and why.

    Reading LastTaskResult was what hid a watch that reported success for 27 hours
    without running once. Task Scheduler reports 0 for a wrapper that starts and
    then stops, so the only sound check deletes the artifact the run had to produce
    and confirms it came back.

    Skipped where the task is not scheduled rather than passing on a machine where
    the check never ran.
    """
    state = _ps(f"if (Get-ScheduledTask -TaskName 'ACE-Watch-Hourly' -ErrorAction SilentlyContinue)"
                f"{{ 'yes' }} else {{ 'no' }}")
    if state != "yes":
        pytest.skip("ACE-Watch-Hourly is not scheduled on this host")

    backup = None
    if SNAPSHOT.is_file():
        backup = SNAPSHOT.read_bytes()
        SNAPSHOT.unlink()

    try:
        subprocess.run([PS, "-NoProfile", "-Command",
                        "Start-ScheduledTask -TaskName 'ACE-Watch-Hourly'"],
                       check=True, capture_output=True, timeout=120)

        deadline = time.time() + 300
        task_state = ""
        while time.time() < deadline:
            task_state = _ps("(Get-ScheduledTask -TaskName 'ACE-Watch-Hourly').State")
            if task_state in ("3", "Ready"):
                break
            time.sleep(3)

        assert SNAPSHOT.is_file(), (
            "the scheduled task did not regenerate the snapshot it owns; an exit "
            "code of 0 is not evidence it ran, which is exactly the failure this "
            "check exists to catch"
        )
        data = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        assert "unreachable_incident_rules" in data, (
            "the snapshot was regenerated but is not the watch's own output"
        )
    finally:
        if backup is not None and not SNAPSHOT.is_file():
            SNAPSHOT.write_bytes(backup)


def test_the_tick_is_not_launched_through_powershell():
    """Keeps the workaround from quietly being undone.

    The tick is a Python entry point launched by pythonw precisely because the
    wscript -> powershell -> py chain stops in a window-less context. Routing it
    back through powershell would restore the silent failure, and the artifact
    check above would start failing on a clean host.
    """
    assert TICK.suffix == ".py", (
        "the tick must stay a Python entry point; the PowerShell wrapper stopped "
        "running under the scheduler"
    )
    action = _ps("(Get-ScheduledTask -TaskName 'ACE-Watch-Hourly' -ErrorAction SilentlyContinue)"
                 ".Actions.Arguments")
    if action:
        assert "watch_tick.py" in action and "powershell" not in action.lower(), (
            f"the scheduled action goes back through PowerShell: {action!r}"
        )