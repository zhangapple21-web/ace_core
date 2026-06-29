"""
Intent Contract（意图契约）

核心职责：
    在执行任何操作之前，先写下意图。

    我要解决什么？
    为什么？
    预期影响？
    影响哪些模块？

然后再执行。

设计原则：
    - Intent Contract在执行契约之前
    - 记录为什么做，比记录做了什么更重要
    - 以后DecisionLog看的是整个意图链，而不只是结果
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Intent:
    """意图"""
    id: str
    operator: str  # 谁
    action_type: str  # 做什么
    problem: str  # 要解决什么问题
    reason: str  # 为什么
    expected_impact: str  # 预期影响
    affected_modules: List[str] = field(default_factory=list)  # 影响哪些模块
    related_knowledge: List[str] = field(default_factory=list)  # 涉及哪些知识
    prerequisites: List[str] = field(default_factory=list)  # 前置条件
    risks: List[str] = field(default_factory=list)  # 风险
    success_criteria: List[str] = field(default_factory=list)  # 成功标准
    created: str = ""
    status: str = "pending"  # pending / approved / rejected / executed / cancelled


@dataclass
class IntentRecord:
    """意图记录"""
    intent_id: str
    decision: str  # approved / rejected / modified
    reasoning: str  # 决策理由
    modified_intent: Dict = field(default_factory=dict)  # 如果被修改，修改后的意图
    evaluated_by: str = "system"
    timestamp: str = ""


class IntentContract:
    """
    意图契约

    在执行操作之前，必须先填写意图契约。

    流程：
        1. 填写Intent Contract
        2. Governor审核
        3. 执行操作
        4. 记录结果

    Intent Contract不是审批流程。
    而是记录流程。
    """

    def __init__(self, data_dir: str):
        """
        初始化意图契约

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.intent_dir = self.data_dir / "intents"
        self.intent_dir.mkdir(parents=True, exist_ok=True)

        self.intents_file = self.intent_dir / "intents.jsonl"
        self.evaluations_file = self.intent_dir / "intent_evaluations.jsonl"

        self.intents: Dict[str, Intent] = {}

    def create_intent(
        self,
        operator: str,
        action_type: str,
        problem: str,
        reason: str,
        expected_impact: str,
        affected_modules: List[str] = None,
        related_knowledge: List[str] = None,
        prerequisites: List[str] = None,
        risks: List[str] = None,
        success_criteria: List[str] = None,
    ) -> Intent:
        """
        创建意图

        Args:
            operator: 操作者
            action_type: 操作类型
            problem: 要解决的问题
            reason: 为什么
            expected_impact: 预期影响
            affected_modules: 影响哪些模块
            related_knowledge: 涉及哪些知识
            prerequisites: 前置条件
            risks: 风险
            success_criteria: 成功标准

        Returns:
            创建的Intent
        """
        if affected_modules is None:
            affected_modules = []
        if related_knowledge is None:
            related_knowledge = []
        if prerequisites is None:
            prerequisites = []
        if risks is None:
            risks = []
        if success_criteria is None:
            success_criteria = []

        intent_id = f"INTENT-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        intent = Intent(
            id=intent_id,
            operator=operator,
            action_type=action_type,
            problem=problem,
            reason=reason,
            expected_impact=expected_impact,
            affected_modules=affected_modules,
            related_knowledge=related_knowledge,
            prerequisites=prerequisites,
            risks=risks,
            success_criteria=success_criteria,
            created=datetime.now().isoformat(),
            status="pending",
        )

        self.intents[intent_id] = intent
        self._save_intent(intent)

        logger.info(f"创建意图: {intent_id}")
        return intent

    def _save_intent(self, intent: Intent):
        """保存意图"""
        try:
            with open(self.intents_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": intent.id,
                    "operator": intent.operator,
                    "action_type": intent.action_type,
                    "problem": intent.problem,
                    "reason": intent.reason,
                    "expected_impact": intent.expected_impact,
                    "affected_modules": intent.affected_modules,
                    "related_knowledge": intent.related_knowledge,
                    "prerequisites": intent.prerequisites,
                    "risks": intent.risks,
                    "success_criteria": intent.success_criteria,
                    "created": intent.created,
                    "status": intent.status,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存意图失败: {e}")

    def evaluate_intent(self, intent_id: str, decision: str, reasoning: str, modified_intent: Dict = None) -> IntentRecord:
        """
        评估意图

        Args:
            intent_id: 意图ID
            decision: 决策（approved/rejected/modified）
            reasoning: 决策理由
            modified_intent: 如果被修改，修改后的意图

        Returns:
            IntentRecord
        """
        intent = self.intents.get(intent_id)
        if not intent:
            return None

        record = IntentRecord(
            intent_id=intent_id,
            decision=decision,
            reasoning=reasoning,
            modified_intent=modified_intent or {},
            evaluated_by="governor",
            timestamp=datetime.now().isoformat(),
        )

        # 更新意图状态
        intent.status = decision
        if modified_intent:
            intent.problem = modified_intent.get("problem", intent.problem)
            intent.reason = modified_intent.get("reason", intent.reason)
            intent.expected_impact = modified_intent.get("expected_impact", intent.expected_impact)

        self._save_intent(intent)
        self._save_evaluation(record)

        logger.info(f"评估意图: {intent_id} -> {decision}")
        return record

    def _save_evaluation(self, record: IntentRecord):
        """保存评估记录"""
        try:
            with open(self.evaluations_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "intent_id": record.intent_id,
                    "decision": record.decision,
                    "reasoning": record.reasoning,
                    "modified_intent": record.modified_intent,
                    "evaluated_by": record.evaluated_by,
                    "timestamp": record.timestamp,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存意图评估失败: {e}")

    def get_intent(self, intent_id: str) -> Optional[Intent]:
        """获取意图"""
        return self.intents.get(intent_id)

    def get_pending_intents(self) -> List[Intent]:
        """获取待处理意图"""
        return [i for i in self.intents.values() if i.status == "pending"]

    def get_intent_history(self, operator: str = None, limit: int = 50) -> List[Dict]:
        """获取意图历史"""
        history = []

        try:
            with open(self.intents_file, "r", encoding="utf-8") as f:
                lines = f.readlines()

            for line in lines[-limit:]:
                try:
                    intent = json.loads(line.strip())
                    if operator is None or intent.get("operator") == operator:
                        history.append(intent)
                except Exception:
                    continue
        except Exception as e:
            logger.error(f"读取意图历史失败: {e}")

        return history
