"""
Daily Civilization Report（每日文明报告）

核心职责：
    每天结束时生成文明报告。

    不是 "今天新增了多少知识"，
    而是 "今天文明发生了什么变化"。

四类变化：
    - Added（新增）
    - Revised（修订）
    - Merged（合并）
    - Retired（淘汰）

这才是真正的文明成长。
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


@dataclass
class DailyChange:
    """每日变化"""
    type: str  # added/revised/merged/retired
    knowledge_id: str
    knowledge_title: str
    reason: str
    before: Dict = field(default_factory=dict)
    after: Dict = field(default_factory=dict)
    timestamp: str = ""


@dataclass
class CivilizationReport:
    """文明报告"""
    date: str
    generated_at: str = ""

    # 四类变化
    added: List[DailyChange] = field(default_factory=list)
    revised: List[DailyChange] = field(default_factory=list)
    merged: List[DailyChange] = field(default_factory=list)
    retired: List[DailyChange] = field(default_factory=list)

    # 统计
    total_knowledge_before: int = 0
    total_knowledge_after: int = 0

    # 状态变化
    hypothesis_promoted: List[str] = field(default_factory=list)   # 假说升级
    facts_downgraded: List[str] = field(default_factory=list)    # 事实降级
    evidence_added: List[str] = field(default_factory=list)      # 新增证据
    evidence_expired: List[str] = field(default_factory=list)    # 证据失效

    # 文明健康度
    health_score_before: float = 0.0
    health_score_after: float = 0.0

    # 总结
    summary: str = ""


class DailyCivilizationReporter:
    """
    每日文明报告生成器

    核心问题：
        "今天文明发生了什么变化？"

    不是：
        "今天学了多少东西？"

    而是：
        "今天文明成熟了多少？"
    """

    def __init__(self, ace_runtime_dir: str):
        """
        初始化报告生成器

        Args:
            ace_runtime_dir: ACE Runtime根目录
        """
        self.ace_runtime_dir = Path(ace_runtime_dir)
        self.data_dir = self.ace_runtime_dir / "08_GOVERNANCE"
        self.reports_dir = self.data_dir / "journals"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # 各模块路径
        self.experiences_file = self.ace_runtime_dir / "09_KNOWLEDGE" / "experiences.json"
        self.evolution_file = self.ace_runtime_dir / "09_KNOWLEDGE" / "evolution.json"
        self.revisions_dir = self.data_dir / "revisions"
        self.governor_dir = self.data_dir / "governor"

    def generate_daily_report(self) -> CivilizationReport:
        """
        生成每日文明报告

        Returns:
            CivilizationReport，每日文明报告
        """
        now = datetime.now()
        report_date = now.strftime("%Y-%m-%d")

        report = CivilizationReport(
            date=report_date,
            generated_at=now.isoformat(),
        )

        # 1. 统计当前总知识量
        report.total_knowledge_before = self._count_total_knowledge()
        report.total_knowledge_after = report.total_knowledge_before  # 暂时假设不变

        # 2. 收集今日新增
        report.added = self._collect_added_today(report_date)

        # 3. 收集今日修订
        report.revised = self._collect_revised_today(report_date)

        # 4. 收集今日合并
        report.merged = self._collect_merged_today(report_date)

        # 5. 收集今日淘汰
        report.retired = self._collect_retired_today(report_date)

        # 6. 收集状态变化
        report.hypothesis_promoted = self._collect_hypothesis_promoted(report_date)
        report.facts_downgraded = self._collect_facts_downgraded(report_date)

        # 7. 计算健康度
        report.health_score_after = self._calculate_health_score()

        # 8. 生成总结
        report.summary = self._generate_summary(report)

        # 9. 保存报告
        self._save_report(report)

        return report

    def _count_total_knowledge(self) -> int:
        """统计总知识量"""
        total = 0

        # 经验数
        if self.experiences_file.exists():
            try:
                with open(self.experiences_file, "r", encoding="utf-8") as f:
                    experiences = json.load(f)
                    if isinstance(experiences, list):
                        total += len(experiences)
            except Exception:
                pass

        # 演化链数
        if self.evolution_file.exists():
            try:
                with open(self.evolution_file, "r", encoding="utf-8") as f:
                    evolutions = json.load(f)
                    if isinstance(evolutions, list):
                        total += len(evolutions)
            except Exception:
                pass

        return total

    def _collect_added_today(self, report_date: str) -> List[DailyChange]:
        """收集今日新增"""
        added = []

        # 检查Governor记录中PASS的决策
        governor_file = self.governor_dir / "knowledge_governor_records.jsonl"
        if governor_file.exists():
            try:
                with open(governor_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            if record["decision"] == "pass" and record.get("timestamp", "").startswith(report_date):
                                added.append(DailyChange(
                                    type="added",
                                    knowledge_id=record["knowledge_id"],
                                    knowledge_title=record.get("knowledge_title", ""),
                                    reason=record.get("reason", ""),
                                    timestamp=record.get("timestamp", ""),
                                ))
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"读取Governor记录失败: {e}")

        return added

    def _collect_revised_today(self, report_date: str) -> List[DailyChange]:
        """收集今日修订"""
        revised = []

        # 检查修订记录
        revisions_file = self.revisions_dir / "revision_records.jsonl"
        if revisions_file.exists():
            try:
                with open(revisions_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            if record.get("timestamp", "").startswith(report_date):
                                revised.append(DailyChange(
                                    type="revised",
                                    knowledge_id=record["revised_knowledge_id"],
                                    knowledge_title=record.get("revised_knowledge_title", ""),
                                    reason=record.get("reason", ""),
                                    before=record.get("old_value", {}),
                                    after=record.get("new_value", {}),
                                    timestamp=record.get("timestamp", ""),
                                ))
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"读取修订记录失败: {e}")

        return revised

    def _collect_merged_today(self, report_date: str) -> List[DailyChange]:
        """收集今日合并"""
        merged = []

        # 检查Governor记录中MERGE的决策
        governor_file = self.governor_dir / "knowledge_governor_records.jsonl"
        if governor_file.exists():
            try:
                with open(governor_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            if record["decision"] == "merge" and record.get("timestamp", "").startswith(report_date):
                                merged.append(DailyChange(
                                    type="merged",
                                    knowledge_id=record["knowledge_id"],
                                    knowledge_title=record.get("knowledge_title", ""),
                                    reason=record.get("reason", ""),
                                    timestamp=record.get("timestamp", ""),
                                ))
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"读取Governor记录失败: {e}")

        return merged

    def _collect_retired_today(self, report_date: str) -> List[DailyChange]:
        """收集今日淘汰"""
        retired = []

        # 检查Governor记录中REJECT/SUPERSEDE的决策
        governor_file = self.governor_dir / "knowledge_governor_records.jsonl"
        if governor_file.exists():
            try:
                with open(governor_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            if record["decision"] in ["reject", "supersede"] and record.get("timestamp", "").startswith(report_date):
                                retired.append(DailyChange(
                                    type="retired",
                                    knowledge_id=record["knowledge_id"],
                                    knowledge_title=record.get("knowledge_title", ""),
                                    reason=record.get("reason", ""),
                                    timestamp=record.get("timestamp", ""),
                                ))
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"读取Governor记录失败: {e}")

        return retired

    def _collect_hypothesis_promoted(self, report_date: str) -> List[str]:
        """收集假说升级"""
        promoted = []
        # 可以通过比较前后状态来实现
        # 这里先返回空列表
        return promoted

    def _collect_facts_downgraded(self, report_date: str) -> List[str]:
        """收集事实降级"""
        downgraded = []
        return downgraded

    def _calculate_health_score(self) -> float:
        """计算文明健康度"""
        # 简化计算
        score = 0.0

        # 基于经验库
        if self.experiences_file.exists():
            try:
                with open(self.experiences_file, "r", encoding="utf-8") as f:
                    experiences = json.load(f)
                    if isinstance(experiences, list):
                        total = len(experiences)
                        validated = sum(1 for e in experiences if isinstance(e, dict) and e.get("status") == "VALIDATED")
                        facts = sum(1 for e in experiences if isinstance(e, dict) and e.get("status") == "FACT")

                        # 验证率和事实率贡献健康度
                        if total > 0:
                            score += (validated / total) * 30
                            score += (facts / total) * 20

                        # 平均置信度
                        confidences = [e.get("confidence", 0) for e in experiences if isinstance(e, dict)]
                        if confidences:
                            avg_conf = sum(confidences) / len(confidences)
                            score += avg_conf * 30
            except Exception:
                pass

        return round(score, 2)

    def _generate_summary(self, report: CivilizationReport) -> str:
        """生成总结"""
        total_changes = len(report.added) + len(report.revised) + len(report.merged) + len(report.retired)

        summary_parts = []

        if total_changes == 0:
            summary_parts.append("今日文明无显著变化，保持稳定。")
        else:
            if report.added:
                summary_parts.append(f"新增知识 {len(report.added)} 个")
            if report.revised:
                summary_parts.append(f"修订知识 {len(report.revised)} 个")
            if report.merged:
                summary_parts.append(f"合并知识 {len(report.merged)} 个")
            if report.retired:
                summary_parts.append(f"淘汰知识 {len(report.retired)} 个")

        # 文明成熟度判断
        if report.revised and not report.added:
            summary_parts.append("今日文明主要在修订旧知识，走向成熟。")
        elif report.retired and not report.added:
            summary_parts.append("今日文明在淘汰冗余，熵在减少。")
        elif report.added and report.revised:
            summary_parts.append("今日文明在扩展和深化同时进行。")

        return "。".join(summary_parts) + "。"

    def _save_report(self, report: CivilizationReport):
        """保存报告"""
        report_file = self.reports_dir / f"civilization_report_{report.date}.md"

        content = f"""# 每日文明报告

**报告日期**: {report.date}
**生成时间**: {report.generated_at}

---

## 一、文明健康度

| 指标 | 值 |
|------|-----|
| 总知识量 | {report.total_knowledge_after} |
| 健康度 | {report.health_score_after}/100 |

---

## 二、今日变化

| 类型 | 数量 |
|------|------|
| 🆕 新增 (Added) | {len(report.added)} |
| ✏️ 修订 (Revised) | {len(report.revised)} |
| 🔗 合并 (Merged) | {len(report.merged)} |
| 🗑️ 淘汰 (Retired) | {len(report.retired)} |
| **总计** | **{len(report.added) + len(report.revised) + len(report.merged) + len(report.retired)}** |

---

## 三、详细变化

"""

        # 新增
        content += "### 🆕 新增\n\n"
        if report.added:
            content += "| ID | 标题 | 原因 |\n"
            content += "|----|------|------|\n"
            for change in report.added:
                content += f"| {change.knowledge_id} | {change.knowledge_title} | {change.reason} |\n"
        else:
            content += "今日无新增\n\n"

        # 修订
        content += "\n### ✏️ 修订\n\n"
        if report.revised:
            content += "| ID | 标题 | 原因 |\n"
            content += "|----|------|------|\n"
            for change in report.revised:
                content += f"| {change.knowledge_id} | {change.knowledge_title} | {change.reason} |\n"
        else:
            content += "今日无修订\n\n"

        # 合并
        content += "\n### 🔗 合并\n\n"
        if report.merged:
            content += "| ID | 标题 | 原因 |\n"
            content += "|----|------|------|\n"
            for change in report.merged:
                content += f"| {change.knowledge_id} | {change.knowledge_title} | {change.reason} |\n"
        else:
            content += "今日无合并\n\n"

        # 淘汰
        content += "\n### 🗑️ 淘汰\n\n"
        if report.retired:
            content += "| ID | 标题 | 原因 |\n"
            content += "|----|------|------|\n"
            for change in report.retired:
                content += f"| {change.knowledge_id} | {change.knowledge_title} | {change.reason} |\n"
        else:
            content += "今日无淘汰\n\n"

        content += f"""
---

## 四、总结

{report.summary}

---

> **文明真正成长，不是不断加新页面，而是不断让旧页面变得更准确。**
"""

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"每日文明报告已生成: {report_file}")
        except Exception as e:
            logger.error(f"保存文明报告失败: {e}")
