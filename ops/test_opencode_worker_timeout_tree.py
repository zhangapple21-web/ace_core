"""Regression: a timed-out CLI call leaves no process behind.

subprocess.run(timeout=) kills only the direct child, so a CLI's own
helpers used to survive as orphans. A probe CLI that spawns a grandchild
and then sleeps must leave nothing running once run() returns.

The probe is a .bat wrapper, mirroring the real opencode.exe on Windows:
what gets timed out is a launcher, not the process doing the work.
"""

import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.opencode_worker import OpenCodeWorker


SPAWNER = """
import pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(300)"])
pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding="utf-8")
time.sleep(300)
"""


def _alive(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True, text=True, errors="replace", timeout=60,
    )
    return str(pid) in result.stdout


def test_timeout_leaves_no_orphans():
    work = Path(tempfile.mkdtemp(prefix="worker_tree_probe_"))
    pid_file = work / "grandchild.pid"
    spawner = work / "spawner.py"
    spawner.write_text(SPAWNER, encoding="utf-8")
    launcher = work / "probe_cli.bat"
    launcher.write_text(
        f'@echo off\r\n"{sys.executable}" "{spawner}" "{pid_file}"\r\n',
        encoding="utf-8",
    )

    worker = OpenCodeWorker(executable=str(launcher), timeout_seconds=5)

    # Watch from outside: the point is that the grandchild was genuinely alive
    # while run() was still blocked on it, then gone afterwards.
    observed_alive = []

    def watch():
        for _ in range(60):
            if pid_file.is_file():
                pid = int(pid_file.read_text(encoding="utf-8").strip())
                if _alive(pid):
                    observed_alive.append(pid)
                    return
            time.sleep(0.2)

    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    worker.run(
        task="probe",
        workspace=str(work),
        model_order=["opencode/mimo-v2.6-flash-free"],
    )
    watcher.join(timeout=20)

    assert observed_alive, "probe grandchild was never observed running; the test proves nothing"
    grandchild = observed_alive[0]
    try:
        assert not _alive(grandchild), f"grandchild {grandchild} outlived the timeout"
    finally:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(grandchild)],
            capture_output=True, check=False, timeout=60,
        )
