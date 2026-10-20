"""Keep ACE daemon work off the interactive desktop on Windows.

pythonw itself has no console, but console-subsystem children such as git.exe
still allocate a new visible window unless CREATE_NO_WINDOW is set.  The
long-running miner must never flash a terminal or steal focus.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
STARTF_USESHOWWINDOW = 0x00000001
SW_HIDE = 0

_INSTALLED = False
_ORIGINAL_POPEN = subprocess.Popen


def is_ace_daemon_argv(argv=None):
    """True for ace.py daemon ... including --serve."""
    argv = list(sys.argv if argv is None else argv)
    if len(argv) < 2:
        return False
    script = Path(argv[0]).name.lower()
    if script not in {"ace.py", "ace"}:
        return False
    return argv[1] == "daemon"


def silent_popen_kwargs(kwargs):
    """Return Popen kwargs that do not create a console window."""
    if sys.platform != "win32":
        return kwargs
    out = dict(kwargs)
    out["creationflags"] = int(out.get("creationflags") or 0) | CREATE_NO_WINDOW
    startupinfo = out.get("startupinfo")
    if startupinfo is None:
        startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = SW_HIDE
    out["startupinfo"] = startupinfo
    return out


def hide_current_console():
    """Hide and detach this process console if one exists."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        hwnd = kernel32.GetConsoleWindow()
        if hwnd:
            user32.ShowWindow(hwnd, SW_HIDE)
            kernel32.FreeConsole()
        return True
    except Exception:
        return False


def install_silent_child_processes():
    """Patch subprocess.Popen so later run/Popen calls stay windowless."""
    global _INSTALLED
    if sys.platform != "win32":
        return False
    if _INSTALLED:
        return True

    def _silent_popen(*args, **kwargs):
        return _ORIGINAL_POPEN(*args, **silent_popen_kwargs(kwargs))

    subprocess.Popen = _silent_popen
    _INSTALLED = True
    return True


def install_daemon_silence():
    """Hide this console and force child processes not to steal the desktop."""
    hide_current_console()
    install_silent_child_processes()