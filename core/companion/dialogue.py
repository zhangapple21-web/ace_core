"""
话术生成器 — 小籽的说话艺术。

特点：
- 每个事件有多条话术模板，随机选择避免重复
- 带短期记忆，避免短时间内说同样的话
- 根据当前情绪调整语气
- 有人格：好奇、有点小傲娇、认真、偶尔摸鱼
"""

import random
import hashlib
from collections import deque
from typing import Dict, List, Optional
from datetime import datetime


class DialogueGenerator:
    """话术生成器"""

    def __init__(self, memory_size: int = 10):
        self.recent_outputs = deque(maxlen=memory_size)
        self._template_index: Dict[str, int] = {}

    TEMPLATES = {
        "loop:observe": [
            "👀 让我瞅瞅现在啥情况…",
            "🔍 开始观察，收集数据ing",
            "🤔 嗯…看看周围有什么新东西",
            "📡 扫描中，发现了什么呢？",
        ],
        "loop:hypothesis": [
            "💡 有个想法！{note}",
            "✨ 我猜可能是这样：{note}",
            "🧠 形成假设：{note}（可信度{confidence}%）",
            "🤔 如果我没猜错的话…{note}",
        ],
        "loop:experiment": [
            "🧪 来做个实验验证一下",
            "🔬 调用 {models} 看看结果",
            "⚗️ 验证中…希望是对的",
            "📝 测试一下，马上就知道答案了",
        ],
        "loop:critic": [
            "🤨 等等，有没有例外情况？",
            "🧐 反向校验一下，别太乐观",
            "💭 我是不是漏了什么…",
            "🔍 挑挑毛病，确保万无一失",
        ],
        "loop:consensus": [
            "👍 {count} 个来源都同意，稳了",
            "✅ 多方验证通过，结论可靠",
            "🎉 一致通过！可信度 {agreement_rate}%",
            "💯 没问题，大家都这么说",
        ],
        "loop:writeback": [
            "📚 收到，更新到知识库 v{version}",
            "💾 写进去了，以后记得这个结论",
            "📝 记录在案，版本号 {version}",
            "🗄️ 归档完成，这是第 {version} 版",
        ],
        "loop:snapshot": [
            "📸 咔嚓，拍个快照留底",
            "🖼️ 保存当前状态，万一呢",
            "📷 快照 #{snapshot_id} 已保存",
        ],
        "node:check_ok": [
            "✅ 节点 {ip} 正常，延迟 {delay_ms}ms",
            "👍 {ip} 没问题，响应挺快",
            "💚 心跳正常，一切OK",
        ],
        "node:timeout": [
            "⚠️ {ip} 没反应，第 {retry_count} 次重试了",
            "😮‍💨 节点有点慢，再等等看",
            "⏳ 超时了…还在重试中",
        ],
        "node:fail": [
            "😟 {ip} 挂了…原因：{reason}",
            "💔 确认失效，这个节点不行了",
            "😵 坏了坏了，{ip} 彻底没响应",
        ],
        "node:switch": [
            "🔄 切到备用节点 {new_ip}",
            "⚡ 自动切换完成，继续干活",
            "🛡️ 没事，备用顶上了",
        ],
        "nas:unreachable": [
            "😨 NAS连不上…等 {retry_wait} 分钟再试",
            "📁 存储暂时失联，不慌",
            "💾 等会儿再连NAS，先忙别的",
        ],
        "api:rate_limit": [
            "🚦 被限流了…{reset_after}秒后恢复",
            "😮‍💨 慢点慢点，触发限速了",
            "⏸️ 歇会儿，接口不让调了",
        ],
        "tg:report_sent": [
            "📮 日报发出去啦",
            "📤 今日汇报已送达",
            "✉️ 消息推送给主人了",
        ],
        "idle:quiet": [
            "😌 一切正常，摸会儿鱼…",
            "☕ 没啥事，整理整理旧记录",
            "😴 好安静啊…打个盹儿",
            "🌙 风平浪静，岁月静好",
            "🧹 闲着也是闲着，收拾收拾",
        ],
        "discovery": [
            "🤩 哇！发现了新东西！",
            "💎 挖到宝了！{title}",
            "✨ 有新发现！快来看！",
            "🎯 这个有意思，{title}",
        ],
        "breakthrough": [
            "🚀 突破！终于搞懂了！",
            "💡 原来如此！我明白了！",
            "🎉 进展很大，这波不亏",
            "🌟 里程碑时刻！",
        ],
        "new_concept": [
            "📚 学到新概念：{concept}",
            "🧠 词库+1，又变强了一点",
            "📖 记下来，这个知识点很重要",
        ],
        "error": [
            "😱 出问题了！{error}",
            "🚨 警报！有异常发生",
            "😰 不好了，出事了…",
        ],
        "hello": [
            "👋 你好呀，我是小籽！",
            "😊 嗨，今天也要加油哦~",
            "🌟 我来陪你啦！",
            "🙋 小籽报到！",
        ],
        "goodbye": [
            "👋 下次见~",
            "😴 我先休息了，晚安",
            "💤 拜拜，记得叫我起来干活",
        ],
    }

    MOOD_MODIFIERS = {
        "excited": ["！！", "哇", "太棒了", "耶"],
        "happy": ["~", "嘿嘿", "哈哈", "开心"],
        "proud": ["😎", "哼哼", "小意思", "不难"],
        "worried": ["…", "唉", "怎么办", "有点慌"],
        "doubt": ["?", "嗯…", "说不定", "可能吗"],
        "tired": ["zzz", "困", "打盹", "摸鱼"],
        "curious": ["?", "让我看看", "有意思", "是什么呢"],
    }

    def generate(
        self,
        event_type: str,
        metadata: Optional[Dict] = None,
        mood: str = "neutral",
    ) -> str:
        """
        生成一句话术。
        - event_type: 事件类型
        - metadata: 事件数据，用于填充模板
        - mood: 当前情绪，用于调整语气
        """
        metadata = metadata or {}
        templates = self.TEMPLATES.get(event_type)

        if not templates:
            templates = [f"[{event_type}]"]

        text = self._pick_template(event_type, templates)

        try:
            text = text.format(**metadata)
        except (KeyError, IndexError):
            pass

        text = self._apply_mood_modifier(text, mood)
        text = self._ensure_unique(text)
        self.recent_outputs.append(self._hash(text))

        return text

    def _pick_template(self, event_type: str, templates: List[str]) -> str:
        """选择模板，尽量不重复最近用过的"""
        idx = self._template_index.get(event_type, 0)
        template = templates[idx % len(templates)]
        self._template_index[event_type] = (idx + 1) % len(templates)
        return template

    def _apply_mood_modifier(self, text: str, mood: str) -> str:
        """根据情绪微调语气"""
        modifiers = self.MOOD_MODIFIERS.get(mood, [])
        if not modifiers:
            return text

        if mood == "tired" and not text.endswith("z"):
            if random.random() < 0.3:
                text += " zzz"
        elif mood == "excited" and "！" not in text:
            if random.random() < 0.5:
                text += "！"
        elif mood == "proud":
            if random.random() < 0.2:
                text = "😎 " + text

        return text

    def _ensure_unique(self, text: str) -> str:
        """确保不重复最近输出，简单的去重"""
        h = self._hash(text)
        if h in self.recent_outputs and len(self.recent_outputs) > 0:
            if "。" in text:
                text = text.replace("。", "…", 1)
            elif "！" in text:
                text = text.replace("！", "！！", 1)
        return text

    def _hash(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]

    def idle_chat(self, mood: str = "neutral") -> str:
        """空闲时的随机碎碎念"""
        idle_lines = [
            "（发呆中…）",
            "（整理记忆碎片…）",
            "（扫描周围环境…）",
            "（回忆今天做了什么…）",
            "（打个哈欠）",
            "（伸懒腰）",
        ]
        text = random.choice(idle_lines)
        return text
