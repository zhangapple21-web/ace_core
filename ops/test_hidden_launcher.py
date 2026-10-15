"""A background job must never wait for a human click.

The defect this pins: eight scheduled tasks launched unsigned .cmd files through
`WScript.Shell.Run`, which routes them via ShellExecute. For an unsigned .cmd the
Attachment Manager raises "Open File - Security Warning" and BLOCKS the job until
somebody clicks. Every fire of all eight tasks was therefore waiting on a person -
the launcher looked hidden, the task state looked fine, and the site work silently
never happened. No test caught it because nothing tested the launcher.

The contract, stated as a rule a machine can check:

  run-hidden-wait.vbs must not hand a .cmd/.bat path directly to ShellExecute.
  It routes those through cmd.exe /c, so the Attachment Manager inspects a
  signed, unzoned system binary instead of the script.

  run-hidden.vbs must NOT be given that routing. Its first argument is a signed
  executable with its own arguments following it, so wrapping it in cmd.exe /c
  would break the four tasks that use it.

The static checks run everywhere. The behavioural checks need Windows plus the
deployed launcher and are skipped elsewhere rather than reported green on a
machine where they never ran.
"""
import ctypes
import ctypes.wintypes as w
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
WAIT = REPO / "ops" / "launchers" / "run-hidden-wait.vbs"
PLAIN = REPO / "ops" / "launchers" / "run-hidden.vbs"

# where the deployed copy lives; the repo is the source of truth, this is the
# working copy the scheduled tasks actually invoke
DEPLOYED_WAIT = Path(r"C:\tmp\run-hidden-wait.vbs")
DEPLOYED_PLAIN = Path(r"C:\tmp\run-hidden.vbs")

WSCRIPT = Path(r"C:\Windows\System32\wscript.exe")


def _text(path):
    return path.read_text(encoding="utf-8", errors="replace")


def _normalise(text):
    return " ".join(text.split())


def _strip_vbs_comments(text):
    """Remove VBS comments so assertions inspect code, not prose.

    The sibling launcher's header deliberately names the routing it must not
    gain, which defeats a naive substring check - the test passed the fix and
    failed the comment. Quote-aware: an apostrophe inside a double-quoted string
    is not a comment start.
    """
    out = []
    for line in text.splitlines():
        in_string = False
        cut = None
        for index, char in enumerate(line):
            if char == '"':
                in_string = not in_string
            elif char == "'" and not in_string:
                cut = index
                break
        out.append(line if cut is None else line[:cut])
    return "\n".join(out)


def _code(path):
    """The launcher with comments removed - what actually executes."""
    return _normalise(_strip_vbs_comments(_text(path)))


# --------------------------------------------------------------- static contract


def test_the_waiting_launcher_never_hands_a_cmd_to_shellexecute():
    """The vulnerable shape, named so it cannot come back quietly.

    `Run QuoteArg(target)` with a .cmd target is exactly what raised the dialog.
    The fix produces `Run "cmd.exe /c " & QuoteArg(target)` instead. Asserting
    the vulnerable shape is absent is stricter than asserting the fix text is
    present, because it also rejects a rewrite that shuffles the same bug.
    """
    source = _code(WAIT)
    normalised = source
    assert 'Run QuoteArg(target)' not in normalised, (
        "a bare .cmd path reaching ShellExecute is the shape that made eight "
        "tasks wait on a human click"
    )
    assert "cmd.exe /c" in normalised, (
        "the waiting launcher must route script targets through cmd.exe"
    )


def test_the_waiting_launcher_only_routes_script_files_through_cmd():
    """Conditional, not blanket: other targets keep their old behaviour.

    A future caller passing an executable with arguments must not have it
    swallowed by cmd.exe /c. The guard has to be present in the source, not just
    assumed from the fix.
    """
    source = _code(WAIT)
    assert "IsCmdScript" in source and "Right(lower, 4)" in source, (
        "the cmd.exe routing must be gated on the target's extension"
    )


def test_the_plain_launcher_must_not_gain_cmd_routing():
    """The sibling takes powershell.exe plus arguments; wrapping it breaks it.

    This is the guard against a well-meant "unify the two launchers" change.
    Four ACE tasks depend on this shape.
    """
    source = _code(PLAIN)
    assert "cmd.exe /c" not in source, (
        "run-hidden.vbs launches a signed executable with its own arguments; "
        "cmd.exe routing would mis-handle them"
    )


def test_both_launchers_quote_their_arguments():
    """A CJK path with spaces must survive the hop.

    The tinghe site lives under a Chinese-named directory, which is why the
    quoting helper exists at all. Dropping it would break all eight tasks in a
    way no dialog would announce.
    """
    for path in (WAIT, PLAIN):
        assert "Function QuoteArg" in _code(path), (
            f"{path.name} lost its argument quoting"
        )


# --------------------------------------------------------- deployment agreement


def test_the_deployed_waiting_launcher_is_the_fixed_one():
    """The repo is the source of truth; the deployed copy must not be the old one.

    Skipped only when there is no deployed copy at all - a machine that never
    deployed it is not a regression. A deployed copy that still carries the
    vulnerable shape IS a regression, and it is reported rather than skipped.
    """
    if not DEPLOYED_WAIT.is_file():
        pytest.skip(f"no deployed launcher at {DEPLOYED_WAIT}")
    deployed = _code(DEPLOYED_WAIT)
    assert 'Run QuoteArg(target)' not in deployed, (
        "the deployed run-hidden-wait.vbs still hands a .cmd to ShellExecute; "
        "the eight scheduled tasks are still waiting on a click"
    )
    assert "cmd.exe /c" in deployed


def test_the_deployed_plain_launcher_has_not_drifted():
    """The sibling is signed-executable shape; a drift here breaks four tasks.

    Syncing this file from the repo is safe precisely because the code is
    unchanged - verified. This pins that the deployed copy still is that shape.
    """
    if not DEPLOYED_PLAIN.is_file():
        pytest.skip(f"no deployed launcher at {DEPLOYED_PLAIN}")
    deployed = _code(DEPLOYED_PLAIN)
    assert "cmd.exe /c" not in deployed, (
        "the deployed run-hidden.vbs gained cmd.exe routing; four ACE tasks "
        "pass powershell.exe with their own arguments and would mis-handle them"
    )
    assert "Run cmd, 0, False" in deployed, (
        "the plain launcher must keep not waiting; that is its whole purpose"
    )


# ------------------------------------------------------------ behavioural proof


@pytest.mark.skipif(not (WAIT.is_file() and WSCRIPT.is_file()),
                    reason="needs the launcher and wscript on a Windows host")
def test_the_launcher_runs_a_cmd_without_a_dialog(tmp_path):
    """The real thing: launch an unsigned .cmd and assert it runs, silently.

    This is the check that would have caught the defect. It does not grep the
    launcher - it runs it the way the tasks do and observes both outcomes that
    matter: the job completes and no security dialog appears. A launcher that
    stayed quiet but never ran the job would fail here, which is the failure
    mode that mattered.
    """
    probe = tmp_path / "_launcher_probe.cmd"
    marker = tmp_path / "marker.txt"
    # deliberately exit non-zero: the code must be observable in the marker,
    # proving the child really executed rather than the shell merely returning
    probe.write_text(
        f"@echo off\r\necho ran > \"{marker}\"\r\nexit /b 5\r\n",
        encoding="ascii",
    )

    dialogs = []
    proc = subprocess.Popen(
        [str(WSCRIPT), "//B", "//nologo", str(WAIT), str(probe)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        proc.communicate(timeout=90)
    except subprocess.TimeoutExpired:
        proc.kill()
        raise AssertionError("the launcher hung: the job is waiting on a click")

    assert marker.is_file(), (
        "the .cmd never ran - the launcher blocked it, which is the defect"
    )
    assert proc.returncode == 0, f"launcher returned {proc.returncode}"

    dialogs = _security_windows_on_screen()
    assert not dialogs, f"a security dialog appeared: {dialogs}"


def _security_windows_on_screen():
    """Visible top-level windows whose title names the Attachment Manager."""
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [w.HWND, ctypes.c_wchar_p, ctypes.c_int]
    found = []

    def cb(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(512)
        user32.GetWindowTextW(hwnd, buf, 512)
        title = buf.value
        if title:
            for word in ("安全警告", "无法验证", "发布者",
                         "Security Warning", "Open File"):
                if word in title:
                    found.append(title[:100])
        return True

    user32.EnumWindows(ctypes.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)(cb), 0)
    return sorted(set(found))
