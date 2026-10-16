"""The tinghe task installer must reproduce what the machine actually runs.

The installer exists because the eight task definitions lived only in the Task
Scheduler database. That fix is only worth something if the declared table keeps
matching the deployed state, and if the three bugs found while building it cannot
come back:

  - New-ScheduledTaskAction's parameter is -Argument, singular. The task object's
    property is Arguments, plural. Passing the plural form fails parameter
    binding and the installer registers nothing at all - which is exactly what
    happened until the registration probe caught it.
  - Wrapper log paths are absolute under the site directory. A relative path
    writes into the wrappers directory instead, so the logs never reach the site.
  - Wrappers are GBK. cmd.exe reads a batch file in the OEM codepage, so UTF-8
    would make the cd fail - the failure the 2026-10-14 probe scripts chased.

Static assertions run everywhere. The behavioural one runs -Check against the
deployed subsystem, and skips on a machine that never deployed it rather than
reporting green on a machine where it never ran.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "ops" / "install_tinghe_tasks.ps1"
WRAPPERS = Path(r"C:\tmp\tinghe-wrappers")
LAUNCHER = Path(r"C:\tmp/run-hidden-wait.vbs")
POWERSHELL = shutil.which("powershell") or r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"


def _source():
    return INSTALLER.read_text(encoding="utf-8", errors="replace")


def _source_of(path):
    return path.read_text(encoding="utf-8", errors="replace")


def _normalise(text):
    return " ".join(text.split())


def _names():
    return re.findall(r'Name\s*=\s*"(tinghe-[a-z0-9-]+)"', _source())


# ------------------------------------------------------------- static contract


def test_the_installer_uses_the_singular_argument_parameter():
    """The bug that made the installer register nothing.

    New-ScheduledTaskAction takes -Argument; the task object exposes Arguments.
    Using the plural form is a parameter-binding failure, not a warning, so the
    installer silently registers zero tasks and still reports the seven that were
    already correct.
    """
    source = _source()
    assert "-Arguments " not in source, (
        "New-ScheduledTaskAction's parameter is -Argument (singular); the plural "
        "fails binding and the installer registers nothing"
    )
    assert "-Argument " in source, (
        "the action must pass its arguments somewhere"
    )


def test_wrapper_log_paths_are_absolute_under_the_site():
    """A relative log path writes into the wrappers dir, not the site.

    Found by diffing generated wrappers against the working ones byte for byte:
    eight files differed on exactly this.
    """
    source = _source()
    assert "Join-Path $SitePath $Task.Log" in source, (
        "the log path must be built under the site directory"
    )
    assert 'Join-Path $SitePath "$base.rc"' in source, (
        "the rc path must be built under the site directory too"
    )


def test_wrappers_are_written_as_gbk():
    """UTF-8 wrappers make cmd.exe's cd fail on the CJK site path."""
    source = _source()
    assert "GetEncoding(936)" in source, (
        "wrappers must be written in the OEM codepage cmd.exe reads (GBK/936)"
    )
    assert "WriteAllBytes" in source, (
        "writing bytes, not text, is what makes the encoding explicit"
    )


def test_the_launcher_is_deployed_from_the_repo_not_regenerated():
    """The .cmd routing fix must travel with the installer.

    If the installer wrote its own launcher, the verified cmd.exe routing could
    be replaced by a vulnerable copy that nobody noticed.
    """
    source = _source()
    assert "Copy-Item -LiteralPath $LauncherSource" in source, (
        "the launcher must be copied from the repo, not regenerated"
    )
    assert (REPO / "ops" / "launchers" / "run-hidden-wait.vbs").is_file()


def test_the_task_table_declares_every_task_exactly_once():
    source = _source()
    names = _names()
    assert len(names) == 8, f"expected eight tasks, found {len(names)}: {names}"
    assert len(set(names)) == len(names), "duplicate task names in the table"

    times = re.findall(r'Time\s*=\s*"(\d{2}:\d{2})"', source)
    assert len(times) == 8 and len(set(times)) == len(times), (
        f"each task needs its own fire time: {times}"
    )


def test_the_two_tasks_that_differ_from_the_default_still_do():
    """genre-check and daily-origin are not interchangeable with the rest.

    A well-meant "all of these are the same" cleanup would silently change a job
    that runs elevated with a one-hour cap into one that does not.
    """
    source = _source()
    genre = re.search(r'Name = "tinghe-genre-check".*?RestartCount = \d+;',
                      source, re.S)
    assert genre, "cannot find the genre-check row"
    row = genre.group(0)
    assert "LimitHours = 1" in row, "genre-check has a one-hour cap, not twelve"
    assert "Elevated = $true" in row, "genre-check runs elevated"
    assert "BatteryOk = $false" in row, "genre-check must not run on batteries"
    assert "Wake = $false" in row, "genre-check must not wake the machine"

    daily = re.search(r'Name = "tinghe-daily-origin".*?RestartIntervalMinutes = \d+',
                      source, re.S)
    assert daily, "cannot find the daily-origin row"
    assert "RestartCount = 2" in daily.group(0), (
        "daily-origin alone retries twice"
    )
    assert "RestartIntervalMinutes = 5" in daily.group(0)


# ---------------------------------------------------------- the restart interval


def _strip_ps_comments(text):
    """Remove PowerShell comments so assertions inspect code, not prose.

    The installer's own comment names the broken spelling to explain why it is
    avoided, which defeats a naive substring check - the test passed the fix and
    failed the comment. Quote-aware: a # inside a string is not a comment.
    Handles both # line comments and <# block #> comments.
    """
    out = []
    i = 0
    n = len(text)
    in_string = None
    while i < n:
        ch = text[i]
        if in_string:
            if ch == in_string:
                # a doubled quote is an escaped quote, not a terminator
                if i + 1 < n and text[i + 1] == in_string:
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
            i = n if end == -1 else end + 2
            out.append(" ")
            continue
        if ch == "#":
            end = text.find("\n", i)
            i = n if end == -1 else end
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _code(path):
    """The installer with comments removed - what actually executes."""
    return _normalise(_strip_ps_comments(_source_of(path)))


def test_restart_interval_is_passed_as_a_cmdlet_parameter():
    """The trap that made daily-origin unregisterable.

    Both spellings look equivalent and only one of them is. Passing
    -RestartInterval to New-ScheduledTaskSettingsSet serialises to
    <Interval>PT5M</Interval>. Assigning $settings.RestartInterval afterwards
    serialises the same TimeSpan to 00:05:00 instead, and Register-ScheduledTask
    rejects the XML: "(36,28):Interval:00:05:00".

    Only tinghe-daily-origin sets a retry interval, so nothing else exercised the
    path and the installer registered seven tasks while reporting the eighth as
    failed. The assertion names the broken spelling rather than requiring the
    fixed one, so a rewrite that finds another way is still accepted.

    Checked against comment-stripped source: the installer's own comment names
    the broken spelling in order to explain why it is avoided.
    """
    source = _code(INSTALLER)
    assert "$settings.RestartInterval =" not in source, (
        "assigning RestartInterval as a property serialises to 00:05:00 and "
        "Register-ScheduledTask rejects the XML; pass it to the cmdlet instead"
    )
    assert "RestartInterval" in source and "New-TimeSpan -Minutes" in source, (
        "the retry interval must still be settable for the task that uses it"
    )


# ---------------------------------------------------------- behavioural check

@pytest.mark.skipif(not POWERSHELL, reason="no powershell on this host")
def test_the_deployed_subsystem_matches_the_declared_contract():
    """-Check is the contract test: does the machine match the table?

    Skipped when this machine never deployed the subsystem. A machine that has it
    and reports drift fails, which is the whole point - a green suite that does
    not notice drift is the failure mode the installer was built to end.
    """
    if not WRAPPERS.is_dir() or not LAUNCHER.is_file():
        pytest.skip(f"tinghe subsystem not deployed here ({WRAPPERS} / {LAUNCHER})")

    proc = subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass",
         "-File", str(INSTALLER), "-Check"],
        capture_output=True, text=True, timeout=300, encoding="utf-8", errors="replace",
    )
    output = proc.stdout + proc.stderr
    drift = [ln for ln in output.splitlines() if "[drift]" in ln or "[not installed]" in ln]
    assert not drift, (
        "the deployed tasks do not match ops/install_tinghe_tasks.ps1:\n  "
        + "\n  ".join(drift)
    )
    assert proc.returncode == 0, f"-Check exited {proc.returncode}\n{output[:800]}"
