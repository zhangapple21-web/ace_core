# ACE 运维脚本 - 巡检执行器 (ID-08)
#
# 每30/60分钟自动执行：
#   1. 健康检查
#   2. 异常告警
#   3. 日志轮转
#   4. 状态快照
#
# 用法：
#   python ops/run_checkup.py
#   python ops/run_checkup.py --full     # 完整巡检（含日志轮转）
#   python ops/run_checkup.py --quiet    # 静默，仅写日志
#   python ops/run_checkup.py --alert    # 异常时发Windows通知

import json
import sys
import os
import subprocess
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
OPS_DIR = BASE_DIR / "ops"
LOGS_DIR = OPS_DIR / "logs"


def run_script(script_name: str, args: list = None) -> dict:
    """运行运维脚本，捕获输出和返回码"""
    script_path = OPS_DIR / script_name
    if not script_path.is_file():
        return {"success": False, "error": f"脚本不存在: {script_path}"}

    cmd = [sys.executable, str(script_path)] + (args or [])
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(BASE_DIR),
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "超时（120秒）"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def write_snapshot(snapshot: dict):
    """写入状态快照到日志"""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_file = LOGS_DIR / "checkup_history.jsonl"
    with open(snapshot_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")


def send_alert(level: str, module: str, message: str, notify: bool = False):
    """发送告警"""
    args = ["--level", level, "--module", module, "--message", message]
    if notify:
        args.append("--notify")
    run_script("alert.py", args)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ACE 巡检执行器")
    parser.add_argument("--full", action="store_true", help="完整巡检（含日志轮转）")
    parser.add_argument("--quiet", action="store_true", help="静默模式")
    parser.add_argument("--alert", action="store_true", help="异常时发Windows通知")
    args = parser.parse_args()

    timestamp = datetime.now().isoformat()
    snapshot = {
        "timestamp": timestamp,
        "checks": {},
        "overall": "ok",
    }

    if not args.quiet:
        print("=" * 60)
        print(f"ACE 巡检  —  {timestamp}")
        print("=" * 60)
        print()

    # 1. 健康检查
    if not args.quiet:
        print("【1/4】健康检查...")
    hc_result = run_script("health_check.py", ["--json"])
    if hc_result["success"]:
        try:
            hc_data = json.loads(hc_result["stdout"])
            snapshot["checks"]["health"] = {
                "overall": hc_data["overall"],
                "passed": hc_data["passed"],
                "warnings": hc_data["warnings"],
                "errors": hc_data["errors"],
            }
            if hc_data["overall"] == "error":
                snapshot["overall"] = "error"
                send_alert("error", "checkup", f"健康检查失败: {hc_data['errors']}个错误", args.alert)
            elif hc_data["overall"] == "warning":
                if snapshot["overall"] == "ok":
                    snapshot["overall"] = "warning"
                send_alert("warn", "checkup", f"健康检查警告: {hc_data['warnings']}个警告", args.alert)
            if not args.quiet:
                print(f"  结果: {hc_data['overall']} (通过{hc_data['passed']}, 警告{hc_data['warnings']}, 错误{hc_data['errors']})")
        except Exception as e:
            snapshot["checks"]["health"] = {"error": str(e)}
            if not args.quiet:
                print(f"  解析失败: {e}")
    else:
        snapshot["checks"]["health"] = {"error": hc_result.get("error", "执行失败")}
        snapshot["overall"] = "error"
        if not args.quiet:
            print(f"  失败: {hc_result.get('error', '未知错误')}")

    # 2. 状态快照
    if not args.quiet:
        print("【2/4】状态快照...")
    ss_result = run_script("status_summary.py", ["--json"])
    if ss_result["success"]:
        try:
            ss_data = json.loads(ss_result["stdout"])
            snapshot["checks"]["status"] = {
                "concepts": ss_data["data"]["lexicon_concepts"],
                "memory": ss_data["data"]["memory_index"],
                "knowledge": sum(ss_data["data"]["knowledge"].values()),
                "tasks_total": ss_data["tasks"]["total"],
                "disk_free_gb": ss_data["system"]["disk_free_gb"],
            }
            if not args.quiet:
                s = snapshot["checks"]["status"]
                print(f"  概念:{s['concepts']} 记忆:{s['memory']} 经验:{s['knowledge']} 任务:{s['tasks_total']} 磁盘:{s['disk_free_gb']}GB")
        except Exception as e:
            snapshot["checks"]["status"] = {"error": str(e)}
    else:
        snapshot["checks"]["status"] = {"error": ss_result.get("error", "执行失败")}

    # 3. 日志轮转（仅full模式）
    if args.full:
        if not args.quiet:
            print("【3/4】日志轮转...")
        lr_result = run_script("log_rotate.py", ["--verbose" if not args.quiet else ""])
        snapshot["checks"]["log_rotate"] = {"success": lr_result["success"]}
        if not args.quiet:
            print(f"  {'完成' if lr_result['success'] else '失败'}")
    else:
        snapshot["checks"]["log_rotate"] = {"skipped": True}

    # 4. 告警检查
    if not args.quiet:
        print("【4/4】告警检查...")
    if snapshot["overall"] != "ok":
        send_alert(
            "error" if snapshot["overall"] == "error" else "warn",
            "checkup",
            f"巡检结果: {snapshot['overall']}",
            args.alert,
        )
        if not args.quiet:
            print(f"  已发送 {snapshot['overall']} 级别告警")
    else:
        if not args.quiet:
            print("  状态正常，无需告警")

    # 写入快照
    write_snapshot(snapshot)

    if not args.quiet:
        print()
        print(f"巡检完成。总体状态: {snapshot['overall']}")
        print("=" * 60)

    if snapshot["overall"] == "error":
        sys.exit(2)
    elif snapshot["overall"] == "warning":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
