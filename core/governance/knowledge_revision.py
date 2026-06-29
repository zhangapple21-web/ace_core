"""
Knowledge Revision Module（知识修订模块）

核心职责：
    "今天有哪些东西，因为今天的发现，导致过去的理解需要修改？"

文明真正成长，不是不断加新页面，而是不断让旧页面变得更准确。

这不是新增知识。
这是让旧知识变得更成熟。

设计原则：
    - 修订 > 新增
    - 每天结束时必须执行
    - 记录所有修订原因
    - 形成修订历史
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RevisionRecord:
    """修订记录"""
    revised_knowledge_id: str
    revised_knowledge_title: str
    revision_type: str  # update/supersede/deprecate/merge/split
    reason: str  # 为什么今天需要修改
    trigger_discovery: str  # 是什么触发了这次修订
    old_value: Dict = field(default_factory=dict)
    new_value: Dict = field(default_factory=dict)
    operator: str = "revision_system"
    timestamp: str = ""


@dataclass
class DailyRevisionReport:
    """每日修订报告"""
    date: str
    total_knowledge: int
    revisions_count: int
    new_insights_count: int
    old_knowledge_updated_count: int
    revisions: List[RevisionRecord] = field(default_factory=list)
    new_insights: List[str] = field(default_factory=list)
    abandoned_beliefs: List[str] = field(default_factory=list)


class KnowledgeRevision:
    """
    知识修订器

    核心问题：
        今天有哪些东西，因为今天的发现，导致过去的理解需要修改？

    工作流程：
        1. 收集今天的新发现
        2. 检查新发现是否影响旧知识
        3. 执行修订
        4. 生成修订报告
    """

    def __init__(self, ace_runtime_dir: str):
        """
        初始化知识修订器

        Args:
            ace_runtime_dir: ACE Runtime根目录
        """
        self.ace_runtime_dir = Path(ace_runtime_dir)
        self.data_dir = self.ace_runtime_dir / "08_GOVERNANCE"
        self.revisions_dir = self.data_dir / "revisions"
        self.revisions_dir.mkdir(parents=True, exist_ok=True)

        # 知识库路径
        self.experiences_file = self.ace_runtime_dir / "09_KNOWLEDGE" / "experiences.json"
        self.lexicon_file = self.ace_runtime_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
        self.evolution_file = self.ace_runtime_dir / "09_KNOWLEDGE" / "evolution.json"

        # 记录文件
        self.records_file = self.revisions_dir / "revision_records.jsonl"

    def check_and_revise(
        self,
        today_discoveries: List[Dict[str, Any]]
    ) -> DailyRevisionReport:
        """
        检查并执行修订

        Args:
            today_discoveries: 今天的新发现列表

        Returns:
            DailyRevisionReport，每日修订报告
        """
        now = datetime.now()
        report = DailyRevisionReport(
            date=now.strftime("%Y-%m-%d"),
            total_knowledge=self._count_total_knowledge(),
            revisions_count=0,
            new_insights_count=len(today_discoveries),
            old_knowledge_updated_count=0,
            new_insights=[d.get("title", d.get("id", "")) for d in today_discoveries],
        )

        # 1. 读取现有知识
        existing_knowledge = self._load_existing_knowledge()

        # 2. 检查每个新发现是否影响旧知识
        for discovery in today_discoveries:
            affected = self._find_affected_knowledge(discovery, existing_knowledge)

            for affected_item in affected:
                revision = self._create_revision(discovery, affected_item)
                if revision:
                    report.revisions.append(revision)
                    report.revisions_count += 1
                    report.old_knowledge_updated_count += 1

                    # 执行修订
                    self._execute_revision(revision)

        # 3. 生成被抛弃的信念
        report.abandoned_beliefs = self._find_abandoned_beliefs(report.revisions)

        # 4. 保存修订记录
        self._save_revision_records(report)

        # 5. 生成修订报告文件
        self._generate_revision_report(report)

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

        # 概念数
        if self.lexicon_file.exists():
            try:
                with open(self.lexicon_file, "r", encoding="utf-8") as f:
                    lexicon = json.load(f)
                    concepts = lexicon.get("concepts", {})
                    total += len(concepts)
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

    def _load_existing_knowledge(self) -> List[Dict[str, Any]]:
        """加载现有知识"""
        knowledge = []

        # 加载经验
        if self.experiences_file.exists():
            try:
                with open(self.experiences_file, "r", encoding="utf-8") as f:
                    experiences = json.load(f)
                    if isinstance(experiences, list):
                        for exp in experiences:
                            if isinstance(exp, dict):
                                exp["_type"] = "experience"
                                knowledge.append(exp)
            except Exception:
                pass

        # 加载演化链
        if self.evolution_file.exists():
            try:
                with open(self.evolution_file, "r", encoding="utf-8") as f:
                    evolutions = json.load(f)
                    if isinstance(evolutions, list):
                        for evo in evolutions:
                            if isinstance(evo, dict):
                                evo["_type"] = "evolution"
                                knowledge.append(evo)
            except Exception:
                pass

        return knowledge

    def _find_affected_knowledge(
        self,
        discovery: Dict[str, Any],
        existing_knowledge: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        找出被新发现影响的旧知识

        检查维度：
        - 主题相似
        - 结论冲突
        - 新发现修正旧理解
        - 新发现补充旧理解
        """
        affected = []
        discovery_title = discovery.get("title", "").lower()
        discovery_content = discovery.get("conclusion", "") + discovery.get("description", "")

        for item in existing_knowledge:
            item_title = item.get("title", "").lower()
            item_content = item.get("conclusion", "") + item.get("description", "")

            # 1. 主题相似（标题包含）
            if discovery_title and item_title:
                if discovery_title in item_title or item_title in discovery_title:
                    affected.append({
                        "knowledge": item,
                        "reason": "主题相似",
                        "revision_type": "update",
                    })
                    continue

            # 2. 内容重叠
            discovery_words = set(discovery_content.split())
            item_words = set(item_content.split())
            if discovery_words and item_words:
                overlap = len(discovery_words & item_words) / len(discovery_words | item_words)
                if overlap > 0.3:
                    affected.append({
                        "knowledge": item,
                        "reason": f"内容重叠({overlap:.2f})",
                        "revision_type": "update",
                    })
                    continue

            # 3. 检查是否冲突
            if self._is_conflicting(discovery, item):
                affected.append({
                    "knowledge": item,
                    "reason": "结论冲突",
                    "revision_type": "supersede",
                })

        return affected[:5]  # 最多返回5个

    def _is_conflicting(self, new: Dict, old: Dict) -> bool:
        """检查新旧知识是否冲突"""
        # 简单的冲突检测
        # 如果一个说"A是正"，另一个说"A是负"，则冲突

        new_conclusion = new.get("conclusion", "")[:100].lower()
        old_conclusion = old.get("conclusion", "")[:100].lower()

        # 检查关键词冲突
        positive_words = ["好", "正确", "是", "有效", "true", "yes", "good"]
        negative_words = ["坏", "错误", "否", "无效", "假", "false", "no", "bad"]

        new_positive = any(w in new_conclusion for w in positive_words)
        new_negative = any(w in new_conclusion for w in negative_words)
        old_positive = any(w in old_conclusion for w in positive_words)
        old_negative = any(w in old_conclusion for w in negative_words)

        if new_positive and old_negative:
            return True
        if new_negative and old_positive:
            return True

        return False

    def _create_revision(
        self,
        discovery: Dict[str, Any],
        affected_item: Dict[str, Any]
    ) -> Optional[RevisionRecord]:
        """创建修订记录"""
        knowledge = affected_item["knowledge"]
        reason = affected_item["reason"]
        revision_type = affected_item["revision_type"]

        revision = RevisionRecord(
            revised_knowledge_id=knowledge.get("id", ""),
            revised_knowledge_title=knowledge.get("title", ""),
            revision_type=revision_type,
            old_value=knowledge.copy(),
            new_value=knowledge.copy(),
            reason=f"今天发现'{discovery.get('title', '')}'，{reason}",
            trigger_discovery=discovery.get("title", ""),
            timestamp=datetime.now().isoformat(),
        )

        # 更新new_value
        if revision_type == "update":
            # 补充新信息
            if discovery.get("conclusion"):
                revision.new_value["conclusion"] = (
                    revision.new_value.get("conclusion", "") + "\n\n补充："
                    + discovery.get("conclusion", "")
                )
            # 更新引用
            if "references" not in revision.new_value:
                revision.new_value["references"] = []
            revision.new_value["references"].append(discovery.get("id", ""))
            # 更新时间
            revision.new_value["updated"] = datetime.now().isoformat()
            # 提升置信度
            if discovery.get("confidence", 0) > revision.new_value.get("confidence", 0):
                revision.new_value["confidence"] = discovery.get("confidence", 0)

        elif revision_type == "supersede":
            revision.new_value["status"] = "SUPERSEDED"
            revision.new_value["superseded_by"] = discovery.get("id", "")
            revision.new_value["updated"] = datetime.now().isoformat()

        return revision

    def _execute_revision(self, revision: RevisionRecord):
        """执行修订"""
        knowledge_type = revision.revised_knowledge_id.split("-")[0] if "-" in revision.revised_knowledge_id else "exp"

        # 根据知识类型执行修订
        if "exp" in knowledge_type or revision.revised_knowledge_id.startswith("EXP"):
            self._update_experience(revision)
        elif revision.revised_knowledge_id.startswith("EVOL"):
            self._update_evolution(revision)

    def _update_experience(self, revision: RevisionRecord):
        """更新经验"""
        if not self.experiences_file.exists():
            return

        try:
            with open(self.experiences_file, "r", encoding="utf-8") as f:
                experiences = json.load(f)

            if isinstance(experiences, list):
                for i, exp in enumerate(experiences):
                    if isinstance(exp, dict) and exp.get("id") == revision.revised_knowledge_id:
                        experiences[i] = revision.new_value
                        break

            with open(self.experiences_file, "w", encoding="utf-8") as f:
                json.dump(experiences, f, ensure_ascii=False, indent=2)

            logger.info(f"已更新经验: {revision.revised_knowledge_id}")

        except Exception as e:
            logger.error(f"更新经验失败: {e}")

    def _update_evolution(self, revision: RevisionRecord):
        """更新演化链"""
        if not self.evolution_file.exists():
            return

        try:
            with open(self.evolution_file, "r", encoding="utf-8") as f:
                evolutions = json.load(f)

            if isinstance(evolutions, list):
                for i, evo in enumerate(evolutions):
                    if isinstance(evo, dict) and evo.get("id") == revision.revised_knowledge_id:
                        evolutions[i] = revision.new_value
                        break

            with open(self.evolution_file, "w", encoding="utf-8") as f:
                json.dump(evolutions, f, ensure_ascii=False, indent=2)

            logger.info(f"已更新演化链: {revision.revised_knowledge_id}")

        except Exception as e:
            logger.error(f"更新演化链失败: {e}")

    def _find_abandoned_beliefs(self, revisions: List[RevisionRecord]) -> List[str]:
        """找出被抛弃的信念"""
        abandoned = []

        for revision in revisions:
            if revision.revision_type == "supersede":
                abandoned.append(
                    f"{revision.revised_knowledge_title} "
                    f"(被 {revision.trigger_discovery} 替代)"
                )

        return abandoned

    def _save_revision_records(self, report: DailyRevisionReport):
        """保存修订记录"""
        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                for revision in report.revisions:
                    f.write(json.dumps({
                        "revised_knowledge_id": revision.revised_knowledge_id,
                        "revised_knowledge_title": revision.revised_knowledge_title,
                        "revision_type": revision.revision_type,
                        "old_value": revision.old_value,
                        "new_value": revision.new_value,
                        "reason": revision.reason,
                        "trigger_discovery": revision.trigger_discovery,
                        "operator": revision.operator,
                        "timestamp": revision.timestamp,
                    }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存修订记录失败: {e}")

    def _generate_revision_report(self, report: DailyRevisionReport):
        """生成修订报告文件"""
        report_file = self.revisions_dir / f"revision_report_{report.date}.md"

        content = f"""# 每日知识修订报告

**报告日期**: {report.date}
**总知识量**: {report.total_knowledge}
**今日新发现**: {report.new_insights_count}
**修订次数**: {report.revisions_count}
**旧知识更新**: {report.old_knowledge_updated_count}

---

## 一、今日新发现

"""

        for insight in report.new_insights:
            content += f"- {insight}\n"

        content += f"""

---

## 二、修订记录

"""

        if report.revisions:
            content += "| 被修订知识 | 修订类型 | 原因 | 触发发现 |\n"
            content += "|------------|----------|------|----------|\n"
            for r in report.revisions:
                content += f"| {r.revised_knowledge_title} | {r.revision_type} | {r.reason} | {r.trigger_discovery} |\n"
        else:
            content += "今日无修订\n"

        content += f"""

---

## 三、被抛弃的信念

"""

        if report.abandoned_beliefs:
            for belief in report.abandoned_beliefs:
                content += f"- ~~{belief}~~\n"
        else:
            content += "今日无被抛弃的信念\n"

        content += f"""

---

## 四、核心洞察

> **文明真正成长，不是不断加新页面，而是不断让旧页面变得更准确。**

今日修订使得 {report.old_knowledge_updated_count} 个旧知识得到更新或替代。

---

**生成时间**: {datetime.now().isoformat()}
"""

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"修订报告已生成: {report_file}")
        except Exception as e:
            logger.error(f"生成修订报告失败: {e}")

    def get_revision_history(self, limit: int = 50) -> List[Dict]:
        """获取修订历史"""
        history = []

        if not self.records_file.exists():
            return history

        try:
            with open(self.records_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines[-limit:]:
                try:
                    history.append(json.loads(line.strip()))
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"读取修订历史失败: {e}")

        return history
