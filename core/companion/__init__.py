"""
ACE Companion - ACE Runtime 的人格化小伙伴

模块：
- mood_engine: 情绪状态机
- dialogue: 话术生成器（带记忆）
- event_subscriber: 事件订阅器（文件系统）
- frequency_controller: 输出频率控制
- desktop_pet: 桌面浮窗渲染层
- companion: 主控制器
"""

from .mood_engine import MoodEngine, MoodState
from .dialogue import DialogueGenerator
from .event_subscriber import EventSubscriber
from .frequency_controller import FrequencyController
from .companion import AceCompanion

__all__ = [
    "MoodEngine",
    "MoodState",
    "DialogueGenerator",
    "EventSubscriber",
    "FrequencyController",
    "AceCompanion",
]
