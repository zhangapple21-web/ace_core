#!/usr/bin/env python3
"""
ACE 静默告警脚本 (ID-09)

异常时：
  1. 写告警日志到 ops/logs/alerts.log
  2. 可选：Windows 本地通知（Toast，可选）

不弹窗、不打断、后台静默运行。

用法：
  python ops/alert.py --level error --module "test" --message "测试告警"
  python ops/alert.py --level warn  --module "test" --message "测试警告"
  python ops/alert.py --level info  --module "test" --message "测试通知"
  python ops/alert.py --check      # 从健康检查结果自动判断并告警
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

ALERT_LOG = BASE_DIR / "ops" / "logs" / "alerts.log"


def ensure_log_dir():
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)


def write_alert(level: str, module: str, message: str, details: dict = None):
    ensure_log_dir()
    entry = {
        "timestamp": datetime.now().isoformat(),
        "level": level,
        "module": module,
        "message": message,
        "details": details or {},
    }
    line = json.dumps(entry, ensure_ascii=False)
    with open(ALERT_LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    return entry


def send_windows_toast(title: str, message: str):
    """发送 Windows 本地通知（静默，不抢焦点）"""
    try:
        from win10toast import ToastNotifier
        toaster = ToastNotifier()
        toaster.show_toast(title, message, duration=5, threaded=True)
        return True
    except ImportError:
        return False
    except Exception:
        return False


def check_and_alert() -> dict:
    """运行健康检查，根据结果自动告警"""
    from health_check import HealthChecker

    checker = HealthChecker()
    result = checker.run_all()

    alerts_sent = []

    if result["errors"]:
        for err in result["error_details"][:3]:
            entry = write_alert("error", "health_check", f"健康检查错误: {err}")
            alerts_sent.append(entry)
            send_windows_toast("ACE 告警 - 错误", err)

    if result["warnings"]:
        for warn in result["warning_details"][:3]:
            entry = write_alert("warn", "health_check", f"健康检查警告: {warn}")
            alerts_sent.append(entry)

    if not alerts_sent:
        entry = write_alert("info", "health_check", "健康检查通过")
        alerts_sent.append(entry)

    return {
        "health_overall": result["overall"],
        "alerts_sent": len(alerts_sent),
        "alerts": alerts_sent,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ACE 静默告警")
    parser.add_argument("--level", choices=["info", "warn", "error"], default="info")
    parser.add_argument("--module", default="unknown")
    parser.add_argument("--message", default="")
    parser.add_argument("--details", default="", help="JSON格式的详情")
    parser.add_argument("--check", action="store_true", help="运行健康检查并自动告警")
    parser.add_argument("--notify", action="store_true", help="同时发送Windows通知")
    args = parser.parse_args()

    if args.check:
        result = check_and_alert()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if not args.message:
        parser.error("--message is required unless --check is used")

    details = {}
    if args.details:
        try:
            details = json.loads(args.details)
        except json.JSONDecodeError:
            details = {"raw": args.details}

    entry = write_alert(args.level, args.module, args.message, details)
    print(json.dumps(entry, ensure_ascii=False, indent=2))

    if args.notify:
        send_windows_toast(f"ACE {args.level.upper()}", args.message)


if __name__ == "__main__":
    main()
