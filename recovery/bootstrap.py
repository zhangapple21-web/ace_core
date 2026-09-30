#!/usr/bin/env python3
"""Portable, non-secret ACE disaster-recovery bootstrap.

This script is deliberately conservative: it only creates rebuildable
directories, generates a local configuration template, compiles source, and
runs bounded checks.  It never downloads credentials, starts providers, or
touches the user's existing source outside the selected workspace.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path, *, allow_warning: bool = False) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    result = {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-8000:],
        "stderr": proc.stderr[-8000:],
        "status": "PASS" if proc.returncode == 0 else ("WARN" if allow_warning else "FAIL"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap ACE from a remote checkout")
    parser.add_argument("--workspace-root", type=Path, default=ROOT, help="checkout to prepare")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace_root.expanduser().resolve()
    if not (workspace / ".git").exists() or not (workspace / "ace_config.example.json").is_file():
        print(f"FAIL: 不是有效的 ace_core checkout: {workspace}", file=sys.stderr)
        return 2

    checks: list[dict] = []
    checks.append({"name": "git", "status": "PASS" if shutil.which("git") else "FAIL"})
    checks.append({"name": "python", "status": "PASS" if sys.version_info >= (3, 11) else "WARN", "version": sys.version})
    if checks[0]["status"] == "FAIL":
        print("FAIL: 找不到 git")
        return 2

    local_config = workspace / "ace_config.local.json"
    if not local_config.exists():
        template = json.loads((workspace / "ace_config.example.json").read_text(encoding="utf-8"))
        # Keep paths explicit but portable.  Empty values disable optional
        # integrations until a human supplies a private path.
        template["runtime"]["miner_pool_assets_path"] = os.environ.get("ACE_MINER_ASSETS_PATH", "")
        template["runtime"]["video_kingdom_root"] = os.environ.get("ACE_VIDEO_KINGDOM_ROOT", "")
        local_config.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        checks.append({"name": "local_config", "status": "PASS", "detail": str(local_config)})
    else:
        checks.append({"name": "local_config", "status": "EXISTS", "detail": str(local_config)})

    rebuildable_dirs = [
        "task_pool/pending", "task_pool/running", "task_pool/completed", "task_pool/failed", "task_pool/archived",
        "runtime", "06_RUNTIME/ace/data/events", "06_RUNTIME/ace/data/tasks", "06_RUNTIME/ace/data/memory",
        "09_KNOWLEDGE/axiom", "09_KNOWLEDGE/constraint", "09_KNOWLEDGE/pattern",
    ]
    for relative in rebuildable_dirs:
        (workspace / relative).mkdir(parents=True, exist_ok=True)
    checks.append({"name": "rebuildable_directories", "status": "PASS", "count": len(rebuildable_dirs)})

    checks.append({"name": "compileall", **run([sys.executable, "-m", "compileall", "-q", "."], workspace)})

    if not args.skip_tests:
        candidates = [
            "ops/test_task_ledger.py", "ops/test_memory_gateway.py", "ops/test_memory_index_recovery.py",
            "ops/test_cognitive_think_gate.py", "ops/test_task.py", "ops/test_workspace_write_lock.py",
        ]
        existing = [path for path in candidates if (workspace / path).is_file()]
        pytest_available = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            cwd=workspace,
            text=True,
            capture_output=True,
        ).returncode == 0
        if existing and pytest_available:
            checks.append({"name": "pytest", **run([sys.executable, "-m", "pytest", "-q", *existing], workspace)})
        else:
            checks.append({"name": "pytest", "status": "SKIP", "detail": "没有 pytest 或候选测试文件"})

    health = workspace / "ops" / "health_check.py"
    if health.is_file():
        checks.append({"name": "health_check", **run([sys.executable, str(health), "--json"], workspace, allow_warning=True)})
    smoke = run([sys.executable, "ace.py", "status"], workspace, allow_warning=True)
    checks.append({"name": "ace_status_smoke", **smoke})

    report = {
        "schema": "ace.bootstrap_report.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "remote_commit": run(["git", "rev-parse", "HEAD"], workspace)["stdout"].strip(),
        "checks": checks,
        "human_required": str(workspace / "recovery" / "MISSING_HUMAN_REQUIRED.md"),
        "notes": [
            "未读取、生成或上传任何密钥。",
            "3000/3002 及 legacy scheduler/heartbeat 不由 bootstrap 启动。",
            "WARN 结果必须结合 recovery/RESTORE_TEST_RESULT.md 由人工复核。",
        ],
    }
    report_path = workspace / "recovery" / "bootstrap_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(item.get("status") not in {"FAIL"} for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

