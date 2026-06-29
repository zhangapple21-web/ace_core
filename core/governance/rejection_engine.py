"""
Governor Rejection Engine — ACE 拒绝引擎

老张的核心要求：
系统要学会说"不要"，而不是全部 YES YES YES。

真正成熟后会大量输出：
- Reject（拒绝）
- Duplicate（重复）
- Already Known（已知）
- Too Implementation-Specific（只是实现细节）
- Only Keep Philosophy（只保留哲学层）

每天应该输出：
"今天拒绝了 X 个结构"
这才说明开始成熟。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pathlib import Path
import json


class RejectionReason(Enum):
    """拒绝理由枚举"""
    DUPLICATE = "Duplicate"  # 与已有结构重复
    ALREADY_KNOWN = "Already Known"  # 词库中已有
    TOO_IMPLEMENTATION = "Too Implementation-Specific"  # 只是实现细节，无骨架价值
    ONLY_TOOL = "Only Tool"  # 只是工具，不是骨架
    LOW_VALUE = "Low Value"  # ROI 太低，不值得
    OUT_OF_SCOPE = "Out of Scope"  # 超出当前演化方向
    CONTRADICTS_EXISTING = "Contradicts Existing"  # 与已有知识矛盾
    NO_EVIDENCE = "No Evidence"  # 缺乏考古证据


@dataclass
class Rejection:
    """拒绝记录"""
    timestamp: str
    item: str  # 被拒绝的内容
    reason: RejectionReason
    detail: str  # 拒绝原因详细说明
    alternative: Optional[str] = None  # 替代方案（如果有）

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "item": self.item,
            "reason": self.reason.value,
            "detail": self.detail,
            "alternative": self.alternative,
        }


class AcceptanceRecord:
    """接受记录"""
    def __init__(self):
        self.accepted_today = 0
        self.max_daily_accept = 5  # 每天最多 5 个进入文明

    def can_accept(self) -> bool:
        """今天还能接受新结构吗"""
        return self.accepted_today < self.max_daily_accept

    def record_accept(self):
        """记录一次接受"""
        self.accepted_today += 1

    def remaining(self) -> int:
        """今天还能接受几个"""
        return max(0, self.max_daily_accept - self.accepted_today)


class GovernorRejectionEngine:
    """
    Governor 拒绝引擎

    核心职责：
    1. 评估每个新结构是否值得进入文明
    2. 拒绝不符合标准的结构
    3. 记录拒绝原因，形成判断力积累

    每天的输出应该包含：
    - 今天拒绝了 X 个结构
    - 今天进入了 Y 个结构（最多 5 个）

    设计原则：
    - 拒绝也是成绩（说明有判断力）
    - 每天最多 5 个进入文明（代谢）
    - 拒绝必须有明确理由（不是随意拒绝）
    """

    def __init__(self, lexicon_path: str):
        self.lexicon_path = Path(lexicon_path)
        self.rejections_today: List[Rejection] = []
        self.acceptance = AcceptanceRecord()
        self._load_lexicon()

    def _load_lexicon(self):
        """加载词库，查找已知的骨架和模式"""
        self.known_patterns: List[str] = []
        self.known_concepts: List[str] = []

        if self.lexicon_path.exists():
            try:
                data = json.loads(self.lexicon_path.read_text(encoding="utf-8"))
                # 从词库中提取已知概念
                for entry in data.get("entries", []):
                    if entry.get("type") == "pattern":
                        self.known_patterns.append(entry.get("name", ""))
                    elif entry.get("type") == "concept":
                        self.known_concepts.append(entry.get("name", ""))
            except Exception:
                pass

    def evaluate(
        self,
        item: str,
        source: str,
        extracted_skeleton: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        评估一个新结构是否值得接受

        返回格式：
        {
            "decision": "accept" | "reject",
            "reason": "...",
            "alternative": "..." | None,
        }
        """
        item_lower = item.lower()
        skeleton_lower = (extracted_skeleton or "").lower()

        # 检查是否已存在
        for pattern in self.known_patterns:
            if self._is_similar(item, pattern) or self._is_similar(skeleton_lower, pattern.lower()):
                return self._reject(
                    item,
                    RejectionReason.DUPLICATE,
                    f"与已知模式 '{pattern}' 高度相似",
                    f"深化对 '{pattern}' 的理解，而不是新增",
                )

        # 检查是否只是工具
        if self._is_only_tool(item, skeleton_lower):
            return self._reject(
                item,
                RejectionReason.ONLY_TOOL,
                "只是工具，不是骨架",
                "提取其背后的设计哲学",
            )

        # 检查是否只是实现细节
        if self._is_implementation_detail(item, skeleton_lower):
            return self._reject(
                item,
                RejectionReason.TOO_IMPLEMENTATION,
                "只是实现细节，无骨架价值",
                None,
            )

        # 检查今天是否还能接受
        if not self.acceptance.can_accept():
            return self._reject(
                item,
                RejectionReason.LOW_VALUE,
                f"今天已达上限（{self.acceptance.max_daily_accept}个），进入等待队列",
                "明天继续评估",
            )

        # 可以接受
        self.acceptance.record_accept()
        return {
            "decision": "accept",
            "reason": f"骨架价值确认，今日剩余：{self.acceptance.remaining()} 个",
            "alternative": None,
        }

    def _reject(
        self,
        item: str,
        reason: RejectionReason,
        detail: str,
        alternative: Optional[str] = None,
    ) -> Dict[str, Any]:
        """记录一次拒绝"""
        rejection = Rejection(
            timestamp=datetime.now().isoformat(),
            item=item,
            reason=reason,
            detail=detail,
            alternative=alternative,
        )
        self.rejections_today.append(rejection)

        return {
            "decision": "reject",
            "reason": reason.value,
            "detail": detail,
            "alternative": alternative,
        }

    def _is_similar(self, str1: str, str2: str) -> bool:
        """简单判断两个字符串是否相似（共享关键词）"""
        words1 = set(str1.replace("-", " ").replace("_", " ").split())
        words2 = set(str2.replace("-", " ").replace("_", " ").split())
        return bool(words1 & words2)  # 有交集即相似

    def _is_only_tool(self, item: str, skeleton: str) -> bool:
        """判断是否只是工具（没有骨架价值）"""
        tool_indicators = [
            "ghidra", "ida", "jadx", "radare2", "objdump",
            "mitmproxy", "reverse-skill", "blackbox",
        ]
        return any(t in skeleton for t in tool_indicators) and "philosophy" not in skeleton

    def _is_implementation_detail(self, item: str, skeleton: str) -> bool:
        """判断是否只是实现细节"""
        impl_indicators = [
            "import ", "from ", "def ", "class ", "function ",
            ".py", ".java", ".rs", ".go",
            "api_key", "token", "config",
        ]
        return any(ind in skeleton for ind in impl_indicators[:4]) and len(skeleton) < 50

    def get_daily_summary(self) -> Dict[str, Any]:
        """获取今日拒绝摘要"""
        return {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "accepted_count": self.acceptance.accepted_today,
            "rejected_count": len(self.rejections_today),
            "rejections": [r.to_dict() for r in self.rejections_today],
            "remaining_capacity": self.acceptance.remaining(),
        }

    def format_rejection_report(self) -> str:
        """格式化拒绝报告"""
        summary = self.get_daily_summary()
        lines = [
            f"# Governor 每日判断报告 — {summary['date']}",
            "",
            f"**接受**：{summary['accepted_count']} 个结构",
            f"**拒绝**：{summary['rejected_count']} 个结构",
            "",
        ]

        if summary['rejections']:
            lines.append("## 拒绝清单")
            for r in summary['rejections']:
                lines.append(f"- **{r['reason']}**：{r['item']}")
                lines.append(f"  - 原因：{r['detail']}")
                if r['alternative']:
                    lines.append(f"  - 建议：{r['alternative']}")
                lines.append("")

        return "\n".join(lines)

    def reset_daily(self):
        """重置每日计数器"""
        self.rejections_today = []
        self.acceptance = AcceptanceRecord()

    def add_to_lexicon(self, item: str, pattern_type: str = "pattern"):
        """将被接受的骨架添加到词库"""
        self.known_patterns.append(item)
        if pattern_type == "concept":
            self.known_concepts.append(item)
