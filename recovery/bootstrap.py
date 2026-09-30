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
sys.path.insert(0, str(ROOT))
from portable_paths import layout, portable_environment  # noqa: E402


def run(cmd: list[str], cwd: Path, *, allow_warning: bool = False) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, env=portable_environment(cwd), text=True, capture_output=True)
    result = {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "status": "PASS" if proc.returncode == 0 else ("WARN" if allow_warning else "FAIL"),
    }
    return result


def aggregate_status(checks: list[dict]) -> str:
    if any(item.get("status") == "FAIL" for item in checks if item.get("name") != "health_check"):
        return "FAIL"
    health = [item for item in checks if item.get("name") == "health_check"]
    tests = [item for item in checks if item.get("name") == "pytest"]
    if not health or any(item.get("status") != "PASS" for item in health):
        return "PARTIAL"
    if not tests or any(item.get("status") != "PASS" for item in tests):
        return "PARTIAL"
    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description="Bootstrap ACE from a remote checkout")
    parser.add_argument("--workspace-root", type=Path, default=ROOT, help="checkout to prepare")
    parser.add_argument("--skip-tests", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace_root.expanduser().resolve()
    paths = layout(workspace)
    if not (workspace / ".git").exists() or not paths["config_example"].is_file():
        print(f"FAIL: 不是有效的 ace_core checkout: {workspace}", file=sys.stderr)
        return 1

    checks: list[dict] = []
    checks.append({"name": "git", "status": "PASS" if shutil.which("git") else "FAIL"})
    checks.append({"name": "python", "status": "PASS" if sys.version_info >= (3, 11) else "WARN", "version": sys.version})
    if checks[0]["status"] == "FAIL":
        print("FAIL: 找不到 git")
        return 1

    local_config = paths["config_local"]
    if not local_config.exists():
        template = json.loads(paths["config_example"].read_text(encoding="utf-8"))
        # Keep paths explicit but portable.  Empty values disable optional
        # integrations until a human supplies a private path.
        template["runtime"]["miner_pool_assets_path"] = os.environ.get("ACE_MINER_ASSETS_PATH", "")
        template["runtime"]["video_kingdom_root"] = os.environ.get("ACE_VIDEO_KINGDOM_ROOT", "")
        local_config.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        checks.append({"name": "local_config", "status": "PASS", "detail": str(local_config)})
    else:
        checks.append({"name": "local_config", "status": "EXISTS", "detail": str(local_config)})

    rebuildable_dirs = [
        paths["task_pool"] / name for name in ("pending", "running", "completed", "failed", "archived")
    ] + [paths[key] for key in ("runtime", "events", "tasks", "memory_cache", "knowledge_axiom", "knowledge_constraint", "knowledge_pattern")]
    for directory in rebuildable_dirs:
        directory.mkdir(parents=True, exist_ok=True)
    checks.append({"name": "rebuildable_directories", "status": "PASS", "count": len(rebuildable_dirs)})

    path_audit = paths["recovery"] / "path_audit.py"
    if path_audit.is_file():
        checks.append({"name": "portable_path_audit", **run([sys.executable, str(path_audit), "--workspace-root", str(workspace)], workspace)})
    else:
        checks.append({"name": "portable_path_audit", "status": "FAIL", "detail": "path_audit.py 不存在"})

    checks.append({"name": "compileall", **run([sys.executable, "-m", "compileall", "-q", "."], workspace)})

    if not args.skip_tests:
        candidates = [
            "ops/test_task_ledger.py",
            "ops/test_memory_gateway.py",
            "ops/test_memory_index_recovery.py",
            "ops/test_cognitive_think_gate.py",
            "ops/test_task.py",
            "ops/test_workspace_write_lock.py",
            "ops/test_worker_capsule.py",
            "ops/test_worker_capsule_cli.py",
            "ops/test_runtime_continuity_repairs.py",
            "ops/test_runtime_continue_gate.py",
            "ops/test_finance_work_windows.py",
            "ops/test_stock_data_reliability.py",
            "ops/test_capability_routing.py",
            "ops/test_video_kingdom_consumer.py",
            "ops/test_video_kingdom_dispatch.py",
        ]
        existing = [path for path in candidates if (workspace / path).is_file()]
        pytest_available = subprocess.run(
            [sys.executable, "-m", "pytest", "--version"],
            cwd=workspace,
            env=portable_environment(workspace),
            text=True,
            capture_output=True,
        ).returncode == 0
        if existing and pytest_available:
            checks.append({"name": "pytest", **run([sys.executable, "-m", "pytest", "-q", *existing], workspace)})
        else:
            checks.append({"name": "pytest", "status": "SKIP", "detail": "没有 pytest 或候选测试文件"})

    else:
        checks.append({"name": "pytest", "status": "SKIP", "detail": "--skip-tests"})

    health = paths["health_check"]
    if health.is_file():
        checks.append({"name": "health_check", **run([sys.executable, str(health), "--json"], workspace, allow_warning=True)})
    else:
        checks.append({"name": "health_check", "status": "SKIP", "detail": "health_check.py 不存在"})
    smoke = run([sys.executable, str(paths["ace_cli"]), "status"], workspace)
    checks.append({"name": "ace_status_smoke", **smoke})

    report = {
        "schema": "ace.bootstrap_report.v1",
        "status": aggregate_status(checks),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace),
        "remote_commit": run(["git", "rev-parse", "HEAD"], workspace)["stdout"].strip(),
        "checks": checks,
        "human_required": str(paths["recovery"] / "MISSING_HUMAN_REQUIRED.md"),
        "portable_paths": {key: str(value) for key, value in paths.items()},
        "notes": [
            "未读取、生成或上传任何密钥。",
            "health 实际执行；任何非 PASS health 或跳过测试均不等价于完整验收。",
            "3000/3002 及 legacy scheduler/heartbeat 不由 bootstrap 启动。",
        ],
    }
    report_path = paths["recovery"] / "bootstrap_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return {"PASS": 0, "PARTIAL": 3, "FAIL": 1}[report["status"]]


if __name__ == "__main__":
    raise SystemExit(main())

