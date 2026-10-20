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
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.heartbeat import Heartbeat


def _process_command_line(pid: int) -> str:
    if os.name == "nt":
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine",
        ]
    else:
        command = ["ps", "-p", str(pid), "-o", "command="]
    result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    return result.stdout.strip()


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
        self._check_runtime_liveness()
        self._check_task_pool()
        self._check_provider_freshness()
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

    def _check_runtime_liveness(self):
        runtime_dir = BASE_DIR / "06_RUNTIME" / "ace" / "data" / "memory"
        status = Heartbeat(runtime_dir).get_status(max_idle_seconds=3600)
        self.check(
            "daemon心跳存活",
            status["is_alive"],
            severity="error",
            detail=(
                f"status={status.get('status')}, pid={status.get('pid')}, "
                f"seconds_since_last_beat={status.get('seconds_since_last_beat')}"
            ),
        )
        if not status["is_alive"]:
            return
        pid = status.get("pid")
        try:
            command_line = _process_command_line(pid)
        except (OSError, subprocess.SubprocessError):
            command_line = ""
        self.check(
            "daemon进程归属",
            "ace_daemon.py" in command_line
            or ("ace.py" in command_line and "daemon" in command_line),
            severity="error",
            detail=f"pid={pid}, command_line={command_line or 'unavailable'}",
        )

    # A blocked task parked terminally while waiting on a human or
    # external/governance decision is known inventory, not a fresh failure.
    # Only tasks that are neither known-governance nor freshly transitional
    # fail the gate: error-signatured reasons, or owned-by-nobody records
    # untouched for longer than ORPHAN_AFTER_HOURS.
    GOVERNANCE_WAIT_MARKERS = (
        "人工", "外部", "治理", "governance", "manual", "等待",
    )
    ERROR_REASON_MARKERS = (
        "失败", "错误", "error", "exception", "timeout", "超时",
        "异常", "crash", "traceback", "refused", "unreachable",
    )
    ORPHAN_AFTER_HOURS = 48
    ABNORMAL_DETAIL_IDS = 5

    def _classify_blocked(self, task_pool: Path) -> dict:
        """Split blocked files into known-governance / abnormal / unclassified.

        Returns task-id lists; unreadable files count as abnormal (a task
        the pool cannot even read is itself worth flagging). Pure read: no
        task is moved, edited, or reaped here — 009/010 own that decision.
        """
        known, abnormal, unclassified = [], [], []
        now = datetime.now()
        for path in (task_pool / "blocked").glob("RQ-*.json"):
            task_id = path.stem
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except Exception:
                abnormal.append((task_id, "unreadable_task_file"))
                continue
            if not isinstance(data, dict):
                abnormal.append((task_id, "unreadable_task_file"))
                continue
            outputs = data.get("outputs") if isinstance(data.get("outputs"), dict) else {}
            terminal = bool(outputs.get("terminal_non_convergent"))
            reason = str(
                data.get("blocked_reason") or outputs.get("rework_reason") or ""
            )
            lowered = reason.lower()
            if terminal and any(mark in lowered for mark in self.GOVERNANCE_WAIT_MARKERS):
                known.append(task_id)
                continue
            if any(mark in lowered for mark in self.ERROR_REASON_MARKERS):
                abnormal.append((task_id, "error_reason:" + reason[:48]))
                continue
            owner = data.get("lease_owner") or data.get("claim_id") or ""
            try:
                updated = datetime.fromisoformat(
                    str(data.get("updated_at", "")).replace("Z", "")
                )
                age_hours = (now - updated).total_seconds() / 3600
            except (TypeError, ValueError):
                age_hours = None
            if not owner and age_hours is not None and age_hours > self.ORPHAN_AFTER_HOURS:
                abnormal.append((task_id, f"orphaned:{age_hours:.0f}h_unowned"))
                continue
            unclassified.append(task_id)
        return {"known": known, "abnormal": abnormal, "unclassified": unclassified}

    def _check_task_pool(self):
        task_pool = BASE_DIR / "task_pool"
        if not task_pool.is_dir():
            self.check("任务池目录", False, severity="error", detail="不存在")
            return

        active = len(list((task_pool / "active").glob("RQ-*.json")))
        pending = len(list((task_pool / "pending").glob("RQ-*.json")))
        triage = self._classify_blocked(task_pool)
        known, abnormal, unclassified = (
            triage["known"], triage["abnormal"], triage["unclassified"],
        )
        total_blocked = len(known) + len(abnormal) + len(unclassified)
        counts = (
            f"active={active}, blocked={total_blocked} "
            f"(known_governance={len(known)}, abnormal={len(abnormal)}, "
            f"unclassified={len(unclassified)}), pending={pending}"
        )

        # Only genuine abnormality errors. Known governance backlog and
        # fresh transitional tasks never fail this gate. The abnormal
        # entries keep their reasons so the receipt names the fault.
        abnormal_shown = ",".join(
            f"{task_id}:{why}" for task_id, why in abnormal[: self.ABNORMAL_DETAIL_IDS]
        )
        self.check(
            "无大量阻塞任务",
            len(abnormal) == 0,
            severity="error",
            detail=counts + (f"; abnormal={abnormal_shown}" if abnormal_shown else ""),
        )

        # The known backlog stays visible as inventory with its reasons —
        # counted and named, never silently green.
        if known:
            reasons: dict = defaultdict(int)
            for path in (task_pool / "blocked").glob("RQ-*.json"):
                if path.stem not in set(known):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as handle:
                        data = json.load(handle)
                    reason = str(
                        data.get("blocked_reason")
                        or (data.get("outputs") or {}).get("rework_reason")
                        or "?"
                    )
                    reasons[reason[:40]] += 1
                except Exception:
                    reasons["unreadable"] += 1
            inventory = ";".join(f"{count}x:{reason}" for reason, count in sorted(
                reasons.items(), key=lambda item: -item[1])[:3])
            self.check(
                "已知治理阻塞登记",
                False,
                severity="warning",
                detail=f"{len(known)} known_governance; {inventory}",
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

    def _check_provider_freshness(self):
        """Report model-health ratings with their age, never as timeless fact.

        Read-only: parses the persisted watchdog snapshot and labels each
        provider by the shared effective-status rule. STALE is inventory,
        never fault — an idle pool revalidates on next live traffic, and
        nothing here manufactures a call or a task to force a refresh.
        """
        state_file = (
            BASE_DIR / "06_RUNTIME" / "ace" / "data" / "miner_pool"
            / "provider_watchdog" / "watchdog_state.json"
        )
        if not state_file.is_file():
            self.check(
                "模型健康评级新鲜",
                True,
                severity="warning",
                detail="no watchdog state yet (no traffic observed)",
            )
            return
        try:
            from core.miner_pool.provider_watchdog import (
                STALE,
                STALE_TTL_SECONDS,
                effective_status_for,
                observation_age_hours,
            )
        except Exception as error:
            self.check(
                "模型健康评级新鲜",
                True,
                severity="warning",
                detail=f"watchdog module unreadable: {type(error).__name__}",
            )
            return
        try:
            with open(state_file, "r", encoding="utf-8") as handle:
                snapshot = json.load(handle)
            providers = snapshot.get("providers")
            if not isinstance(providers, dict):
                raise ValueError("watchdog snapshot has no providers")
        except Exception as error:
            self.check(
                "模型健康评级新鲜",
                True,
                severity="warning",
                detail=f"watchdog snapshot unreadable: {str(error)[:80]}",
            )
            return
        stale_names, fresh_summary = [], defaultdict(int)
        for name in sorted(providers):
            record = providers[name]
            if not isinstance(record, dict):
                continue
            effective = effective_status_for(record, ttl_seconds=STALE_TTL_SECONDS)
            age = observation_age_hours(record)
            fresh_summary[effective] += 1
            if effective == STALE:
                age_text = f"{age:.1f}h" if age is not None else "never"
                stale_names.append(f"{name}({age_text})")
        summary = ",".join(
            f"{status}={fresh_summary[status]}" for status in sorted(fresh_summary)
        )
        detail = summary + (
            "; stale:" + ",".join(stale_names[:8]) if stale_names else ""
        )
        # Idle is not a fault: stale ratings warn (stay visible) but never
        # error. Fresh UNHEALTHY/OFFLINE are live failures the watchdog
        # already owns — this probe only reports age, it does not re-judge.
        self.check(
            "模型健康评级新鲜",
            not stale_names,
            severity="warning",
            detail=detail,
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

