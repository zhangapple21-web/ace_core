#!/usr/bin/env python3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import silent_windows


def test_is_ace_daemon_argv_serve():
    assert silent_windows.is_ace_daemon_argv([r'C:\\tmp\\ace_core\\ace.py', 'daemon', '--serve'])
    assert silent_windows.is_ace_daemon_argv(['ace.py', 'daemon'])
    assert not silent_windows.is_ace_daemon_argv(['ace.py', 'status'])
    assert not silent_windows.is_ace_daemon_argv(['pytest'])


def test_silent_popen_kwargs_sets_no_window():
    kwargs = silent_windows.silent_popen_kwargs({})
    assert kwargs['creationflags'] & silent_windows.CREATE_NO_WINDOW
    assert kwargs['startupinfo'].dwFlags & silent_windows.STARTF_USESHOWWINDOW
    assert kwargs['startupinfo'].wShowWindow == silent_windows.SW_HIDE


def test_silent_popen_kwargs_preserves_existing_flags():
    kwargs = silent_windows.silent_popen_kwargs({'creationflags': 0x10, 'cwd': 'C:\\tmp'})
    assert kwargs['cwd'] == 'C:\\tmp'
    assert kwargs['creationflags'] & 0x10
    assert kwargs['creationflags'] & silent_windows.CREATE_NO_WINDOW


def test_install_silent_child_processes_is_idempotent():
    original = silent_windows._ORIGINAL_POPEN
    previous = subprocess.Popen
    installed_before = silent_windows._INSTALLED
    try:
        silent_windows._INSTALLED = False
        assert silent_windows.install_silent_child_processes() is True
        first = subprocess.Popen
        assert first is not original
        assert silent_windows.install_silent_child_processes() is True
        assert subprocess.Popen is first
    finally:
        subprocess.Popen = previous
        silent_windows._INSTALLED = installed_before