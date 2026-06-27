"""
自我修复模块（SelfHealing）

系统活着的第二个证据：它能自己修复自己。

什么系统最容易死？
- 出了错只会报错的系统
- 死锁了只会等着的系统
- 文件丢了只会崩溃的系统

什么系统能活下来？
- 能检测问题的系统
- 能尝试修复的系统
- 修不好也不会全盘崩溃的系统

修复优先级（从易到难）：
1. 状态文件损坏 → 从备份恢复 / 重建
2. 任务死锁 → 超时自动解锁
3. 依赖缺失 → 降级运行
4. 结构损坏 → 从种子重建
"""

import json
import shutil
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable


class SelfHealing:
    """
    自我修复器

    设计原则：
    - 先检测，再修复
    - 修复要有日志
    - 修不好不要硬修，要降级
    - 每次修复都要记经验
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.healing_log_file = self.data_dir / "healing_log.json"
        self.healing_log = self._load_log()

    def _load_log(self) -> List[Dict[str, Any]]:
        if self.healing_log_file.exists():
            try:
                with open(self.healing_log_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return []
        return []

    def _save_log(self):
        with open(self.healing_log_file, "w", encoding="utf-8") as f:
            json.dump(self.healing_log, f, ensure_ascii=False, indent=2)

    def _record(self, issue_type: str, severity: str, description: str,
                action: str, result: str, details: Dict = None):
        """记录一次修复事件。"""
        entry = {
            "at": datetime.now().isoformat(),
            "issue_type": issue_type,
            "severity": severity,
            "description": description,
            "action": action,
            "result": result,
            "details": details or {},
        }
        self.healing_log.append(entry)
        if len(self.healing_log) > 500:
            self.healing_log = self.healing_log[-500:]
        self._save_log()
        return entry

    def diagnose(self, base_dir: Path = None) -> Dict[str, Any]:
        """
        全面诊断系统健康状况。

        返回：
        - health_score: 0-100
        - issues: 发现的问题列表
        - recommendations: 建议的修复动作
        """
        base_dir = base_dir or self.data_dir.parent
        issues = []
        health_score = 100

        checks = [
            ("critical_files", self._check_critical_files, base_dir),
            ("task_deadlocks", self._check_task_deadlocks, base_dir),
            ("state_consistency", self._check_state_consistency, base_dir),
            ("disk_space", self._check_disk_space, base_dir),
            ("memory_integrity", self._check_memory_integrity, base_dir),
        ]

        for name, check_fn, arg in checks:
            try:
                result = check_fn(arg)
                if result.get("issues"):
                    for issue in result["issues"]:
                        issues.append(issue)
                        severity = issue.get("severity", "low")
                        if severity == "critical":
                            health_score -= 30
                        elif severity == "high":
                            health_score -= 15
                        elif severity == "medium":
                            health_score -= 5
                        else:
                            health_score -= 1
            except Exception as e:
                issues.append({
                    "type": name,
                    "severity": "medium",
                    "description": f"检查失败: {e}",
                })
                health_score -= 5

        health_score = max(0, min(100, health_score))

        return {
            "health_score": health_score,
            "issue_count": len(issues),
            "issues": issues,
            "diagnosed_at": datetime.now().isoformat(),
        }

    def _check_critical_files(self, base_dir: Path) -> Dict[str, Any]:
        """检查关键文件是否存在且可读。"""
        issues = []
        critical_files = [
            "ace_config.json",
            "01_CORE/identity.json",
            "02_MEMORY/recent/daily",
            "05_TASKS",
        ]

        for rel_path in critical_files:
            full_path = base_dir / rel_path
            if not full_path.exists():
                issues.append({
                    "type": "missing_file",
                    "severity": "high" if "config" in rel_path or "identity" in rel_path else "medium",
                    "description": f"关键文件/目录缺失: {rel_path}",
                    "path": str(full_path),
                    "fixable": True,
                })

        return {"issues": issues}

    def _check_task_deadlocks(self, base_dir: Path) -> Dict[str, Any]:
        """检查是否有死锁任务（处于active状态超过1小时）。"""
        issues = []
        tasks_dir = base_dir / "05_TASKS"

        if not tasks_dir.exists():
            return {"issues": issues}

        active_dir = tasks_dir / "active"
        if not active_dir.exists():
            return {"issues": issues}

        now = datetime.now()
        for task_file in active_dir.glob("*.json"):
            try:
                with open(task_file, "r", encoding="utf-8") as f:
                    task = json.load(f)
                updated_at = task.get("updated_at") or task.get("created_at")
                if updated_at:
                    updated = datetime.fromisoformat(updated_at)
                    elapsed = (now - updated).total_seconds()
                    if elapsed > 3600:
                        issues.append({
                            "type": "task_deadlock",
                            "severity": "medium",
                            "description": f"任务疑似死锁: {task.get('task_id', task_file.stem)} (活跃{int(elapsed/60)}分钟)",
                            "task_id": task.get("task_id", task_file.stem),
                            "file": str(task_file),
                            "fixable": True,
                        })
            except Exception:
                pass

        return {"issues": issues}

    def _check_state_consistency(self, base_dir: Path) -> Dict[str, Any]:
        """检查状态文件一致性。"""
        issues = []

        state_file = base_dir / "00_STATE" / "daemon_state.json"
        if state_file.exists():
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                if not isinstance(state, dict):
                    issues.append({
                        "type": "state_corruption",
                        "severity": "high",
                        "description": "daemon_state.json 格式错误",
                        "fixable": True,
                    })
            except json.JSONDecodeError:
                issues.append({
                    "type": "state_corruption",
                    "severity": "high",
                    "description": "daemon_state.json 损坏无法解析",
                    "fixable": True,
                })

        return {"issues": issues}

    def _check_disk_space(self, base_dir: Path) -> Dict[str, Any]:
        """检查磁盘空间（简单检查）。"""
        issues = []
        try:
            usage = shutil.disk_usage(str(base_dir))
            free_percent = usage.free / usage.total * 100
            if free_percent < 5:
                issues.append({
                    "type": "low_disk_space",
                    "severity": "critical",
                    "description": f"磁盘空间不足: {free_percent:.1f}% 剩余",
                    "fixable": False,
                })
            elif free_percent < 10:
                issues.append({
                    "type": "low_disk_space",
                    "severity": "medium",
                    "description": f"磁盘空间偏低: {free_percent:.1f}% 剩余",
                    "fixable": False,
                })
        except Exception:
            pass

        return {"issues": issues}

    def _check_memory_integrity(self, base_dir: Path) -> Dict[str, Any]:
        """检查记忆索引完整性。"""
        issues = []
        memory_dir = base_dir / "02_MEMORY"

        if not memory_dir.exists():
            return {"issues": issues}

        index_file = memory_dir / "memory_index.json"
        if index_file.exists():
            try:
                with open(index_file, "r", encoding="utf-8") as f:
                    idx = json.load(f)
                if not isinstance(idx, dict):
                    issues.append({
                        "type": "memory_index_corruption",
                        "severity": "medium",
                        "description": "记忆索引格式错误",
                        "fixable": True,
                    })
            except json.JSONDecodeError:
                issues.append({
                    "type": "memory_index_corruption",
                    "severity": "medium",
                    "description": "记忆索引损坏",
                    "fixable": True,
                })

        return {"issues": issues}

    def heal(self, base_dir: Path = None) -> Dict[str, Any]:
        """
        执行自我修复。

        流程：
        1. 诊断问题
        2. 按严重程度排序
        3. 逐个尝试修复
        4. 记录结果
        """
        base_dir = base_dir or self.data_dir.parent
        diagnosis = self.diagnose(base_dir)

        fixed = []
        failed = []
        skipped = []

        issues = sorted(
            diagnosis["issues"],
            key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                x.get("severity", "low"), 4
            ),
        )

        for issue in issues:
            if not issue.get("fixable", False):
                skipped.append(issue)
                continue

            try:
                result = self._fix_issue(issue, base_dir)
                if result.get("success"):
                    fixed.append({
                        **issue,
                        "fix_result": result,
                    })
                    self._record(
                        issue_type=issue["type"],
                        severity=issue.get("severity", "low"),
                        description=issue["description"],
                        action=result.get("action", "unknown"),
                        result="fixed",
                        details=result.get("details", {}),
                    )
                else:
                    failed.append({
                        **issue,
                        "fix_result": result,
                    })
                    self._record(
                        issue_type=issue["type"],
                        severity=issue.get("severity", "low"),
                        description=issue["description"],
                        action=result.get("action", "unknown"),
                        result="failed",
                        details=result.get("details", {}),
                    )
            except Exception as e:
                failed.append({
                    **issue,
                    "fix_result": {"success": False, "error": str(e)},
                })
                self._record(
                    issue_type=issue["type"],
                    severity=issue.get("severity", "low"),
                    description=issue["description"],
                    action="exception",
                    result="failed",
                    details={"error": str(e)},
                )

        new_diagnosis = self.diagnose(base_dir)

        return {
            "before_health": diagnosis["health_score"],
            "after_health": new_diagnosis["health_score"],
            "issues_before": diagnosis["issue_count"],
            "issues_after": new_diagnosis["issue_count"],
            "fixed": len(fixed),
            "failed": len(failed),
            "skipped": len(skipped),
            "fixed_issues": fixed,
            "failed_issues": failed,
            "skipped_issues": skipped,
        }

    def _fix_issue(self, issue: Dict[str, Any], base_dir: Path) -> Dict[str, Any]:
        """修复单个问题。"""
        issue_type = issue.get("type", "")

        if issue_type == "missing_file":
            return self._fix_missing_file(issue, base_dir)
        elif issue_type == "task_deadlock":
            return self._fix_task_deadlock(issue, base_dir)
        elif issue_type == "state_corruption":
            return self._fix_state_corruption(issue, base_dir)
        elif issue_type == "memory_index_corruption":
            return self._fix_memory_index_corruption(issue, base_dir)
        else:
            return {"success": False, "action": "unsupported", "error": f"不支持的修复类型: {issue_type}"}

    def _fix_missing_file(self, issue: Dict[str, Any], base_dir: Path) -> Dict[str, Any]:
        """修复缺失的文件/目录。"""
        path = Path(issue.get("path", ""))
        if not path.parent.exists():
            path.parent.mkdir(parents=True, exist_ok=True)

        if path.suffix == ".json":
            with open(path, "w", encoding="utf-8") as f:
                json.dump({}, f)
        else:
            path.mkdir(parents=True, exist_ok=True)

        return {
            "success": True,
            "action": "create_empty",
            "details": {"path": str(path)},
        }

    def _fix_task_deadlock(self, issue: Dict[str, Any], base_dir: Path) -> Dict[str, Any]:
        """修复死锁任务（移回pending）。"""
        task_id = issue.get("task_id", "")
        task_file = Path(issue.get("file", ""))

        if not task_file.exists():
            return {"success": False, "action": "not_found", "error": "任务文件不存在"}

        try:
            with open(task_file, "r", encoding="utf-8") as f:
                task = json.load(f)

            task["status"] = "pending"
            task["blocked_reason"] = task.get("blocked_reason", "") + f" [自动解锁: 死锁恢复]"
            task["retry_count"] = task.get("retry_count", 0) + 1

            pending_dir = base_dir / "05_TASKS" / "pending"
            pending_dir.mkdir(parents=True, exist_ok=True)

            new_path = pending_dir / task_file.name
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(task, f, ensure_ascii=False, indent=2)

            task_file.unlink()

            return {
                "success": True,
                "action": "unlock_to_pending",
                "details": {"task_id": task_id},
            }
        except Exception as e:
            return {"success": False, "action": "unlock_failed", "error": str(e)}

    def _fix_state_corruption(self, issue: Dict[str, Any], base_dir: Path) -> Dict[str, Any]:
        """修复状态文件损坏（备份后重建）。"""
        state_dir = base_dir / "00_STATE"
        state_file = state_dir / "daemon_state.json"

        if state_file.exists():
            backup = state_file.with_suffix(".bak." + datetime.now().strftime("%Y%m%d%H%M%S"))
            shutil.copy2(state_file, backup)

        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({
                "last_run": None,
                "iteration": 0,
                "mining_progress": {},
                "stats": {},
                "errors": [],
                "created_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "action": "rebuild_state",
            "details": {"backup": str(state_file.with_suffix(".bak.*"))},
        }

    def _fix_memory_index_corruption(self, issue: Dict[str, Any], base_dir: Path) -> Dict[str, Any]:
        """修复记忆索引损坏（备份后重建空索引）。"""
        memory_dir = base_dir / "02_MEMORY"
        index_file = memory_dir / "memory_index.json"

        if index_file.exists():
            backup = index_file.with_suffix(".bak." + datetime.now().strftime("%Y%m%d%H%M%S"))
            shutil.copy2(index_file, backup)

        with open(index_file, "w", encoding="utf-8") as f:
            json.dump({
                "items": [],
                "concept_index": {},
                "stats": {"total": 0},
                "created_at": datetime.now().isoformat(),
            }, f, ensure_ascii=False, indent=2)

        return {
            "success": True,
            "action": "rebuild_memory_index",
            "details": {"backup": str(index_file.with_suffix(".bak.*"))},
        }

    def get_healing_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """获取修复历史。"""
        return list(reversed(self.healing_log[-limit:]))

    def get_healing_stats(self) -> Dict[str, Any]:
        """获取修复统计。"""
        total = len(self.healing_log)
        fixed = sum(1 for e in self.healing_log if e.get("result") == "fixed")
        failed = sum(1 for e in self.healing_log if e.get("result") == "failed")

        by_type = {}
        for entry in self.healing_log:
            t = entry.get("issue_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1

        return {
            "total_healing_events": total,
            "fixed": fixed,
            "failed": failed,
            "success_rate": fixed / total if total > 0 else 0,
            "by_issue_type": by_type,
        }
