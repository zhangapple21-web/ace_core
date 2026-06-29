"""
Time Perception Module（时间感知模块）

核心职责：
- 提供当前时间/日期查询
- 时间概率计算（未来事件的概率）
- 时间上下文注入（对话/任务/报告中自动添加时间戳）
- 时间格式转换（UTC/本地时区/自定义格式）

设计原则：
- 时区感知：默认Asia/Singapore（用户本地时区）
- 概率支持：对未来时间点的事件进行概率评估
- 自动注入：在系统输出中自动添加时间信息
"""

import time
import calendar
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional
from dataclasses import dataclass, field


@dataclass
class TimeContext:
    """时间上下文"""
    timestamp: str
    date: str
    time: str
    weekday: str
    week_number: int
    day: int
    month: str
    year: int
    is_weekend: bool
    is_work_hour: bool
    timezone: str
    utc_offset: str


@dataclass
class TimeProbability:
    """时间概率"""
    event: str
    target_time: str
    probability: float
    confidence: float
    factors: Dict[str, float] = field(default_factory=dict)


class TimePerception:
    """
    时间感知模块

    提供时间查询、时间概率计算、时间上下文注入等能力
    """

    def __init__(self, timezone_str: str = "Asia/Singapore"):
        """
        初始化时间感知模块

        Args:
            timezone_str: 时区字符串，如 "Asia/Singapore", "Asia/Shanghai"
        """
        self.timezone_str = timezone_str
        self._local_tz = self._get_local_timezone()

    def _get_local_timezone(self):
        """获取本地时区对象"""
        try:
            import zoneinfo
            return zoneinfo.ZoneInfo(self.timezone_str)
        except Exception:
            return datetime.now(timezone.utc).astimezone().tzinfo

    def get_current_time(self, format: str = "%Y-%m-%d %H:%M:%S") -> str:
        """
        获取当前时间的字符串表示

        Args:
            format: 时间格式，默认 "%Y-%m-%d %H:%M:%S"

        Returns:
            当前时间字符串
        """
        return datetime.now(self._local_tz).strftime(format)

    def get_current_date(self) -> str:
        """获取当前日期（YYYY-MM-DD）"""
        return datetime.now(self._local_tz).strftime("%Y-%m-%d")

    def get_current_time_human(self) -> str:
        """获取人类可读的当前时间描述"""
        now = datetime.now(self._local_tz)
        
        weekday_map = {
            0: "周一", 1: "周二", 2: "周三",
            3: "周四", 4: "周五", 5: "周六", 6: "周日"
        }
        
        month_map = {
            1: "一月", 2: "二月", 3: "三月", 4: "四月", 5: "五月", 6: "六月",
            7: "七月", 8: "八月", 9: "九月", 10: "十月", 11: "十一月", 12: "十二月"
        }
        
        weekday = weekday_map.get(now.weekday(), "未知")
        month = month_map.get(now.month(), "未知")
        
        return (
            f"{now.year}年{month}{now.day}日 {weekday} "
            f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
        )

    def get_time_context(self) -> TimeContext:
        """
        获取完整的时间上下文

        Returns:
            TimeContext 对象，包含日期、时间、周、月、年等信息
        """
        now = datetime.now(self._local_tz)
        
        weekday_map = {
            0: "周一", 1: "周二", 2: "周三",
            3: "周四", 4: "周五", 5: "周六", 6: "周日"
        }
        
        month_map = {
            1: "一月", 2: "二月", 3: "三月", 4: "四月", 5: "五月", 6: "六月",
            7: "七月", 8: "八月", 9: "九月", 10: "十月", 11: "十一月", 12: "十二月"
        }
        
        # 判断是否工作日
        is_weekend = now.weekday() >= 5
        
        # 判断是否工作时间（9:00-18:00）
        is_work_hour = 9 <= now.hour < 18
        
        # 获取周数
        week_number = now.isocalendar()[1]
        
        # 获取UTC偏移
        utc_offset = now.strftime("%z")
        
        return TimeContext(
            timestamp=now.isoformat(),
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M:%S"),
            weekday=weekday_map.get(now.weekday(), "未知"),
            week_number=week_number,
            day=now.day,
            month=month_map.get(now.month, "未知"),
            year=now.year,
            is_weekend=is_weekend,
            is_work_hour=is_work_hour,
            timezone=self.timezone_str,
            utc_offset=utc_offset,
        )

    def calculate_time_probability(
        self,
        event_description: str,
        target_time: Optional[str] = None,
        duration_minutes: int = 60
    ) -> TimeProbability:
        """
        计算事件发生的时间概率

        Args:
            event_description: 事件描述
            target_time: 目标时间（可选，格式：HH:MM 或 YYYY-MM-DD HH:MM）
            duration_minutes: 事件持续时间（分钟）

        Returns:
            TimeProbability 对象，包含概率和置信度
        """
        now = datetime.now(self._local_tz)
        
        factors = {}
        probability = 0.5
        confidence = 0.3
        
        if target_time:
            try:
                # 解析目标时间
                if len(target_time) <= 5:
                    # 仅时间 HH:MM
                    target = datetime.strptime(target_time, "%H:%M")
                    target_dt = now.replace(
                        hour=target.hour,
                        minute=target.minute,
                        second=0,
                        microsecond=0
                    )
                else:
                    # 完整时间 YYYY-MM-DD HH:MM
                    target_dt = datetime.strptime(target_time, "%Y-%m-%d %H:%M")
                    target_dt = target_dt.replace(tzinfo=self._local_tz)
                
                # 计算时间差
                time_diff = (target_dt - now).total_seconds()
                
                # 时间越近，概率越高
                if abs(time_diff) <= duration_minutes * 60:
                    probability = 0.9
                    confidence = 0.8
                    factors["timing"] = 0.4
                elif time_diff < 0:
                    # 已过时间，概率降低
                    probability = 0.1
                    confidence = 0.5
                    factors["past"] = -0.3
                else:
                    # 未来时间，根据距离调整
                    hours_ahead = time_diff / 3600
                    if hours_ahead < 1:
                        probability = 0.7
                        confidence = 0.6
                        factors["near_future"] = 0.3
                    elif hours_ahead < 4:
                        probability = 0.5
                        confidence = 0.4
                        factors["medium_future"] = 0.2
                    else:
                        probability = 0.2
                        confidence = 0.3
                        factors["distant_future"] = -0.2
                
            except Exception as e:
                factors["parse_error"] = -0.1
        
        # 基于工作日/周末调整
        if now.weekday() >= 5:
            factors["weekend"] = 0.1 if "休息" in event_description else -0.1
            probability += factors["weekend"] * 0.1
        
        # 基于工作时间调整
        if 9 <= now.hour < 18:
            factors["work_hour"] = 0.1 if "工作" in event_description else -0.05
            probability += factors["work_hour"] * 0.05
        
        # 限制概率范围
        probability = max(0.0, min(1.0, probability))
        
        return TimeProbability(
            event=event_description,
            target_time=target_time or now.strftime("%Y-%m-%d %H:%M"),
            probability=probability,
            confidence=confidence,
            factors=factors,
        )

    def format_duration(self, seconds: float) -> str:
        """
        将秒数格式化为人类可读的持续时间

        Args:
            seconds: 秒数

        Returns:
            格式化的持续时间字符串
        """
        if seconds < 60:
            return f"{int(seconds)}秒"
        elif seconds < 3600:
            minutes = int(seconds // 60)
            secs = int(seconds % 60)
            return f"{minutes}分{secs}秒"
        elif seconds < 86400:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            return f"{hours}小时{minutes}分"
        else:
            days = int(seconds // 86400)
            hours = int((seconds % 86400) // 3600)
            return f"{days}天{hours}小时"

    def get_time_until(self, target_time: str) -> str:
        """
        获取距离目标时间还有多久

        Args:
            target_time: 目标时间（格式：HH:MM 或 YYYY-MM-DD HH:MM）

        Returns:
            距离描述字符串
        """
        now = datetime.now(self._local_tz)
        
        try:
            if len(target_time) <= 5:
                target = datetime.strptime(target_time, "%H:%M")
                target_dt = now.replace(
                    hour=target.hour,
                    minute=target.minute,
                    second=0,
                    microsecond=0
                )
                if target_dt <= now:
                    target_dt += timedelta(days=1)
            else:
                target_dt = datetime.strptime(target_time, "%Y-%m-%d %H:%M")
                target_dt = target_dt.replace(tzinfo=self._local_tz)
            
            diff = (target_dt - now).total_seconds()
            
            if diff < 0:
                return "目标时间已过"
            
            return f"还有 {self.format_duration(diff)}"
        
        except Exception as e:
            return f"无法解析目标时间: {e}"

    def get_time_since(self, past_time: str) -> str:
        """
        获取距离过去时间已经过了多久

        Args:
            past_time: 过去时间（格式：YYYY-MM-DD HH:MM 或 ISO格式）

        Returns:
            已过时间描述字符串
        """
        now = datetime.now(self._local_tz)
        
        try:
            # 尝试多种格式
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]:
                try:
                    past_dt = datetime.strptime(past_time, fmt)
                    past_dt = past_dt.replace(tzinfo=self._local_tz)
                    diff = (now - past_dt).total_seconds()
                    return f"已过去 {self.format_duration(diff)}"
                except ValueError:
                    continue
            
            # 尝试ISO格式
            past_dt = datetime.fromisoformat(past_time.replace("Z", "+00:00"))
            diff = (now - past_dt).total_seconds()
            return f"已过去 {self.format_duration(diff)}"
        
        except Exception as e:
            return f"无法解析过去时间: {e}"

    def inject_time_context(self, text: str) -> str:
        """
        在文本中注入时间上下文

        Args:
            text: 原始文本

        Returns:
            带有时间上下文的文本
        """
        ctx = self.get_time_context()
        time_header = f"【当前时间：{ctx.date} {ctx.time} {ctx.weekday}】"
        return f"{time_header}\n\n{text}"

    def get_daily_report_header(self) -> str:
        """获取日报头部（包含完整时间信息）"""
        ctx = self.get_time_context()
        
        return (
            f"📅 {ctx.year}年{ctx.month}{ctx.day}日 {ctx.weekday}\n"
            f"⏰ {ctx.time} (UTC{ctx.utc_offset})\n"
            f"📊 第{ctx.week_number}周 | {'工作时间' if ctx.is_work_hour else '非工作时间'}"
        )


# 全局实例
time_perception = TimePerception("Asia/Singapore")
