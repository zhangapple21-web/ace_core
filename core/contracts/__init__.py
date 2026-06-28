"""
Contracts — 契约层

定义系统核心契约，包括：
- 馆长决策契约 (curator_decision_contract)
- 同步执行契约 (sync_execution_contract)

契约层是决策层与执行层之间的接口规范，
确保模块间解耦和可替换性。
"""

from .curator_decision_contract import (
    DecisionAction,
    ArtifactType,
    ScoreDimension,
    ArtifactScore,
    SimilarDocument,
    SplitCandidate,
    ArtifactDecision,
    CuratorDecisionContext,
    ICuratorDecisionEngine,
    SyncPlan,
    CuratorDecisionContract,
)

from .sync_execution_contract import (
    SyncAction,
    SyncStatus,
    RepoType,
    SyncOperation,
    SyncResult,
    LastSyncRecord,
    SyncLogEntry,
    SyncPlanVerification,
    ISyncExecutor,
    IGitOperator,
    GitOperator,
    SyncExecutionContract,
)

__all__ = [
    "DecisionAction",
    "ArtifactType",
    "ScoreDimension",
    "ArtifactScore",
    "SimilarDocument",
    "SplitCandidate",
    "ArtifactDecision",
    "CuratorDecisionContext",
    "ICuratorDecisionEngine",
    "SyncPlan",
    "CuratorDecisionContract",
    "SyncAction",
    "SyncStatus",
    "RepoType",
    "SyncOperation",
    "SyncResult",
    "LastSyncRecord",
    "SyncLogEntry",
    "SyncPlanVerification",
    "ISyncExecutor",
    "IGitOperator",
    "GitOperator",
    "SyncExecutionContract",
]
