"""
任务生命周期核心模型

任务不是一张纸。
任务有出生、成长、被挑战、被批准、被遗忘。

统一任务格式 + 状态流转 + 热度/死亡机制。
"""

import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import defaultdict


TASK_STATUSES = [
    "pending",
    "active",
    "blocked",
    "review",
    "approved",
    "archived",
    "rejected",
    "graveyard",
]

STATUS_DIRS = {
    "pending": "pending",
    "active": "active",
    "blocked": "blocked",
    "review": "review",
    "approved": "approved",
    "archived": "archived",
    "rejected": "rejected",
    "graveyard": "graveyard",
}

PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


class Task:
    """任务对象 — 有生命周期的活物"""

    def __init__(
        self,
        task_id: str,
        title: str,
        creator: str = "observer",
        status: str = "pending",
        priority: str = "medium",
        hypothesis: str = "",
        evidence: Optional[List] = None,
        counter_examples: Optional[List] = None,
        result: Optional[Any] = None,
        tags: Optional[List[str]] = None,
        references: Optional[List[str]] = None,
        created_at: Optional[str] = None,
        updated_at: Optional[str] = None,
        last_referenced_at: Optional[str] = None,
        reference_count: int = 0,
        assignee: Optional[str] = None,
        research_notes: Optional[List] = None,
        validation_notes: Optional[List] = None,
        guardian_decision: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        blocked_reason: Optional[str] = None,
        parent_task: Optional[str] = None,
        outputs: Optional[Dict] = None,
        failure_reason: Optional[str] = None,
        retry_count: int = 0,
        audit_log: Optional[List] = None,
        **kwargs,
    ):
        self.task_id = task_id
        self.title = title
        self.creator = creator
        self.status = status if status in TASK_STATUSES else "pending"
        self.priority = priority if priority in PRIORITY_ORDER else "medium"
        self.hypothesis = hypothesis or ""
        self.evidence = evidence or []
        self.counter_examples = counter_examples or []
        self.result = result
        self.tags = tags or []
        self.references = references or []
        self.created_at = created_at or datetime.now().isoformat()
        self.updated_at = updated_at or datetime.now().isoformat()
        self.last_referenced_at = last_referenced_at or datetime.now().isoformat()
        self.reference_count = reference_count
        self.assignee = assignee
        self.research_notes = research_notes or []
        self.validation_notes = validation_notes or []
        self.guardian_decision = guardian_decision
        self.review_count = kwargs.get("review_count", 0)
        self.depends_on = depends_on or []
        self.blocked_reason = blocked_reason or ""
        self.parent_task = parent_task or ""
        self.outputs = outputs or {}
        self.failure_reason = failure_reason or ""
        self.retry_count = retry_count
        self.audit_log = audit_log or []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "creator": self.creator,
            "status": self.status,
            "priority": self.priority,
            "hypothesis": self.hypothesis,
            "evidence": self.evidence,
            "counter_examples": self.counter_examples,
            "result": self.result,
            "tags": self.tags,
            "references": self.references,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_referenced_at": self.last_referenced_at,
            "reference_count": self.reference_count,
            "assignee": self.assignee,
            "research_notes": self.research_notes,
            "validation_notes": self.validation_notes,
            "guardian_decision": self.guardian_decision,
            "review_count": getattr(self, "review_count", 0),
            "depends_on": self.depends_on,
            "blocked_reason": self.blocked_reason,
            "parent_task": self.parent_task,
            "outputs": self.outputs,
            "failure_reason": self.failure_reason,
            "retry_count": self.retry_count,
            "audit_log": self.audit_log,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Task":
        return cls(**data)

    def touch(self):
        self.updated_at = datetime.now().isoformat()

    def add_reference(self):
        self.reference_count += 1
        self.last_referenced_at = datetime.now().isoformat()
        self.touch()

    def add_evidence(self, evidence: str, source: str = ""):
        self.evidence.append({
            "content": evidence,
            "source": source,
            "added_at": datetime.now().isoformat(),
        })
        self.touch()

    def add_counter_example(self, example: str, source: str = ""):
        self.counter_examples.append({
            "content": example,
            "source": source,
            "added_at": datetime.now().isoformat(),
        })
        self.touch()

    def add_research_note(self, note: str, researcher: str = "researcher"):
        self.research_notes.append({
            "content": note,
            "researcher": researcher,
            "added_at": datetime.now().isoformat(),
        })
        self.touch()

    def add_validation_note(self, note: str, validator: str = "validator"):
        self.validation_notes.append({
            "content": note,
            "validator": validator,
            "added_at": datetime.now().isoformat(),
        })
        self.touch()

    def transition_to(self, new_status: str, actor: str = "", reason: str = ""):
        if new_status not in TASK_STATUSES:
            raise ValueError(f"无效状态: {new_status}")
        old_status = self.status
        self.status = new_status
        if old_status != new_status:
            self.audit_log.append({
                "event": "transition",
                "from": old_status,
                "to": new_status,
                "actor": actor,
                "reason": reason,
                "at": datetime.now().isoformat(),
            })
            self.touch()
        return old_status, new_status

    def age_days(self) -> int:
        created = datetime.fromisoformat(self.created_at.replace("Z", ""))
        return (datetime.now() - created).days

    def days_since_reference(self) -> int:
        last = datetime.fromisoformat(self.last_referenced_at.replace("Z", ""))
        return (datetime.now() - last).days


class TaskPool:
    """
    任务池 — 所有任务的家

    目录结构：
    task_pool/
        pending/     待领取
        active/      研究中
        review/      待验证
        approved/    已通过
        archived/    已归档
        rejected/    已拒绝
        graveyard/   无人问津（30天+）
    """

    def __init__(self, pool_dir: str):
        self.pool_dir = Path(pool_dir)
        self._ensure_dirs()

    def _ensure_dirs(self):
        for status in TASK_STATUSES:
            (self.pool_dir / STATUS_DIRS[status]).mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: str, status: str) -> Path:
        return self.pool_dir / STATUS_DIRS[status] / f"{task_id}.json"

    def _find_task_file(self, task_id: str) -> Optional[Path]:
        for status in TASK_STATUSES:
            path = self._task_path(task_id, status)
            if path.exists():
                return path
        return None

    def create_task(
        self,
        title: str,
        hypothesis: str = "",
        creator: str = "observer",
        priority: str = "medium",
        tags: Optional[List[str]] = None,
        depends_on: Optional[List[str]] = None,
        parent_task: str = "",
    ) -> Task:
        today = datetime.now().strftime("%Y%m%d")
        existing = self.list_tasks(status="pending") + self.list_tasks(status="active")
        today_count = sum(1 for t in existing if t.task_id.startswith(f"RQ-{today}"))
        task_id = f"RQ-{today}-{today_count + 1:03d}"

        task = Task(
            task_id=task_id,
            title=title,
            creator=creator,
            status="pending",
            priority=priority,
            hypothesis=hypothesis,
            tags=tags or [],
            depends_on=depends_on or [],
            parent_task=parent_task,
        )
        self._save_task(task)
        return task

    def _save_task(self, task: Task):
        task.touch()
        path = self._task_path(task.task_id, task.status)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(task.to_dict(), f, ensure_ascii=False, indent=2)

    def load_task(self, task_id: str) -> Optional[Task]:
        path = self._find_task_file(task_id)
        if not path:
            return None
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Task.from_dict(data)

    def update_task(self, task: Task) -> bool:
        existing_path = self._find_task_file(task.task_id)
        if not existing_path:
            self._save_task(task)
            return True

        old_status = Path(existing_path).parent.name
        if old_status != STATUS_DIRS.get(task.status, task.status):
            existing_path.unlink()

        self._save_task(task)
        return True

    def list_tasks(
        self,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100,
        sort_by: str = "priority",
    ) -> List[Task]:
        tasks = []

        statuses = [status] if status else TASK_STATUSES

        for s in statuses:
            dir_path = self.pool_dir / STATUS_DIRS.get(s, s)
            if not dir_path.exists():
                continue
            for fpath in dir_path.glob("RQ-*.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    task = Task.from_dict(data)
                    if priority and task.priority != priority:
                        continue
                    tasks.append(task)
                except Exception:
                    pass

        if sort_by == "priority":
            tasks.sort(key=lambda t: (PRIORITY_ORDER.get(t.priority, 99), t.created_at))
        elif sort_by == "created":
            tasks.sort(key=lambda t: t.created_at, reverse=True)
        elif sort_by == "reference_count":
            tasks.sort(key=lambda t: t.reference_count, reverse=True)

        return tasks[:limit]

    def move_task(self, task_id: str, new_status: str, actor: str = "", reason: str = "", task: Optional[Task] = None) -> Optional[Task]:
        """移动任务到新状态。优先使用传入的 task 对象避免从磁盘重复加载覆盖内存修改"""
        if task is None:
            task = self.load_task(task_id)
            if not task:
                return None
        else:
            task = task

        old_path = self._find_task_file(task_id)
        if old_path:
            old_path.unlink()

        current_status = task.status
        if current_status != new_status:
            task.audit_log.append({
                "event": "transition",
                "from": current_status,
                "to": new_status,
                "actor": actor,
                "reason": reason,
                "at": datetime.now().isoformat(),
            })
        task.status = new_status
        task.updated_at = datetime.now().isoformat()

        self._save_task(task)
        return task

    def block_task(self, task_id: str, reason: str, actor: str = "") -> Optional[Task]:
        task = self.load_task(task_id)
        if not task:
            return None
        task.blocked_reason = reason
        task.assignee = None
        self.move_task(task_id, "blocked", actor=actor, reason=reason)
        return task

    def unblock_task(self, task_id: str, actor: str = "") -> Optional[Task]:
        task = self.load_task(task_id)
        if not task:
            return None
        task.blocked_reason = ""
        self.move_task(task_id, "pending", actor=actor, reason="解除阻塞")
        return task

    def fail_task(self, task_id: str, reason: str, actor: str = "") -> Optional[Task]:
        task = self.load_task(task_id)
        if not task:
            return None
        task.failure_reason = reason
        task.retry_count += 1
        task.touch()
        if task.retry_count >= 3:
            self.move_task(task_id, "graveyard", actor=actor, reason=f"重试{ task.retry_count}次失败: {reason}")
        else:
            self.move_task(task_id, "pending", actor=actor, reason=f"失败重试({task.retry_count}/3): {reason}")
        return task

    def check_depends_satisfied(self, task: Task) -> bool:
        """检查任务依赖是否全部完成（approved/archived）"""
        if not task.depends_on:
            return True
        for dep_id in task.depends_on:
            dep_task = self.load_task(dep_id)
            if not dep_task:
                return False
            if dep_task.status not in ("approved", "archived"):
                return False
        return True

    def get_blocked(self) -> List[Task]:
        return self.list_tasks(status="blocked", limit=100)

    def get_stats(self) -> Dict[str, Any]:
        stats = {s: 0 for s in TASK_STATUSES}
        by_priority = defaultdict(int)

        for status in TASK_STATUSES:
            dir_path = self.pool_dir / STATUS_DIRS[status]
            if not dir_path.exists():
                continue
            count = len(list(dir_path.glob("RQ-*.json")))
            stats[status] = count

            for fpath in dir_path.glob("RQ-*.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    pri = data.get("priority", "medium")
                    by_priority[pri] += 1
                except Exception:
                    pass

        total = sum(stats.values())
        return {
            "total": total,
            "by_status": stats,
            "by_priority": dict(by_priority),
        }

    def check_heat_upgrade(self, task: Task) -> bool:
        """连续被引用>=3次，自动升级优先级"""
        if task.reference_count >= 3 and task.priority == "low":
            task.priority = "medium"
            self.update_task(task)
            return True
        if task.reference_count >= 5 and task.priority == "medium":
            task.priority = "high"
            self.update_task(task)
            return True
        if task.reference_count >= 8 and task.priority == "high":
            task.priority = "critical"
            self.update_task(task)
            return True
        return False

    def check_graveyard(self) -> List[Task]:
        """超过30天无人引用的任务移入墓地"""
        moved = []
        for status in ["pending", "active", "blocked", "review", "archived"]:
            tasks = self.list_tasks(status=status, limit=500)
            for task in tasks:
                if task.days_since_reference() >= 30 and status != "graveyard":
                    self.move_task(task.task_id, "graveyard", reason="30天无人引用")
                    moved.append(task)
        return moved

    def generate_daily_report(self) -> str:
        """生成每日任务状态报告"""
        stats = self.get_stats()
        today = datetime.now().strftime("%Y-%m-%d")

        lines = [
            f"# 任务池每日报告 — {today}",
            "",
            f"**任务总数**: {stats['total']}",
            "",
            "## 状态分布",
            "",
        ]

        status_labels = {
            "pending": "待领取",
            "active": "研究中",
            "blocked": "被阻塞",
            "review": "待验证",
            "approved": "已通过",
            "archived": "已归档",
            "rejected": "已拒绝",
            "graveyard": "墓地",
        }

        for status, label in status_labels.items():
            count = stats["by_status"].get(status, 0)
            lines.append(f"- **{label}**: {count}")

        lines.extend(["", "## 优先级分布", ""])
        for pri in ["critical", "high", "medium", "low"]:
            count = stats["by_priority"].get(pri, 0)
            if count > 0:
                pri_label = {"critical": "紧急", "high": "高", "medium": "中", "low": "低"}[pri]
                lines.append(f"- **{pri_label}**: {count}")

        lines.extend(["", "## 高优先级待领取", ""])
        pending_high = self.list_tasks(status="pending", priority="high", limit=5)
        pending_high += self.list_tasks(status="pending", priority="critical", limit=5)
        for task in pending_high[:5]:
            lines.append(f"- [{task.task_id}] {task.title} ({task.priority})")

        if not pending_high:
            lines.append("_无_")

        lines.extend(["", "## 研究中任务", ""])
        active_tasks = self.list_tasks(status="active", limit=10)
        for task in active_tasks:
            assignee = task.assignee or "未分配"
            lines.append(f"- [{task.task_id}] {task.title} → {assignee}")

        if not active_tasks:
            lines.append("_无_")

        lines.extend(["", "## 最近完成", ""])
        approved_tasks = self.list_tasks(status="approved", limit=5, sort_by="created")
        for task in approved_tasks:
            lines.append(f"- [{task.task_id}] {task.title}")

        if not approved_tasks:
            lines.append("_无_")

        lines.extend(["", "---"])
        lines.append(f"_自动生成于 {datetime.now().isoformat()}_")

        return "\n".join(lines)
