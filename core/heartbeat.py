"""
心跳模块（Heartbeat）

系统活着的第一个证据：它能持续跳动。

心跳不是装饰。
心跳是系统对自己说"我还在"的方式。
心跳中断 = 系统死亡。

设计原则：
- 简单：只记录心跳时间和存活状态，不做复杂计算
- 可靠：即使其他模块挂了，心跳也要能跳
- 可观测：能从外部检查系统是否还活着
"""

import json
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional


class Heartbeat:
    """
    系统心跳 — 最简单的存活证明

    用法：
        hb = Heartbeat(data_dir)
        hb.beat()  # 跳一下
        hb.is_alive()  # 检查是否还活着
        hb.get_status()  # 获取完整状态
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.heartbeat_file = self.data_dir / "heartbeat.json"
        self.status = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.heartbeat_file.exists():
            try:
                with open(self.heartbeat_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "born_at": datetime.now().isoformat(),
            "last_beat": None,
            "beat_count": 0,
            "status": "born",
            "consecutive_misses": 0,
            "total_uptime_seconds": 0,
            "last_start": None,
            "death_count": 0,
            "last_death_reason": None,
        }

    def _save(self):
        with open(self.heartbeat_file, "w", encoding="utf-8") as f:
            json.dump(self.status, f, ensure_ascii=False, indent=2)

    def beat(self, reason: str = "regular") -> Dict[str, Any]:
        """
        跳一下。

        每次心跳记录：
        - 什么时候跳的
        - 为什么跳（regular / recovery / startup / manual）
        - 累计跳了多少次
        """
        now = datetime.now()
        now_iso = now.isoformat()

        if self.status.get("last_start") is None:
            self.status["last_start"] = now_iso

        self.status["last_beat"] = now_iso
        self.status["beat_count"] = self.status.get("beat_count", 0) + 1
        self.status["consecutive_misses"] = 0
        self.status["status"] = "alive"
        self.status["last_beat_reason"] = reason

        if reason == "startup":
            self.status["last_start"] = now_iso
        elif reason == "recovery":
            self.status["status"] = "recovered"

        self._save()
        return self.status

    def is_alive(self, max_idle_seconds: int = 3600) -> bool:
        """
        检查系统是否还活着。

        默认1小时（3600秒）内有心跳就算活着。
        为什么是1小时？
        - 太短了，容易误判（比如系统在忙大任务）
        - 太长了，真死了发现不了
        - 1小时是一个合理的平衡
        """
        last_beat = self.status.get("last_beat")
        if not last_beat:
            return False

        try:
            last = datetime.fromisoformat(last_beat)
            elapsed = (datetime.now() - last).total_seconds()
            return elapsed <= max_idle_seconds
        except Exception:
            return False

    def mark_dead(self, reason: str = "unknown"):
        """
        标记系统死亡。

        不是真的杀死系统，是记录"这次死亡"。
        活着的系统会自己恢复，death_count会增加——
        死亡次数越多，说明系统越脆弱。
        """
        self.status["status"] = "dead"
        self.status["death_count"] = self.status.get("death_count", 0) + 1
        self.status["last_death_reason"] = reason
        self.status["last_death_at"] = datetime.now().isoformat()

        last_start = self.status.get("last_start")
        if last_start:
            try:
                start = datetime.fromisoformat(last_start)
                uptime = (datetime.now() - start).total_seconds()
                self.status["total_uptime_seconds"] = (
                    self.status.get("total_uptime_seconds", 0) + uptime
                )
            except Exception:
                pass

        self._save()

    def record_miss(self) -> int:
        """记录一次心跳缺失。返回连续缺失次数。"""
        self.status["consecutive_misses"] = self.status.get("consecutive_misses", 0) + 1
        self._save()
        return self.status["consecutive_misses"]

    def get_status(self) -> Dict[str, Any]:
        """获取完整心跳状态。"""
        status = dict(self.status)

        last_beat = status.get("last_beat")
        if last_beat:
            try:
                last = datetime.fromisoformat(last_beat)
                status["seconds_since_last_beat"] = int(
                    (datetime.now() - last).total_seconds()
                )
            except Exception:
                status["seconds_since_last_beat"] = None
        else:
            status["seconds_since_last_beat"] = None

        last_start = status.get("last_start")
        if last_start:
            try:
                start = datetime.fromisoformat(last_start)
                status["current_uptime_seconds"] = int(
                    (datetime.now() - start).total_seconds()
                )
            except Exception:
                status["current_uptime_seconds"] = None
        else:
            status["current_uptime_seconds"] = None

        status["is_alive"] = self.is_alive()

        return status

    def get_uptime_string(self) -> str:
        """可读的存活时长。"""
        uptime = self.get_status().get("current_uptime_seconds", 0) or 0
        hours = uptime // 3600
        minutes = (uptime % 3600) // 60
        seconds = uptime % 60
        return f"{hours}h {minutes}m {seconds}s"
