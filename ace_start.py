#!/usr/bin/env python3
"""Public ACE start shim; lifecycle authority remains AceDaemon/TaskPool."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) < 3 or args[0] != "task":
        print("用法: python ace_start.py task <任务ID> <owner> [lease_seconds]")
        return 2
    try:
        lease_seconds = int(args[3]) if len(args) > 3 else 300
    except ValueError:
        print(json.dumps({"status": "REJECTED", "reason": "invalid_lease_seconds"}, ensure_ascii=False))
        return 2
    from core.ace_start import ace_start
    from core.task import TaskPool

    result = ace_start(TaskPool(str(Path(__file__).resolve().parent / "task_pool")), args[1], args[2], lease_seconds)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "STARTED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
