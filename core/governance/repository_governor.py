"""
Repository Governor（仓库治理官）

职责：
    "它应该去哪？"

    Knowledge Governor 负责 "能不能进文明"
    Repository Governor 负责 "应该放在哪个仓库"

仓库分类：
    - mine-seed: 种子仓，最核心的结构资产
    - r1-archaeology: 考古发现，R1历史遗迹
    - knowledge_base: 知识库，经验/概念/演化链
    - archive: 归档，废弃但需要保留的知识
    - graveyard: 墓地，已被完全替代或验证错误的

决策流程：
    Knowledge Governor
        ↓ PASS
    Repository Governor
        ↓
    mine-seed?  →  核心约束/公理/架构
    r1-archaeology? → R1考古发现
    knowledge_base? → 经验/概念/演化
    archive? → 旧知识
    graveyard? → 错误/废弃

设计原则：
    - 仓库分类 = 知识重要性分级
    - mine-seed 最严格，数量最少
    - 越低的层，数量可以越多
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class RepositoryTier:
    """仓库层级"""
    MINE_SEED = "mine_seed"           # 种子仓，最核心
    R1_ARCHAEOLOGY = "r1_archaeology"  # R1考古
    KNOWLEDGE_BASE = "knowledge_base"  # 知识库
    ARCHIVE = "archive"                # 归档
    GRAVEYARD = "graveyard"            # 墓地


@dataclass
class PlacementDecision:
    """放置决策"""
    knowledge_id: str
    target_repository: str
    target_path: str
    confidence: float
    reason: str
    alternatives: List[str] = field(default_factory=list)
    conditions: List[str] = field(default_factory=list)
    timestamp: str = ""


class RepositoryGovernor:
    """
    仓库治理官

    核心职责：
        决定知识应该放在哪个仓库/哪个位置

    只问一个问题：
        "它应该去哪？"
    """

    def __init__(self, ace_runtime_dir: str):
        """
        初始化仓库治理官

        Args:
            ace_runtime_dir: ACE Runtime根目录
        """
        self.ace_runtime_dir = Path(ace_runtime_dir)
        self.data_dir = self.ace_runtime_dir / "08_GOVERNANCE"
        self.records_dir = self.data_dir / "repository_governor"
        self.records_dir.mkdir(parents=True, exist_ok=True)

        self.records_file = self.records_dir / "placement_records.jsonl"

        # 仓库路径配置
        self.repositories = {
            RepositoryTier.MINE_SEED: {
                "path": "../mine-seed",
                "description": "种子仓，最核心的结构资产",
                "strictness": 10,  # 最严格
            },
            RepositoryTier.R1_ARCHAEOLOGY: {
                "path": "../r1-archaeology",
                "description": "R1考古发现",
                "strictness": 8,
            },
            RepositoryTier.KNOWLEDGE_BASE: {
                "path": "09_KNOWLEDGE",
                "description": "知识库",
                "strictness": 5,
            },
            RepositoryTier.ARCHIVE: {
                "path": "08_ARCHAEOLOGY",
                "description": "归档",
                "strictness": 3,
            },
            RepositoryTier.GRAVEYARD: {
                "path": "08_GOVERNANCE/graveyard",
                "description": "墓地",
                "strictness": 1,
            },
        }

        # 知识类型到仓库的映射规则
        self.type_rules = {
            "constraint": {
                "primary": RepositoryTier.MINE_SEED,
                "secondary": RepositoryTier.KNOWLEDGE_BASE,
            },
            "axiom": {
                "primary": RepositoryTier.MINE_SEED,
                "secondary": RepositoryTier.KNOWLEDGE_BASE,
            },
            "core_principle": {
                "primary": RepositoryTier.MINE_SEED,
                "secondary": RepositoryTier.KNOWLEDGE_BASE,
            },
            "architecture": {
                "primary": RepositoryTier.MINE_SEED,
                "secondary": RepositoryTier.R1_ARCHAEOLOGY,
            },
            "protocol": {
                "primary": RepositoryTier.MINE_SEED,
                "secondary": RepositoryTier.KNOWLEDGE_BASE,
            },
            "r1_archaeology": {
                "primary": RepositoryTier.R1_ARCHAEOLOGY,
                "secondary": RepositoryTier.ARCHIVE,
            },
            "experience": {
                "primary": RepositoryTier.KNOWLEDGE_BASE,
                "secondary": RepositoryTier.ARCHIVE,
            },
            "concept": {
                "primary": RepositoryTier.KNOWLEDGE_BASE,
                "secondary": RepositoryTier.ARCHIVE,
            },
            "evolution": {
                "primary": RepositoryTier.KNOWLEDGE_BASE,
                "secondary": RepositoryTier.R1_ARCHAEOLOGY,
            },
            "archaeology_report": {
                "primary": RepositoryTier.ARCHIVE,
                "secondary": RepositoryTier.R1_ARCHAEOLOGY,
            },
            "rejected": {
                "primary": RepositoryTier.GRAVEYARD,
                "secondary": RepositoryTier.ARCHIVE,
            },
            "superseded": {
                "primary": RepositoryTier.ARCHIVE,
                "secondary": RepositoryTier.GRAVEYARD,
            },
        }

    def decide_placement(self, knowledge: Dict[str, Any]) -> PlacementDecision:
        """
        决定知识应该放在哪个仓库

        Args:
            knowledge: 知识对象

        Returns:
            PlacementDecision，放置决策
        """
        knowledge_id = knowledge.get("id", f"unknown_{datetime.now().timestamp()}")
        knowledge_type = knowledge.get("type", knowledge.get("artifact_type", "experience"))
        status = knowledge.get("status", "HYPOTHESIS")
        confidence = knowledge.get("confidence", 0.0)
        importance = knowledge.get("importance", knowledge.get("priority", 0.5))

        decision = PlacementDecision(
            knowledge_id=knowledge_id,
            target_repository="",
            target_path="",
            confidence=0.0,
            reason="",
            timestamp=datetime.now().isoformat(),
        )

        # 1. 根据状态决定
        if status == "REJECTED":
            decision.target_repository = RepositoryTier.GRAVEYARD
            decision.target_path = self._get_target_path(RepositoryTier.GRAVEYARD, knowledge)
            decision.confidence = 0.9
            decision.reason = "被拒绝的知识进入墓地"
            self._save_decision(decision)
            return decision

        if status == "SUPERSEDED":
            decision.target_repository = RepositoryTier.ARCHIVE
            decision.target_path = self._get_target_path(RepositoryTier.ARCHIVE, knowledge)
            decision.confidence = 0.8
            decision.reason = "被替代的知识进入归档"
            self._save_decision(decision)
            return decision

        if status in ["DEPRECATED", "ARCHIVED"]:
            decision.target_repository = RepositoryTier.ARCHIVE
            decision.target_path = self._get_target_path(RepositoryTier.ARCHIVE, knowledge)
            decision.confidence = 0.7
            decision.reason = "废弃/归档的知识进入归档库"
            self._save_decision(decision)
            return decision

        # 2. 根据类型决定
        rule = self.type_rules.get(knowledge_type, {
            "primary": RepositoryTier.KNOWLEDGE_BASE,
            "secondary": RepositoryTier.ARCHIVE,
        })

        primary_repo = rule["primary"]
        secondary_repo = rule["secondary"]

        # 3. 根据置信度调整
        if confidence >= 0.9:
            decision.target_repository = primary_repo
            decision.confidence = 0.8
            decision.reason = f"高置信度({confidence})，进入主仓库{primary_repo}"
        elif confidence >= 0.7:
            decision.target_repository = primary_repo
            decision.confidence = 0.6
            decision.reason = f"中等置信度({confidence})，进入主仓库{primary_repo}"
        elif confidence >= 0.5:
            decision.target_repository = secondary_repo
            decision.confidence = 0.5
            decision.reason = f"低置信度({confidence})，进入次仓库{secondary_repo}"
            decision.conditions = [f"置信度提升到0.7以上时迁移到{primary_repo}"]
        else:
            decision.target_repository = RepositoryTier.ARCHIVE
            decision.confidence = 0.3
            decision.reason = f"置信度过低({confidence})，暂存归档"
            decision.conditions = ["需要补充证据提升置信度"]

        decision.target_path = self._get_target_path(decision.target_repository, knowledge)
        decision.alternatives = [secondary_repo] if secondary_repo != decision.target_repository else []

        self._save_decision(decision)
        return decision

    def _get_target_path(self, repository: str, knowledge: Dict[str, Any]) -> str:
        """获取目标路径"""
        repo_config = self.repositories.get(repository, {})
        base_path = repo_config.get("path", "")

        knowledge_type = knowledge.get("type", "experience")
        knowledge_id = knowledge.get("id", "unknown")

        # 根据类型决定子目录
        if knowledge_type in ["constraint", "axiom", "core_principle"]:
            sub_dir = "02_CONSTRAINTS"
        elif knowledge_type in ["protocol", "blueprint"]:
            sub_dir = "04_PROTOCOLS"
        elif knowledge_type == "experience":
            sub_dir = "experiences"
        elif knowledge_type == "concept":
            sub_dir = "lexicon"
        elif knowledge_type == "evolution":
            sub_dir = "evolution"
        elif knowledge_type == "archaeology_report":
            sub_dir = "reports"
        else:
            sub_dir = "misc"

        return f"{base_path}/{sub_dir}/{knowledge_id}.json"

    def check_migration_candidates(self) -> List[Dict[str, Any]]:
        """
        检查需要迁移的知识

        例如：
        - 低置信度但后来验证通过的知识，应该从archive迁移到knowledge_base
        - 高重要性的知识，应该从knowledge_base迁移到mine-seed

        Returns:
            迁移候选列表
        """
        candidates = []
        # 实现时需要遍历所有仓库的知识
        # 这里先返回空列表作为框架
        return candidates

    def _save_decision(self, decision: PlacementDecision):
        """保存决策记录"""
        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "knowledge_id": decision.knowledge_id,
                    "target_repository": decision.target_repository,
                    "target_path": decision.target_path,
                    "confidence": decision.confidence,
                    "reason": decision.reason,
                    "alternatives": decision.alternatives,
                    "conditions": decision.conditions,
                    "timestamp": decision.timestamp,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存放置决策失败: {e}")

    def get_governance_summary(self) -> Dict[str, Any]:
        """获取仓库治理摘要"""
        if not self.records_file.exists():
            return {"total_decisions": 0, "by_repository": {}}

        total = 0
        by_repository = {}

        try:
            with open(self.records_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        total += 1
                        repo = record.get("target_repository", "unknown")
                        by_repository[repo] = by_repository.get(repo, 0) + 1
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"读取治理记录失败: {e}")

        return {
            "total_decisions": total,
            "by_repository": by_repository,
        }

    def get_repository_info(self, repository: str) -> Dict[str, Any]:
        """获取仓库信息"""
        return self.repositories.get(repository, {})

    def list_repositories(self) -> List[str]:
        """列出所有仓库"""
        return list(self.repositories.keys())
