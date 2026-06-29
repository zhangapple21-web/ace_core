"""
Policy（治理策略）

核心职责：
    定义Governor按什么规则做判断。

    这些规则可以版本化、可调整。

    Policy = Version + Weight + Threshold

    例如：
        Policy: Novelty
        Version: v1
        Weight: 0.3
        Threshold: 0.7
        允许进入Repository

    Governor只是执行。
    Policy才是真正文明。

设计原则：
    - Policy可以被修改（不像Constitution那么严格）
    - Policy有版本号，可以回滚
    - Policy决定Governor的判断标准
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PolicyRule:
    """策略规则"""
    id: str
    name: str
    description: str
    version: str
    metric: str  # novelty / evidence_quality / confidence / maturity / duplication_risk
    operator: str  # gt / lt / gte / lte / eq / between
    threshold: float
    weight: float  # 在决策中的权重
    is_active: bool = True
    created: str = ""
    updated: str = ""


@dataclass
class PolicyEvaluation:
    """策略评估结果"""
    policy_id: str
    metric_name: str
    actual_value: float
    threshold: float
    operator: str
    passed: bool
    weight: float
    weighted_score: float


class Policy:
    """
    治理策略

    Governor执行时依赖的规则集合

    结构：
        Policy
            ├── NoveltyPolicy (创新度)
            ├── EvidencePolicy (证据质量)
            ├── ConfidencePolicy (置信度)
            ├── MaturityPolicy (成熟度)
            └── DeduplicationPolicy (去重)
    """

    def __init__(self, data_dir: str):
        """
        初始化策略

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.policy_dir = self.data_dir / "policy"
        self.policy_dir.mkdir(parents=True, exist_ok=True)

        self.policies_file = self.policy_dir / "policies.jsonl"
        self.versions_file = self.policy_dir / "policy_versions.jsonl"
        self.evaluations_file = self.policy_dir / "evaluations.jsonl"

        self.policies: Dict[str, PolicyRule] = {}

        # 加载已有策略
        self._load_policies()

        # 如果没有策略，初始化默认策略
        if not self.policies:
            self._initialize_default_policies()

    def _load_policies(self):
        """加载策略"""
        if not self.policies_file.exists():
            return

        try:
            with open(self.policies_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        policy = PolicyRule(
                            id=data["id"],
                            name=data["name"],
                            description=data["description"],
                            version=data.get("version", "v1"),
                            metric=data.get("metric", ""),
                            operator=data.get("operator", "gte"),
                            threshold=data.get("threshold", 0.5),
                            weight=data.get("weight", 1.0),
                            is_active=data.get("is_active", True),
                            created=data.get("created", ""),
                            updated=data.get("updated", ""),
                        )
                        self.policies[policy.id] = policy
                    except Exception:
                        continue
            logger.info(f"加载了 {len(self.policies)} 条策略")
        except Exception as e:
            logger.error(f"加载策略失败: {e}")

    def _initialize_default_policies(self):
        """初始化默认策略"""
        default_policies = [
            {
                "id": "novelty",
                "name": "创新度策略",
                "description": "知识必须有一定的创新度，不能完全是重复",
                "version": "v1",
                "metric": "novelty",
                "operator": "gte",
                "threshold": 0.5,
                "weight": 0.3,
            },
            {
                "id": "evidence_quality",
                "name": "证据质量策略",
                "description": "知识必须有足够的证据支撑",
                "version": "v1",
                "metric": "evidence_quality",
                "operator": "gte",
                "threshold": 0.3,
                "weight": 0.25,
            },
            {
                "id": "confidence",
                "name": "置信度策略",
                "description": "知识必须有足够的置信度",
                "version": "v1",
                "metric": "confidence",
                "operator": "gte",
                "threshold": 0.3,
                "weight": 0.2,
            },
            {
                "id": "maturity",
                "name": "成熟度策略",
                "description": "知识需要有一定的成熟度",
                "version": "v1",
                "metric": "maturity",
                "operator": "gte",
                "threshold": 0.2,
                "weight": 0.15,
            },
            {
                "id": "deduplication",
                "name": "去重策略",
                "description": "高度重复的知识应该被拒绝或合并",
                "version": "v1",
                "metric": "duplication_risk",
                "operator": "lt",
                "threshold": 0.9,
                "weight": 0.1,
            },
        ]

        now = datetime.now().isoformat()
        for p in default_policies:
            policy = PolicyRule(
                id=p["id"],
                name=p["name"],
                description=p["description"],
                version=p["version"],
                metric=p["metric"],
                operator=p["operator"],
                threshold=p["threshold"],
                weight=p["weight"],
                is_active=True,
                created=now,
                updated=now,
            )
            self.policies[p["id"]] = policy
            self._save_policy(policy)

        logger.info(f"初始化了 {len(self.policies)} 条默认策略")

    def _save_policy(self, policy: PolicyRule):
        """保存策略到文件"""
        try:
            with open(self.policies_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": policy.id,
                    "name": policy.name,
                    "description": policy.description,
                    "version": policy.version,
                    "metric": policy.metric,
                    "operator": policy.operator,
                    "threshold": policy.threshold,
                    "weight": policy.weight,
                    "is_active": policy.is_active,
                    "created": policy.created,
                    "updated": policy.updated,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存策略失败: {e}")

    def evaluate(self, criteria: Dict[str, float]) -> tuple[bool, List[PolicyEvaluation], float]:
        """
        评估知识是否符合策略

        Args:
            criteria: 评估指标字典 {metric_name: value}

        Returns:
            (是否通过所有策略, 评估结果列表, 总加权分数)
        """
        evaluations = []
        total_weight = 0.0
        weighted_sum = 0.0

        for policy_id, policy in self.policies.items():
            if not policy.is_active:
                continue

            actual_value = criteria.get(policy.metric, 0.0)
            passed = self._check_condition(actual_value, policy.operator, policy.threshold)

            evaluation = PolicyEvaluation(
                policy_id=policy_id,
                metric_name=policy.metric,
                actual_value=actual_value,
                threshold=policy.threshold,
                operator=policy.operator,
                passed=passed,
                weight=policy.weight,
                weighted_score=policy.weight if passed else 0.0,
            )
            evaluations.append(evaluation)

            total_weight += policy.weight
            weighted_sum += evaluation.weighted_score

        # 计算总分数
        total_score = weighted_sum / total_weight if total_weight > 0 else 0.0

        # 所有必须通过的策略都通过才算通过
        all_passed = all(e.passed for e in evaluations)

        # 保存评估记录
        self._save_evaluation(criteria, evaluations, total_score)

        return all_passed, evaluations, total_score

    def _check_condition(self, value: float, operator: str, threshold: float) -> bool:
        """检查条件是否满足"""
        if operator == "gt":
            return value > threshold
        elif operator == "lt":
            return value < threshold
        elif operator == "gte":
            return value >= threshold
        elif operator == "lte":
            return value <= threshold
        elif operator == "eq":
            return value == threshold
        elif operator == "between":
            return 0 <= value <= threshold
        return False

    def _save_evaluation(self, criteria: Dict, evaluations: List[PolicyEvaluation], total_score: float):
        """保存评估记录"""
        try:
            with open(self.evaluations_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "criteria": criteria,
                    "evaluations": [
                        {
                            "policy_id": e.policy_id,
                            "metric_name": e.metric_name,
                            "actual_value": e.actual_value,
                            "threshold": e.threshold,
                            "operator": e.operator,
                            "passed": e.passed,
                            "weight": e.weight,
                            "weighted_score": e.weighted_score,
                        }
                        for e in evaluations
                    ],
                    "total_score": total_score,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存评估记录失败: {e}")

    def update_policy(
        self,
        policy_id: str,
        new_threshold: float = None,
        new_weight: float = None,
        new_operator: str = None
    ) -> bool:
        """
        更新策略

        Args:
            policy_id: 策略ID
            new_threshold: 新阈值（可选）
            new_weight: 新权重（可选）
            new_operator: 新操作符（可选）

        Returns:
            是否成功
        """
        policy = self.policies.get(policy_id)
        if not policy:
            return False

        # 记录版本变更
        old_version = policy.version
        version_parts = policy.version.replace("v", "").split(".")
        new_minor = int(version_parts[0]) + 1
        policy.version = f"v{new_minor}.0"

        # 更新策略
        if new_threshold is not None:
            policy.threshold = new_threshold
        if new_weight is not None:
            policy.weight = new_weight
        if new_operator is not None:
            policy.operator = new_operator

        policy.updated = datetime.now().isoformat()

        # 保存新版本
        self._save_policy(policy)

        # 记录版本变更
        self._save_version_change(policy_id, old_version, policy.version, {
            "threshold": new_threshold,
            "weight": new_weight,
            "operator": new_operator,
        })

        return True

    def _save_version_change(self, policy_id: str, old_version: str, new_version: str, changes: Dict):
        """保存版本变更"""
        try:
            with open(self.versions_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "policy_id": policy_id,
                    "old_version": old_version,
                    "new_version": new_version,
                    "changes": changes,
                    "timestamp": datetime.now().isoformat(),
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存版本变更失败: {e}")

    def get_policy(self, policy_id: str) -> Optional[PolicyRule]:
        """获取策略"""
        return self.policies.get(policy_id)

    def get_all_policies(self) -> List[PolicyRule]:
        """获取所有策略"""
        return list(self.policies.values())

    def get_active_policies(self) -> List[PolicyRule]:
        """获取所有活跃策略"""
        return [p for p in self.policies.values() if p.is_active]

    def get_policy_summary(self) -> Dict[str, Any]:
        """获取策略摘要"""
        policies = list(self.policies.values())
        active = [p for p in policies if p.is_active]

        return {
            "total_policies": len(policies),
            "active_policies": len(active),
            "by_metric": {p.metric: p.id for p in active},
            "total_weight": sum(p.weight for p in active),
        }
