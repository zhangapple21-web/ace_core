"""
事件总线（Event Bus）

用文件系统实现。为什么不用消息队列？
因为考古发现：笨的东西活得久。
文件系统 = 所有平台都有、可读、可追溯、不会崩。

每个事件是一个JSON文件，命名格式：
  {timestamp}_{event_type}_{id}.json

事件生命周期：
  OBS（观察）→ RFC（提案）→ TASK（任务）→ CONST（约束）
  或者
  OBS → 废弃

append-only：事件只追加，不删除。
"""

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from .identity import Identity


class EventBus:
    """文件系统事件总线"""

    VALID_TYPES = ["OBS", "RFC", "TASK", "CONST"]

    def __init__(self, events_dir: Path, identity: Identity):
        self.events_dir = events_dir
        self.identity = identity
        self.events_dir.mkdir(parents=True, exist_ok=True)

    def emit(
        self,
        event_type: str,
        title: str,
        content: str,
        source: str = "system",
        metadata: Optional[Dict[str, Any]] = None,
        parent_id: Optional[str] = None,
    ) -> str:
        """
        发射一个事件。
        返回事件ID。
        """
        if event_type not in self.VALID_TYPES:
            raise ValueError(f"无效事件类型: {event_type}，有效类型: {self.VALID_TYPES}")

        event_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        event = {
            "id": event_id,
            "type": event_type,
            "title": title,
            "content": content,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "status": "new",
            "parent_id": parent_id,
            "metadata": metadata or {},
            "continuity": self.identity.continuity_mark(),
        }

        filename = f"{timestamp}_{event_type}_{event_id}.json"
        filepath = self.events_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(event, f, ensure_ascii=False, indent=2)

        return event_id

    def get_event(self, event_id: str) -> Optional[Dict[str, Any]]:
        """根据ID获取事件"""
        for f in self.events_dir.glob(f"*_{event_id}.json"):
            with open(f, "r", encoding="utf-8") as fp:
                return json.load(fp)
        return None

    def list_events(
        self,
        event_type: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """列出事件，按时间倒序"""
        events = []
        files = sorted(self.events_dir.glob("*.json"), reverse=True)

        for f in files[:limit]:
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    event = json.load(fp)
                if event_type and event.get("type") != event_type:
                    continue
                if status and event.get("status") != status:
                    continue
                events.append(event)
            except Exception:
                continue

        return events

    def update_status(self, event_id: str, status: str, note: str = ""):
        """更新事件状态"""
        for f in self.events_dir.glob(f"*_{event_id}.json"):
            with open(f, "r", encoding="utf-8") as fp:
                event = json.load(fp)

            event["status"] = status
            if note:
                event["status_note"] = note
            event["updated_at"] = datetime.now().isoformat()

            with open(f, "w", encoding="utf-8") as fp:
                json.dump(event, fp, ensure_ascii=False, indent=2)
            return

    def get_chain(self, event_id: str) -> List[Dict[str, Any]]:
        """获取事件的完整链路（从祖先到当前）"""
        chain = []
        current_id = event_id

        visited = set()
        while current_id and current_id not in visited:
            visited.add(current_id)
            event = self.get_event(current_id)
            if not event:
                break
            chain.insert(0, event)
            current_id = event.get("parent_id")

        return chain
