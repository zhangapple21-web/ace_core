#!/usr/bin/env python3
"""从远程真源创建一个全新的 ACE 恢复工作区。

安全边界：只 clone 明确列出的远程仓库；拒绝覆盖非空目录或 dirty checkout；
不读取旧工作区、不下载凭据、不启动 Provider/废弃端口。完成后调用核心
bootstrap，并可选运行视频能力域的离线测试与 dry-run。
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


CORE_URL = "https://github.com/zhangapple21-web/ace_core.git"
CORE_REF = "core/daemon-lifecycle-resilience-20260912"
VIDEO_URL = "https://github.com/zhangapple21-web/ace-video-kingdom.git"
VIDEO_REF = "main"


def run(cmd: list[str], cwd: Path | None = None) -> dict:
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout[-10000:],
        "stderr": proc.stderr[-10000:],
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 2


def clone(url: str, ref: str, destination: Path) -> dict:
    if destination.exists():
        if any(destination.iterdir()):
            raise RuntimeError(f"拒绝覆盖非空目录: {destination}")
        destination.rmdir()
    destination.parent.mkdir(parents=True, exist_ok=True)
    result = run(["git", "clone", "--branch", ref, "--single-branch", url, str(destination)])
    if result["status"] == "PASS":
        result["head"] = run(["git", "rev-parse", "HEAD"], destination)["stdout"].strip()
        result["remote"] = run(["git", "config", "--get", "remote.origin.url"], destination)["stdout"].strip()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="ACE remote-only restore orchestrator")
    parser.add_argument("--workspace-root", type=Path, required=True, help="空的恢复目录")
    parser.add_argument("--with-video", action="store_true", help="同时恢复 ace-video-kingdom 并运行离线视频验证")
    parser.add_argument("--skip-tests", action="store_true", help="只做 clone/bootstrap，不运行测试")
    args = parser.parse_args()
    root = args.workspace_root.expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        return fail(f"恢复目标必须为空，避免覆盖现有工作: {root}")
    root.mkdir(parents=True, exist_ok=True)
    if not shutil.which("git"):
        return fail("找不到 git")
    python = sys.executable
    receipt: dict = {
        "schema": "ace.remote_restore_receipt.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(root),
        "remote_only": True,
        "forbidden_revival_dependencies": ["3000", "3002", "legacy scheduler", "legacy heartbeat"],
        "steps": [],
    }
    try:
        core = root / "ace_core"
        receipt["steps"].append({"name": "clone_core", **clone(CORE_URL, CORE_REF, core)})
        if receipt["steps"][-1]["status"] != "PASS":
            raise RuntimeError("核心仓库 clone 失败")
        bootstrap = [python, "recovery/bootstrap.py", "--workspace-root", str(core)]
        if args.skip_tests:
            bootstrap.append("--skip-tests")
        receipt["steps"].append({"name": "core_bootstrap", **run(bootstrap, core)})
        if receipt["steps"][-1]["status"] != "PASS":
            raise RuntimeError("核心 bootstrap 失败")
        if args.with_video:
            video = root / "ace-video-kingdom"
            receipt["steps"].append({"name": "clone_video", **clone(VIDEO_URL, VIDEO_REF, video)})
            if receipt["steps"][-1]["status"] != "PASS":
                raise RuntimeError("视频仓库 clone 失败")
            if not args.skip_tests:
                tests = [python, "-m", "pytest", "-q", "tests/test_production_control.py", "tests/test_video_kingdom_entry.py", "tests/test_voice_execution_steps.py"]
                receipt["steps"].append({"name": "video_offline_tests", **run(tests, video)})
                if receipt["steps"][-1]["status"] != "PASS":
                    raise RuntimeError("视频离线测试失败")
                out = video / "temp" / "recovery_entry_receipt.json"
                out.parent.mkdir(parents=True, exist_ok=True)
                cmd = [python, "tools/video_kingdom_entry.py", "--text", "灾备 smoke test：只生成计划，不提交 Provider", "--out", str(out)]
                receipt["steps"].append({"name": "video_dry_run", **run(cmd, video)})
                if receipt["steps"][-1]["status"] != "PASS":
                    raise RuntimeError("视频 dry-run 失败")
        receipt["status"] = "PASS"
    except (OSError, RuntimeError) as exc:
        receipt["status"] = "FAIL"
        receipt["error"] = str(exc)
    receipt_path = root / "ACE_REMOTE_RESTORE_RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
