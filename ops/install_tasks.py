#!/usr/bin/env python3
"""
ACE 运维 - Windows 计划任务安装器 (Python版)
(ID-06 + ID-08)

不需要修改PowerShell执行策略，直接用schtasks命令。

用法：
  python ops/install_tasks.py           # 安装所有任务
  python ops/install_tasks.py --remove  # 卸载所有任务
  python ops/install_tasks.py --check   # 检查任务状态
"""

import subprocess
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
OPS_DIR = Path(__file__).resolve().parent
PYTHON_EXE = sys.executable

TASKS = [
    {
        "name": "ACE_HealthCheck_Hourly",
        "description": "ACE 每小时健康检查（静默）",
        "script": str(OPS_DIR / "run_checkup.py"),
        "args": "--quiet",
        "schedule": "HOURLY",
        "start_time": "00:00",
    },
    {
        "name": "ACE_FullCheckup_Daily",
        "description": "ACE 每日完整巡检 + 日志轮转（凌晨3点）",
        "script": str(OPS_DIR / "run_checkup.py"),
        "args": "--full",
        "schedule": "DAILY",
        "start_time": "03:00",
    },
    {
        "name": "ACE_Daemon_Boot",
        "description": "ACE 开机自启主循环（开机后5分钟）",
        "script": str(BASE_DIR / "ace_daemon.py"),
        "args": "",
        "schedule": "ONSTART",
        "start_time": "",
        "delay": "0005:00",  # mmmm:ss 格式，5分钟
    },
]


def run_cmd(cmd: list, capture: bool = True) -> dict:
    """运行命令，返回结果"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            timeout=30,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def task_exists(task_name: str) -> bool:
    """检查任务是否存在"""
    result = run_cmd(["schtasks", "/Query", "/TN", task_name])
    return result["success"]


def delete_task(task_name: str) -> dict:
    """删除任务"""
    result = run_cmd(["schtasks", "/Delete", "/TN", task_name, "/F"])
    return result


def create_task(task: dict) -> dict:
    """创建计划任务"""
    name = task["name"]
    script = task["script"]
    args = task["args"]
    schedule = task["schedule"]

    cmd = [
        "schtasks", "/Create",
        "/TN", name,
        "/TR", f'"{PYTHON_EXE}" "{script}" {args}'.strip(),
        "/SC", schedule,
        "/F",
    ]

    if task.get("start_time") and schedule != "ONSTART":
        cmd += ["/ST", task["start_time"]]

    if task.get("delay"):
        cmd += ["/DELAY", task["delay"]]

    result = run_cmd(cmd)
    return result


def check_tasks():
    """检查所有任务状态"""
    print("=" * 60)
    print("  ACE 计划任务状态")
    print("=" * 60)
    print()

    for task in TASKS:
        name = task["name"]
        exists = task_exists(name)
        if exists:
            result = run_cmd(["schtasks", "/Query", "/TN", name, "/FO", "LIST", "/V"])
            status_line = "未知"
            last_run = "未知"
            next_run = "未知"
            if result["success"]:
                for line in result["stdout"].split("\n"):
                    if "状态:" in line or "Status:" in line:
                        status_line = line.split(":", 1)[1].strip()
                    if "上次运行时间:" in line or "Last Run Time:" in line:
                        last_run = line.split(":", 1)[1].strip()
                    if "下次运行时间:" in line or "Next Run Time:" in line:
                        next_run = line.split(":", 1)[1].strip()
            print(f"  [运行中] {name}")
            print(f"       状态: {status_line}")
            print(f"       上次: {last_run}")
            print(f"       下次: {next_run}")
        else:
            print(f"  [未安装] {name}")
        print()

    print("=" * 60)


def install_tasks():
    """安装所有任务"""
    print("=" * 60)
    print("  正在安装 ACE 计划任务...")
    print("=" * 60)
    print()
    print(f"  Python: {PYTHON_EXE}")
    print(f"  目录:   {BASE_DIR}")
    print()

    success_count = 0
    for task in TASKS:
        name = task["name"]

        if task_exists(name):
            delete_task(name)

        result = create_task(task)

        if result["success"]:
            print(f"  [OK] {name}")
            print(f"       {task['description']}")
            success_count += 1
        else:
            print(f"  [FAIL] {name}")
            err = result.get("stderr", "").strip() or result.get("error", "未知错误")
            print(f"       {err}")
        print()

    print(f"完成：{success_count}/{len(TASKS)} 个任务安装成功")
    print("=" * 60)

    if success_count < len(TASKS):
        print()
        print("提示：部分任务创建失败，可能原因：")
        print("  1. 需要管理员权限（右键以管理员身份运行）")
        print("  2. ONSTART 任务需要管理员权限")
        print()
        print("请以管理员身份重新运行此脚本。")


def remove_tasks():
    """卸载所有任务"""
    print("=" * 60)
    print("  正在卸载 ACE 计划任务...")
    print("=" * 60)
    print()

    removed = 0
    for task in TASKS:
        name = task["name"]
        if task_exists(name):
            result = delete_task(name)
            if result["success"]:
                print(f"  [已删除] {name}")
                removed += 1
            else:
                print(f"  [失败] {name}")
        else:
            print(f"  [不存在] {name}")

    print()
    print(f"完成：删除了 {removed} 个任务")
    print("=" * 60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ACE 计划任务安装器")
    parser.add_argument("--remove", action="store_true", help="卸载所有任务")
    parser.add_argument("--check", action="store_true", help="检查任务状态")
    args = parser.parse_args()

    if args.check:
        check_tasks()
    elif args.remove:
        remove_tasks()
    else:
        install_tasks()


if __name__ == "__main__":
    main()
