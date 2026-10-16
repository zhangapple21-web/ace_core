"""A watch that is not run is not a watch.

The hourly tick had two failure modes that both looked like success.

Its launcher lived under the opencode temp directory, which was cleaned. After it
vanished, ACE-Watch-Hourly fired and failed every hour while the
dead_components_snapshot it exists to refresh went 27 hours stale, and nothing
reported it because nothing watched the watcher.

Then the tick itself was PowerShell, launched through wscript. In the scheduler's
window-less context that chain stops silently while Task Scheduler still records
exit 0, so the job reported success having done nothing - twice over, across two
different causes. The tick is now a Python entry point launched by pythonw, which
needs no window and no wrapper. That change is what these tests protect, along
with the discipline that proved it: delete the artifact, run the task, confirm the
artifact came back. An exit code is not evidence.

Each watch is judged by its own snapshot age rather than one shared threshold,
because dead_component_watch owns a twelve-hour interval and its snapshot is
routinely two hours old. A single freshness bound made the tick fail on eleven of
twelve hours - a watcher that cries wolf is as blind as one that never speaks.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TICK = REPO / "ops" / "watch_tick.py"
WATCH_SCRIPT = REPO / "ops" / "incident_reachability_watch.py"

python = sys.executable or "py"


# --------------------------------------------------------------- static contract


def test_the_tick_is_a_python_entry_point():
    """The PowerShell wrapper stopped running under the scheduler.

    wscript -> powershell -> py -> python is four layers that each need something
    the scheduler's context does not provide. pythonw needs none of it. Routing
    the tick back through PowerShell restores a silent failure that reports exit 0.
    """
    assert TICK.is_file(), "the tick must be a Python entry point"
    assert not (REPO / "ops" / "watch_tick.ps1").exists(), (
        "the PowerShell tick was removed once it was shown to stop silently under "
        "the scheduler; its return would restore that failure"
    )


def test_both_watches_are_driven_by_the_same_tick():
    """The incident watch needs the same guarantee the dead-component watch got.

    A persistent incident pointer sat claiming open work for eighteen days while
    the task it named had been archived minutes after creation, because the rule's
    category never produced an observation the reconciler could see. A watch that
    is not run is not a watch, and running it by hand is not running it.
    """
    source = TICK.read_text(encoding="utf-8")
    assert "incident_reachability_watch.py" in source, (
        "the incident-reachability watch must be driven by the hourly tick"
    )
    assert "dead_component_watch.py" in source
    assert "incident_reachability_snapshot.json" in source, (
        "the incident watch's snapshot must be checked, not merely invoked"
    )


def test_each_watch_has_its_own_age_floor():
    """One threshold for both would fail eleven hours in twelve.

    dead_component_watch runs every twelve hours, so its snapshot is legitimately
    old. incident_reachability_watch has no interval and must refresh every tick.
    """
    source = TICK.read_text(encoding="utf-8")
    floors = re.findall(r'"max_age_minutes":\s*(\d+)', source)
    assert len(floors) >= 2, "each watch needs its own age floor"
    assert len(set(floors)) >= 2, (
        "both watches share one floor, which either fails the interval-guarded "
        "watch on every no-op hour or lets the other go stale unnoticed"
    )


def test_exit_zero_is_not_treated_as_proof():
    """The snapshot on disk is the evidence, not the return code."""
    source = TICK.read_text(encoding="utf-8")
    assert "NO_SNAPSHOT" in source and "STALE_SNAPSHOT" in source, (
        "a watch that exits 0 without writing or refreshing its snapshot must be "
        "a failure - that is precisely how the scheduler reported success for 27 "
        "hours of not running"
    )


def test_each_watch_is_verified_independently():
    """One failing watch must not be masked by another passing."""
    source = TICK.read_text(encoding="utf-8")
    assert "results = [run_watch(watch, root, python) for watch in watches]" in source
    assert "failed = [r for r in results if r[\"status\"] != \"OK\"]" in source


def test_forcing_a_watch_every_tick_is_not_permitted():
    """--force would destroy the cadence evidence of when it last looked."""
    source = TICK.read_text(encoding="utf-8")
    assert '"--force"' not in source, (
        "the tick must let each watch own its interval"
    )


# ---------------------------------------------------------- behavioural proof


def test_the_tick_runs_both_watches_and_judges_each_by_its_own_snapshot():
    proc = subprocess.run(
        [python, "-u", str(TICK), "--root", str(REPO)],
        capture_output=True, text=True, timeout=1200,
        encoding="utf-8", errors="replace", cwd=str(REPO))
    assert proc.returncode == 0, (
        f"tick failed: {(proc.stdout or '')[-400:]}{(proc.stderr or '')[-300:]}"
    )
    for name in ("dead_component_watch", "incident_reachability_watch"):
        assert name in (proc.stdout or ""), f"{name} did not run under the tick"


def test_the_tick_reports_a_broken_watch_instead_of_passing():
    """A watch that cannot run must fail the tick, not be skipped.

    Verified with a throwaway root whose incident-reachability script is absent,
    so the failure is real without touching the deployed subsystem.
    """
    import shutil
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "ops").mkdir()
        shutil.copy2(TICK, root / "ops" / "watch_tick.py")
        shutil.copy2(REPO / "ops" / "incident_reachability_watch.py",
                     root / "ops" / "incident_reachability_watch.py")
        # dead_component_watch.py deliberately left absent
        proc = subprocess.run(
            [python, "-u", str(root / "ops" / "watch_tick.py"),
             "--root", str(root), "--json"],
            capture_output=True, text=True, timeout=600,
            encoding="utf-8", errors="replace")
        assert proc.returncode != 0, (
            "a missing watch script produced a passing tick; that is how a broken "
            "watcher looks exactly like a working one"
        )
        assert "dead_component_watch" in (proc.stdout or "")


def test_the_tick_does_not_force_the_interval_guarded_watch():
    """dead_component_watch is NOT_DUE most hours, and that is not a failure.

    Its twelve-hour interval means an hourly tick is a no-op eleven times in twelve.
    Treating the unchanged snapshot as an error would make the tick cry wolf every
    hour and train people to ignore it.
    """
    report = json.loads(subprocess.run(
        [python, "-u", str(TICK), "--root", str(REPO), "--json"],
        capture_output=True, text=True, timeout=1200,
        encoding="utf-8", errors="replace", cwd=str(REPO)).stdout)
    statuses = {w["name"]: w["status"] for w in report["watches"]}
    assert statuses["dead_component_watch"] in {"OK"}, (
        f"an interval-guarded no-op must read OK, got {statuses['dead_component_watch']}"
    )