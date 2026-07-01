"""
情绪状态机 — 小籽的心情由运行结果连续累积决定，不是随机变化。

情绪转换规则：
- 连续成功 → 开心 → 兴奋
- 出现不一致/失败 → 怀疑 → 担忧
- 长时间空闲 → 疲惫/摸鱼
- 新发现/突破 → 兴奋
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Dict, Optional


@dataclass
class MoodState:
    """当前情绪状态"""
    mood: str = "neutral"
    emoji: str = "😊"
    since: datetime = field(default_factory=datetime.now)
    consecutive_success: int = 0
    consecutive_fail: int = 0
    last_event_time: datetime = field(default_factory=datetime.now)


class MoodEngine:
    """情绪状态机"""

    MOODS = {
        "neutral":    {"emoji": "😊", "label": "平静"},
        "happy":      {"emoji": "😄", "label": "开心"},
        "excited":    {"emoji": "🤩", "label": "兴奋"},
        "doubt":      {"emoji": "🤨", "label": "怀疑"},
        "worried":    {"emoji": "😟", "label": "担忧"},
        "tired":      {"emoji": "😴", "label": "犯困"},
        "curious":    {"emoji": "🤔", "label": "好奇"},
        "proud":      {"emoji": "😎", "label": "得意"},
        "shocked":    {"emoji": "😱", "label": "震惊"},
    }

    SUCCESS_EVENTS = {
        "loop:consensus", "loop:writeback", "node:check_ok",
        "node:switch", "tg:report_sent", "breakthrough"
    }

    FAIL_EVENTS = {
        "node:timeout", "node:fail", "nas:unreachable",
        "api:rate_limit", "loop:critic"
    }

    EXCITING_EVENTS = {
        "loop:hypothesis", "discovery", "breakthrough",
        "new_structure", "new_concept"
    }

    DOUBT_EVENTS = {
        "loop:critic", "contradiction", "validation_fail"
    }

    def __init__(self, idle_timeout_minutes: int = 10):
        self.state = MoodState()
        self.idle_timeout = timedelta(minutes=idle_timeout_minutes)
        self.history: List[Dict] = []

    def process_event(self, event_type: str, metadata: Optional[Dict] = None) -> MoodState:
        """
        处理事件，更新情绪状态。
        返回更新后的情绪状态。
        """
        metadata = metadata or {}
        now = datetime.now()
        self.state.last_event_time = now

        old_mood = self.state.mood

        if event_type in self.SUCCESS_EVENTS:
            self.state.consecutive_success += 1
            self.state.consecutive_fail = 0

            if self.state.consecutive_success >= 5:
                self._set_mood("proud")
            elif self.state.consecutive_success >= 3:
                self._set_mood("happy")
            else:
                if self.state.mood in ("worried", "doubt"):
                    self._set_mood("neutral")

        elif event_type in self.FAIL_EVENTS:
            self.state.consecutive_fail += 1
            self.state.consecutive_success = 0

            if self.state.consecutive_fail >= 3:
                self._set_mood("worried")
            elif self.state.consecutive_fail >= 1:
                self._set_mood("doubt")

        elif event_type in self.EXCITING_EVENTS:
            self._set_mood("excited")
            self.state.consecutive_success += 1

        elif event_type in self.DOUBT_EVENTS:
            self._set_mood("doubt")

        elif event_type == "loop:observe":
            if self.state.mood in ("tired", "neutral"):
                self._set_mood("curious")

        elif event_type == "loop:experiment":
            self._set_mood("curious")

        elif event_type == "idle:quiet":
            pass

        self.history.append({
            "time": now.isoformat(),
            "event": event_type,
            "old_mood": old_mood,
            "new_mood": self.state.mood,
        })
        if len(self.history) > 100:
            self.history = self.history[-100:]

        return self.state

    def tick(self) -> MoodState:
        """
        时间流逝检查。空闲太久会犯困。
        应该周期性调用。
        """
        now = datetime.now()
        idle_duration = now - self.state.last_event_time

        if idle_duration > self.idle_timeout:
            if self.state.mood != "tired":
                self._set_mood("tired")

        return self.state

    def _set_mood(self, mood: str):
        """设置情绪（只有变化时才更新时间）"""
        if mood != self.state.mood and mood in self.MOODS:
            self.state.mood = mood
            self.state.emoji = self.MOODS[mood]["emoji"]
            self.state.since = datetime.now()

    def get_current(self) -> MoodState:
        """获取当前情绪状态"""
        return self.state

    def get_emoji(self) -> str:
        """获取当前表情符号"""
        return self.state.emoji

    def get_mood_label(self) -> str:
        """获取当前情绪文字描述"""
        return self.MOODS.get(self.state.mood, {}).get("label", "未知")
