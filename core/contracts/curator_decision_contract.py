"""
馆长决策契约 — Repository Curator 决策层接口规范

定义馆长决策过程中的核心数据结构和接口契约：
- 产物评估标准
- 决策选项与理由
- 同步计划生成
- 决策审计追踪

设计原则：
  1. 决策可追溯 — 每一个决策都有评分依据和理由
  2. 动作可枚举 — create / update / merge / discard / split
  3. 计划可验证 — 生成的 SyncPlan 带有签名和哈希
  4. 权限可校验 — 只有 Curator 有权生成决策
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Protocol, runtime_checkable


class DecisionAction(str, Enum):
    """决策动作枚举"""
    CREATE = "create"
    UPDATE = "update"
    MERGE = "merge"
    DISCARD = "discard"
    SPLIT = "split"
    ARCHIVE = "archive"


class ArtifactType(str, Enum):
    """产物类型枚举"""
    MARKDOWN = "md"
    JSON = "json"
    PYTHON = "py"
    YAML = "yaml"
    UNKNOWN = "unknown"


class ScoreDimension(str, Enum):
    """评分维度枚举"""
    NOVELTY = "novelty"
    SIMILARITY = "similarity"
    STABILITY = "stability"
    REUSABILITY = "reusability"
    COMPOSITE = "composite"


@dataclass
class ArtifactScore:
    """
    产物多维度评分

    每个维度 0-100 分，综合评分由各维度加权计算。
    评分是决策的主要依据。
    """
    novelty: float = 0.0
    similarity: float = 0.0
    stability: float = 0.0
    reusability: float = 0.0
    composite: float = 0.0
    weights: Dict[str, float] = field(default_factory=lambda: {
        "novelty": 0.30,
        "similarity": 0.20,
        "stability": 0.25,
        "reusability": 0.25,
    })

    def calculate_composite(self) -> float:
        """
        计算综合评分

        使用加权平均法，相似度维度取反（相似度越高，新颖度贡献越低）。

        Returns:
            综合评分，0-100
        """
        novelty_score = self.novelty * self.weights["novelty"]
        similarity_contribution = (100 - self.similarity) * self.weights["similarity"]
        stability_score = self.stability * self.weights["stability"]
        reusability_score = self.reusability * self.weights["reusability"]

        self.composite = novelty_score + similarity_contribution + stability_score + reusability_score
        return self.composite

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "novelty": self.novelty,
            "similarity": self.similarity,
            "stability": self.stability,
            "reusability": self.reusability,
            "composite": self.composite,
            "weights": self.weights,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactScore":
        """从字典反序列化"""
        return cls(
            novelty=data.get("novelty", 0.0),
            similarity=data.get("similarity", 0.0),
            stability=data.get("stability", 0.0),
            reusability=data.get("reusability", 0.0),
            composite=data.get("composite", 0.0),
            weights=data.get("weights", {}),
        )


@dataclass
class SimilarDocument:
    """
    相似文档信息

    用于记录与已有知识库中最相似的文档，
    作为 update / merge / discard 决策的依据。
    """
    doc_id: str
    title: str
    path: str
    similarity: float
    repo: str = ""
    category: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "doc_id": self.doc_id,
            "title": self.title,
            "path": self.path,
            "similarity": self.similarity,
            "repo": self.repo,
            "category": self.category,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SimilarDocument":
        """从字典反序列化"""
        return cls(
            doc_id=data.get("doc_id", ""),
            title=data.get("title", ""),
            path=data.get("path", ""),
            similarity=data.get("similarity", 0.0),
            repo=data.get("repo", ""),
            category=data.get("category", ""),
        )


@dataclass
class SplitCandidate:
    """
    拆分候选

    当一个产物包含多个主题时，记录可拆分的部分。
    """
    section_title: str
    category: str
    content_preview: str
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "section_title": self.section_title,
            "category": self.category,
            "content_preview": self.content_preview,
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SplitCandidate":
        """从字典反序列化"""
        return cls(
            section_title=data.get("section_title", ""),
            category=data.get("category", ""),
            content_preview=data.get("content_preview", ""),
            confidence=data.get("confidence", 0.0),
        )


@dataclass
class ArtifactDecision:
    """
    单产物决策

    对每一个待同步产物，Curator 生成一个决策对象，
    包含评分、动作、目标位置、理由等完整信息。
    """
    artifact_id: str
    artifact_title: str
    artifact_path: str
    artifact_type: ArtifactType
    score: ArtifactScore
    action: DecisionAction
    target_repo: str = ""
    target_path: str = ""
    similar_existing: Optional[SimilarDocument] = None
    split_candidates: List[SplitCandidate] = field(default_factory=list)
    reason: str = ""
    override: bool = False
    override_reason: str = ""
    decided_at: str = field(default_factory=lambda: datetime.now().isoformat())
    decision_trace: List[Dict[str, Any]] = field(default_factory=list)

    def add_decision_step(self, step_name: str, detail: str, actor: str = "curator"):
        """
        添加决策步骤追踪

        Args:
            step_name: 步骤名称
            detail: 步骤详情
            actor: 执行者
        """
        self.decision_trace.append({
            "step": step_name,
            "detail": detail,
            "actor": actor,
            "at": datetime.now().isoformat(),
        })

    def validate(self) -> bool:
        """
        验证决策完整性

        Returns:
            是否通过验证
        """
        if not self.artifact_id:
            return False
        if not isinstance(self.action, DecisionAction):
            return False
        if self.action in (DecisionAction.CREATE, DecisionAction.UPDATE, DecisionAction.MERGE):
            if not self.target_repo or not self.target_path:
                return False
        if self.score.composite <= 0:
            self.score.calculate_composite()
        return True

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "artifact_id": self.artifact_id,
            "artifact_title": self.artifact_title,
            "artifact_path": self.artifact_path,
            "artifact_type": self.artifact_type.value if isinstance(self.artifact_type, ArtifactType) else self.artifact_type,
            "score": self.score.to_dict(),
            "action": self.action.value if isinstance(self.action, DecisionAction) else self.action,
            "target_repo": self.target_repo,
            "target_path": self.target_path,
            "similar_existing": self.similar_existing.to_dict() if self.similar_existing else None,
            "split_candidates": [sc.to_dict() for sc in self.split_candidates],
            "reason": self.reason,
            "override": self.override,
            "override_reason": self.override_reason,
            "decided_at": self.decided_at,
            "decision_trace": self.decision_trace,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ArtifactDecision":
        """从字典反序列化"""
        action = data.get("action", "create")
        if isinstance(action, str):
            try:
                action = DecisionAction(action)
            except ValueError:
                action = DecisionAction.CREATE

        artifact_type = data.get("artifact_type", "unknown")
        if isinstance(artifact_type, str):
            try:
                artifact_type = ArtifactType(artifact_type)
            except ValueError:
                artifact_type = ArtifactType.UNKNOWN

        similar_existing = None
        if data.get("similar_existing"):
            similar_existing = SimilarDocument.from_dict(data["similar_existing"])

        split_candidates = [
            SplitCandidate.from_dict(sc)
            for sc in data.get("split_candidates", [])
        ]

        return cls(
            artifact_id=data.get("artifact_id", ""),
            artifact_title=data.get("artifact_title", ""),
            artifact_path=data.get("artifact_path", ""),
            artifact_type=artifact_type,
            score=ArtifactScore.from_dict(data.get("score", {})),
            action=action,
            target_repo=data.get("target_repo", ""),
            target_path=data.get("target_path", ""),
            similar_existing=similar_existing,
            split_candidates=split_candidates,
            reason=data.get("reason", ""),
            override=data.get("override", False),
            override_reason=data.get("override_reason", ""),
            decided_at=data.get("decided_at", datetime.now().isoformat()),
            decision_trace=data.get("decision_trace", []),
        )


@dataclass
class CuratorDecisionContext:
    """
    馆长决策上下文

    记录一次馆长决策运行的完整上下文信息，
    用于审计和追溯。
    """
    run_id: str
    triggered_by: str
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = ""
    artifacts_scanned: int = 0
    decisions_count: int = 0
    existing_docs_count: int = 0
    curator_version: str = "1.0.0"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "run_id": self.run_id,
            "triggered_by": self.triggered_by,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "artifacts_scanned": self.artifacts_scanned,
            "decisions_count": self.decisions_count,
            "existing_docs_count": self.existing_docs_count,
            "curator_version": self.curator_version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CuratorDecisionContext":
        """从字典反序列化"""
        return cls(
            run_id=data.get("run_id", ""),
            triggered_by=data.get("triggered_by", ""),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            artifacts_scanned=data.get("artifacts_scanned", 0),
            decisions_count=data.get("decisions_count", 0),
            existing_docs_count=data.get("existing_docs_count", 0),
            curator_version=data.get("curator_version", "1.0.0"),
            metadata=data.get("metadata", {}),
        )


@runtime_checkable
class ICuratorDecisionEngine(Protocol):
    """
    馆长决策引擎接口协议

    定义 Repository Curator 决策层必须实现的接口。
    任何实现此协议的类都可以作为决策引擎使用。
    """

    def score_artifact(self, artifact: Dict[str, Any]) -> ArtifactScore:
        """
        对单个产物进行多维度评分

        Args:
            artifact: 产数字典，至少包含 path, title, content, type

        Returns:
            ArtifactScore 评分结果
        """
        ...

    def find_similar(self, artifact: Dict[str, Any], existing_docs: List[Dict[str, Any]]) -> List[SimilarDocument]:
        """
        在已有文档中查找相似项

        Args:
            artifact: 待匹配产物
            existing_docs: 已有文档列表

        Returns:
            相似文档列表（按相似度降序）
        """
        ...

    def make_decision(self, artifact: Dict[str, Any], score: ArtifactScore,
                      similar_docs: List[SimilarDocument]) -> ArtifactDecision:
        """
        根据评分和相似度生成决策

        Args:
            artifact: 待决策产物
            score: 评分结果
            similar_docs: 相似文档列表

        Returns:
            ArtifactDecision 决策结果
        """
        ...

    def validate_decision(self, decision: ArtifactDecision) -> bool:
        """
        验证决策的合法性和完整性

        Args:
            decision: 待验证的决策

        Returns:
            是否通过验证
        """
        ...


@dataclass
class SyncPlan:
    """
    同步计划

    馆长决策的最终产出物，包含所有决策的汇总，
    以及用于签名验证的元数据。
    SyncPlan 是 Curator 与 SyncManager 之间的契约。
    """
    plan_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    context: Optional[CuratorDecisionContext] = None
    decisions: List[ArtifactDecision] = field(default_factory=list)
    curator_id: str = "ace_runtime_curator"
    curator_signature: str = ""
    timestamp: str = ""
    plan_hash: str = ""

    def _decisions_data(self) -> List[Dict[str, Any]]:
        """提取决策数据用于哈希计算"""
        return [
            {
                "action": d.action.value if isinstance(d.action, DecisionAction) else d.action,
                "artifact_id": d.artifact_id,
                "artifact_path": d.artifact_path,
                "target_repo": d.target_repo,
                "target_path": d.target_path,
            }
            for d in self.decisions
        ]

    def calculate_hash(self) -> str:
        """
        计算计划哈希值

        基于决策内容生成 MD5 哈希，用于签名验证和防篡改。

        Returns:
            十六进制哈希字符串
        """
        plan_data = {
            "decisions": self._decisions_data(),
            "created_at": self.created_at,
        }
        self.plan_hash = hashlib.md5(
            json.dumps(plan_data, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
        return self.plan_hash

    def sign(self, curator_secret: str) -> str:
        """
        生成馆长签名

        使用 SHA256 对 curator_id + timestamp + plan_hash + secret 进行签名。

        Args:
            curator_secret: 馆长密钥

        Returns:
            签名字符串（前16位）
        """
        if not self.plan_hash:
            self.calculate_hash()
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

        raw = f"{self.curator_id}:{self.timestamp}:{self.plan_hash}:{curator_secret}"
        self.curator_signature = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return self.curator_signature

    def verify_signature(self, curator_secret: str) -> bool:
        """
        验证签名有效性

        Args:
            curator_secret: 馆长密钥

        Returns:
            签名是否有效
        """
        if not all([self.curator_signature, self.timestamp, self.plan_hash]):
            return False

        raw = f"{self.curator_id}:{self.timestamp}:{self.plan_hash}:{curator_secret}"
        expected = hashlib.sha256(raw.encode()).hexdigest()[:16]
        return expected == self.curator_signature

    def get_action_lists(self) -> Dict[str, List[ArtifactDecision]]:
        """
        按动作类型分组决策

        Returns:
            以动作类型为 key 的决策列表字典
        """
        grouped: Dict[str, List[ArtifactDecision]] = {}
        for decision in self.decisions:
            action_key = decision.action.value if isinstance(decision.action, DecisionAction) else decision.action
            if action_key not in grouped:
                grouped[action_key] = []
            grouped[action_key].append(decision)
        return grouped

    def get_summary(self) -> str:
        """
        生成计划摘要

        Returns:
            人类可读的摘要文本
        """
        action_labels = {
            "create": "新增",
            "update": "更新",
            "merge": "合并",
            "discard": "丢弃",
            "split": "拆分",
            "archive": "归档",
        }
        grouped = self.get_action_lists()
        parts = []
        for action in ["create", "update", "merge", "discard", "split", "archive"]:
            count = len(grouped.get(action, []))
            if count > 0:
                label = action_labels.get(action, action)
                parts.append(f"{label}: {count}")
        return " | ".join(parts) if parts else "无变更"

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "context": self.context.to_dict() if self.context else None,
            "decisions": [d.to_dict() for d in self.decisions],
            "curator_id": self.curator_id,
            "curator_signature": self.curator_signature,
            "timestamp": self.timestamp,
            "plan_hash": self.plan_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncPlan":
        """从字典反序列化"""
        context = None
        if data.get("context"):
            context = CuratorDecisionContext.from_dict(data["context"])

        decisions = [
            ArtifactDecision.from_dict(d)
            for d in data.get("decisions", [])
        ]

        return cls(
            plan_id=data.get("plan_id", ""),
            created_at=data.get("created_at", datetime.now().isoformat()),
            context=context,
            decisions=decisions,
            curator_id=data.get("curator_id", "ace_runtime_curator"),
            curator_signature=data.get("curator_signature", ""),
            timestamp=data.get("timestamp", ""),
            plan_hash=data.get("plan_hash", ""),
        )


class CuratorDecisionContract:
    """
    馆长决策契约 — 决策层规范实现

    封装 Curator 决策过程的所有数据结构和验证逻辑，
    确保决策过程的可追溯性和一致性。

    使用示例:
        contract = CuratorDecisionContract()
        score = contract.score_artifact(artifact_data)
        decision = contract.make_decision(artifact_data, score, similar_docs)
        sync_plan = contract.build_sync_plan([decision], context)
        sync_plan.sign(secret)
    """

    # 决策阈值常量
    THRESHOLDS = {
        "discard_novelty": 10.0,
        "discard_similarity": 95.0,
        "update_similarity": 85.0,
        "split_stability": 30.0,
        "min_composite_create": 20.0,
    }

    def __init__(self, curator_id: str = "ace_runtime_curator"):
        """
        初始化决策契约

        Args:
            curator_id: 馆长标识符，用于签名
        """
        self.curator_id = curator_id

    def validate_artifact(self, artifact: Dict[str, Any]) -> bool:
        """
        验证输入产物的基本格式

        Args:
            artifact: 待验证产数字典

        Returns:
            是否通过验证
        """
        required_fields = ["path", "title", "content", "type"]
        for field_name in required_fields:
            if field_name not in artifact or not artifact[field_name]:
                return False
        return True

    def score_artifact(self, artifact: Dict[str, Any]) -> ArtifactScore:
        """
        对产物进行多维度评分

        Args:
            artifact: 产数字典，包含 path/title/content/type/size/mtime/author 等

        Returns:
            ArtifactScore — 四维评分结果
        """
        content = artifact.get("content", "")
        title = artifact.get("title", "")
        size = artifact.get("size", 0)
        file_type = artifact.get("type", "md")
        mtime = artifact.get("mtime", 0)
        author = artifact.get("author", "unknown")
        similarity = artifact.get("similarity", 0.0)

        # 1. 新颖度 (0-100)
        novelty = self._calc_novelty(title, content, size, file_type)

        # 2. 稳定性 (0-100)
        stability = self._calc_stability(mtime, author, file_type, content)

        # 3. 可复用性 (0-100)
        reusability = self._calc_reusability(title, content, file_type)

        score_obj = ArtifactScore(
            novelty=novelty,
            similarity=similarity,
            stability=stability,
            reusability=reusability,
        )
        score_obj.calculate_composite()
        return score_obj

    def _calc_novelty(self, title: str, content: str, size: int, file_type: str) -> float:
        """计算新颖度"""
        score = 0.0
        if size > 5000:
            score += 30
        elif size > 2000:
            score += 20
        elif size > 500:
            score += 10

        import re
        heading_count = len(re.findall(r'^#{1,4}\s', content, re.MULTILINE))
        if heading_count > 10:
            score += 25
        elif heading_count > 5:
            score += 15
        elif heading_count > 2:
            score += 10

        unique_words = set(re.findall(r'[\u4e00-\u9fa5]{2,4}|[a-zA-Z]{3,}', content.lower()))
        if len(unique_words) > 200:
            score += 25
        elif len(unique_words) > 100:
            score += 15
        elif len(unique_words) > 50:
            score += 10

        high_value = ["公理", "协议", "架构", "设计", "规范", "契约", "runtime", "定律"]
        if any(kw in title for kw in high_value):
            score += 20

        return min(100.0, score)

    def _calc_stability(self, mtime: float, author: str, file_type: str, content: str) -> float:
        """计算稳定性/成熟度"""
        import time
        score = 30.0

        if mtime > 0:
            age_days = (time.time() - mtime) / 86400
            if age_days > 7:
                score += 30
            elif age_days > 3:
                score += 20
            elif age_days > 1:
                score += 10

        if author and author != "unknown":
            score += 10

        if file_type == "py":
            score += 20

        if "结论" in content or "summary" in content.lower():
            score += 10

        return min(100.0, score)

    def _calc_reusability(self, title: str, content: str, file_type: str) -> float:
        """计算可复用性"""
        score = 20.0

        patterns = ["模式", "pattern", "模板", "template", "框架", "framework",
                   "原则", "principle", "方法", "method", "流程", "pipeline"]
        for p in patterns:
            if p.lower() in content.lower():
                score += 5

        rule_indicators = ["必须", "必须不", "应当", "不应当", "must", "should", "shall"]
        for r in rule_indicators:
            if r in content:
                score += 5

        if file_type == "py":
            score += 30

        if "目录" in content or "table of contents" in content.lower():
            score += 10

        return min(100.0, score)

    def make_decision(
        self,
        artifact: Dict[str, Any],
        score: ArtifactScore,
        similar_docs: List[SimilarDocument],
        split_candidates: Optional[List[SplitCandidate]] = None,
    ) -> ArtifactDecision:
        """
        根据评分和相似度生成完整决策

        Args:
            artifact: 待决策产物
            score: 评分结果
            similar_docs: 相似文档列表
            split_candidates: 拆分候选列表

        Returns:
            ArtifactDecision — 完整决策结果
        """
        if split_candidates is None:
            split_candidates = []

        # 分类决策动作
        action = self.classify_action(score, similar_docs, split_candidates)

        # 生成理由
        reason = self.generate_reason(action, score, similar_docs, split_candidates)

        # 确定目标仓库和路径
        target_repo = artifact.get("target_repo", "mine-seed")
        target_path = artifact.get("target_path", f"03_DATA/research/r1_archaeology/misc/{artifact.get('title', 'untitled')}")

        # 最相似文档
        most_similar = similar_docs[0] if similar_docs else None

        # 类型转换
        type_str = artifact.get("type", "md")
        try:
            artifact_type = ArtifactType(type_str)
        except Exception:
            artifact_type = ArtifactType.UNKNOWN

        return ArtifactDecision(
            artifact_id=artifact.get("artifact_id", artifact.get("path", "unknown")),
            artifact_title=artifact.get("title", ""),
            artifact_path=artifact.get("path", ""),
            artifact_type=artifact_type,
            action=action,
            target_repo=target_repo,
            target_path=target_path,
            score=score,
            similar_existing=most_similar,
            split_candidates=split_candidates,
            reason=reason,
        )

    def classify_action(self, score: ArtifactScore, similar_docs: List[SimilarDocument],
                        split_candidates: List[SplitCandidate]) -> DecisionAction:
        """
        根据评分和相似度分类决策动作

        决策规则（按优先级）:
        1. 新颖度极低且相似度极高 → discard
        2. 相似度很高 → update
        3. 稳定性低且有拆分候选 → split
        4. 其他情况 → create

        Args:
            score: 评分结果
            similar_docs: 相似文档列表
            split_candidates: 拆分候选列表

        Returns:
            决策动作
        """
        thresholds = self.THRESHOLDS

        top_similarity = similar_docs[0].similarity if similar_docs else 0.0

        if (score.novelty < thresholds["discard_novelty"] and
                top_similarity > thresholds["discard_similarity"]):
            return DecisionAction.DISCARD

        if top_similarity > thresholds["update_similarity"]:
            return DecisionAction.UPDATE

        if score.stability < thresholds["split_stability"] and split_candidates:
            return DecisionAction.SPLIT

        if score.composite < thresholds["min_composite_create"]:
            return DecisionAction.DISCARD

        return DecisionAction.CREATE

    def generate_reason(self, action: DecisionAction, score: ArtifactScore,
                        similar_docs: List[SimilarDocument],
                        split_candidates: List[SplitCandidate]) -> str:
        """
        生成决策理由文本

        Args:
            action: 决策动作
            score: 评分结果
            similar_docs: 相似文档列表
            split_candidates: 拆分候选列表

        Returns:
            理由文本
        """
        top_similarity = similar_docs[0].similarity if similar_docs else 0.0
        top_title = similar_docs[0].title if similar_docs else "无"

        reasons = {
            DecisionAction.CREATE: (
                f"新内容(新颖度{score.novelty:.1f}，稳定性{score.stability:.1f}，"
                f"可复用性{score.reusability:.1f}，综合{score.composite:.1f})"
            ),
            DecisionAction.UPDATE: (
                f"相似度{top_similarity:.1f}高，更新已有内容「{top_title}」"
            ),
            DecisionAction.MERGE: (
                f"与多个文档相关，建议合并处理"
            ),
            DecisionAction.DISCARD: (
                f"新颖度{score.novelty:.1f}低且相似度{top_similarity:.1f}高，内容重复"
            ),
            DecisionAction.SPLIT: (
                f"稳定性{score.stability:.1f}低，发现{len(split_candidates)}个可拆分部分"
            ),
            DecisionAction.ARCHIVE: (
                f"内容过时或不再活跃，建议归档"
            ),
        }

        return reasons.get(action, "默认决策")

    def build_sync_plan(self, decisions: List[ArtifactDecision],
                        context: Optional[CuratorDecisionContext] = None) -> SyncPlan:
        """
        构建同步计划

        Args:
            decisions: 决策列表
            context: 决策上下文

        Returns:
            SyncPlan 同步计划
        """
        plan_id = f"sync_plan_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        plan = SyncPlan(
            plan_id=plan_id,
            context=context,
            decisions=decisions,
            curator_id=self.curator_id,
        )

        plan.calculate_hash()
        return plan
