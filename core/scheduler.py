"""
调度器（Scheduler）

把事件和任务串起来的核心。
负责：
- 从事件总线接收新事件
- 根据事件类型派发给对应的节点
- 管理任务队列
- 记录完整链路

不是"多个Agent抢任务"，而是"一个系统按顺序处理任务"。
因为这是ACE，不是多Agent社会。
"""

import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from .identity import Identity
from .memory import Memory
from .event_bus import EventBus
from .task_queue import TaskQueue
from .lexicon import Lexicon
from .memory_index import MemoryIndex
from .disk_scanner import DiskScanner
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from nodes.observer import ObserverNode
from nodes.researcher import ResearcherNode
from nodes.validator import ValidatorNode
from nodes.archivist import ArchivistNode


class Scheduler:
    """ACE调度器 — 单一身份下的任务流转"""

    def __init__(self, base_dir: Path, config: dict):
        self.base_dir = base_dir
        self.config = config

        self.identity = Identity(base_dir, config)
        self.memory = Memory(base_dir, config, self.identity)

        data_config = config.get("data", {})
        self.event_bus = EventBus(
            base_dir / data_config.get("events_dir", "06_RUNTIME/ace/data/events"),
            self.identity,
        )
        self.task_queue = TaskQueue(
            base_dir / data_config.get("tasks_dir", "06_RUNTIME/ace/data/tasks"),
            self.identity,
        )

        self.lexicon = Lexicon(
            base_dir / data_config.get("memory_cache_dir", "06_RUNTIME/ace/data/memory"),
            self.identity,
        )
        self.memory_index = MemoryIndex(
            base_dir / data_config.get("memory_cache_dir", "06_RUNTIME/ace/data/memory"),
            self.identity,
            self.lexicon,
        )
        self.disk_scanner = DiskScanner(
            self.identity,
            self.lexicon,
            self.memory_index,
        )

        self.observer = ObserverNode(
            self.identity, self.memory, self.event_bus, self.task_queue
        )
        self.researcher = ResearcherNode(
            self.identity, self.memory, self.event_bus, self.task_queue
        )
        self.validator = ValidatorNode(
            self.identity, self.memory, self.event_bus, self.task_queue
        )
        self.archivist = ArchivistNode(
            self.identity, self.memory, self.event_bus, self.task_queue
        )

        self._node_map = {
            "observer": self.observer,
            "researcher": self.researcher,
            "validator": self.validator,
            "archivist": self.archivist,
        }

        self._running = False

    def submit_observation(self, title: str, content: str, source: str = "manual") -> str:
        """
        手动提交一个观察 — 这是系统的入口。
        后面的流转自动发生。
        """
        event_id = self.event_bus.emit(
            event_type="OBS",
            title=title,
            content=content,
            source=source,
        )

        self.task_queue.create(
            task_type="record_observation",
            title=title,
            description=content,
            assigned_to="observer",
            source_event_id=event_id,
            priority=3,
        )

        return event_id

    def process_one(self) -> Optional[Dict[str, Any]]:
        """
        处理一个任务。返回处理结果或None（没有待处理任务）。
        """
        task = self.task_queue.claim_next()
        if not task:
            return None

        assigned_to = task.get("assigned_to", "observer")
        node = self._node_map.get(assigned_to)

        if not node:
            self.task_queue.complete(
                task["id"],
                result={"error": f"未知节点: {assigned_to}"},
                status="failed",
            )
            return {"task_id": task["id"], "status": "failed", "error": f"未知节点: {assigned_to}"}

        try:
            result = node.process(task)
            status = result.get("status", "done")

            self.task_queue.complete(
                task["id"],
                result=result,
                status=status,
            )

            self._auto_chain(task, result)

            return {
                "task_id": task["id"],
                "node": assigned_to,
                "status": status,
                "result": result,
            }

        except Exception as e:
            self.task_queue.complete(
                task["id"],
                result={"error": str(e)},
                status="failed",
            )
            return {
                "task_id": task["id"],
                "node": assigned_to,
                "status": "failed",
                "error": str(e),
            }

    def _auto_chain(self, task: Dict[str, Any], result: Dict[str, Any]):
        """
        自动链路 — 一个节点完成后，自动触发下游节点。
        这是沉淀链的工程实现：OBS → Research → Validate → Archive
        """
        if result.get("status") != "done":
            return

        task_type = task.get("type", "")
        source_event_id = task.get("source_event_id")

        if task_type == "record_observation":
            event_id = result.get("output", {}).get("event_id")
            if event_id:
                self.task_queue.create(
                    task_type="analyze_observation",
                    title=f"分析: {task.get('title', '')}",
                    description=task.get("description", ""),
                    assigned_to="researcher",
                    source_event_id=event_id,
                    priority=3,
                )

        elif task_type == "analyze_observation":
            rfc_id = result.get("output", {}).get("rfc_event_id")
            if rfc_id:
                self.task_queue.create(
                    task_type="validate_rfc",
                    title=f"验证: {task.get('title', '')}",
                    description=task.get("description", ""),
                    assigned_to="validator",
                    source_event_id=rfc_id,
                    priority=3,
                )

        elif task_type == "validate_rfc":
            validation_result = result.get("output", {})
            if validation_result.get("passed"):
                self.task_queue.create(
                    task_type="archive_event",
                    title=f"归档: {task.get('title', '')}",
                    description="验证通过，归档到长期记忆",
                    assigned_to="archivist",
                    source_event_id=task.get("source_event_id"),
                    priority=2,
                )

    def run_once(self) -> List[Dict[str, Any]]:
        """
        运行一轮 — 把所有待处理任务都处理完。
        适合手动触发和测试。
        """
        results = []
        max_iterations = 50
        iterations = 0

        while iterations < max_iterations:
            result = self.process_one()
            if not result:
                break
            results.append(result)
            iterations += 1

        return results

    def start(self, poll_interval: float = 2.0):
        """
        启动持续运行模式 — 轮询任务队列。
        这是"24小时运行"的基础。
        """
        self._running = True
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ACE Runtime 启动")
        print(f"身份: {self.identity.name}")
        print(f"核心原则: {len(self.identity.principles)} 条")
        print(f"轮询间隔: {poll_interval}s")
        print("-" * 50)

        try:
            while self._running:
                result = self.process_one()
                if result:
                    status = result.get("status", "unknown")
                    node = result.get("node", "?")
                    task_id = result.get("task_id", "?")
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] {node}: {status} ({task_id})")
                else:
                    time.sleep(poll_interval)
        except KeyboardInterrupt:
            print("\n收到停止信号，正在关闭...")
        finally:
            self._running = False
            print("ACE Runtime 已停止")

    def stop(self):
        """停止持续运行"""
        self._running = False

    def status(self) -> Dict[str, Any]:
        """获取系统状态"""
        pending = len(self.task_queue.list_tasks("pending", limit=100))
        done = len(self.task_queue.list_tasks("done", limit=100))
        failed = len(self.task_queue.list_tasks("failed", limit=100))
        events = len(self.event_bus.list_events(limit=100))

        return {
            "identity": self.identity.name,
            "version": self.config.get("version", "0.1.0"),
            "events_count": events,
            "tasks": {
                "pending": pending,
                "done": done,
                "failed": failed,
            },
            "memory_files": self.memory.get_index(),
            "lexicon": self.lexicon.get_stats(),
            "memory_index": self.memory_index.get_stats(),
        }
