"""
任务队列（Task Queue）

事件变成任务后进入队列，等待调度执行。

任务状态：
  pending  →  等待执行
  running  →  正在执行
  done     →  完成
  failed   →  失败
  archived →  已归档

任务和事件的关系：
  事件是"发生了什么"，任务是"要做什么"。
  一个事件可以派生出多个任务。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .identity import Identity


class TaskQueue:
    """文件系统任务队列"""

    STATUSES = ["pending", "running", "done", "failed", "archived"]

    def __init__(self, tasks_dir: Path, identity: Identity):
        self.tasks_dir = tasks_dir
        self.identity = identity
        for status in self.STATUSES:
            (self.tasks_dir / status).mkdir(parents=True, exist_ok=True)

    def create(
        self,
        task_type: str,
        title: str,
        description: str,
        assigned_to: str,
        source_event_id: Optional[str] = None,
        priority: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """创建一个新任务，返回任务ID"""
        task_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        task = {
            "id": task_id,
            "type": task_type,
            "title": title,
            "description": description,
            "assigned_to": assigned_to,
            "priority": priority,
            "status": "pending",
            "source_event_id": source_event_id,
            "created_at": datetime.now().isoformat(),
            "metadata": metadata or {},
            "continuity": self.identity.continuity_mark(),
            "result": None,
        }

        filename = f"{timestamp}_{task_id}.json"
        filepath = self.tasks_dir / "pending" / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(task, f, ensure_ascii=False, indent=2)

        return task_id

    def claim_next(self, worker: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """领取下一个待处理任务。返回任务或None。"""
        pending_dir = self.tasks_dir / "pending"
        files = sorted(pending_dir.glob("*.json"))

        if not files:
            return None

        for filepath in files:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    task = json.load(f)

                if worker and task.get("assigned_to") != worker:
                    continue

                task["status"] = "running"
                task["started_at"] = datetime.now().isoformat()
                task["claimed_by"] = worker or "system"

                running_path = self.tasks_dir / "running" / filepath.name
                with open(running_path, "w", encoding="utf-8") as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)

                filepath.unlink()
                return task

            except Exception:
                continue

        return None

    def complete(self, task_id: str, result: Any = None, status: str = "done"):
        """完成或失败一个任务"""
        if status not in ["done", "failed"]:
            raise ValueError(f"无效完成状态: {status}")

        running_dir = self.tasks_dir / "running"
        for filepath in running_dir.glob(f"*_{task_id}.json"):
            with open(filepath, "r", encoding="utf-8") as f:
                task = json.load(f)

            task["status"] = status
            task["completed_at"] = datetime.now().isoformat()
            task["result"] = result

            target_dir = self.tasks_dir / status
            target_path = target_dir / filepath.name

            with open(target_path, "w", encoding="utf-8") as f:
                json.dump(task, f, ensure_ascii=False, indent=2)

            filepath.unlink()
            return

    def archive(self, task_id: str):
        """归档已完成的任务"""
        for status in ["done", "failed"]:
            dirpath = self.tasks_dir / status
            for filepath in dirpath.glob(f"*_{task_id}.json"):
                with open(filepath, "r", encoding="utf-8") as f:
                    task = json.load(f)

                task["archived_at"] = datetime.now().isoformat()
                target_path = self.tasks_dir / "archived" / filepath.name

                with open(target_path, "w", encoding="utf-8") as f:
                    json.dump(task, f, ensure_ascii=False, indent=2)

                filepath.unlink()
                return

    def list_tasks(self, status: str = "pending", limit: int = 20) -> List[Dict[str, Any]]:
        """列出指定状态的任务"""
        dirpath = self.tasks_dir / status
        if not dirpath.exists():
            return []

        tasks = []
        files = sorted(dirpath.glob("*.json"), reverse=True)

        for filepath in files[:limit]:
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    tasks.append(json.load(f))
            except Exception:
                continue

        return tasks

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取任务"""
        for status in self.STATUSES:
            dirpath = self.tasks_dir / status
            for filepath in dirpath.glob(f"*_{task_id}.json"):
                with open(filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
        return None
