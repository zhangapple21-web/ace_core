"""
Governor Protocol — ACE 治理协议

借鉴 public-apis CONTRIBUTING.md 的治理思路：
- 准入标准：什么东西有资格进入
- 提交规则：怎么提交才合规
- 拒绝标准：什么情况直接拒
- 质量保证：怎么确保质量
- 决策权限：谁有权力做什么

这是治理层的"宪法实施细则"。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════════════════
# 准入标准（Admission Criteria）
# ═══════════════════════════════════════════════════════════════════════════

class AdmissionCriterion(Enum):
    """准入标准枚举"""
    HAS_EVIDENCE = "has_evidence"
    HAS_VALIDATION = "has_validation"
    GOVERNOR_APPROVAL = "governor_approval"
    NOT_HYPOTHESIS_TO_FACT = "not_hypothesis_to_fact"


@dataclass
class AdmissionCriteriaResult:
    """准入标准检查结果"""
    passed: bool
    criteria: Dict[str, bool] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class AdmissionCriteria:
    """
    准入标准
    
    一个知识单元要进入文明，必须满足：
    1. 必须有 Evidence
    2. 必须经过 Validation
    3. 必须通过 Governor 审批
    4. 不得是 Hypothesis 直接变 Fact
    """

    CRITERIA = {
        AdmissionCriterion.HAS_EVIDENCE: "必须有 Evidence",
        AdmissionCriterion.HAS_VALIDATION: "必须经过 Validation",
        AdmissionCriterion.GOVERNOR_APPROVAL: "必须通过 Governor 审批",
        AdmissionCriterion.NOT_HYPOTHESIS_TO_FACT: "不得是 Hypothesis 直接变 Fact",
    }

    def check(self, concept: Dict[str, Any]) -> AdmissionCriteriaResult:
        """
        检查概念是否符合准入标准
        
        Args:
            concept: 待检查的知识单元
            
        Returns:
            AdmissionCriteriaResult
        """
        result = AdmissionCriteriaResult(passed=True)

        # 1. 检查是否有 Evidence
        has_evidence = self._check_has_evidence(concept)
        result.criteria[AdmissionCriterion.HAS_EVIDENCE.value] = has_evidence
        if not has_evidence:
            result.passed = False
            result.failures.append("缺乏 Evidence")
            result.details["evidence_issue"] = "知识单元没有关联任何证据"

        # 2. 检查是否经过 Validation
        has_validation = self._check_has_validation(concept)
        result.criteria[AdmissionCriterion.HAS_VALIDATION.value] = has_validation
        if not has_validation:
            result.passed = False
            result.failures.append("未经过 Validation")
            result.details["validation_issue"] = "知识单元没有验证记录"

        # 3. 检查是否通过 Governor 审批
        has_governor_approval = self._check_governor_approval(concept)
        result.criteria[AdmissionCriterion.GOVERNOR_APPROVAL.value] = has_governor_approval
        if not has_governor_approval:
            result.passed = False
            result.failures.append("未通过 Governor 审批")
            result.details["governor_issue"] = "知识单元没有 Governor 的审批记录"

        # 4. 检查是否 Hypothesis 直接变 Fact
        not_hypothesis_to_fact = self._check_not_hypothesis_to_fact(concept)
        result.criteria[AdmissionCriterion.NOT_HYPOTHESIS_TO_FACT.value] = not_hypothesis_to_fact
        if not not_hypothesis_to_fact:
            result.passed = False
            result.failures.append("Hypothesis 直接变 Fact")
            result.details["status_issue"] = "不能从 Hypothesis 直接跳到 Fact，必须经过 Validation 阶段"

        return result

    def _check_has_evidence(self, concept: Dict[str, Any]) -> bool:
        """检查是否有 Evidence"""
        evidence = concept.get("evidence", [])
        evidence_ids = concept.get("evidence_ids", [])
        return bool(evidence) or bool(evidence_ids)

    def _check_has_validation(self, concept: Dict[str, Any]) -> bool:
        """检查是否经过 Validation"""
        validation_status = concept.get("validation_status", "")
        validated = concept.get("validated", False)
        validation_history = concept.get("validation_history", [])
        return bool(validation_status) or validated or bool(validation_history)

    def _check_governor_approval(self, concept: Dict[str, Any]) -> bool:
        """检查是否通过 Governor 审批"""
        governor_approved = concept.get("governor_approved", False)
        approval_record = concept.get("governor_approval", "")
        decision = concept.get("governor_decision", "")
        return governor_approved or bool(approval_record) or decision == "approved"

    def _check_not_hypothesis_to_fact(self, concept: Dict[str, Any]) -> bool:
        """检查是否 Hypothesis 直接变 Fact"""
        status = concept.get("status", "").lower()
        previous_status = concept.get("previous_status", "").lower()

        if status == "fact" and previous_status == "hypothesis":
            return False

        status_history = concept.get("status_history", [])
        if status_history and len(status_history) >= 2:
            prev = status_history[-2].get("status", "").lower() if isinstance(status_history[-2], dict) else ""
            curr = status_history[-1].get("status", "").lower() if isinstance(status_history[-1], dict) else ""
            if curr == "fact" and prev == "hypothesis":
                return False

        return True


# ═══════════════════════════════════════════════════════════════════════════
# 提交规则（Submission Rules）
# ═══════════════════════════════════════════════════════════════════════════

class SubmissionRule(Enum):
    """提交规则枚举"""
    SINGLE_KNOWLEDGE_UNIT = "single_knowledge_unit"
    CLEAR_CATEGORY = "clear_category"
    NO_DUPLICATE = "no_duplicate"


@dataclass
class SubmissionRulesResult:
    """提交规则检查结果"""
    passed: bool
    rules: Dict[str, bool] = field(default_factory=dict)
    failures: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)


class SubmissionRules:
    """
    提交规则
    
    每个 PR（提交）必须满足：
    1. 每个 PR 只提交一个知识单元
    2. 必须有明确的分类
    3. 不得重复已有知识
    """

    RULES = {
        SubmissionRule.SINGLE_KNOWLEDGE_UNIT: "每个 PR 只提交一个知识单元",
        SubmissionRule.CLEAR_CATEGORY: "必须有明确的分类",
        SubmissionRule.NO_DUPLICATE: "不得重复已有知识",
    }

    def __init__(self, existing_knowledge: Optional[List[Dict[str, Any]]] = None):
        self.existing_knowledge = existing_knowledge or []

    def check(self, concept: Dict[str, Any]) -> SubmissionRulesResult:
        """
        检查提交是否符合规则
        
        Args:
            concept: 待提交的知识单元
            
        Returns:
            SubmissionRulesResult
        """
        result = SubmissionRulesResult(passed=True)

        # 1. 检查是否只提交一个知识单元
        single_unit = self._check_single_knowledge_unit(concept)
        result.rules[SubmissionRule.SINGLE_KNOWLEDGE_UNIT.value] = single_unit
        if not single_unit:
            result.passed = False
            result.failures.append("包含多个知识单元")
            result.details["unit_count"] = concept.get("knowledge_unit_count", "unknown")

        # 2. 检查是否有明确的分类
        clear_category = self._check_clear_category(concept)
        result.rules[SubmissionRule.CLEAR_CATEGORY.value] = clear_category
        if not clear_category:
            result.passed = False
            result.failures.append("没有明确的分类")
            result.details["category_issue"] = "知识单元缺少 category 或 type 字段"

        # 3. 检查是否重复已有知识
        no_duplicate = self._check_no_duplicate(concept)
        result.rules[SubmissionRule.NO_DUPLICATE.value] = no_duplicate
        if not no_duplicate:
            result.passed = False
            result.failures.append("重复已有知识")
            result.details["duplicate_issue"] = "发现与现有知识高度相似"

        return result

    def _check_single_knowledge_unit(self, concept: Dict[str, Any]) -> bool:
        """检查是否只提交一个知识单元"""
        unit_count = concept.get("knowledge_unit_count", 1)
        if isinstance(unit_count, int) and unit_count > 1:
            return False
        if isinstance(concept.get("items"), list) and len(concept["items"]) > 1:
            return False
        return True

    def _check_clear_category(self, concept: Dict[str, Any]) -> bool:
        """检查是否有明确的分类"""
        category = concept.get("category", "")
        concept_type = concept.get("type", "")
        concept_class = concept.get("class", "")
        return bool(category) or bool(concept_type) or bool(concept_class)

    def _check_no_duplicate(self, concept: Dict[str, Any]) -> bool:
        """检查是否重复已有知识"""
        if not self.existing_knowledge:
            return True

        title = concept.get("title", "").lower()
        concept_id = concept.get("id", "")

        for existing in self.existing_knowledge:
            existing_title = existing.get("title", "").lower()
            existing_id = existing.get("id", "")

            if concept_id and existing_id and concept_id == existing_id:
                return False

            if title and existing_title and title == existing_title:
                return False

            if title and existing_title and (title in existing_title or existing_title in title):
                    similarity = self._calculate_similarity(title, existing_title)
                    if similarity > 0.8:
                        return False

        return True

    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """计算两个字符串的相似度"""
        if not str1 or not str2:
            return 0.0

        words1 = set(str1.replace("-", " ").replace("_", " ").split())
        words2 = set(str2.replace("-", " ").replace("_", " ").split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 拒绝标准（Rejection Reasons）
# ═══════════════════════════════════════════════════════════════════════════

class RejectionReason(Enum):
    """拒绝原因枚举"""
    LACK_OF_EVIDENCE = "lack_of_evidence"
    VALIDATION_FAILED = "validation_failed"
    VIOLATES_LAW = "violates_law"
    FORMAT_INCORRECT = "format_incorrect"
    LOW_ROI = "low_roi"
    DUPLICATE = "duplicate"


@dataclass
class RejectionEvaluation:
    """拒绝评估结果"""
    should_reject: bool
    reasons: List[str] = field(default_factory=list)
    primary_reason: Optional[str] = None
    severity: str = "medium"
    suggestions: List[str] = field(default_factory=list)


class RejectionCriteria:
    """
    拒绝标准
    
    出现以下情况直接拒绝：
    1. 缺乏 Evidence
    2. Validation 失败
    3. 违反已有 Law
    4. 格式不符合
    5. ROI 太低
    6. 重复已知
    """

    REASONS = {
        RejectionReason.LACK_OF_EVIDENCE: "缺乏 Evidence",
        RejectionReason.VALIDATION_FAILED: "Validation 失败",
        RejectionReason.VIOLATES_LAW: "违反已有 Law",
        RejectionReason.FORMAT_INCORRECT: "格式不符合",
        RejectionReason.LOW_ROI: "ROI 太低",
        RejectionReason.DUPLICATE: "重复已知",
    }

    def __init__(self, existing_laws: Optional[List[Dict[str, Any]]] = None,
                 existing_knowledge: Optional[List[Dict[str, Any]]] = None,
                 roi_threshold: float = 0.3):
        self.existing_laws = existing_laws or []
        self.existing_knowledge = existing_knowledge or []
        self.roi_threshold = roi_threshold

    def evaluate(self, concept: Dict[str, Any]) -> RejectionEvaluation:
        """
        评估是否应该拒绝
        
        Args:
            concept: 待评估的知识单元
            
        Returns:
            RejectionEvaluation
        """
        result = RejectionEvaluation(should_reject=False)

        # 1. 检查是否缺乏 Evidence
        if self._check_lack_of_evidence(concept):
            result.should_reject = True
            result.reasons.append(RejectionReason.LACK_OF_EVIDENCE.value)
            result.suggestions.append("补充 Evidence 后重新提交")

        # 2. 检查 Validation 是否失败
        if self._check_validation_failed(concept):
            result.should_reject = True
            result.reasons.append(RejectionReason.VALIDATION_FAILED.value)
            result.suggestions.append("修复 Validation 问题后重新提交")

        # 3. 检查是否违反已有 Law
        if self._check_violates_law(concept):
            result.should_reject = True
            result.reasons.append(RejectionReason.VIOLATES_LAW.value)
            result.suggestions.append("修改内容以符合现有 Law")

        # 4. 检查格式是否符合
        if self._check_format_incorrect(concept):
            result.should_reject = True
            result.reasons.append(RejectionReason.FORMAT_INCORRECT.value)
            result.suggestions.append("按照规范格式重新提交")

        # 5. 检查 ROI 是否太低
        if self._check_low_roi(concept):
            result.should_reject = True
            result.reasons.append(RejectionReason.LOW_ROI.value)
            result.suggestions.append("提升价值或降低维护成本")

        # 6. 检查是否重复已知
        if self._check_duplicate(concept):
            result.should_reject = True
            result.reasons.append(RejectionReason.DUPLICATE.value)
            result.suggestions.append("使用现有知识或与现有知识合并")

        if result.reasons:
            result.primary_reason = result.reasons[0]
            if len(result.reasons) >= 3:
                result.severity = "high"
            elif len(result.reasons) == 2:
                result.severity = "medium"
            else:
                result.severity = "low"

        return result

    def _check_lack_of_evidence(self, concept: Dict[str, Any]) -> bool:
        """检查是否缺乏 Evidence"""
        evidence = concept.get("evidence", [])
        evidence_ids = concept.get("evidence_ids", [])
        return not evidence and not evidence_ids

    def _check_validation_failed(self, concept: Dict[str, Any]) -> bool:
        """检查 Validation 是否失败"""
        validation_status = concept.get("validation_status", "").lower()
        return validation_status == "failed" or validation_status == "rejected"

    def _check_violates_law(self, concept: Dict[str, Any]) -> bool:
        """检查是否违反已有 Law"""
        if not self.existing_laws:
            return False

        content = concept.get("content", "") + concept.get("description", "") + concept.get("title", "")
        content_lower = content.lower()

        for law in self.existing_laws:
            law_content = law.get("content", "").lower()
            law_name = law.get("name", "").lower()
            prohibited = law.get("prohibited", [])

            if law_content and law_content in content_lower:
                if law.get("type") == "constraint" or law.get("is_prohibition", False):
                    return True

            for item in prohibited:
                if item.lower() in content_lower:
                    return True

        return False

    def _check_format_incorrect(self, concept: Dict[str, Any]) -> bool:
        """检查格式是否符合"""
        required_fields = ["title", "status"]
        missing = [f for f in required_fields if not concept.get(f)]

        if missing:
            return True

        title = concept.get("title", "")
        if not title or len(str(title)) < 2:
            return True

        return False

    def _check_low_roi(self, concept: Dict[str, Any]) -> bool:
        """检查 ROI 是否太低"""
        roi = concept.get("roi", 0.0)
        if isinstance(roi, (int, float)) and roi < self.roi_threshold:
            return True

        value = concept.get("value", 0.0)
        cost = concept.get("maintenance_cost", 1.0)
        if isinstance(value, (int, float)) and isinstance(cost, (int, float)) and cost > 0:
            calculated_roi = value / cost
            if calculated_roi < self.roi_threshold:
                return True

        return False

    def _check_duplicate(self, concept: Dict[str, Any]) -> bool:
        """检查是否重复已知"""
        if not self.existing_knowledge:
            return False

        title = concept.get("title", "").lower()
        concept_id = concept.get("id", "")

        for existing in self.existing_knowledge:
            existing_title = existing.get("title", "").lower()
            existing_id = existing.get("id", "")

            if concept_id and existing_id and concept_id == existing_id:
                return True

            if title and existing_title and title == existing_title:
                return True

        return False


# ═══════════════════════════════════════════════════════════════════════════
# 质量保证（Quality Assurance）
# ═══════════════════════════════════════════════════════════════════════════

class QualityCheck(Enum):
    """质量检查项枚举"""
    EVIDENCE_VALIDITY = "evidence_validity"
    VALIDATOR_REVIEW = "validator_review"
    GOVERNOR_ROI = "governor_roi"


@dataclass
class QualityAssessment:
    """质量评估结果"""
    score: float
    checks: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    passed: bool = False
    issues: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)


class QualityAssurance:
    """
    质量保证
    
    三层质量把关：
    1. Evidence 有效性检查
    2. Validator 审查
    3. Governor ROI 评估
    """

    CHECKS = {
        QualityCheck.EVIDENCE_VALIDITY: "Evidence 有效性检查",
        QualityCheck.VALIDATOR_REVIEW: "Validator 审查",
        QualityCheck.GOVERNOR_ROI: "Governor ROI 评估",
    }

    def __init__(self, evidence_registry=None, min_quality_score: float = 0.6):
        self.evidence_registry = evidence_registry
        self.min_quality_score = min_quality_score

    def evaluate(self, concept: Dict[str, Any]) -> QualityAssessment:
        """
        评估知识单元质量
        
        Args:
            concept: 待评估的知识单元
            
        Returns:
            QualityAssessment
        """
        result = QualityAssessment(score=0.0)
        check_scores = []

        # 1. Evidence 有效性检查
        evidence_result = self._check_evidence_validity(concept)
        result.checks[QualityCheck.EVIDENCE_VALIDITY.value] = evidence_result
        check_scores.append(evidence_result["score"])
        if not evidence_result["passed"]:
            result.issues.append("Evidence 有效性不足")
            result.improvements.extend(evidence_result.get("suggestions", []))

        # 2. Validator 审查
        validator_result = self._check_validator_review(concept)
        result.checks[QualityCheck.VALIDATOR_REVIEW.value] = validator_result
        check_scores.append(validator_result["score"])
        if not validator_result["passed"]:
            result.issues.append("Validator 审查未通过")
            result.improvements.extend(validator_result.get("suggestions", []))

        # 3. Governor ROI 评估
        roi_result = self._check_governor_roi(concept)
        result.checks[QualityCheck.GOVERNOR_ROI.value] = roi_result
        check_scores.append(roi_result["score"])
        if not roi_result["passed"]:
            result.issues.append("ROI 评估不达标")
            result.improvements.extend(roi_result.get("suggestions", []))

        if check_scores:
            result.score = sum(check_scores) / len(check_scores)

        result.passed = result.score >= self.min_quality_score

        return result

    def _check_evidence_validity(self, concept: Dict[str, Any]) -> Dict[str, Any]:
        """检查 Evidence 有效性"""
        evidence = concept.get("evidence", [])
        evidence_ids = concept.get("evidence_ids", [])
        score = 0.0
        passed = False
        suggestions = []

        if isinstance(evidence, list):
            if len(evidence) >= 3:
                score += 0.4
            elif len(evidence) >= 1:
                score += 0.2
            elif len(evidence_ids) >= 1:
                score += 0.2

            for ev in evidence:
                if isinstance(ev, dict):
                    if ev.get("source") and ev.get("source") not in ["unknown", ""]:
                        score += 0.15
                        break
                elif isinstance(ev, str) and ev:
                    score += 0.1
                    break

            for ev in evidence:
                if isinstance(ev, dict):
                    confidence = ev.get("confidence", 0.0)
                    if isinstance(confidence, (int, float)) and confidence >= 0.7:
                        score += 0.15
                        break

        if score >= 0.5:
            passed = True
        else:
            suggestions.append("增加更多高质量的 Evidence")
            suggestions.append("确保 Evidence 有明确的来源")
            suggestions.append("提升 Evidence 的置信度")

        return {
            "score": min(1.0, score),
            "passed": passed,
            "evidence_count": len(evidence) if isinstance(evidence, list) else 0,
            "suggestions": suggestions,
        }

    def _check_validator_review(self, concept: Dict[str, Any]) -> Dict[str, Any]:
        """检查 Validator 审查"""
        score = 0.0
        passed = False
        suggestions = []

        validation_status = concept.get("validation_status", "")
        if validation_status:
            if validation_status.lower() == "passed":
                score += 0.5
            elif validation_status.lower() == "validated":
                score += 0.4
            elif validation_status.lower() == "pending":
                score += 0.2

        validated_by = concept.get("validated_by", "")
        if validated_by:
            score += 0.2

        validation_history = concept.get("validation_history", [])
        if isinstance(validation_history, list) and len(validation_history) > 0:
            score += 0.2
            if len(validation_history) >= 2:
                score += 0.1

        test_coverage = concept.get("test_coverage", 0.0)
        if isinstance(test_coverage, (int, float)):
            score += min(0.2, test_coverage * 0.2)

        if score >= 0.5:
            passed = True
        else:
            suggestions.append("完成 Validation 流程")
            suggestions.append("添加测试用例验证")
            suggestions.append("邀请 Validator 审查")

        return {
            "score": min(1.0, score),
            "passed": passed,
            "validation_status": validation_status,
            "suggestions": suggestions,
        }

    def _check_governor_roi(self, concept: Dict[str, Any]) -> Dict[str, Any]:
        """检查 Governor ROI 评估"""
        score = 0.0
        passed = False
        suggestions = []

        roi = concept.get("roi", 0.0)
        if isinstance(roi, (int, float)):
            score += min(0.4, roi * 0.4)

        value = concept.get("value", 0.0)
        if isinstance(value, (int, float)):
            score += min(0.2, value * 0.2)

        impact = concept.get("impact", "")
        if impact:
            if impact == "high":
                score += 0.2
            elif impact == "medium":
                score += 0.1

        reuse_potential = concept.get("reuse_potential", "")
        if reuse_potential:
            if reuse_potential == "high":
                score += 0.2
            elif reuse_potential == "medium":
                score += 0.1

        maintenance_cost = concept.get("maintenance_cost", "")
        if maintenance_cost == "low":
            score += 0.1

        if score >= 0.5:
            passed = True
        else:
            suggestions.append("提升知识单元的价值")
            suggestions.append("降低维护成本")
            suggestions.append("提高复用潜力")

        return {
            "score": min(1.0, score),
            "passed": passed,
            "roi_score": min(1.0, score),
            "suggestions": suggestions,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 决策权限（Decision Authority）
# ═══════════════════════════════════════════════════════════════════════════

class AuthorityLevel(Enum):
    """权限级别枚举"""
    ANYONE = "anyone"
    GOVERNOR = "governor"
    EVOLUTION = "evolution"


class DecisionAuthority:
    """
    决策权限
    
    三级权限体系：
    - anyone: 可以提交
    - governor: 决定是否进入
    - evolution: 决定演化方向
    """

    PERMISSIONS = {
        AuthorityLevel.ANYONE: [
            "submit",
            "comment",
            "suggest",
            "provide_evidence",
        ],
        AuthorityLevel.GOVERNOR: [
            "approve",
            "reject",
            "request_changes",
            "merge",
            "classify",
            "prioritize",
        ],
        AuthorityLevel.EVOLUTION: [
            "set_direction",
            "define_strategy",
            "approve_evolution",
            "archive_knowledge",
            "define_criteria",
        ],
    }

    def __init__(self):
        self._permissions = {}
        for level, perms in self.PERMISSIONS.items():
            self._permissions[level.value] = set(perms)

    def can(self, actor: str, action: str) -> bool:
        """
        检查某个角色是否可以执行某个操作
        
        Args:
            actor: 角色名称（anyone/governor/evolution）
            action: 操作名称
            
        Returns:
            是否有权限
        """
        actor_lower = actor.lower()

        if actor_lower in self._permissions:
            return action in self._permissions[actor_lower]

        return False

    def get_permissions(self, actor: str) -> List[str]:
        """获取某个角色的所有权限"""
        actor_lower = actor.lower()
        if actor_lower in self._permissions:
            return sorted(list(self._permissions[actor_lower]))
        return []

    def get_authority_level(self, action: str) -> Optional[str]:
        """获取执行某个操作需要的权限级别"""
        for level, perms in self.PERMISSIONS.items():
            if action in perms:
                return level.value
        return None

    def can_submit(self, actor: str) -> bool:
        """检查是否可以提交"""
        return self.can(actor, "submit")

    def can_approve(self, actor: str) -> bool:
        """检查是否可以审批"""
        return self.can(actor, "approve")

    def can_reject(self, actor: str) -> bool:
        """检查是否可以拒绝"""
        return self.can(actor, "reject")

    def can_set_direction(self, actor: str) -> bool:
        """检查是否可以设置演化方向"""
        return self.can(actor, "set_direction")


# ═══════════════════════════════════════════════════════════════════════════
# ProtocolEngine — 协议引擎
# ═══════════════════════════════════════════════════════════════════════════

class ProtocolDecision(Enum):
    """协议决策结果"""
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_REVISION = "needs_revision"
    PENDING = "pending"


@dataclass
class ProtocolResult:
    """协议检查总结果"""
    decision: str
    admission: AdmissionCriteriaResult = None
    submission: SubmissionRulesResult = None
    rejection: RejectionEvaluation = None
    quality: QualityAssessment = None
    reasons: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class ProtocolEngine:
    """
    协议引擎
    
    整合所有治理协议，提供统一的检查接口：
    - check_admission: 检查准入标准
    - check_submission: 检查提交规则
    - evaluate_rejection: 评估拒绝原因
    - evaluate_quality: 质量评估
    - get_decision: 获取最终决策
    """

    def __init__(
        self,
        existing_laws: Optional[List[Dict[str, Any]]] = None,
        existing_knowledge: Optional[List[Dict[str, Any]]] = None,
        evidence_registry=None,
        roi_threshold: float = 0.3,
        min_quality_score: float = 0.6,
    ):
        self.admission_criteria = AdmissionCriteria()
        self.submission_rules = SubmissionRules(existing_knowledge)
        self.rejection_criteria = RejectionCriteria(
            existing_laws=existing_laws,
            existing_knowledge=existing_knowledge,
            roi_threshold=roi_threshold,
        )
        self.quality_assurance = QualityAssurance(
            evidence_registry=evidence_registry,
            min_quality_score=min_quality_score,
        )
        self.decision_authority = DecisionAuthority()

    def check_admission(self, concept: Dict[str, Any]) -> AdmissionCriteriaResult:
        """
        检查是否符合准入标准
        
        Args:
            concept: 待检查的知识单元
            
        Returns:
            AdmissionCriteriaResult
        """
        return self.admission_criteria.check(concept)

    def check_submission(self, concept: Dict[str, Any]) -> SubmissionRulesResult:
        """
        检查提交规则
        
        Args:
            concept: 待提交的知识单元
            
        Returns:
            SubmissionRulesResult
        """
        return self.submission_rules.check(concept)

    def evaluate_rejection(self, concept: Dict[str, Any]) -> RejectionEvaluation:
        """
        评估拒绝原因
        
        Args:
            concept: 待评估的知识单元
            
        Returns:
            RejectionEvaluation
        """
        return self.rejection_criteria.evaluate(concept)

    def evaluate_quality(self, concept: Dict[str, Any]) -> QualityAssessment:
        """
        质量评估
        
        Args:
            concept: 待评估的知识单元
            
        Returns:
            QualityAssessment
        """
        return self.quality_assurance.evaluate(concept)

    def get_decision(self, concept: Dict[str, Any]) -> ProtocolResult:
        """
        获取最终决策
        
        执行完整的协议检查流程，返回最终决策：
        1. 先检查提交规则
        2. 再检查准入标准
        3. 评估拒绝原因
        4. 质量评估
        5. 综合决策
        
        Args:
            concept: 待决策的知识单元
            
        Returns:
            ProtocolResult
        """
        result = ProtocolResult(decision=ProtocolDecision.PENDING.value)

        # 1. 检查提交规则
        submission_result = self.check_submission(concept)
        result.submission = submission_result

        if not submission_result.passed:
            result.decision = ProtocolDecision.REJECTED.value
            result.reasons.extend([f"提交规则不通过: {f}" for f in submission_result.failures])
            return result

        # 2. 评估拒绝原因（先看有没有硬伤）
        rejection_result = self.evaluate_rejection(concept)
        result.rejection = rejection_result

        if rejection_result.should_reject:
            result.decision = ProtocolDecision.REJECTED.value
            result.reasons.extend([f"拒绝原因: {r}" for r in rejection_result.reasons])
            result.suggestions.extend(rejection_result.suggestions)
            return result

        # 3. 检查准入标准
        admission_result = self.check_admission(concept)
        result.admission = admission_result

        if not admission_result.passed:
            result.decision = ProtocolDecision.NEEDS_REVISION.value
            result.reasons.extend([f"准入标准不满足: {f}" for f in admission_result.failures])
            return result

        # 4. 质量评估
        quality_result = self.evaluate_quality(concept)
        result.quality = quality_result

        if not quality_result.passed:
            result.decision = ProtocolDecision.NEEDS_REVISION.value
            result.reasons.extend([f"质量不达标: {issue}" for issue in quality_result.issues])
            result.suggestions.extend(quality_result.improvements)
            return result

        # 5. 全部通过
        result.decision = ProtocolDecision.APPROVED.value
        result.reasons.append("所有检查通过")
        result.suggestions.append("可以进入文明")

        return result

    def update_existing_knowledge(self, knowledge: List[Dict[str, Any]]):
        """更新现有知识库"""
        self.submission_rules.existing_knowledge = knowledge
        self.rejection_criteria.existing_knowledge = knowledge

    def update_existing_laws(self, laws: List[Dict[str, Any]]):
        """更新现有法律库"""
        self.rejection_criteria.existing_laws = laws


# ═══════════════════════════════════════════════════════════════════════════
# Roundtable Meeting — 圆桌会议
# ═══════════════════════════════════════════════════════════════════════════
#
# 四个角色按顺序发言、质询、裁决、记录：
#
#   Researcher → Validator → Governor → Archivist
#       ↓            ↓          ↓            ↓
#    提交发现    提出质疑    做出裁决    记录结论
#
# 会议不是数据结构，是对话序列。
# 时钟不是模块，是流程。
# Cloud 是执行者，不参与投票。
# ═══════════════════════════════════════════════════════════════════════════

class RoundtableRole(Enum):
    """圆桌会议角色"""
    RESEARCHER = "researcher"
    VALIDATOR = "validator"
    GOVERNOR = "governor"
    ARCHIVIST = "archivist"
    CLOUD = "cloud"  # 执行者，不投票


@dataclass
class RoundtableStatement:
    """会议发言"""
    role: str
    content: str
    topic: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class RoundtableDecision:
    """会议决议"""
    topic: str
    decision: str  # approved / rejected / delayed / merged / revised
    confidence: float = 0.0
    reasons: List[str] = field(default_factory=list)
    evidence: List[Dict] = field(default_factory=list)
    actions: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class RoundtableRecord:
    """会议记录"""
    meeting_id: str
    topic: str
    statements: List[RoundtableStatement] = field(default_factory=list)
    decision: Optional[RoundtableDecision] = None
    archived: bool = False
    cloud_executed: bool = False
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: str = ""


class RoundtableMeeting:
    """
    圆桌会议流程引擎

    把 Researcher → Validator → Governor → Archivist 串成一个会议序列。
    每个阶段按顺序发言，Governor 做最终裁决，Archivist 记录，Cloud 执行。

    设计原则：
        - 会议是流程，不是数据结构
        - 每个角色只说自己职责内的话
        - Governor 是唯一决策者
        - Cloud 只执行，不投票
        - Archivist 只记录，不判断
    """

    def __init__(self, topic: str, ace_runtime_dir: str = None):
        self.topic = topic
        self.meeting_id = f"roundtable_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.record = RoundtableRecord(
            meeting_id=self.meeting_id,
            topic=topic,
        )
        self.runtime_dir = Path(ace_runtime_dir) if ace_runtime_dir else None
        self._current_stage = 0  # 0=准备, 1=Researcher, 2=Validator, 3=Governor, 4=Archivist, 5=Cloud, 6=结束

    # ===== 阶段1：Researcher 提交发现 =====
    def researcher_present(self, findings: Dict[str, Any]) -> str:
        """
        Researcher 发言：提交发现

        只陈述观察到的事实，不做判断。
        """
        self._current_stage = 1
        summary = findings.get("summary", findings.get("title", ""))
        evidence = findings.get("evidence", [])
        sources = findings.get("sources", [])

        content = (
            f"【发现提交】关于「{self.topic}」，我提交以下发现：\n"
            f"  核心结论：{summary}\n"
            f"  证据数量：{len(evidence)}\n"
            f"  来源：{', '.join(sources) if sources else '未标注'}"
        )

        self._add_statement("researcher", content)
        return content

    # ===== 阶段2：Validator 提出质疑 =====
    def validator_challenge(self, challenges: List[str] = None,
                            existing_knowledge: List[Dict] = None) -> str:
        """
        Validator 发言：提出质疑

        从以下角度质询：
          - 证据是否充分？
          - 是否有反例？
          - 是否与已知知识冲突？
          - 方法论是否可靠？
        """
        self._current_stage = 2

        if challenges is None:
            challenges = []
            if existing_knowledge:
                challenges.append(f"与现有 {len(existing_knowledge)} 条知识的关系需要澄清")
            challenges.append("证据链是否完整？")
            challenges.append("是否存在替代解释？")

        content = (
            f"【质询】关于「{self.topic}」，我提出以下质疑：\n"
            + "\n".join(f"  {i+1}. {c}" for i, c in enumerate(challenges))
        )

        self._add_statement("validator", content)
        return content

    # ===== 阶段3：Governor 做出裁决 =====
    def governor_decide(self, governor_obj=None, knowledge: Dict = None) -> RoundtableDecision:
        """
        Governor 发言：做出裁决

        这是会议的决策点。
        如果传入 governor 对象（统一Governor实例），用它来做正式评估。
        否则根据已有的发言做简单决策。
        """
        self._current_stage = 3

        if governor_obj and knowledge:
            result = governor_obj.govern(knowledge)
            admission = result["admission"]
            decision = RoundtableDecision(
                topic=self.topic,
                decision=admission.decision,
                confidence=max(0.0, min(1.0, admission.criteria.confidence if hasattr(admission.criteria, 'confidence') else 0.5)),
                reasons=admission.reasons,
                actions=admission.suggestions,
            )
        else:
            statement_count = len(self.record.statements)
            decision = RoundtableDecision(
                topic=self.topic,
                decision="delayed",
                confidence=0.3,
                reasons=["证据不足，待补充"],
                actions=["需要更多验证"],
            )

        self.record.decision = decision

        content = (
            f"【裁决】关于「{self.topic}」，裁决如下：\n"
            f"  决定：{decision.decision}\n"
            f"  置信度：{decision.confidence}\n"
            f"  原因：{'; '.join(decision.reasons[:3])}"
        )
        self._add_statement("governor", content)

        return decision

    # ===== 阶段4：Archivist 记录结论 =====
    def archivist_record(self) -> str:
        """
        Archivist 发言：记录结论

        只做记录，不做判断。
        把会议过程和结论归档。
        """
        self._current_stage = 4

        if not self.record.decision:
            content = "【记录】暂无裁决，记录会议讨论内容。"
        else:
            content = (
                f"【记录】已归档本次会议：\n"
                f"  会议ID：{self.meeting_id}\n"
                f"  主题：{self.topic}\n"
                f"  裁决：{self.record.decision.decision}\n"
                f"  发言数：{len(self.record.statements)}\n"
                f"  状态：已归档"
            )

        self.record.archived = True
        self._add_statement("archivist", content)
        return content

    # ===== 阶段5：Cloud 执行 =====
    def cloud_execute(self) -> str:
        """
        Cloud 执行：执行裁决结果

        Cloud 是执行者，不参与决策。
        它只做：同步、备份、结束。
        """
        self._current_stage = 5

        if not self.record.decision:
            content = "【执行】无裁决，跳过执行。"
        else:
            content = (
                f"【执行】Cloud收到裁决，开始执行：\n"
                f"  裁决：{self.record.decision.decision}\n"
                f"  操作：同步到仓库 + 创建备份 + 更新索引\n"
                f"  状态：待执行（由实际SyncManager处理）"
            )
            self.record.cloud_executed = True

        self._add_statement("cloud", content)
        self.record.end_time = datetime.now().isoformat()
        return content

    # ===== 完整会议流程 =====
    def run_full_meeting(self, findings: Dict, governor_obj=None,
                        knowledge: Dict = None, challenges: List[str] = None,
                        existing_knowledge: List[Dict] = None) -> RoundtableDecision:
        """
        执行完整的圆桌会议流程

        顺序：Researcher → Validator → Governor → Archivist → Cloud
        """
        self.researcher_present(findings)
        self.validator_challenge(challenges, existing_knowledge)
        decision = self.governor_decide(governor_obj, knowledge)
        self.archivist_record()
        self.cloud_execute()

        self._current_stage = 6  # 结束
        return decision

    # ===== 工具方法 =====
    def _add_statement(self, role: str, content: str):
        """添加发言记录"""
        self.record.statements.append(RoundtableStatement(
            role=role,
            content=content,
            topic=self.topic,
        ))

    def get_summary(self) -> Dict[str, Any]:
        """获取会议摘要"""
        return {
            "meeting_id": self.meeting_id,
            "topic": self.topic,
            "stage": self._current_stage,
            "statement_count": len(self.record.statements),
            "decision": self.record.decision.decision if self.record.decision else None,
            "archived": self.record.archived,
            "cloud_executed": self.record.cloud_executed,
            "duration": self._calc_duration(),
        }

    def _calc_duration(self) -> float:
        """计算会议时长（秒）"""
        try:
            start = datetime.fromisoformat(self.record.start_time)
            end = datetime.fromisoformat(
                self.record.end_time or datetime.now().isoformat()
            )
            return (end - start).total_seconds()
        except Exception:
            return 0.0
