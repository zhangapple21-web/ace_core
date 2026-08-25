#!/usr/bin/env python3
"""ACE Windows scheduled-task installer."""

import argparse
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
TASK = {
    "name": "ACE_Daemon_Boot",
    "description": "ACE boot daemon main loop",
    "args": "daemon --serve",
}
INSTALLER = Path(__file__).with_suffix(".ps1")


def run_installer(option: str = "") -> int:
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(INSTALLER),
    ]
    if option:
        command.append(option)
    return subprocess.run(command, cwd=BASE_DIR).returncode


def main():
    parser = argparse.ArgumentParser(description="ACE scheduled-task installer")
    parser.add_argument("--remove", action="store_true", help="remove daemon task")
    parser.add_argument("--check", action="store_true", help="check daemon task")
    args = parser.parse_args()
    option = "-Check" if args.check else "-Remove" if args.remove else ""
    raise SystemExit(run_installer(option))


if __name__ == "__main__":
    main()
