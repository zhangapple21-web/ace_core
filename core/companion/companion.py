"""
ACE Companion 主控制器 — 整合所有模块。

小籽：ACE Runtime 的人格化小伙伴
- 监听事件总线
- 情绪状态机
- 话术生成
- 频率控制
- 桌面浮窗渲染
"""

from pathlib import Path
from typing import Optional, Dict
import sys
import os


class AceCompanion:
    """ACE Companion 主类"""

    def __init__(
        self,
        events_dir: Optional[Path] = None,
        base_dir: Optional[Path] = None,
        enable_subscriber: bool = True,
    ):
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()

        if events_dir:
            self.events_dir = Path(events_dir)
        else:
            self.events_dir = self.base_dir / "06_RUNTIME" / "ace" / "data" / "events"

        self._setup_modules(enable_subscriber)

    def _setup_modules(self, enable_subscriber: bool):
        """初始化所有模块"""
        from .mood_engine import MoodEngine
        from .dialogue import DialogueGenerator
        from .frequency_controller import FrequencyController

        self.mood_engine = MoodEngine(idle_timeout_minutes=5)
        self.dialogue = DialogueGenerator(memory_size=10)
        self.freq_controller = FrequencyController(
            normal_interval_seconds=8,
            idle_interval_seconds=90,
            alert_interval_seconds=3,
        )

        self.subscriber = None
        if enable_subscriber:
            from .event_subscriber import EventSubscriber
            self.subscriber = EventSubscriber(
                events_dir=self.events_dir,
                poll_interval=2.0,
                callback=self._on_event,
            )

        self.desktop_pet = None

    def _on_event(self, event_type: str, metadata: Dict):
        """
        事件回调 — 收到新事件时调用。
        运行在事件监听线程，需要安全地更新UI。
        """
        try:
            mood_state = self.mood_engine.process_event(event_type, metadata)
            mood = mood_state.mood

            is_alert = event_type in ("error", "node:fail", "nas:unreachable")
            is_idle = event_type == "idle:quiet"

            if not self.freq_controller.can_output(event_type, is_alert, is_idle):
                if self.desktop_pet:
                    status = self._event_to_status(event_type)
                    self._safe_update_status(status, mood)
                return

            self.freq_controller.record_output(event_type)

            text = self.dialogue.generate(event_type, metadata, mood)
            status = self._event_to_status(event_type)

            if self.desktop_pet:
                self._safe_say(text, mood, status)

        except Exception as e:
            print(f"[Companion] 处理事件异常: {e}")

    def _event_to_status(self, event_type: str) -> str:
        """把事件类型映射到状态模式"""
        mapping = {
            "loop:observe": "thinking",
            "loop:hypothesis": "thinking",
            "loop:experiment": "experiment",
            "loop:critic": "critic",
            "loop:consensus": "consensus",
            "loop:writeback": "writeback",
            "loop:snapshot": "idle",
            "node:check_ok": "idle",
            "node:timeout": "error",
            "node:fail": "error",
            "node:switch": "experiment",
            "nas:unreachable": "error",
            "api:rate_limit": "error",
            "tg:report_sent": "idle",
            "idle:quiet": "idle",
            "discovery": "excited",
            "breakthrough": "excited",
            "new_concept": "excited",
            "error": "error",
        }
        return mapping.get(event_type, "thinking")

    def _safe_say(self, text: str, mood: str, status: str):
        """线程安全地更新UI（通过after调度到主线程）"""
        if self.desktop_pet:
            try:
                self.desktop_pet.after(0, lambda: self.desktop_pet.say(text, mood, status))
            except Exception:
                pass

    def _safe_update_status(self, status: str, mood: str):
        """线程安全地只更新状态"""
        if self.desktop_pet:
            try:
                self.desktop_pet.after(0, lambda: self.desktop_pet.set_status(status, mood))
            except Exception:
                pass

    def start(self):
        """启动 Companion"""
        from .desktop_pet import DesktopPet

        self.desktop_pet = DesktopPet(
            on_close=self._on_close,
            on_click=self._on_pet_click,
        )

        if self.subscriber:
            self.subscriber.start()

        self._start_idle_checker()
        self._greet()

        try:
            self.desktop_pet.run()
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """停止 Companion"""
        if self.subscriber:
            self.subscriber.stop()
        if self.desktop_pet:
            try:
                self.desktop_pet._on_close()
            except Exception:
                pass

    def _on_close(self):
        """窗口关闭回调"""
        self.stop()

    def _on_pet_click(self):
        """点击宠物回调"""
        pass

    def _greet(self):
        """启动问候"""
        greetings = [
            ("👋 你好呀，我是小籽！", "happy", "idle"),
            ("😊 嗨，今天也要加油哦~", "happy", "idle"),
            ("🌟 小籽报到！有什么发现吗？", "excited", "idle"),
        ]
        import random
        text, mood, status = random.choice(greetings)
        if self.desktop_pet:
            self.desktop_pet.say(text, mood, status)

    def _start_idle_checker(self):
        """启动空闲检查"""
        self._idle_check()

    def _idle_check(self):
        """周期性检查空闲状态"""
        try:
            mood_state = self.mood_engine.tick()
            mood = mood_state.mood

            if mood == "tired":
                if self.freq_controller.can_output("idle:quiet", is_idle=True):
                    text = self.dialogue.generate("idle:quiet", {}, mood)
                    self._safe_say(text, mood, "tired")
                    self.freq_controller.record_output("idle:quiet")
                else:
                    self._safe_update_status("tired", mood)
        except Exception as e:
            print(f"[Companion] 空闲检查异常: {e}")

        if self.desktop_pet:
            self.desktop_pet.after(30000, self._idle_check)

    def emit_event(self, event_type: str, metadata: Optional[Dict] = None):
        """手动发射事件（用于测试）"""
        self._on_event(event_type, metadata or {})


def run_companion():
    """独立运行入口"""
    script_dir = Path(__file__).resolve().parent.parent.parent
    base_dir = script_dir

    companion = AceCompanion(base_dir=base_dir, enable_subscriber=True)
    companion.start()


if __name__ == "__main__":
    run_companion()
