"""
Telegram 通知模块 — ACE 分级推送

参考疯子的通知规则：
- 告警：必通知，不受限
- 突破：每天最多1条，合并发布
- 日报：每天1条汇总

文案像朋友聊天，有重点不堆砌。
"""

import json
import urllib.request
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional


class TgNotifier:
    """TG 分级通知器"""

    # 通知级别
    LEVEL_ALERT = "alert"          # 告警：必推
    LEVEL_BREAKTHROUGH = "break"    # 突破：每天最多1条
    LEVEL_DAILY = "daily"          # 日报：每天1条

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        base_dir: Optional[Path] = None,
        enabled: bool = True,
        max_daily_breakthrough: int = 1,
        max_daily_total: int = 3,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_dir = Path(base_dir) if base_dir else Path.cwd()
        self.enabled = enabled
        self.max_daily_breakthrough = max_daily_breakthrough
        self.max_daily_total = max_daily_total

        self._api_base = f"https://api.telegram.org/bot{bot_token}"
        self._today = datetime.now().strftime("%Y-%m-%d")
        self._sent_today = {
            "alert": 0,
            "break": 0,
            "daily": 0,
        }
        self._alert_hashes = set()

    def _send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """发送一条消息（底层）"""
        if not self.enabled:
            return False

        url = f"{self._api_base}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }

        try:
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("ok", False)
        except Exception as e:
            print(f"[TG] 发送失败: {e}")
            return False

    def _check_today(self):
        """检查日期，跨天重置计数"""
        today = datetime.now().strftime("%Y-%m-%d")
        if today != self._today:
            self._today = today
            self._sent_today = {"alert": 0, "break": 0, "daily": 0}
            self._alert_hashes.clear()

    def _can_send(self, level: str) -> bool:
        """检查是否可以发送（频率控制）"""
        self._check_today()

        if level == self.LEVEL_ALERT:
            return True

        if level == self.LEVEL_BREAKTHROUGH:
            if self._sent_today["break"] >= self.max_daily_breakthrough:
                return False

        total_non_alert = self._sent_today["break"] + self._sent_today["daily"]
        if total_non_alert >= self.max_daily_total:
            return False

        return True

    def _record_sent(self, level: str):
        """记录已发送"""
        self._check_today()
        if level in self._sent_today:
            self._sent_today[level] += 1

    # ── 告警级 ──────────────────────────────────────────

    def alert(self, title: str, details: str = "", dedup_key: str = "") -> bool:
        """
        发送告警。必推，不受限，但同类告警去重。

        dedup_key: 去重键，相同键的告警一天只推一次
        """
        if not self.enabled:
            return False

        self._check_today()

        if dedup_key:
            if dedup_key in self._alert_hashes:
                return False
            self._alert_hashes.add(dedup_key)

        text = f"🚨 <b>{title}</b>"
        if details:
            text += f"\n\n{details}"

        ok = self._send_message(text)
        if ok:
            self._record_sent(self.LEVEL_ALERT)
        return ok

    # ── 突破级 ──────────────────────────────────────────

    def breakthrough(self, headline: str, what_happened: str = "") -> bool:
        """
        发送突破消息。每天最多1条。

        headline: 一句话头条，比如"挖到了eco_layer深度考古报告"
        what_happened: 补充说明，简短即可
        """
        if not self._can_send(self.LEVEL_BREAKTHROUGH):
            return False

        text = f"💎 <b>{headline}</b>"
        if what_happened:
            text += f"\n\n{what_happened}"

        ok = self._send_message(text)
        if ok:
            self._record_sent(self.LEVEL_BREAKTHROUGH)
        return ok

    # ── 日报级 ──────────────────────────────────────────

    def daily_report(self, state: Dict, memory_entries: List[Dict]) -> bool:
        """
        发送每日汇报。像朋友聊天一样，讲今天干了啥。
        每天1条。
        """
        if not self._can_send(self.LEVEL_DAILY):
            return False

        text = self._build_daily_chat(state, memory_entries)
        ok = self._send_message(text)
        if ok:
            self._record_sent(self.LEVEL_DAILY)
        return ok

    def _build_daily_chat(self, state: Dict, memory_entries: List[Dict]) -> str:
        """构建聊天式日报"""
        today = datetime.now().strftime("%Y-%m-%d")

        daily_list = state.get("daily_summaries", [])
        today_runs = [d for d in daily_list if d.get("date") == today]
        run_count = len(today_runs)

        lex_count = (
            state.get("lexicon_stats", {}).get("total_concepts")
            or state.get("last_lexicon_count", 0)
        )
        mem_count = state.get("last_memory_count", len(memory_entries))

        # 收集今日行动
        actions = set()
        new_concepts = 0
        new_index = 0
        for d in today_runs:
            for a in d.get("actions", []):
                actions.add(a)
            new_concepts += d.get("new_concepts", 0)
            new_index += d.get("new_index_entries", 0)

        # 今日重要发现
        important = self._find_cool_stuff(memory_entries, today)

        # 异常检测
        anomalies = self._detect_anomalies(state, today_runs)

        # ── 写文案 ──
        lines = []

        # 开头：一句话总结今天在干嘛
        if run_count == 0:
            lines.append("🧬 今天有点安静，系统没怎么跑。")
        elif anomalies:
            lines.append(f"🧬 今天跑了 <b>{run_count}</b> 轮，但是出了点状况 👇")
        elif new_concepts > 0 or important:
            lines.append(f"🧬 今天跑了 <b>{run_count}</b> 轮，有新东西 👇")
        else:
            lines.append(f"🧬 今天跑了 <b>{run_count}</b> 轮，一切正常。")

        lines.append("")

        # 有突破就重点说突破
        if important:
            top = important[0]
            title = top.get("title", "")
            lines.append(f"💡 <b>今天最有意思的：{title}</b>")
            lines.append("")
            if len(important) > 1:
                lines.append("还有这些：")
                for item in important[1:4]:
                    t = item.get("title", "")[:30]
                    lines.append(f"  · {t}")
                lines.append("")

        # 今天在做什么（用口语化描述）
        if actions:
            action_desc = self._describe_actions(actions, new_concepts, new_index)
            lines.append(f"⚙️ 今天主要在做：{action_desc}")
            lines.append("")

        # 关键数字（只说变化的，不说没变化的）
        stats_parts = []
        if new_concepts > 0:
            stats_parts.append(f"词库 <b>+{new_concepts}</b> → 共 {lex_count}")
        else:
            stats_parts.append(f"词库 {lex_count}（没涨）")
        if new_index > 0:
            stats_parts.append(f"记忆 <b>+{new_index}</b> → 共 {mem_count}")
        else:
            stats_parts.append(f"记忆 {mem_count}（没涨）")

        lines.append("📊 " + " · ".join(stats_parts))
        lines.append("")

        # 异常单独拎出来说
        if anomalies:
            lines.append("⚠️ <b>需要注意：</b>")
            for a in anomalies:
                lines.append(f"  · {a}")
            lines.append("")

        lines.append("─" * 15)
        lines.append(f"<i>ACE · {today}</i>")

        return "\n".join(lines)

    def _describe_actions(self, actions: set, new_concepts: int, new_index: int) -> str:
        """把技术行动翻译成口语描述"""
        action_map = {
            "eco_mining": "挖ECO矿",
            "slice_mining": "切Ω切片",
            "lexicon_gap": "补词库缺口",
            "concept_health": "检查概念健康",
            "triple_validation": "三源交叉验证",
            "roundtable": "开圆桌会议",
            "local_archaeology": "本地考古",
        }

        labels = [action_map.get(a, a) for a in sorted(actions)]

        if len(labels) <= 2:
            return "、".join(labels)
        elif len(labels) <= 4:
            return "、".join(labels[:-1]) + "和" + labels[-1]
        else:
            return "、".join(labels[:3]) + f"等{len(labels)}件事"

    # ── 工具方法 ────────────────────────────────────────

    def _detect_anomalies(self, state: Dict, today_runs: List[Dict]) -> List[str]:
        """检测异常"""
        anomalies = []

        if len(today_runs) == 0:
            anomalies.append("今天主循环一次都没跑")

        task_stats = state.get("task_stats", {})
        pending = task_stats.get("pending", 0)
        review = task_stats.get("review", 0)
        if pending > 50:
            anomalies.append(f"任务积压了 {pending} 个")
        if review > 30:
            anomalies.append(f"待评审的有 {review} 个，有点多")

        total_concepts = (
            state.get("lexicon_stats", {}).get("total_concepts")
            or state.get("last_lexicon_count", 0)
        )
        if len(today_runs) >= 5 and total_concepts == 0:
            anomalies.append("词库是空的，可能数据没加载上")

        return anomalies

    def _find_cool_stuff(self, entries: List[Dict], today: str) -> List[Dict]:
        """找出今天有意思的发现"""
        cool_keywords = [
            "考古报告", "深度考古", "结构考古", "治理协议",
            "命名冲突", "演化", "突破", "发现", "协议建立",
            "文明", "核心", "架构",
        ]

        result = []
        seen_titles = set()

        for e in entries:
            title = str(e.get("title", ""))
            cat = str(e.get("category", ""))
            mtype = str(e.get("memory_type", ""))

            is_today = (
                today in title
                or today in str(e.get("created_at", ""))
                or today in str(e.get("timestamp", ""))
            )

            is_cool = any(kw in title for kw in cool_keywords)

            if is_today and is_cool and title not in seen_titles:
                result.append(e)
                seen_titles.add(title)

        return result

    def test_connection(self) -> bool:
        """测试连通性"""
        return self._send_message("🧪 ACE TG 通知测试 - 连通性验证通过")
