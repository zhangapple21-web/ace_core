"""
AsyncAuditLogger — 异步审计日志写入

设计原则：
  - 队列缓冲，不阻塞主循环
  - 队列大小限制 10000 条，超过时丢弃并告警
  - 后台线程批量写入
  - 支持多种输出目标（文件、内存等）

（结构资产：日志写入模式比具体写入什么更重要。）
"""

import json
import time
import queue
import threading
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class AsyncAuditLogger:
    """
    异步审计日志写入器

    使用队列 + 后台线程，避免阻塞主循环。
    """

    def __init__(
        self,
        log_dir: str = "",
        max_queue_size: int = 10000,
        flush_interval: float = 1.0,
        batch_size: int = 100,
    ):
        self.log_dir = Path(log_dir) if log_dir else None
        if self.log_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        self.max_queue_size = max_queue_size
        self.flush_interval = flush_interval
        self.batch_size = batch_size

        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        # 统计
        self._total_logged = 0
        self._total_dropped = 0
        self._total_flushed = 0
        self._drop_alerts = 0

        # 内存中的日志（用于查询）
        self._recent_logs: List[Dict] = []
        self._max_recent = 1000

    def start(self) -> None:
        """启动后台写入线程"""
        if self._running:
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._worker_loop,
            name="async-audit-logger",
            daemon=True,
        )
        self._running = True
        self._thread.start()
        logger.info("[AsyncAuditLogger] 已启动")

    def stop(self) -> None:
        """停止后台写入线程"""
        if not self._running:
            return

        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
        self._running = False
        logger.info("[AsyncAuditLogger] 已停止")

    def log(
        self,
        event_type: str,
        data: Optional[Dict[str, Any]] = None,
        level: str = "info",
    ) -> bool:
        """
        异步写入日志（非阻塞）

        Args:
            event_type: 事件类型
            data: 事件数据
            level: 日志级别

        Returns:
            True = 入队成功，False = 队列满被丢弃
        """
        entry = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "level": level,
            "data": data or {},
        }

        try:
            self._queue.put_nowait(entry)
            self._total_logged += 1
            return True
        except queue.Full:
            self._total_dropped += 1
            self._drop_alerts += 1
            if self._drop_alerts % 100 == 0:  # 每丢弃 100 条告警一次
                logger.warning(
                    f"[AsyncAuditLogger] 队列已满，已丢弃 {self._total_dropped} 条日志"
                )
            return False

    def log_unpack(self, data_hash: str, result: Dict[str, Any]) -> None:
        """记录解包事件"""
        self.log(
            event_type="protocol_unpack",
            data={
                "data_hash": data_hash,
                "success": result.get("success", False),
                "protocol": result.get("protocol", "unknown"),
                "handler": result.get("handler", "unknown"),
                "fallback_level": result.get("fallback_level", 0),
                "cached": result.get("cached", False),
                "raw_size": result.get("raw_size", 0),
            },
        )

    def log_handler_error(self, handler_name: str, error: str) -> None:
        """记录处理器错误"""
        self.log(
            event_type="handler_error",
            data={
                "handler": handler_name,
                "error": error,
            },
            level="error",
        )

    def flush(self) -> None:
        """强制刷新队列"""
        # 给 worker 发信号，让它立刻处理
        # 通过塞入一个特殊的哨兵值实现
        try:
            self._queue.put_nowait(None)  # None 作为立即刷新标记
        except queue.Full:
            pass

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "running": self._running,
            "queue_size": self._queue.qsize(),
            "max_queue_size": self.max_queue_size,
            "total_logged": self._total_logged,
            "total_dropped": self._total_dropped,
            "total_flushed": self._total_flushed,
            "drop_alerts": self._drop_alerts,
            "recent_logs_count": len(self._recent_logs),
        }

    def get_recent_logs(
        self, limit: int = 100, event_type: Optional[str] = None
    ) -> List[Dict]:
        """获取最近的日志"""
        logs = self._recent_logs
        if event_type:
            logs = [l for l in logs if l.get("event_type") == event_type]
        return logs[-limit:]

    def _worker_loop(self) -> None:
        """后台工作线程主循环"""
        while not self._stop_event.is_set():
            try:
                self._flush_batch()
            except Exception as e:
                logger.error(f"[AsyncAuditLogger] 写入异常: {e}")

            # 等待 flush_interval 秒，或被 stop_event 打断
            self._stop_event.wait(self.flush_interval)

        # 退出前刷新剩余日志
        try:
            self._flush_batch()
        except Exception as e:
            logger.error(f"[AsyncAuditLogger] 退出前刷新失败: {e}")

    def _flush_batch(self) -> None:
        """批量写入一批日志"""
        batch = []
        start_time = time.time()

        # 收集一批日志
        while len(batch) < self.batch_size:
            try:
                entry = self._queue.get_nowait()
                if entry is None:  # 哨兵值，触发立即刷新
                    break
                batch.append(entry)
            except queue.Empty:
                break

        if not batch:
            return

        # 写入内存缓存
        self._recent_logs.extend(batch)
        if len(self._recent_logs) > self._max_recent:
            self._recent_logs = self._recent_logs[-self._max_recent:]

        # 写入文件（如果配置了）
        if self.log_dir:
            self._write_to_file(batch)

        self._total_flushed += len(batch)

    def _write_to_file(self, batch: List[Dict]) -> None:
        """写入日志文件（按天切割）"""
        try:
            today = datetime.now().strftime("%Y-%m-%d")
            log_file = self.log_dir / f"audit_{today}.jsonl"

            with open(log_file, "a", encoding="utf-8") as f:
                for entry in batch:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"[AsyncAuditLogger] 写入文件失败: {e}")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False
