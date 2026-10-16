"""A health check must never end as a task pointing at nothing.

The defect this pins: ACE-Watch-Hourly and ACE-Loop-Guardian both referenced
.ps1 scripts under the opencode temp directory. When the directory was cleaned,
both tasks fired on schedule and both failed on schedule, and nothing said so:
one was a structural-integrity watch that had not looked in 27 hours, the other
a loop monitor whose loop had already closed.

The contract, stated so a machine can check it:

  - The watch tick launcher must live in the repo, not under a cleanable temp
    directory. A path under a temp dir is the shape that vanished once already.
  - NOT_DUE is a success state. The watch owns a twelve-hour interval and the
    task fires hourly, so most ticks are correctly no-ops. Treating "snapshot
    not refreshed on a no-op hour" as failure cries wolf every hour between real
    runs, which is how you train people to ignore the watch.
  - The closed loop monitor must not be re-pointed at anything. Its receipt says
    the loop held for three consecutive sweeps; a task that re-fires a closed
    monitor is re-opening finished work, not watching.

The static checks run everywhere. The behavioural checks need the deployed
subsystem and skip where it was never deployed rather than reporting green on
machines where they never ran.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TICK = REPO / "ops" / "watch_tick.ps1"
POWERSHELL = shutil.which("powershell") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def _text(path):
    return Path(path).read_text(encoding="utf-8", errors="replace")


def _normalise(text):
    return " ".join(text.split())


def _code(path):
    """PowerShell with comments removed - what actually executes.

    The repo's own headers name the temp directory that swallowed the scripts,
    which defeats a naive substring check the same way it did for the installer
    tests. Quote-aware: a # inside a string is not a comment.
    """
    text = _text(path)
    out, i = [], 0
    in_string = None
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == in_string:
                if i + 1 < len(text) and text[i + 1] == in_string:
                    out.append(text[i:i + 2])
                    i += 2
                    continue
                in_string = None
            out.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            in_string = ch
            out.append(ch)
            i += 1
            continue
        if ch == "<" and text.startswith("<#", i):
            end = text.find("#>", i + 2)
            i = len(text) if end == -1 else end + 2
            out.append(" ")
            continue
        if ch == "#":
            end = text.find("\n", i)
            i = len(text) if end == -1 else end
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return _normalise("".join(out))


# --------------------------------------------------------------- static contract


def test_the_tick_launcher_does_not_reference_a_temp_directory():
    """The shape that vanished once already.

    Asserting "no temp path" rather than "repo path" keeps the test honest: it
    rejects any cleanable directory, not just the one that bit us.
    """
    source = _code(TICK)
    assert "Temp" not in source and "TEMP" not in source and "Local\\Temp" not in source, (
        "the tick launcher must live where a cleaner cannot remove it"
    )


def test_not_due_is_a_success_state():
    """The watch's interval is twelve hours and the task fires hourly.

    Treating a no-op hour as failure reports an error eleven hours out of twelve,
    which is how you train people to ignore the watch they built.
    """
    source = _code(TICK)
    assert "NOT_DUE" in source, "the no-op state must be handled, not ignored"
    assert re.search(r'"NOT_DUE"\)?\s*\{[^}]*exit 0', source), (
        "a no-op tick must exit zero"
    )


def test_the_tick_never_forces_the_watch():
    """--force on every tick would rewrite the snapshot hourly.

    The snapshot's cadence is evidence of when the watch last actually looked.
    Forcing it destroys that evidence.
    """
    source = _code(TICK)
    assert "--force" not in source, (
        "the tick must let the watch own its interval"
    )


def test_a_scan_is_verified_by_freshness_not_by_exit_code():
    """Zero exit is not proof the watch looked; only a fresh snapshot is.

    The check must be conditional on SCANNED: demanding freshness on a no-op hour
    is the same wolf-crying as the NOT_DUE bug in the other direction.
    """
    source = _code(TICK)
    scanned = source.find("SCANNED")
    assert scanned > 0, "the scan state must be handled"
    assert "snapshot" in source[scanned:scanned + 800], (
        "after a scan, the snapshot must be verified fresh"
    )


# ------------------------------------------------------------ behavioural proof

@pytest.mark.skipif(not (TICK.is_file() and POWERSHELL), reason="needs the tick and powershell on a Windows host")
def test_the_tick_exits_zero_in_both_states():
    """The tick must not fail on a no-op hour.

    Two consecutive runs: the first may scan or not, but the second is certainly
    inside the twelve-hour interval and must exit zero anyway. A watcher that
    needs forcing to look healthy is not healthy.
    """
    for attempt in range(2):
        proc = subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(TICK)],
            capture_output=True, text=True, timeout=600,
            encoding="utf-8", errors="replace", cwd=str(REPO),
        )
        assert proc.returncode == 0, (
            f"tick run {attempt + 1} failed (rc={proc.returncode}):\n"
            f"{(proc.stdout or '')[:600]}{(proc.stderr or '')[:600]}"
        )
