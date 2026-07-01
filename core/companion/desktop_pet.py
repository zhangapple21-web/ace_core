"""
桌面浮窗渲染层 — 小籽，一只站在桌面上的科技猫。

特点：
- 真正的桌面宠物形态，可随意拖动
- 大号emoji宠物 + 发光底座，有立体感
- 浮动动画 + 眨眼，活灵活现
- 消息气泡从旁边冒出来
- 状态指示灯显示当前模式
- 右键菜单
- 始终置顶，不抢焦点
- 透明背景，像真的站在桌面上
"""

import tkinter as tk
from tkinter import messagebox
from datetime import datetime
from typing import Optional, Callable, List, Tuple
import math
import random


class DesktopPet:
    """桌面小宠物 — 科技猫小籽"""

    TRANS_COLOR = "magenta"
    PET_EMOJI = "🐱"

    MOOD_EMOJIS = {
        "neutral": "🐱",
        "happy": "😸",
        "excited": "🤩",
        "doubt": "🤨",
        "worried": "😿",
        "tired": "😴",
        "curious": "🤔",
        "proud": "😎",
        "shocked": "🙀",
        "love": "😻",
    }

    STATUS_COLORS = {
        "idle": "#4ade80",
        "thinking": "#60a5fa",
        "experiment": "#fbbf24",
        "critic": "#a78bfa",
        "consensus": "#4ade80",
        "writeback": "#38bdf8",
        "error": "#f87171",
        "excited": "#f472b6",
        "tired": "#94a3b8",
    }

    STATUS_LABELS = {
        "idle": "IDLE",
        "thinking": "THINKING",
        "experiment": "EXPERIMENT",
        "critic": "CRITIC",
        "consensus": "CONSENSUS",
        "writeback": "WRITEBACK",
        "error": "ERROR",
        "excited": "EXCITED",
        "tired": "SLEEPY",
    }

    BUBBLE_BG = "#ffffff"
    BUBBLE_TEXT = "#1e293b"
    BUBBLE_BORDER = "#e2e8f0"

    def __init__(
        self,
        on_close: Optional[Callable] = None,
        on_click: Optional[Callable] = None,
        use_border: bool = False,
    ):
        self.on_close_callback = on_close
        self.on_click_callback = on_click
        self._use_border = use_border

        self.root = tk.Tk()
        self.root.title("🐱 小籽 - ACE Companion")
        self.root.attributes("-topmost", True)

        if not use_border:
            try:
                self.root.overrideredirect(True)
                self._has_border = False
            except Exception:
                self._has_border = True
        else:
            self._has_border = True

        self._has_transparent = False
        if not self._has_border:
            try:
                self.root.attributes("-transparentcolor", self.TRANS_COLOR)
                self._has_transparent = True
            except tk.TclError:
                self._has_transparent = False
                self.root.attributes("-alpha", 0.95)
        else:
            self.root.configure(bg="#f0f4f8")

        self._drag_data = {"x": 0, "y": 0, "dragging": False}
        self._bubble_text = "你好呀~ 我是小籽！"
        self._bubble_visible = True
        self._current_mood = "neutral"
        self._current_status = "idle"
        self._bubble_timer = None
        self._anim_frame = 0
        self._float_offset = 0
        self._pet_emoji = self.MOOD_EMOJIS["neutral"]

        self._setup_ui()
        self._setup_bindings()
        self._setup_menu()

        self._position_window()
        self.root.after(100, self._ensure_visible)
        self._start_animation()

    def _setup_ui(self):
        """设置界面"""
        window_w = 280
        window_h = 180

        bg = self.TRANS_COLOR if self._has_transparent else "#f0f4f8"

        self.canvas = tk.Canvas(
            self.root,
            width=window_w,
            height=window_h,
            bg=bg,
            highlightthickness=0,
            bd=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self._draw_pet()
        self._draw_bubble()

        self.root.geometry(f"{window_w}x{window_h}")

    def _draw_pet(self):
        """绘制宠物 — emoji + 发光底座 + 状态灯"""
        pet_x = 70
        pet_y = 95

        self._pet_items = []

        shadow_y = pet_y + 45
        for i in range(3):
            offset = i * 4
            alpha = 0.15 - i * 0.04
            self.canvas.create_oval(
                pet_x - 25 - offset, shadow_y - 8 - offset,
                pet_x + 25 + offset, shadow_y + 8 + offset,
                fill="",
                outline="#94a3b8",
                width=2,
                tags="pet",
            )

        glow_r = 38
        self._glow = self.canvas.create_oval(
            pet_x - glow_r, pet_y - glow_r,
            pet_x + glow_r, pet_y + glow_r,
            fill="",
            outline="#00d4ff",
            width=2,
            tags="pet",
        )
        self._glow2 = self.canvas.create_oval(
            pet_x - glow_r - 8, pet_y - glow_r - 8,
            pet_x + glow_r + 8, pet_y + glow_r + 8,
            fill="",
            outline="#00d4ff",
            width=1,
            tags="pet",
        )

        self._pet_text = self.canvas.create_text(
            pet_x, pet_y,
            text=self._pet_emoji,
            font=("Segoe UI Emoji", 52),
            tags="pet",
        )

        status_color = self.STATUS_COLORS["idle"]
        self._status_light = self.canvas.create_oval(
            pet_x + 28, pet_y - 35,
            pet_x + 40, pet_y - 23,
            fill=status_color,
            outline="white",
            width=2,
            tags="pet",
        )

        self.canvas.create_text(
            pet_x, pet_y + 58,
            text="小籽",
            fill="#64748b",
            font=("Microsoft YaHei", 9, "bold"),
            tags="pet",
        )

    def _draw_bubble(self):
        """绘制消息气泡"""
        bubble_x = 125
        bubble_y = 15
        bubble_w = 140
        bubble_h = 60

        self._bubble_items = []

        r = 14
        self.canvas.create_rectangle(
            bubble_x + r, bubble_y,
            bubble_x + bubble_w - r, bubble_y + bubble_h,
            fill=self.BUBBLE_BG,
            outline="",
            tags="bubble",
        )
        self.canvas.create_rectangle(
            bubble_x, bubble_y + r,
            bubble_x + bubble_w, bubble_y + bubble_h - r,
            fill=self.BUBBLE_BG,
            outline="",
            tags="bubble",
        )

        corners = [
            (bubble_x, bubble_y),
            (bubble_x + bubble_w - r * 2, bubble_y),
            (bubble_x, bubble_y + bubble_h - r * 2),
            (bubble_x + bubble_w - r * 2, bubble_y + bubble_h - r * 2),
        ]
        for cx, cy in corners:
            self.canvas.create_oval(
                cx, cy,
                cx + r * 2, cy + r * 2,
                fill=self.BUBBLE_BG,
                outline="",
                tags="bubble",
            )

        self.canvas.create_arc(
            bubble_x + r, bubble_y,
            bubble_x + r * 3, bubble_y + r * 2,
            start=90, extent=90,
            style="arc",
            outline=self.BUBBLE_BORDER,
            width=1,
            tags="bubble",
        )
        self.canvas.create_arc(
            bubble_x + bubble_w - r * 3, bubble_y,
            bubble_x + bubble_w - r, bubble_y + r * 2,
            start=0, extent=90,
            style="arc",
            outline=self.BUBBLE_BORDER,
            width=1,
            tags="bubble",
        )
        self.canvas.create_arc(
            bubble_x + r, bubble_y + bubble_h - r * 2,
            bubble_x + r * 3, bubble_y + bubble_h,
            start=180, extent=90,
            style="arc",
            outline=self.BUBBLE_BORDER,
            width=1,
            tags="bubble",
        )
        self.canvas.create_arc(
            bubble_x + bubble_w - r * 3, bubble_y + bubble_h - r * 2,
            bubble_x + bubble_w - r, bubble_y + bubble_h,
            start=270, extent=90,
            style="arc",
            outline=self.BUBBLE_BORDER,
            width=1,
            tags="bubble",
        )
        self.canvas.create_line(
            bubble_x + r, bubble_y,
            bubble_x + bubble_w - r, bubble_y,
            fill=self.BUBBLE_BORDER,
            width=1,
            tags="bubble",
        )
        self.canvas.create_line(
            bubble_x + r, bubble_y + bubble_h,
            bubble_x + bubble_w - r, bubble_y + bubble_h,
            fill=self.BUBBLE_BORDER,
            width=1,
            tags="bubble",
        )
        self.canvas.create_line(
            bubble_x, bubble_y + r,
            bubble_x, bubble_y + bubble_h - r,
            fill=self.BUBBLE_BORDER,
            width=1,
            tags="bubble",
        )
        self.canvas.create_line(
            bubble_x + bubble_w, bubble_y + r,
            bubble_x + bubble_w, bubble_y + bubble_h - r,
            fill=self.BUBBLE_BORDER,
            width=1,
            tags="bubble",
        )

        self.canvas.create_polygon(
            bubble_x - 5, bubble_y + 22,
            bubble_x + 12, bubble_y + 16,
            bubble_x + 12, bubble_y + 32,
            fill=self.BUBBLE_BG,
            outline=self.BUBBLE_BORDER,
            width=1,
            tags="bubble",
        )

        self._bubble_text_id = self.canvas.create_text(
            bubble_x + 12, bubble_y + 10,
            text=self._bubble_text,
            fill=self.BUBBLE_TEXT,
            font=("Microsoft YaHei", 9),
            anchor="nw",
            width=bubble_w - 24,
            tags="bubble",
        )

    def _position_window(self):
        """定位窗口到屏幕右下角"""
        self.root.update_idletasks()
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()

        x = sw - w - 50
        y = sh - h - 120

        x = max(10, min(x, sw - w - 10))
        y = max(10, min(y, sh - h - 50))

        self.root.geometry(f"+{x}+{y}")

    def _ensure_visible(self):
        """确保窗口可见（防止在屏幕外或被最小化）"""
        try:
            self.root.deiconify()
            self.root.lift()

            x = self.root.winfo_x()
            y = self.root.winfo_y()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()

            need_move = False
            if x < 0 or x + w > sw - 10:
                x = sw - w - 50
                need_move = True
            if y < 0 or y + h > sh - 50:
                y = sh - h - 120
                need_move = True

            if need_move:
                x = max(10, min(x, sw - w - 10))
                y = max(10, min(y, sh - h - 50))
                self.root.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def _setup_bindings(self):
        """设置事件绑定"""
        self.canvas.bind("<ButtonPress-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_end)
        self.canvas.bind("<Button-3>", self._show_menu)
        self.canvas.bind("<Double-Button-1>", self._on_double_click)

    def _setup_menu(self):
        """设置右键菜单"""
        self.menu = tk.Menu(
            self.root,
            tearoff=0,
            bg="#ffffff",
            fg="#1e293b",
            activebackground="#f1f5f9",
            activeforeground="#1e293b",
            font=("Microsoft YaHei", 9),
        )
        self.menu.add_command(label="😺 说点什么", command=self._say_random)
        self.menu.add_command(label="🔄 切换心情", command=self._cycle_mood)
        self.menu.add_separator()
        self.menu.add_command(label="💬 隐藏气泡", command=self._toggle_bubble)
        self.menu.add_command(label="📖 关于小籽", command=self._show_about)
        self.menu.add_separator()
        self.menu.add_command(label="👋 退出", command=self._on_close)

    def _on_drag_start(self, event):
        """开始拖动"""
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self._drag_data["dragging"] = True

    def _on_drag_motion(self, event):
        """拖动中"""
        if not self._drag_data["dragging"]:
            return
        x = self.root.winfo_x() + (event.x - self._drag_data["x"])
        y = self.root.winfo_y() + (event.y - self._drag_data["y"])
        self.root.geometry(f"+{x}+{y}")

    def _on_drag_end(self, event):
        """拖动结束"""
        self._drag_data["dragging"] = False

    def _show_menu(self, event):
        """显示右键菜单"""
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def _on_double_click(self, event):
        """双击事件"""
        if self.on_click_callback:
            self.on_click_callback()

    def say(self, text: str, mood: str = "neutral", status: str = "thinking", duration: int = 6000):
        """
        让小籽说一句话。
        - text: 要说的话
        - mood: 情绪（影响表情）
        - status: 状态模式
        - duration: 气泡显示时长（毫秒）
        """
        self._current_mood = mood
        self._current_status = status
        self._bubble_text = text

        emoji = self.MOOD_EMOJIS.get(mood, self.PET_EMOJI)
        self._pet_emoji = emoji
        self.canvas.itemconfigure(self._pet_text, text=emoji)

        status_color = self.STATUS_COLORS.get(status, "#4ade80")
        self.canvas.itemconfigure(self._status_light, fill=status_color)

        self._show_bubble()
        self.canvas.itemconfigure(self._bubble_text_id, text=text)

        if self._bubble_timer:
            self.root.after_cancel(self._bubble_timer)

        if duration > 0:
            self._bubble_timer = self.root.after(duration, self._hide_bubble)

    def set_status(self, status: str, mood: str = "neutral"):
        """只更新状态，不说话"""
        self._current_status = status
        self._current_mood = mood

        emoji = self.MOOD_EMOJIS.get(mood, self.PET_EMOJI)
        self._pet_emoji = emoji
        self.canvas.itemconfigure(self._pet_text, text=emoji)

        status_color = self.STATUS_COLORS.get(status, "#4ade80")
        self.canvas.itemconfigure(self._status_light, fill=status_color)

    def _show_bubble(self):
        """显示气泡"""
        self._bubble_visible = True
        self.canvas.itemconfigure("bubble", state="normal")

    def _hide_bubble(self):
        """隐藏气泡"""
        self._bubble_visible = False
        self.canvas.itemconfigure("bubble", state="hidden")

    def _start_animation(self):
        """启动动画循环"""
        self._animate()

    def _animate(self):
        """动画帧更新"""
        self._anim_frame += 1

        float_speed = 0.05
        float_amplitude = 3
        new_offset = math.sin(self._anim_frame * float_speed) * float_amplitude
        delta = new_offset - self._float_offset
        self._float_offset = new_offset

        if abs(delta) > 0.01:
            self.canvas.move("pet", 0, delta)

        glow_pulse = math.sin(self._anim_frame * 0.08) * 0.3 + 0.7
        glow_r = int(38 + glow_pulse * 5)
        pet_x = 70
        pet_y = 95 + self._float_offset
        self.canvas.coords(
            self._glow,
            pet_x - glow_r, pet_y - glow_r,
            pet_x + glow_r, pet_y + glow_r,
        )
        self.canvas.coords(
            self._glow2,
            pet_x - glow_r - 8, pet_y - glow_r - 8,
            pet_x + glow_r + 8, pet_y + glow_r + 8,
        )

        if self._anim_frame % 180 == 0:
            self._blink()

        if self._current_mood == "tired" and self._anim_frame % 200 == 0:
            self._sleepy_anim()

        if self._current_status == "excited" and self._anim_frame % 30 == 0:
            self._excited_wiggle()

        self.root.after(50, self._animate)

    def _update_pet_position(self):
        """更新宠物垂直位置（浮动效果）"""
        pass

    def _blink(self):
        """眨眼动画"""
        if self._current_mood in ("tired", "sleepy"):
            return

        original = self._pet_emoji
        self.canvas.itemconfigure(self._pet_text, text="😺")
        self.root.after(100, lambda: self.canvas.itemconfigure(self._pet_text, text=original))

    def _sleepy_anim(self):
        """犯困动画 — 点头"""
        self.canvas.move(self._pet_text, 0, 3)
        self.canvas.move(self._status_light, 0, 3)
        self.root.after(
            500,
            lambda: (
                self.canvas.move(self._pet_text, 0, -3),
                self.canvas.move(self._status_light, 0, -3),
            ),
        )

    def _excited_wiggle(self):
        """兴奋时左右摇摆"""
        if random.random() < 0.3:
            dx = random.choice([-2, 2])
            self.canvas.move(self._pet_text, dx, 0)
            self.root.after(100, lambda: self.canvas.move(self._pet_text, -dx, 0))

    def _say_random(self):
        """随机说句话"""
        from .dialogue import DialogueGenerator
        gen = DialogueGenerator()
        text = gen.idle_chat(self._current_mood)
        self.say(text, self._current_mood, self._current_status)

    def _cycle_mood(self):
        """切换心情（调试用）"""
        moods = ["neutral", "happy", "excited", "curious", "doubt", "worried", "proud", "tired", "love"]
        try:
            idx = moods.index(self._current_mood)
            next_mood = moods[(idx + 1) % len(moods)]
        except ValueError:
            next_mood = "happy"

        statuses = list(self.STATUS_LABELS.keys())
        try:
            sidx = statuses.index(self._current_status)
            next_status = statuses[(sidx + 1) % len(statuses)]
        except ValueError:
            next_status = "idle"

        self.set_status(next_status, next_mood)
        lines = {
            "happy": "嘿嘿，心情不错~",
            "excited": "哇！好兴奋！",
            "curious": "嗯？那是什么？",
            "doubt": "真的吗…我想想",
            "worried": "有点担心…",
            "proud": "哼哼，小菜一碟~",
            "tired": "好困啊…zzz",
            "love": "喜欢你~",
            "neutral": "平静的一天",
        }
        self.say(lines.get(next_mood, "喵~"), next_mood, next_status)

    def _toggle_bubble(self):
        """切换气泡显示"""
        if self._bubble_visible:
            self._hide_bubble()
            if self._bubble_timer:
                self.root.after_cancel(self._bubble_timer)
                self._bubble_timer = None
        else:
            self._show_bubble()

    def _show_about(self):
        """显示关于"""
        messagebox.showinfo(
            "关于小籽",
            "🐱 小籽 - ACE Companion\n\n"
            "一只站在你桌面上的科技猫\n"
            "陪你一起建造、考古、重构、进化\n\n"
            "✅ 可拖动到任意位置\n"
            "✅ 会眨眼睛、会浮动\n"
            "✅ 不同心情不同表情\n"
            "✅ 右键菜单有惊喜\n"
            "✅ 监听ACE系统事件\n\n"
            "拖走试试吧！~",
        )

    def _on_close(self):
        """关闭事件"""
        if self.on_close_callback:
            self.on_close_callback()
        self.root.destroy()

    def run(self):
        """运行主循环"""
        self.root.mainloop()

    def after(self, ms: int, func):
        """封装 tkinter after"""
        self.root.after(ms, func)
