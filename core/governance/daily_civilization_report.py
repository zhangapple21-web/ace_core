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

---

Governor Daily Meeting（四人开会）
===================================

这是 Civilization Clock 的核心。

每天只有一次，22:00 执行。

四个人分别汇报：

1. 小疯子（Observer）
   今天发现 X 个，进入验证 Y 个，失败 Z 个

2. 疯子（Validator）
   今天真正上线 A 个，拒绝 B 个，生产异常 C 个

3. ACE（Archivist + Governor）
   今天新增能力 D 个，删除重复 E 个，文明评分 F

4. 云端（Continuity）
   今天运行成功/失败，备份成功/失败，同步成功/失败

最后 Governor 总结：
   今天真正值得进入文明的：XXX
   理由：连续三天验证成功

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


@dataclass
class DailyMeetingReport:
    """
    Governor Daily Meeting Report（四人开会报告）

    每个人只说三件事：
    - 做了什么
    - 结果如何
    - 问题在哪

    最后 Governor 决定：
    - 今天真正值得进入文明的
    - 理由是什么
    """
    date: str
    generated_at: str = ""

    # 1. 小疯子（Observer）汇报
    observer_discovered: int = 0  # 今天发现
    observer_to_review: int = 0   # 进入验证
    observer_failed: int = 0     # 失败
    observer_notes: str = ""

    # 2. 疯子（Validator）汇报
    validator_passed: int = 0    # 今天真正上线
    validator_rejected: int = 0   # 拒绝
    validator_exceptions: int = 0  # 生产异常
    validator_notes: str = ""

    # 3. ACE（Archivist + Governor）汇报
    ace_new_capabilities: int = 0    # 新增能力
    ace_duplicates_removed: int = 0    # 删除重复
    ace_civilization_score: float = 0.0  # 文明评分
    ace_notes: str = ""

    # 4. 云端（Continuity）汇报
    cloud_runtime_ok: bool = True     # 运行
    cloud_backup_ok: bool = True      # 备份
    cloud_sync_ok: bool = True        # 同步
    cloud_exceptions: int = 0         # 异常
    cloud_notes: str = ""

    # Governor 最终决定
    governor_winner: str = ""         # 今天真正值得进入文明的
    governor_reason: str = ""         # 理由
    governor_decisions: List[Dict] = field(default_factory=list)  # 所有决策

    # StableKernel 稳定内核汇报
    kernel_total_cycles: int = 0       # 今日内核循环数
    kernel_snapshots: int = 0          # 快照数
    kernel_decision_cache: int = 0    # 决策缓存条数
    kernel_stability_rate: float = 1.0  # 稳定率
    kernel_stabilizations: int = 0    # 稳定化干预次数
    kernel_rollbacks: int = 0          # 回滚次数
    kernel_feedback_total: int = 0     # 反馈决策数
    kernel_feedback_accuracy: float = 0.0  # 反馈正确率
    kernel_reflections: int = 0       # 自我反思次数
    kernel_mode: str = "convergence-first"  # 收敛优先模式
    kernel_notes: str = ""


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

    # =========================================================================
    # Governor Daily Meeting（四人开会）
    # =========================================================================

    def generate_daily_meeting_report(self, task_pool_stats: Dict = None,
                                       knowledge_stats: Dict = None,
                                       system_stats: Dict = None) -> DailyMeetingReport:
        """
        生成 Governor Daily Meeting 报告

        四个人分别汇报，Governor 最终决定。

        Args:
            task_pool_stats: 任务池统计数据
            knowledge_stats: 知识库统计数据
            system_stats: 系统运行统计数据

        Returns:
            DailyMeetingReport
        """
        now = datetime.now()
        report_date = now.strftime("%Y-%m-%d")

        report = DailyMeetingReport(
            date=report_date,
            generated_at=now.isoformat(),
        )

        # 1. 小疯子（Observer）汇报 - 从任务池统计数据中获取
        if task_pool_stats:
            tasks_created = task_pool_stats.get("tasks_created", 0)
            tasks_to_review = task_pool_stats.get("tasks_to_review", 0)
            tasks_failed = task_pool_stats.get("tasks_failed", 0)

            report.observer_discovered = tasks_created
            report.observer_to_review = tasks_to_review
            report.observer_failed = tasks_failed

            if tasks_created > 0:
                report.observer_notes = f"小疯子今天发现 {tasks_created} 个，进入验证 {tasks_to_review} 个，失败 {tasks_failed} 个"
            else:
                report.observer_notes = "小疯子今天没有新发现"

        # 2. 疯子（Validator）汇报 - 从知识库和任务池数据中获取
        if task_pool_stats and knowledge_stats:
            tasks_passed = task_pool_stats.get("tasks_approved", 0)
            tasks_rejected = task_pool_stats.get("tasks_rejected", 0)
            exceptions = knowledge_stats.get("exceptions", 0)

            report.validator_passed = tasks_passed
            report.validator_rejected = tasks_rejected
            report.validator_exceptions = exceptions

            if tasks_passed > 0 or tasks_rejected > 0:
                report.validator_notes = f"疯子今天通过 {tasks_passed} 个，拒绝 {tasks_rejected} 个，生产异常 {exceptions} 个"
            else:
                report.validator_notes = "疯子今天没有验证任务"

        # 3. ACE（Archivist + Governor）汇报
        if knowledge_stats:
            new_caps = knowledge_stats.get("new_capabilities", 0)
            dup_removed = knowledge_stats.get("duplicates_removed", 0)
            civ_score = knowledge_stats.get("civilization_score", 0.0)

            report.ace_new_capabilities = new_caps
            report.ace_duplicates_removed = dup_removed
            report.ace_civilization_score = civ_score

            report.ace_notes = f"ACE 今天新增 {new_caps} 个能力，删除 {dup_removed} 个重复，文明评分 {civ_score:.1f}"

        # 4. 云端（Continuity）汇报
        if system_stats:
            report.cloud_runtime_ok = system_stats.get("runtime_ok", True)
            report.cloud_backup_ok = system_stats.get("backup_ok", True)
            report.cloud_sync_ok = system_stats.get("sync_ok", True)
            report.cloud_exceptions = system_stats.get("exceptions", 0)

            status_parts = []
            if report.cloud_runtime_ok:
                status_parts.append("运行成功")
            else:
                status_parts.append("运行失败")

            if report.cloud_backup_ok:
                status_parts.append("备份成功")
            else:
                status_parts.append("备份失败")

            if report.cloud_sync_ok:
                status_parts.append("同步成功")
            else:
                status_parts.append("同步失败")

            if report.cloud_exceptions > 0:
                status_parts.append(f"异常{report.cloud_exceptions}个")

            report.cloud_notes = "，".join(status_parts)

        # 5. StableKernel（稳定内核）汇报
        try:
            from core.governance import StableRecursiveKernel
            kernel_data_dir = self.base_dir / "06_RUNTIME" / "ace" / "data"
            if kernel_data_dir.exists():
                kernel = StableRecursiveKernel(
                    base_dir=str(self.base_dir),
                    runtime_dir=str(kernel_data_dir),
                )
                stats = kernel.get_kernel_stats()
                report.kernel_total_cycles = stats.get("total_cycles", 0)
                report.kernel_snapshots = stats.get("snapshot_stats", {}).get("total_snapshots", 0)
                report.kernel_decision_cache = stats.get("stability_report", {}).get("total_decisions", 0)
                report.kernel_stability_rate = stats.get("stability_report", {}).get("stability_rate", 1.0)
                report.kernel_stabilizations = stats.get("stability_report", {}).get("stabilized", 0)
                fb = stats.get("feedback_stats", {})
                report.kernel_feedback_total = fb.get("total_decisions", 0)
                report.kernel_feedback_accuracy = fb.get("accuracy", 0.0)
                rf = stats.get("reflection_stats", {})
                report.kernel_reflections = rf.get("total_reflections", 0)
                if report.kernel_stabilizations > 0:
                    report.kernel_notes = f"稳定化干预 {report.kernel_stabilizations} 次"
                elif report.kernel_reflections > 0:
                    report.kernel_notes = f"自我反思 {report.kernel_reflections} 次"
                else:
                    report.kernel_notes = "无异常，系统稳定"
        except Exception as e:
            report.kernel_notes = f"内核统计获取失败: {e}"

        # Governor 最终决定
        report.governor_decisions = self._collect_today_decisions(report_date)

        # 选出今天最值得进入文明的知识
        if report.governor_decisions:
            # 按验证通过数排序，取第一个
            sorted_decisions = sorted(
                report.governor_decisions,
                key=lambda d: d.get("validation_count", 0),
                reverse=True
            )
            if sorted_decisions:
                best = sorted_decisions[0]
                report.governor_winner = best.get("knowledge_title", best.get("knowledge_id", "未知"))
                report.governor_reason = f"获得 {best.get('validation_count', 0)} 次验证通过，{best.get('reason', '综合评估最优')}"

        # 保存报告
        self._save_meeting_report(report)

        return report

    def _collect_today_decisions(self, report_date: str) -> List[Dict]:
        """收集今日所有决策"""
        decisions = []

        # 从 Governor 记录中获取
        governor_file = self.data_dir / "governor" / "knowledge_governor_records.jsonl"
        if governor_file.exists():
            try:
                with open(governor_file, "r", encoding="utf-8") as f:
                    for line in f:
                        try:
                            record = json.loads(line.strip())
                            if record.get("timestamp", "").startswith(report_date):
                                decisions.append({
                                    "knowledge_id": record.get("knowledge_id", ""),
                                    "knowledge_title": record.get("knowledge_title", ""),
                                    "decision": record.get("decision", ""),
                                    "validation_count": record.get("validation_count", 1),
                                    "reason": record.get("reason", ""),
                                })
                        except Exception:
                            continue
            except Exception as e:
                logger.warning(f"读取Governor记录失败: {e}")

        return decisions

    def _save_meeting_report(self, report: DailyMeetingReport):
        """保存四人开会报告"""
        report_file = self.reports_dir / f"governor_meeting_{report.date}.md"

        content = f"""# Governor Daily Meeting Report

**日期**: {report.date}
**时间**: {report.generated_at}
**模式**: 四人开会 | Civilization Clock ⏰

---

## 一、小疯子汇报（Observer）

> 观察员：今天发现 → 进入验证 → 失败

- 🆕 今天发现：**{report.observer_discovered}** 个
- 🔍 进入验证：**{report.observer_to_review}** 个
- ❌ 失败：**{report.observer_failed}** 个
- 📝 备注：{report.observer_notes}

---

## 二、疯子汇报（Validator）

> 验证员：上线 → 拒绝 → 异常

- ✅ 今天真正上线：**{report.validator_passed}** 个
- 🚫 拒绝：**{report.validator_rejected}** 个
- ⚠️ 生产异常：**{report.validator_exceptions}** 个
- 📝 备注：{report.validator_notes}

---

## 三、ACE汇报（Archivist + Governor）

> 档案员 + 馆长：能力 → 重复 → 评分

- 🆕 新增能力：**{report.ace_new_capabilities}** 个
- 🗑️ 删除重复：**{report.ace_duplicates_removed}** 个
- 📊 文明评分：**{report.ace_civilization_score:.1f}/100**
- 📝 备注：{report.ace_notes}

---

## 四、云端汇报（Continuity）

> 持续性：运行 → 备份 → 同步

- 🖥️ 运行：{'✅ 成功' if report.cloud_runtime_ok else '❌ 失败'}
- 💾 备份：{'✅ 成功' if report.cloud_backup_ok else '❌ 失败'}
- 🔄 同步：{'✅ 成功' if report.cloud_sync_ok else '❌ 失败'}
- ⚠️ 异常：**{report.cloud_exceptions}** 个
- 📝 备注：{report.cloud_notes}

---

## 五、StableKernel 稳定内核汇报 🔒

> 收敛优先模式（Convergence-first）：漂移控制 + 快照回溯 + 决策稳定 + 反馈闭环 + 自我反思

- 🔄 总内核循环：**{report.kernel_total_cycles}** 次
- 📸 快照数：**{report.kernel_snapshots}** 个
- 🗂️ 决策缓存：**{report.kernel_decision_cache}** 条
- 📊 稳定率：**{report.kernel_stability_rate:.1%}**
- ⚡ 稳定化干预：**{report.kernel_stabilizations}** 次
- 🔁 反馈闭环：**{report.kernel_feedback_total}** 条 (正确率: **{report.kernel_feedback_accuracy:.1%}**)
- 🪞 自我反思：**{report.kernel_reflections}** 次
- ↩️ 回滚次数：**{report.kernel_rollbacks}** 次
- 🎯 模式：**{report.kernel_mode}**
- 📝 备注：{report.kernel_notes}

> 五条护栏：漂移控制（max_drift=0.15）| 快照回溯（append-only）| 决策稳定（same_input→same_output）| 反馈闭环（决策→结果→调整）| 自我反思（失败→模式提取→修正）

---

## 六、Governor 最终决定

### 🏆 今天真正值得进入文明的

**{report.governor_winner or '无'}**

### 📋 理由

{report.governor_reason or '今日无值得进入文明的知识'}

### 📊 今日决策汇总

| 知识 | 决策 | 验证次数 |
|------|------|----------|
"""

        for decision in report.governor_decisions[:10]:
            content += f"| {decision.get('knowledge_title', decision.get('knowledge_id', '?'))[:30]} | {decision.get('decision', '?')} | {decision.get('validation_count', 0)} |\n"

        if not report.governor_decisions:
            content += "| - | - | - |\n"

        content += f"""
---

## 七、会议结束

> **只有 Governor 有资格：Accept / Reject / Observe / Wait**
> 其他 Agent 只能输出，不能决定。

**下次会议**：明天 22:00

---

> Civilization Clock | 昼夜节律 | 文明自有其时
"""

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"Governor Daily Meeting 报告已生成: {report_file}")
        except Exception as e:
            logger.error(f"保存会议报告失败: {e}")
