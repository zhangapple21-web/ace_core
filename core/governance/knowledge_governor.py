"""
Knowledge Governor（知识馆长）

职责：
    "它有没有资格进入文明？"

只问一个问题：
    这个知识是否值得成为文明的一部分？

决策：
    PASS - 值得进入，直接进入候选
    REJECT - 不值得，拒绝
    MERGE - 值得但需要与现有知识合并
    SUPERSEDE - 值得但需要替代旧知识
    REVISE - 值得但需要修订相关旧知识
    DELAY - 证据不足，延迟决定
    SPLIT - 值得但需要拆分成多个知识

设计原则：
    - Knowledge Admission > Git Push
    - 质量 > 数量
    - 不新增，先修订
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class AdmissionDecision:
    """知识准入决策"""
    PASS = "pass"           # 值得进入，直接进入候选
    REJECT = "reject"       # 不值得，拒绝
    MERGE = "merge"         # 需要与现有知识合并
    SUPERSEDE = "supersede" # 需要替代旧知识
    REVISE = "revise"       # 需要修订相关旧知识
    DELAY = "delay"         # 证据不足，延迟决定
    SPLIT = "split"         # 需要拆分成多个知识


@dataclass
class AdmissionCriteria:
    """准入标准"""
    novelty: float = 0.0           # 创新度 0-1
    evidence_quality: float = 0.0   # 证据质量 0-1
    confidence: float = 0.0         # 置信度 0-1
    duplication_risk: float = 0.0   # 重复风险 0-1
    maturity: float = 0.0            # 成熟度 0-1
    references: int = 0             # 引用数量


@dataclass
class AdmissionRecord:
    """准入记录"""
    knowledge_id: str
    decision: str
    reasons: List[str] = field(default_factory=list)
    criteria: AdmissionCriteria = None
    similar_knowledge: List[Dict] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    operator: str = "knowledge_governor"
    timestamp: str = ""


class KnowledgeGovernor:
    """
    知识馆长

    核心职责：
        1. 评估新知识是否值得进入文明
        2. 检测重复/冲突/覆盖
        3. 决定是新增还是修订
        4. 确保知识质量 > 数量
    """

    def __init__(self, ace_runtime_dir: str):
        """
        初始化知识馆长

        Args:
            ace_runtime_dir: ACE Runtime根目录
        """
        self.ace_runtime_dir = Path(ace_runtime_dir)
        self.data_dir = self.ace_runtime_dir / "08_GOVERNANCE"
        self.records_dir = self.data_dir / "governor"
        self.records_dir.mkdir(parents=True, exist_ok=True)

        # 知识库路径
        self.experiences_file = self.ace_runtime_dir / "09_KNOWLEDGE" / "experiences.json"
        self.lexicon_file = self.ace_runtime_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
        self.evolution_file = self.ace_runtime_dir / "09_KNOWLEDGE" / "evolution.json"

        # 记录文件
        self.records_file = self.records_dir / "knowledge_governor_records.jsonl"

    def evaluate(self, knowledge: Dict[str, Any]) -> AdmissionRecord:
        """
        评估知识是否值得进入文明

        Args:
            knowledge: 待评估的知识

        Returns:
            AdmissionRecord，包含决策结果
        """
        knowledge_id = knowledge.get("id", f"unknown_{datetime.now().timestamp()}")
        record = AdmissionRecord(
            knowledge_id=knowledge_id,
            decision=AdmissionDecision.DELAY,
            criteria=AdmissionCriteria(),
            timestamp=datetime.now().isoformat(),
        )

        # 1. 检查必填字段
        missing_fields = self._check_required_fields(knowledge)
        if missing_fields:
            record.decision = AdmissionDecision.REJECT
            record.reasons.append(f"缺少必填字段: {missing_fields}")
            self._save_record(record)
            return record

        # 2. 评估创新度 - 在添加之前先搜索现有
        novelty_result = self._evaluate_novelty(knowledge)
        record.criteria.novelty = novelty_result["novelty"]
        if novelty_result["has_similar"]:
            record.similar_knowledge = novelty_result["similar"]
            record.reasons.append(f"发现相似知识: {len(record.similar_knowledge)}个")

        # 3. 评估证据质量
        record.criteria.evidence_quality = self._evaluate_evidence_quality(knowledge)
        if record.criteria.evidence_quality < 0.3:
            record.reasons.append("证据质量过低")

        # 4. 评估置信度
        record.criteria.confidence = knowledge.get("confidence", 0)
        if record.criteria.confidence < 0.3:
            record.reasons.append("置信度过低")

        # 5. 评估重复风险
        if record.similar_knowledge:
            record.criteria.duplication_risk = 0.8
            record.reasons.append("存在重复风险，建议MERGE或REVISE")

        # 6. 评估成熟度
        record.criteria.maturity = self._evaluate_maturity(knowledge)

        # 7. 评估引用数量
        record.criteria.references = len(knowledge.get("references", []))

        # 8. 做出决策
        record.decision = self._make_decision(record)

        # 9. 生成建议
        record.suggestions = self._generate_suggestions(record)

        # 10. 保存记录
        self._save_record(record)

        return record

    def _check_required_fields(self, knowledge: Dict[str, Any]) -> List[str]:
        """检查必填字段"""
        required = ["title", "status"]
        missing = []

        for field in required:
            if field not in knowledge or not knowledge[field]:
                missing.append(field)

        return missing

    def _evaluate_novelty(self, knowledge: Dict[str, Any]) -> Dict[str, Any]:
        """
        评估创新度 - 在添加之前先搜索现有

        这是最重要的检查：
        不是Add，而是Search Existing → Merge/Replace
        """
        result = {
            "novelty": 0.5,  # 默认中等创新度
            "has_similar": False,
            "similar": [],
        }

        # 在添加之前，先搜索现有知识
        similar = self._search_existing_knowledge(knowledge)

        if similar:
            result["has_similar"] = True
            result["similar"] = similar

            # 如果有高度相似的知识，创新度降低
            for s in similar:
                if s["similarity"] > 0.9:
                    result["novelty"] = 0.1  # 几乎完全重复
                elif s["similarity"] > 0.7:
                    result["novelty"] = 0.3  # 高度相似
                elif s["similarity"] > 0.5:
                    result["novelty"] = 0.5  # 中度相似

        return result

    def _search_existing_knowledge(self, knowledge: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        搜索现有知识 - Add之前必须先搜索

        这是防止知识爆炸的关键机制
        """
        similar = []
        knowledge_type = knowledge.get("type", knowledge.get("artifact_type", "experience"))

        # 1. 搜索经验库
        if self.experiences_file.exists():
            try:
                with open(self.experiences_file, "r", encoding="utf-8") as f:
                    experiences = json.load(f)

                if isinstance(experiences, list):
                    for exp in experiences:
                        if not isinstance(exp, dict):
                            continue

                        # 计算相似度
                        similarity = self._calculate_similarity(knowledge, exp)
                        if similarity > 0.5:
                            similar.append({
                                "type": "experience",
                                "id": exp.get("id", ""),
                                "title": exp.get("title", ""),
                                "similarity": similarity,
                                "reason": "标题或内容相似",
                            })
            except Exception as e:
                logger.warning(f"搜索经验库失败: {e}")

        # 2. 搜索词库
        if self.lexicon_file.exists():
            try:
                with open(self.lexicon_file, "r", encoding="utf-8") as f:
                    lexicon = json.load(f)

                concepts = lexicon.get("concepts", {})
                for name, concept in concepts.items():
                    if not isinstance(concept, dict):
                        continue

                    # 名称匹配
                    title = knowledge.get("title", "")
                    if title.lower() in name.lower() or name.lower() in title.lower():
                        similar.append({
                            "type": "concept",
                            "id": name,
                            "title": name,
                            "similarity": 0.9,
                            "reason": "名称高度匹配",
                        })
            except Exception as e:
                logger.warning(f"搜索词库失败: {e}")

        # 3. 搜索演化链
        if self.evolution_file.exists():
            try:
                with open(self.evolution_file, "r", encoding="utf-8") as f:
                    evolutions = json.load(f)

                if isinstance(evolutions, list):
                    for evo in evolutions:
                        if not isinstance(evo, dict):
                            continue

                        # 名称匹配
                        title = knowledge.get("title", "")
                        evo_name = evo.get("name", "")
                        if title.lower() in evo_name.lower() or evo_name.lower() in title.lower():
                            similar.append({
                                "type": "evolution",
                                "id": evo.get("id", ""),
                                "title": evo_name,
                                "similarity": 0.85,
                                "reason": "演化链名称匹配",
                            })
            except Exception as e:
                logger.warning(f"搜索演化链失败: {e}")

        # 按相似度排序
        similar.sort(key=lambda x: x["similarity"], reverse=True)

        return similar[:10]  # 只返回前10个

    def _calculate_similarity(self, knowledge1: Dict, knowledge2: Dict) -> float:
        """计算两个知识的相似度"""
        # 基于标题的相似度
        title1 = knowledge1.get("title", "").lower()
        title2 = knowledge2.get("title", "").lower()

        if not title1 or not title2:
            return 0.0

        # 简单匹配
        if title1 == title2:
            return 1.0
        if title1 in title2 or title2 in title1:
            return 0.8

        # 基于内容的相似度
        content1 = knowledge1.get("conclusion", "") + knowledge1.get("description", "")
        content2 = knowledge2.get("conclusion", "") + knowledge2.get("description", "")

        # 简单的词集合相似度
        words1 = set(content1.split())
        words2 = set(content2.split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _evaluate_evidence_quality(self, knowledge: Dict[str, Any]) -> float:
        """评估证据质量"""
        evidence = knowledge.get("evidence", [])
        source = knowledge.get("source", "")

        quality = 0.0

        # 有证据
        if evidence:
            quality += 0.3
            if isinstance(evidence, list) and len(evidence) >= 2:
                quality += 0.2

        # 有来源
        if source and source not in ["unknown", "undefined", ""]:
            quality += 0.3

        # 有引用
        references = knowledge.get("references", [])
        if references:
            quality += 0.2

        return min(1.0, quality)

    def _evaluate_maturity(self, knowledge: Dict[str, Any]) -> float:
        """评估成熟度"""
        maturity = 0.0

        status = knowledge.get("status", "")

        if status == "FACT":
            maturity = 1.0
        elif status == "VALIDATED":
            maturity = 0.8
        elif status == "EVIDENCE":
            maturity = 0.6
        elif status == "HYPOTHESIS":
            maturity = 0.3
        else:
            maturity = 0.1

        # 有更新时间表示更成熟
        updated = knowledge.get("updated", "")
        if updated:
            maturity = min(1.0, maturity + 0.1)

        return maturity

    def _make_decision(self, record: AdmissionRecord) -> str:
        """做出准入决策"""
        criteria = record.criteria

        # 如果缺少必填字段，直接拒绝
        if not record.reasons and criteria.confidence < 0.1:
            return AdmissionDecision.REJECT

        # 如果有高度相似的知识
        if record.similar_knowledge:
            for s in record.similar_knowledge:
                if s["similarity"] > 0.9:
                    return AdmissionDecision.REJECT  # 几乎完全重复，拒绝
                elif s["similarity"] > 0.7:
                    return AdmissionDecision.MERGE  # 高度相似，合并
                elif s["similarity"] > 0.5:
                    return AdmissionDecision.REVISE  # 中度相似，修订

        # 证据质量过低，延迟
        if criteria.evidence_quality < 0.3:
            return AdmissionDecision.DELAY

        # 置信度过低，延迟
        if criteria.confidence < 0.3:
            return AdmissionDecision.DELAY

        # 置信度中等，创新度高，通过
        if criteria.confidence >= 0.5 and criteria.novelty >= 0.5:
            return AdmissionDecision.PASS

        # 其他情况，延迟
        return AdmissionDecision.DELAY

    def _generate_suggestions(self, record: AdmissionRecord) -> List[str]:
        """生成处理建议"""
        suggestions = []
        decision = record.decision

        if decision == AdmissionDecision.PASS:
            suggestions.append("知识通过评估，可以进入候选库")

        elif decision == AdmissionDecision.REJECT:
            if record.similar_knowledge:
                for s in record.similar_knowledge[:3]:
                    suggestions.append(f"与现有知识重复: {s['id']} (相似度:{s['similarity']:.2f})")
            suggestions.append("建议直接使用现有知识，不新增")

        elif decision == AdmissionDecision.MERGE:
            suggestions.append("建议与相似知识合并")
            if record.similar_knowledge:
                for s in record.similar_knowledge[:3]:
                    suggestions.append(f"合并目标: {s['id']}")

        elif decision == AdmissionDecision.REVISE:
            suggestions.append("建议修订现有知识，而非新增")
            if record.similar_knowledge:
                for s in record.similar_knowledge[:3]:
                    suggestions.append(f"修订目标: {s['id']}")

        elif decision == AdmissionDecision.DELAY:
            suggestions.append("证据不足，建议补充证据后重试")
            if record.criteria.evidence_quality < 0.3:
                suggestions.append("增加evidence字段")
            if record.criteria.confidence < 0.3:
                suggestions.append("提升置信度或标注为HYPOTHESIS")

        elif decision == AdmissionDecision.SUPERSEDE:
            suggestions.append("建议替代旧知识，标记为SUPERSEDED")

        elif decision == AdmissionDecision.SPLIT:
            suggestions.append("建议拆分为多个独立知识")

        return suggestions

    def _save_record(self, record: AdmissionRecord):
        """保存准入记录"""
        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "knowledge_id": record.knowledge_id,
                    "decision": record.decision,
                    "reasons": record.reasons,
                    "criteria": {
                        "novelty": record.criteria.novelty,
                        "evidence_quality": record.criteria.evidence_quality,
                        "confidence": record.criteria.confidence,
                        "duplication_risk": record.criteria.duplication_risk,
                        "maturity": record.criteria.maturity,
                        "references": record.criteria.references,
                    },
                    "similar_knowledge": record.similar_knowledge,
                    "suggestions": record.suggestions,
                    "operator": record.operator,
                    "timestamp": record.timestamp,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存准入记录失败: {e}")

    def get_governance_summary(self) -> Dict[str, Any]:
        """获取治理摘要"""
        if not self.records_file.exists():
            return {"total": 0, "decisions": {}}

        total = 0
        decisions = {}

        try:
            with open(self.records_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        total += 1
                        decision = record.get("decision", "unknown")
                        decisions[decision] = decisions.get(decision, 0) + 1
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"读取治理记录失败: {e}")

        return {
            "total": total,
            "decisions": decisions,
            "pass_rate": decisions.get(AdmissionDecision.PASS, 0) / total if total > 0 else 0,
            "reject_rate": decisions.get(AdmissionDecision.REJECT, 0) / total if total > 0 else 0,
            "merge_rate": decisions.get(AdmissionDecision.MERGE, 0) / total if total > 0 else 0,
        }
