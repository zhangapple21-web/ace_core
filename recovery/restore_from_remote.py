#!/usr/bin/env python3
"""从远程真源创建一个全新的 ACE 恢复工作区。

安全边界：只 clone 明确列出的远程仓库；拒绝覆盖非空目录或 dirty checkout；
不读取旧工作区、不下载凭据、不启动 Provider/废弃端口。完成后调用核心
bootstrap，并可选运行视频能力域的离线测试与 dry-run。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portable_paths import layout, portable_environment, resolve  # noqa: E402


CORE_URL = "https://github.com/zhangapple21-web/ace_core.git"
CORE_REF = "core/daemon-lifecycle-resilience-20260912"
VIDEO_URL = "https://github.com/zhangapple21-web/ace-video-kingdom.git"
VIDEO_REF = "main"
OPTIONAL_REPOS = [
    ("mine-seed", "https://github.com/zhangapple21-web/mine-seed.git", "main"),
    ("ace-capability-registry", "https://github.com/zhangapple21-web/ace-capability-registry.git", "main"),
    ("ace-skill-vault", "https://github.com/zhangapple21-web/ace-skill-vault.git", "main"),
    ("ace-knowledge-forge", "https://github.com/zhangapple21-web/ace-knowledge-forge.git", "master"),
    ("ace-salvage", "https://github.com/zhangapple21-web/ace-salvage.git", "main"),
    ("ace-structure-steward", "https://github.com/zhangapple21-web/ace-structure-steward.git", "main"),
    ("ace-task-queue", "https://github.com/zhangapple21-web/ace-task-queue.git", "main"),
    ("ace-video-assets", "https://github.com/zhangapple21-web/ace-video-assets.git", "main"),
    ("r1-continuity-backup", "https://github.com/zhangapple21-web/r1-continuity-backup.git", "main"),
    ("r1-archaeology", "https://github.com/zhangapple21-web/r1-archaeology.git", "main"),
    ("R1_continuity_archive", "https://github.com/zhangapple21-web/R1_continuity_archive.git", "main"),
    ("R1", "https://github.com/zhangapple21-web/R1.git", "main"),
    ("claw-soul", "https://github.com/zhangapple21-web/claw-soul.git", "main"),
    ("aum-protocol", "https://github.com/zhangapple21-web/aum-protocol.git", "main"),
    ("r1-open-source-seed", "https://github.com/zhangapple21-web/r1-open-source-seed.git", "main"),
    ("coze-assets", "https://github.com/ACEE0011/coze-assets.git", "main"),
]


def run(cmd: list[str], cwd: Path | None = None) -> dict:
    proc = subprocess.run(cmd, cwd=cwd,
                          env=portable_environment(cwd) if cwd is not None else None,
                          text=True, capture_output=True)
    return {
        "command": " ".join(cmd),
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
    }


def fail(message: str) -> int:
    print(f"FAIL: {message}", file=sys.stderr)
    return 2


def parse_remote_head(output: str, ref: str) -> str:
    requested = ref if ref.startswith("refs/heads/") else f"refs/heads/{ref}"
    heads = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) == 2 and fields[1] == requested:
            if not re.fullmatch(r"[0-9a-fA-F]{40}|[0-9a-fA-F]{64}", fields[0]):
                raise RuntimeError(f"远程 ref 的 HEAD 格式无效: {requested}")
            heads.append(fields[0].lower())
    if len(heads) != 1:
        raise RuntimeError(f"远程 ref 必须有唯一 HEAD: {requested}")
    return heads[0]


def clone(url: str, ref: str, destination: Path, *, result: dict | None = None) -> dict:
    if result is None:
        result = {}
    result.update({
        "status": "FAIL",
        "requested_ref": ref,
        "remote_head": None,
        "checked_out_branch": None,
        "checked_out_head": None,
        "ref_match": False,
        "commands": [],
    })

    def checked_run(cmd: list[str], cwd: Path | None = None) -> dict:
        command = run(cmd, cwd)
        result["commands"].append(command)
        if command["status"] != "PASS":
            raise RuntimeError(f"恢复命令失败: {command['command']}")
        return command

    try:
        if destination.exists():
            if any(destination.iterdir()):
                raise RuntimeError(f"拒绝覆盖非空目录: {destination}")
            destination.rmdir()
        remote = checked_run(["git", "ls-remote", "--heads", url, ref])
        result["remote_head"] = parse_remote_head(remote["stdout"], ref)
        destination.parent.mkdir(parents=True, exist_ok=True)
        cloned = checked_run(["git", "clone", "--branch", ref, "--single-branch", url, str(destination)])
        result.update(cloned)
        result["status"] = "FAIL"
        result["checked_out_branch"] = checked_run(["git", "branch", "--show-current"], destination)["stdout"].strip()
        result["checked_out_head"] = checked_run(["git", "rev-parse", "HEAD"], destination)["stdout"].strip()
        result["head"] = result["checked_out_head"]
        result["ref_match"] = result["checked_out_head"] == result["remote_head"]
        if not result["ref_match"]:
            raise RuntimeError("checkout HEAD 与 clone 前远程 HEAD 不一致")
        result["remote"] = checked_run(["git", "config", "--get", "remote.origin.url"], destination)["stdout"].strip()
        result["status"] = "PASS"
    except (OSError, RuntimeError) as exc:
        result["status"] = "FAIL"
        result["error"] = str(exc)
        raise
    return result


def bootstrap_status(result: dict, report: dict, *, skip_tests: bool = False) -> str:
    if result.get("returncode") not in {0, 3}:
        return "FAIL"
    checks = report.get("checks", [])
    if not isinstance(checks, list) or any(not isinstance(item, dict) for item in checks):
        return "PARTIAL"
    if any(item.get("status") == "FAIL" for item in checks if item.get("name") != "health_check"):
        return "FAIL"
    if report.get("status") == "FAIL":
        return "FAIL"
    health = [item for item in checks if item.get("name") == "health_check"]
    tests = [item for item in checks if item.get("name") == "pytest"]
    if (result["returncode"] == 3 or report.get("status") == "PARTIAL" or skip_tests
            or not health or any(item.get("status") != "PASS" for item in health)
            or not tests or any(item.get("status") != "PASS" for item in tests)):
        return "PARTIAL"
    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser(description="ACE remote-only restore orchestrator")
    parser.add_argument("--workspace-root", type=Path, required=True, help="空的恢复目录")
    parser.add_argument("--with-video", action="store_true", help="同时恢复 ace-video-kingdom 并运行离线视频验证")
    parser.add_argument("--with-optional", action="store_true", help="同时 clone 能力、Skill、知识和公开资产仓库")
    parser.add_argument("--skip-tests", action="store_true", help="只做 clone/bootstrap，不运行测试")
    args = parser.parse_args()
    root = args.workspace_root.expanduser().resolve()
    if root.exists() and any(root.iterdir()):
        return fail(f"恢复目标必须为空，避免覆盖现有工作: {root}")
    if not shutil.which("git"):
        return fail("找不到 git")
    root.mkdir(parents=True, exist_ok=True)
    python = sys.executable
    receipt: dict = {
        "schema": "ace.remote_restore_receipt.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workspace_root": str(root),
        "remote_only": True,
        "forbidden_revival_dependencies": ["3000", "3002", "legacy scheduler", "legacy heartbeat"],
        "steps": [],
        "portable_path_policy": "所有恢复目标由 portable_paths.ROOTS 解析；workspace-root 可位于任意盘符。",
        "portable_roots": {key: str(value) for key, value in layout(root).items()},
    }

    def clone_step(name: str, url: str, ref: str, destination: Path) -> None:
        step = {"name": name}
        receipt["steps"].append(step)
        clone(url, ref, destination, result=step)

    try:
        core = resolve(root, "restore_core")
        clone_step("clone_core", CORE_URL, CORE_REF, core)
        bootstrap = [python, "recovery/bootstrap.py", "--workspace-root", str(core)]
        if args.skip_tests:
            bootstrap.append("--skip-tests")
        step = {"name": "core_bootstrap", **run(bootstrap, core)}
        receipt["steps"].append(step)
        report_path = resolve(core, "recovery", "bootstrap_report.json")
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            if not isinstance(report, dict):
                raise ValueError("bootstrap_report 必须是对象")
        except (OSError, ValueError) as exc:
            report = {}
            step["report_error"] = str(exc)
        step["bootstrap_report"] = report
        step["status"] = bootstrap_status(step, report, skip_tests=args.skip_tests)
        if step["status"] == "FAIL":
            raise RuntimeError("核心 bootstrap 失败")
        if args.with_video:
            video = resolve(root, "restore_video")
            clone_step("clone_video", VIDEO_URL, VIDEO_REF, video)
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
        if args.with_optional:
            for name, url, ref in OPTIONAL_REPOS:
                clone_step(f"clone_{name}", url, ref, resolve(root, "restore_optional", name))
        receipt["status"] = "PARTIAL" if any(item["status"] == "PARTIAL" for item in receipt["steps"]) else "PASS"
    except (OSError, RuntimeError) as exc:
        receipt["status"] = "FAIL"
        receipt["error"] = str(exc)
    if receipt["status"] != "FAIL":
        receipt_path = root / "ACE_REMOTE_RESTORE_RECEIPT.json"
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        # 保留本次失败产物在旁目录，不删除 checkout，也不阻塞同一目标重试。
        failed_root = Path(tempfile.mkdtemp(prefix=f"{root.name}_failed_", dir=root.parent))
        receipt_path = failed_root / "ACE_REMOTE_RESTORE_RECEIPT.json"
        root.rename(failed_root / "workspace")
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(f"receipt: {receipt_path}")
    return {"PASS": 0, "PARTIAL": 3, "FAIL": 1}[receipt["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
