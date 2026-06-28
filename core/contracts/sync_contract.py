"""
同步契约 — Sync Contract

定义系统中所有同步相关的标准数据结构和接口：
  - SyncAction: 同步操作类型枚举
  - SyncDecision: 单个同步决策
  - SyncPlan: 同步计划（一组决策 + 签名）
  - SyncResult: 同步执行结果
  - SyncContract: 同步执行器抽象接口

设计原则：
  - 所有同步操作必须通过 SyncPlan 发起
  - 每个 SyncPlan 必须有可验证的签名
  - 同步结果必须统一格式，便于日志和审计
"""

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional


class SyncAction(str, Enum):
    """同步操作类型"""

    CREATE = "create"
    UPDATE = "update"
    MERGE = "merge"
    SPLIT = "split"
    DISCARD = "discard"
    ARCHIVE = "archive"


@dataclass
class SyncDecision:
    """
    单个同步决策

    描述对一个产物（artifact）的同步处理决定：
      - 做什么（action）
      - 放哪里（target_repo / target_path）
      - 为什么（reason）
    """

    artifact_id: str
    artifact: Dict[str, Any]
    action: SyncAction
    target_repo: str
    target_path: str
    source_path: Optional[str] = None
    source_files: Optional[List[str]] = None
    similar_existing: Optional[Dict[str, Any]] = None
    split_parts: List[Dict[str, Any]] = field(default_factory=list)
    reason: str = ""
    score: Optional[float] = None
    override: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "artifact_id": self.artifact_id,
            "artifact": self.artifact,
            "action": self.action.value if isinstance(self.action, SyncAction) else self.action,
            "target_repo": self.target_repo,
            "target_path": self.target_path,
            "source_path": self.source_path,
            "source_files": self.source_files,
            "similar_existing": self.similar_existing,
            "split_parts": self.split_parts,
            "reason": self.reason,
            "score": self.score,
            "override": self.override,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncDecision":
        """从字典反序列化"""
        action = data.get("action", "create")
        if isinstance(action, str):
            action = SyncAction(action)
        return cls(
            artifact_id=data["artifact_id"],
            artifact=data.get("artifact", {}),
            action=action,
            target_repo=data.get("target_repo", ""),
            target_path=data.get("target_path", ""),
            source_path=data.get("source_path"),
            source_files=data.get("source_files"),
            similar_existing=data.get("similar_existing"),
            split_parts=data.get("split_parts", []),
            reason=data.get("reason", ""),
            score=data.get("score"),
            override=data.get("override", False),
        )


@dataclass
class SyncPlan:
    """
    同步计划

    一组同步决策的集合，带有签名验证。
    只有拥有有效签名的 SyncPlan 才能被执行。
    """

    plan_id: str
    created_at: str
    creator: str
    decisions: List[SyncDecision] = field(default_factory=list)
    summary: str = ""
    curator_signature: str = ""
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()
        if not self.created_at:
            self.created_at = self.timestamp

    @property
    def total_decisions(self) -> int:
        """决策总数"""
        return len(self.decisions)

    @property
    def plan_hash(self) -> str:
        """计划内容哈希（用于签名）"""
        content = (
            f"{self.plan_id}:{self.creator}:{self.timestamp}:"
            f"{';'.join(d.artifact_id for d in self.decisions)}"
        )
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def get_decisions_by_action(self, action: SyncAction) -> List[SyncDecision]:
        """按操作类型筛选决策"""
        return [d for d in self.decisions if d.action == action]

    def get_target_repos(self) -> List[str]:
        """获取涉及的目标仓库列表"""
        repos = set()
        for d in self.decisions:
            if d.target_repo:
                repos.add(d.target_repo)
        return sorted(repos)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "plan_id": self.plan_id,
            "created_at": self.created_at,
            "creator": self.creator,
            "decisions": [d.to_dict() for d in self.decisions],
            "summary": self.summary,
            "curator_signature": self.curator_signature,
            "timestamp": self.timestamp,
            "plan_hash": self.plan_hash,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncPlan":
        """从字典反序列化"""
        decisions_data = data.get("decisions", [])
        decisions = [SyncDecision.from_dict(d) for d in decisions_data]
        return cls(
            plan_id=data["plan_id"],
            created_at=data.get("created_at", ""),
            creator=data.get("creator", ""),
            decisions=decisions,
            summary=data.get("summary", ""),
            curator_signature=data.get("curator_signature", ""),
            timestamp=data.get("timestamp", ""),
        )


@dataclass
class SyncResult:
    """
    同步执行结果

    记录单次同步操作的执行状态，用于日志和审计。
    """

    success: bool
    repo: str
    action: str
    files: List[str]
    commit_hash: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    executed_at: str = ""

    def __post_init__(self):
        if not self.executed_at:
            self.executed_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "success": self.success,
            "repo": self.repo,
            "action": self.action,
            "files": self.files,
            "commit_hash": self.commit_hash,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "executed_at": self.executed_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncResult":
        """从字典反序列化"""
        return cls(
            success=data["success"],
            repo=data.get("repo", ""),
            action=data.get("action", ""),
            files=data.get("files", []),
            commit_hash=data.get("commit_hash"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0.0),
            executed_at=data.get("executed_at", ""),
        )


class SyncContract(ABC):
    """
    同步执行器抽象契约

    所有同步执行器必须实现此接口。
    保证不同实现（本地同步、远程同步、跨仓库同步）
    都遵循统一的调用约定。
    """

    @abstractmethod
    def verify_plan(self, plan: SyncPlan) -> bool:
        """
        验证同步计划的合法性

        检查内容：
          - 签名是否有效
          - 决策格式是否正确
          - 权限是否足够

        Args:
            plan: 待验证的同步计划

        Returns:
            bool: 计划是否合法
        """
        pass

    @abstractmethod
    def execute_plan(self, plan: SyncPlan) -> List[SyncResult]:
        """
        执行同步计划

        Args:
            plan: 已验证的同步计划

        Returns:
            List[SyncResult]: 每个仓库的执行结果列表
        """
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """
        获取同步统计信息

        Returns:
            Dict[str, Any]: 包含总数、成功率、按仓库统计等
        """
        pass
