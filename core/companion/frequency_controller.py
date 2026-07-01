"""
输出频率控制器 — 有节制地说话，不刷屏。

规则：
- 普通事件最小间隔 10 秒
- 严重异常（alert）不受限
- 空闲状态 60 秒才说一句
- 同类事件合并/去重
"""

from datetime import datetime, timedelta
from typing import Dict, Optional


class FrequencyController:
    """输出频率控制器"""

    def __init__(
        self,
        normal_interval_seconds: int = 10,
        idle_interval_seconds: int = 60,
        alert_interval_seconds: int = 2,
    ):
        self.normal_interval = timedelta(seconds=normal_interval_seconds)
        self.idle_interval = timedelta(seconds=idle_interval_seconds)
        self.alert_interval = timedelta(seconds=alert_interval_seconds)

        self._last_output_time = datetime.now() - timedelta(hours=1)
        self._last_event_by_type: Dict[str, datetime] = {}
        self._idle_mode = False

    def can_output(
        self,
        event_type: str,
        is_alert: bool = False,
        is_idle: bool = False,
    ) -> bool:
        """
        检查是否可以输出。
        - event_type: 事件类型，用于同类去重
        - is_alert: 是否告警级（不受限）
        - is_idle: 是否空闲状态
        """
        now = datetime.now()

        if is_alert:
            last_alert = self._last_event_by_type.get(event_type)
            if last_alert and (now - last_alert) < self.alert_interval:
                return False
            return True

        if is_idle:
            if (now - self._last_output_time) < self.idle_interval:
                return False
            return True

        if (now - self._last_output_time) < self.normal_interval:
            return False

        last_same = self._last_event_by_type.get(event_type)
        if last_same and (now - last_same) < self.normal_interval * 2:
            return False

        return True

    def record_output(self, event_type: str):
        """记录一次输出"""
        now = datetime.now()
        self._last_output_time = now
        self._last_event_by_type[event_type] = now

        if len(self._last_event_by_type) > 50:
            oldest = min(self._last_event_by_type.values())
            keys_to_remove = [
                k for k, v in self._last_event_by_type.items() if v == oldest
            ]
            for k in keys_to_remove[:10]:
                del self._last_event_by_type[k]

    def set_idle_mode(self, idle: bool):
        """设置空闲模式"""
        self._idle_mode = idle

    def time_until_next_allowed(self) -> float:
        """距离下一次允许输出还有多少秒"""
        now = datetime.now()
        elapsed = (now - self._last_output_time).total_seconds()
        remaining = self.normal_interval.total_seconds() - elapsed
        return max(0, remaining)
