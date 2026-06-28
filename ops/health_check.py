#!/usr/bin/env python3
"""
ACE 健康检查脚本 (ID-05)

检查项：
  1. 关键目录/文件存在性
  2. 磁盘空间
  3. 词库/记忆/经验数据完整性
  4. 任务池状态（无死锁、无大量阻塞）
  5. 最近错误记录

用法：
  python ops/health_check.py
  python ops/health_check.py --json   # JSON输出
  python ops/health_check.py --quiet  # 静默，只返回exit code

退出码：
  0 = 全部通过
  1 = 有警告
  2 = 有严重错误
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


class HealthChecker:
    def __init__(self):
        self.results = []
        self.warnings = []
        self.errors = []
        self.info = []

    def check(self, name: str, passed: bool, severity: str = "error", detail: str = ""):
        entry = {
            "name": name,
            "passed": passed,
            "severity": severity,
            "detail": detail,
        }
        self.results.append(entry)
        if not passed:
            if severity == "error":
                self.errors.append(entry)
            else:
                self.warnings.append(entry)
        else:
            self.info.append(entry)
        return passed

    def run_all(self) -> dict:
        self._check_filesystem()
        self._check_data_integrity()
        self._check_task_pool()
        self._check_recent_errors()
        self._check_config()

        overall = "ok"
        if self.errors:
            overall = "error"
        elif self.warnings:
            overall = "warning"

        return {
            "timestamp": datetime.now().isoformat(),
            "overall": overall,
            "total_checks": len(self.results),
            "passed": len(self.info),
            "warnings": len(self.warnings),
            "errors": len(self.errors),
            "checks": self.results,
            "warning_details": [e["name"] + ": " + e["detail"] for e in self.warnings],
            "error_details": [e["name"] + ": " + e["detail"] for e in self.errors],
        }

    def _check_filesystem(self):
        critical_dirs = ["core", "06_RUNTIME/workers", "09_KNOWLEDGE", "task_pool"]
        for d in critical_dirs:
            p = BASE_DIR / d
            self.check(
                f"目录存在: {d}",
                p.is_dir(),
                severity="error",
                detail=str(p),
            )

        critical_files = [
            "ace_daemon.py",
            "ace_config.json",
            "core/task.py",
            "core/task_roles.py",
            "06_RUNTIME/workers/base_worker.py",
        ]
        for f in critical_files:
            p = BASE_DIR / f
            self.check(
                f"文件存在: {f}",
                p.is_file(),
                severity="error",
                detail=str(p),
            )

        try:
            import shutil
            total, used, free = shutil.disk_usage(str(BASE_DIR))
            free_gb = free / (1024 ** 3)
            free_pct = free / total * 100
            self.check(
                "磁盘空间充足",
                free_gb >= 5 and free_pct >= 5,
                severity="error" if free_gb < 1 else "warning",
                detail=f"剩余 {free_gb:.1f} GB ({free_pct:.1f}%)",
            )
        except Exception as e:
            self.check("磁盘空间检查", False, severity="warning", detail=str(e))

    def _check_data_integrity(self):
        state_file = BASE_DIR / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json"
        self.check(
            "daemon状态文件存在",
            state_file.is_file(),
            severity="warning",
            detail=str(state_file),
        )

        knowledge_dir = BASE_DIR / "09_KNOWLEDGE"
        if knowledge_dir.is_dir():
            axiom_count = len(list((knowledge_dir / "axiom").glob("*.json"))) if (knowledge_dir / "axiom").exists() else 0
            constraint_count = len(list((knowledge_dir / "constraint").glob("*.json"))) if (knowledge_dir / "constraint").exists() else 0
            pattern_count = len(list((knowledge_dir / "pattern").glob("*.json"))) if (knowledge_dir / "pattern").exists() else 0
            total = axiom_count + constraint_count + pattern_count
            self.check(
                "经验库有内容",
                total > 0,
                severity="warning",
                detail=f"共{total}条 (axiom={axiom_count}, constraint={constraint_count}, pattern={pattern_count})",
            )

        task_pool = BASE_DIR / "task_pool"
        if task_pool.is_dir():
            archived = len(list((task_pool / "archived").glob("RQ-*.json")))
            self.check(
                "有归档任务",
                archived > 0,
                severity="warning",
                detail=f"已归档 {archived} 个任务",
            )

    def _check_task_pool(self):
        task_pool = BASE_DIR / "task_pool"
        if not task_pool.is_dir():
            self.check("任务池目录", False, severity="error", detail="不存在")
            return

        active = len(list((task_pool / "active").glob("RQ-*.json")))
        blocked = len(list((task_pool / "blocked").glob("RQ-*.json")))
        pending = len(list((task_pool / "pending").glob("RQ-*.json")))

        self.check(
            "无大量阻塞任务",
            blocked < 5,
            severity="warning" if blocked < 10 else "error",
            detail=f"active={active}, blocked={blocked}, pending={pending}",
        )

        if active > 0:
            stale_count = 0
            for f in (task_pool / "active").glob("RQ-*.json"):
                try:
                    import json as _json
                    with open(f, "r", encoding="utf-8") as fp:
                        data = _json.load(fp)
                    updated = datetime.fromisoformat(data.get("updated_at", "").replace("Z", ""))
                    if (datetime.now() - updated).total_seconds() > 3600 * 6:
                        stale_count += 1
                except Exception:
                    pass
            self.check(
                "active任务无超时（>6h）",
                stale_count == 0,
                severity="warning",
                detail=f"{stale_count} 个任务运行超过6小时",
            )

    def _check_recent_errors(self):
        state_file = BASE_DIR / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json"
        if not state_file.is_file():
            return

        try:
            with open(state_file, "r", encoding="utf-8") as f:
                state = json.load(f)
            errors = state.get("errors", [])
            recent_24h = []
            now = datetime.now()
            for e in errors:
                try:
                    t = datetime.fromisoformat(e.get("time", "").replace("Z", ""))
                    if (now - t).total_seconds() < 86400:
                        recent_24h.append(e)
                except Exception:
                    pass

            self.check(
                "近24小时错误数正常",
                len(recent_24h) < 10,
                severity="warning" if len(recent_24h) < 20 else "error",
                detail=f"近24h {len(recent_24h)} 个错误",
            )
        except Exception as e:
            self.check("错误记录检查", False, severity="warning", detail=str(e))

    def _check_config(self):
        config_file = BASE_DIR / "ace_config.json"
        if not config_file.is_file():
            self.check("配置文件", False, severity="error", detail="ace_config.json不存在")
            return

        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self.check(
                "配置文件有效",
                isinstance(cfg, dict) and "version" in cfg,
                severity="error",
                detail=f"version={cfg.get('version', 'unknown')}",
            )
        except Exception as e:
            self.check("配置文件有效", False, severity="error", detail=str(e))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="ACE 健康检查")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--quiet", action="store_true", help="静默模式，仅exit code")
    args = parser.parse_args()

    checker = HealthChecker()
    result = checker.run_all()

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif not args.quiet:
        print("=" * 60)
        print(f"ACE 健康检查 — {result['timestamp']}")
        print("=" * 60)
        print()
        status_map = {"ok": "✅ 正常", "warning": "⚠️  警告", "error": "❌ 错误"}
        print(f"总体状态: {status_map.get(result['overall'], result['overall'])}")
        print(f"检查项: {result['total_checks']} 项")
        print(f"  通过: {result['passed']}")
        print(f"  警告: {result['warnings']}")
        print(f"  错误: {result['errors']}")
        print()

        if result["warning_details"]:
            print("【警告】")
            for w in result["warning_details"]:
                print(f"  ⚠️  {w}")
            print()

        if result["error_details"]:
            print("【错误】")
            for e in result["error_details"]:
                print(f"  ❌ {e}")
            print()

        if result["overall"] == "ok":
            print("所有检查通过，系统运行正常。")
        print()

    if result["errors"]:
        sys.exit(2)
    elif result["warnings"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
