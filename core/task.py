"""
任务生命周期核心模型

任务不是一张纸。
任务有出生、成长、被挑战、被批准、被遗忘。

统一任务格式 + 状态流转 + 热度/死亡机制。
"""

import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from core.task_admission import duplicate_task, validate_admission
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

ALLOWED_TRANSITIONS = {
    "pending": {"active", "blocked", "rejected", "graveyard"},
    "active": {"pending", "blocked", "review", "rejected", "graveyard"},
    "blocked": {"pending", "rejected", "graveyard"},
    "review": {"pending", "active", "approved", "blocked", "rejected", "graveyard"},
    "approved": {"archived", "rejected"},
    "rejected": {"graveyard"},
    "archived": set(),
    "graveyard": set(),
}


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
        selection_trace: Optional[List] = None,
        recursion_depth: int = 0,
        lease_owner: Optional[str] = None,
        lease_expires_at: Optional[str] = None,
        claim_id: Optional[str] = None,
        fencing_token: int = 0,
        block_type: Optional[str] = None,
        retry_after: Optional[str] = None,
        rework_count: int = 0,
        last_claimed_at: Optional[str] = None,
        unchanged_review_count: int = 0,
        consecutive_rework_claims: int = 0,
        starvation_age: int = 0,
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
        self.selection_trace = selection_trace or []
        self.recursion_depth = recursion_depth
        self.lease_owner = lease_owner or ""
        self.lease_expires_at = lease_expires_at or ""
        self.claim_id = claim_id or ""
        self.fencing_token = fencing_token
        self.block_type = block_type or ""
        self.retry_after = retry_after or ""
        self.rework_count = rework_count
        self.last_claimed_at = last_claimed_at or ""
        self.unchanged_review_count = unchanged_review_count
        self.consecutive_rework_claims = consecutive_rework_claims
        self.starvation_age = starvation_age

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
            "selection_trace": self.selection_trace,
            "recursion_depth": self.recursion_depth,
            "lease_owner": self.lease_owner,
            "lease_expires_at": self.lease_expires_at,
            "claim_id": self.claim_id,
            "fencing_token": self.fencing_token,
            "block_type": self.block_type,
            "retry_after": self.retry_after,
            "rework_count": self.rework_count,
            "last_claimed_at": self.last_claimed_at,
            "unchanged_review_count": self.unchanged_review_count,
            "consecutive_rework_claims": self.consecutive_rework_claims,
            "starvation_age": self.starvation_age,
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

    def record_selection(
        self,
        decision_point: str,
        selected: str,
        alternatives: List[str] = None,
        reason: str = "",
        actor: str = "",
    ):
        self.selection_trace.append({
            "decision_point": decision_point,
            "selected": selected,
            "alternatives": alternatives or [],
            "reason": reason,
            "actor": actor,
            "at": datetime.now().isoformat(),
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
    def __init__(self, pool_dir: str):
        self.pool_dir = Path(pool_dir)
        self.lock_file = self.pool_dir / ".task_pool.lock"
        self._ensure_dirs()
        self.recover_incomplete_transitions()

    def _ensure_dirs(self):
        for status in TASK_STATUSES:
            (self.pool_dir / STATUS_DIRS[status]).mkdir(parents=True, exist_ok=True)

    def _remove_stale_lock(self) -> bool:
        try:
            raw_pid = self.lock_file.read_text(encoding="ascii").strip()
            pid = int(raw_pid)
        except (FileNotFoundError, OSError, UnicodeDecodeError, ValueError):
            try:
                age_seconds = time.time() - self.lock_file.stat().st_mtime
            except FileNotFoundError:
                return True
            if age_seconds < 60:
                return False
        else:
            if os.name == "nt":
                import ctypes

                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if handle:
                    kernel32.CloseHandle(handle)
                    return False
                if ctypes.get_last_error() == 5:
                    return False
            else:
                try:
                    os.kill(pid, 0)
                    return False
                except ProcessLookupError:
                    pass
                except PermissionError:
                    return False
        try:
            self.lock_file.unlink()
            return True
        except FileNotFoundError:
            return True

    @contextmanager
    def _locked(self, timeout_seconds: float = 10.0):
        deadline = time.monotonic() + timeout_seconds
        self.pool_dir.mkdir(parents=True, exist_ok=True)
        descriptor = None
        while descriptor is None:
            try:
                descriptor = os.open(str(self.lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(descriptor, str(os.getpid()).encode("ascii"))
            except FileExistsError:
                if self._remove_stale_lock():
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("TaskPool lock acquisition timed out")
                time.sleep(0.02)
        try:
            yield
        finally:
            os.close(descriptor)
            try:
                self.lock_file.unlink()
            except FileNotFoundError:
                pass

    def _task_path(self, task_id: str, status: str) -> Path:
        return self.pool_dir / STATUS_DIRS[status] / f"{task_id}.json"

    def _task_files(self, task_id: str) -> List[Path]:
        return [self._task_path(task_id, status) for status in TASK_STATUSES if self._task_path(task_id, status).exists()]

    def _find_task_file(self, task_id: str) -> Optional[Path]:
        files = self._task_files(task_id)
        if not files:
            return None
        return max(files, key=lambda path: path.stat().st_mtime)

    def _read_task(self, path: Path) -> Task:
        with open(path, "r", encoding="utf-8") as handle:
            return Task.from_dict(json.load(handle))

    def _write_task_atomic(self, task: Task, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f".json.{uuid.uuid4().hex}.tmp")
        payload = json.dumps(task.to_dict(), ensure_ascii=False, indent=2)
        with open(temporary, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _save_task(self, task: Task):
        task.touch()
        self._write_task_atomic(task, self._task_path(task.task_id, task.status))

    def _clear_lease(self, task: Task):
        task.lease_owner = ""
        task.lease_expires_at = ""
        task.claim_id = ""

    def _transition(self, task: Task, new_status: str, actor: str = "", reason: str = "") -> Task:
        if new_status not in TASK_STATUSES:
            raise ValueError(f"无效状态: {new_status}")
        old_path = self._find_task_file(task.task_id)
        old_status = task.status
        if old_status != new_status:
            task.audit_log.append({
                "event": "transition",
                "from": old_status,
                "to": new_status,
                "actor": actor,
                "reason": reason,
                "at": datetime.now().isoformat(),
            })
        task.status = new_status
        task.touch()
        new_path = self._task_path(task.task_id, new_status)
        self._write_task_atomic(task, new_path)
        for path in self._task_files(task.task_id):
            if path != new_path:
                try:
                    path.unlink()
                except FileNotFoundError:
                    pass
        return task

    def recover_incomplete_transitions(self) -> List[str]:
        recovered = []
        for temporary in self.pool_dir.glob("**/*.tmp"):
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass
        task_ids = set()
        for status in TASK_STATUSES:
            task_ids.update(path.stem for path in (self.pool_dir / STATUS_DIRS[status]).glob("RQ-*.json"))
        for task_id in task_ids:
            files = self._task_files(task_id)
            if len(files) <= 1:
                continue
            chosen = self._find_task_file(task_id)
            for path in files:
                if path != chosen:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass
            recovered.append(task_id)
        return recovered

    def create_task(self, title: str, hypothesis: str = "", creator: str = "observer", priority: str = "medium", tags: Optional[List[str]] = None, depends_on: Optional[List[str]] = None, parent_task: str = "", admission: Optional[Dict[str, Any]] = None, outputs: Optional[Dict[str, Any]] = None) -> Task:
        if creator != "test":
            admission = validate_admission(admission)
        with self._locked():
            existing = self.list_tasks(limit=10000, sort_by="created")
            if admission:
                duplicate = duplicate_task(existing, admission)
                if duplicate:
                    return duplicate
            today = datetime.now().strftime("%Y%m%d")
            today_count = sum(1 for task in existing if task.task_id.startswith(f"RQ-{today}"))
            task = Task(
                task_id=f"RQ-{today}-{today_count + 1:03d}", title=title, creator=creator,
                status="pending", priority=priority, hypothesis=hypothesis, tags=tags or [],
                depends_on=depends_on or [], parent_task=parent_task,
                outputs={**(outputs or {}), **({"admission": admission} if admission else {})},
            )
            self._save_task(task)
            return task

    def load_task(self, task_id: str) -> Optional[Task]:
        path = self._find_task_file(task_id)
        return self._read_task(path) if path else None

    def update_task(self, task: Task) -> bool:
        with self._locked():
            stored = self.load_task(task.task_id)
            if not stored:
                return False
            if task.claim_id and (
                task.claim_id != stored.claim_id
                or task.fencing_token != stored.fencing_token
            ):
                return False
            self._transition(task, task.status)
            return True

    def list_tasks(self, status: Optional[str] = None, priority: Optional[str] = None, limit: int = 100, sort_by: str = "priority") -> List[Task]:
        tasks = []
        seen = set()
        for current_status in ([status] if status else TASK_STATUSES):
            directory = self.pool_dir / STATUS_DIRS.get(current_status, current_status)
            for path in directory.glob("RQ-*.json") if directory.exists() else []:
                if path.stem in seen:
                    continue
                try:
                    task = self._read_task(path)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if priority and task.priority != priority:
                    continue
                seen.add(task.task_id)
                tasks.append(task)
        if sort_by == "priority":
            tasks.sort(key=lambda task: (PRIORITY_ORDER.get(task.priority, 99), task.created_at))
        elif sort_by == "created":
            tasks.sort(key=lambda task: task.created_at, reverse=True)
        elif sort_by == "reference_count":
            tasks.sort(key=lambda task: task.reference_count, reverse=True)
        return tasks[:limit]

    def move_task(self, task_id: str, new_status: str, actor: str = "", reason: str = "", task: Optional[Task] = None, claim_id: str = "") -> Optional[Task]:
        with self._locked():
            stored = self.load_task(task_id)
            if not stored:
                return None
            task = task or stored
            expected_claim = claim_id or task.claim_id
            if expected_claim and (
                expected_claim != stored.claim_id
                or task.fencing_token != stored.fencing_token
            ):
                return None
            if new_status != stored.status and new_status not in ALLOWED_TRANSITIONS[stored.status]:
                return None
            if new_status != "active":
                self._clear_lease(task)
            return self._transition(task, new_status, actor, reason)

    def claim_task(self, task_id: str, owner: str, lease_seconds: int = 300) -> Optional[Task]:
        with self._locked():
            task = self.load_task(task_id)
            if not task or task.status not in ("pending", "active"):
                return None
            now = datetime.now()
            if task.status == "pending" and task.retry_after:
                try:
                    if datetime.fromisoformat(task.retry_after) > now:
                        return None
                except ValueError:
                    return None
            if task.status == "active" and task.lease_expires_at:
                try:
                    if datetime.fromisoformat(task.lease_expires_at) > now:
                        return None
                except ValueError:
                    return None
            task.assignee = owner
            task.lease_owner = owner
            task.claim_id = uuid.uuid4().hex
            task.fencing_token += 1
            task.last_claimed_at = now.isoformat()
            if task.outputs.get("last_validator_result", {}).get("outcome") == "rework_pending":
                task.consecutive_rework_claims += 1
            else:
                task.consecutive_rework_claims = 0
            task.lease_expires_at = (now + timedelta(seconds=lease_seconds)).isoformat()
            return self._transition(task, "active", owner, "lease_claimed")

    def renew_lease(self, task_id: str, owner: str, claim_id: str, lease_seconds: int = 300) -> Optional[Task]:
        with self._locked():
            task = self.load_task(task_id)
            if not task or task.status != "active" or task.lease_owner != owner or task.claim_id != claim_id:
                return None
            task.lease_expires_at = (datetime.now() + timedelta(seconds=lease_seconds)).isoformat()
            task.audit_log.append({
                "event": "lease_renewed",
                "actor": owner,
                "at": datetime.now().isoformat(),
            })
            self._transition(task, "active", owner, "lease_renewed")
            return task

    def reclaim_stale_leases(self, now: Optional[Any] = None) -> List[Task]:
        reference = datetime.fromisoformat(now) if isinstance(now, str) else now or datetime.now()
        reclaimed = []
        with self._locked():
            for task in self.list_tasks(status="active", limit=10000):
                if not task.lease_expires_at:
                    self._clear_lease(task)
                    task.assignee = None
                    self._transition(task, "pending", "recovery", "orphaned_active_recovered")
                    reclaimed.append(task)
                    continue
                try:
                    expired = datetime.fromisoformat(task.lease_expires_at) <= reference
                except ValueError:
                    expired = True
                if not expired:
                    continue
                self._clear_lease(task)
                task.assignee = None
                self._transition(task, "pending", "recovery", "stale_lease_reclaimed")
                reclaimed.append(task)
        return reclaimed

    def block_task(self, task_id: str, reason: str, actor: str = "", block_type: str = "dependency_blocked") -> Optional[Task]:
        if block_type not in ("dependency_blocked", "external_condition_blocked", "manual_gate_blocked"):
            raise ValueError(f"无效阻塞类型: {block_type}")
        with self._locked():
            task = self.load_task(task_id)
            if not task:
                return None
            task.blocked_reason = reason
            task.block_type = block_type
            task.assignee = None
            self._clear_lease(task)
            return self._transition(task, "blocked", actor, reason)

    def unblock_task(self, task_id: str, actor: str = "") -> Optional[Task]:
        with self._locked():
            task = self.load_task(task_id)
            if not task or task.status != "blocked" or task.outputs.get("terminal_non_convergent"):
                return None
            task.blocked_reason = ""
            task.block_type = ""
            return self._transition(task, "pending", actor, "解除阻塞")

    def unblock_ready_dependencies(self) -> List[Task]:
        unblocked = []
        for task in self.get_blocked():
            if task.block_type == "dependency_blocked" and self.check_depends_satisfied(task):
                recovered = self.unblock_task(task.task_id, actor="dependency_recovery")
                if recovered:
                    unblocked.append(recovered)
        return unblocked

    def fail_task(self, task_id: str, reason: str, actor: str = "", failure_type: str = "retryable") -> Optional[Task]:
        with self._locked():
            task = self.load_task(task_id)
            if not task:
                return None
            task.failure_reason = reason
            task.retry_count += 1
            self._clear_lease(task)
            task.assignee = None
            if failure_type == "manual_gate":
                task.blocked_reason = reason
                task.block_type = "manual_gate_blocked"
                return self._transition(task, "blocked", actor, reason)
            if failure_type == "external_condition":
                task.blocked_reason = reason
                task.block_type = "external_condition_blocked"
                return self._transition(task, "blocked", actor, reason)
            if failure_type == "permanent" or task.retry_count >= 3:
                return self._transition(task, "graveyard", actor, reason)
            delay = min(300, 2 ** task.retry_count)
            task.retry_after = (datetime.now() + timedelta(seconds=delay)).isoformat()
            return self._transition(task, "pending", actor, f"retry_{task.retry_count}: {reason}")

    def check_depends_satisfied(self, task: Task) -> bool:
        for dependency_id in task.depends_on:
            dependency = self.load_task(dependency_id)
            if not dependency or dependency.status not in ("approved", "archived"):
                return False
        return True

    def get_blocked(self) -> List[Task]:
        return self.list_tasks(status="blocked", limit=10000)

    def get_stats(self) -> Dict[str, Any]:
        stats = {status: 0 for status in TASK_STATUSES}
        by_priority = defaultdict(int)
        for task in self.list_tasks(limit=100000):
            stats[task.status] += 1
            by_priority[task.priority] += 1
        return {"total": sum(stats.values()), "by_status": stats, "by_priority": dict(by_priority)}
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
        now = datetime.now()
        for status in ["pending", "active", "review", "rejected"]:
            tasks = self.list_tasks(status=status, limit=500)
            for task in tasks:
                if status == "active" and task.lease_expires_at:
                    try:
                        if datetime.fromisoformat(task.lease_expires_at) > now:
                            continue
                    except ValueError:
                        pass
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
