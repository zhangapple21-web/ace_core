"""
事件订阅模块 — 监听文件系统事件总线。

事件总线用文件系统实现（笨但稳），所以这里采用轮询方式监听新文件。
不依赖 watchdog 等第三方库，减少依赖。

事件映射：把文件系统的 OBS/TASK/RFC/CONST 事件，
翻译成 Companion 能理解的语义化事件（loop:observe 等）。
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Callable, Dict, List, Optional, Set
from threading import Thread, Event
import time


class EventSubscriber:
    """文件系统事件订阅器"""

    def __init__(
        self,
        events_dir: Path,
        poll_interval: float = 2.0,
        callback: Optional[Callable[[str, Dict], None]] = None,
    ):
        self.events_dir = Path(events_dir)
        self.poll_interval = poll_interval
        self.callback = callback
        self._stop_event = Event()
        self._thread: Optional[Thread] = None
        self._seen_files: Set[str] = set()
        self._last_check_time = datetime.now()

    def start(self):
        """启动监听线程"""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """停止监听"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)

    def _poll_loop(self):
        """轮询循环"""
        self._scan_existing()
        while not self._stop_event.is_set():
            try:
                self._check_new_events()
            except Exception as e:
                print(f"[Companion] 事件监听异常: {e}")
            self._stop_event.wait(self.poll_interval)

    def _scan_existing(self):
        """扫描已有文件，避免启动时全部重放"""
        if not self.events_dir.exists():
            return
        for f in self.events_dir.glob("*.json"):
            self._seen_files.add(f.name)

    def _check_new_events(self):
        """检查新事件"""
        if not self.events_dir.exists():
            return

        now = datetime.now()
        new_files = []

        for f in sorted(self.events_dir.glob("*.json")):
            if f.name not in self._seen_files:
                new_files.append(f)
                self._seen_files.add(f.name)

        if len(self._seen_files) > 1000:
            self._seen_files = set(list(self._seen_files)[-500:])

        for f in new_files:
            try:
                event = self._read_event(f)
                if event:
                    self._dispatch_event(event)
            except Exception as e:
                print(f"[Companion] 解析事件失败 {f.name}: {e}")

        self._last_check_time = now

    def _read_event(self, filepath: Path) -> Optional[Dict]:
        """读取事件文件"""
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def _dispatch_event(self, event: Dict):
        """
        把原始事件翻译成 Companion 语义事件，然后调用回调。
        
        原始事件类型: OBS / TASK / RFC / CONST
        根据 title / content / metadata 推断具体语义
        """
        event_type = event.get("type", "")
        title = event.get("title", "")
        content = event.get("content", "")
        metadata = event.get("metadata", {})
        source = event.get("source", "")

        semantic_event = self._infer_semantic_event(event_type, title, content, metadata, source)

        if semantic_event and self.callback:
            self.callback(semantic_event, {
                "title": title,
                "content": content,
                "metadata": metadata,
                "source": source,
                "raw_type": event_type,
            })

    def _infer_semantic_event(
        self,
        event_type: str,
        title: str,
        content: str,
        metadata: Dict,
        source: str,
    ) -> Optional[str]:
        """根据事件内容推断语义化事件类型"""
        text = f"{title} {content}".lower()

        if event_type == "OBS":
            if any(kw in text for kw in ["观察", "observe", "扫描", "scan", "发现"]):
                if any(kw in text for kw in ["新结构", "新发现", "突破", "breakthrough"]):
                    return "discovery"
                return "loop:observe"
            if any(kw in text for kw in ["假设", "hypothesis", "猜想"]):
                return "loop:hypothesis"
            return "loop:observe"

        elif event_type == "TASK":
            if any(kw in text for kw in ["实验", "experiment", "验证", "test", "校验"]):
                return "loop:experiment"
            if any(kw in text for kw in ["节点", "node", "超时", "timeout"]):
                return "node:timeout"
            if any(kw in text for kw in ["失败", "fail", "error"]):
                return "error"
            return "loop:experiment"

        elif event_type == "RFC":
            if any(kw in text for kw in ["批评", "critic", "反证", "质疑", "不一致"]):
                return "loop:critic"
            return "loop:critic"

        elif event_type == "CONST":
            if any(kw in text for kw in ["一致", "consensus", "通过", "验证通过"]):
                return "loop:consensus"
            if any(kw in text for kw in ["写入", "归档", "writeback", "保存"]):
                return "loop:writeback"
            if any(kw in text for kw in ["快照", "snapshot"]):
                return "loop:snapshot"
            return "loop:writeback"

        return None

    def emit_manual(self, event_name: str, metadata: Optional[Dict] = None):
        """手动发射一个事件（用于测试/模拟）"""
        if self.callback:
            self.callback(event_name, metadata or {})
