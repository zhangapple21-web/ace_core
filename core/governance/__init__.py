"""
Governance Layer — 治理层

Knowledge Civilization OS 架构：

    ┌─────────────────────────────────────────────────────────────┐
    │                     Constitution                             │
    │              （文明宪法，不可违背的根本原则）                    │
    │                                                              │
    │  Append-only / Evidence First / Never Delete / No Override   │
    └─────────────────────────────────────────────────────────────┘
                              ▲
                              │
    ┌─────────────────────────────────────────────────────────────┐
    │                        Policy                                │
    │                   （治理策略，版本化可调整）                     │
    │                                                              │
    │  Version / Weight / Threshold / Metric                       │
    └─────────────────────────────────────────────────────────────┘
                              ▲
                              │
    ┌─────────────────────────────────────────────────────────────┐
    │                    Intent Contract                           │
    │                      （意图契约）                              │
    │                                                              │
    │  Problem / Reason / Expected Impact / Affected Modules       │
    └─────────────────────────────────────────────────────────────┘
                              ▲
                              │
    ┌─────────────────────────────────────────────────────────────┐
    │                    Knowledge Flow                             │
    │                      （文明流）                               │
    │                                                              │
    │  Knowledge Status                                            │
    │       │                                                      │
    │       ▼                                                      │
    │  Knowledge Lifecycle                                         │
    │       │                                                      │
    │       ▼                                                      │
    │  Evidence Registry                                           │
    │       │                                                      │
    │       ▼                                                      │
    │  Repository Memory                                           │
    │       │                                                      │
    │       ▼                                                      │
    │  Decision Log                                                │
    │       │                                                      │
    │       ▼                                                      │
    │  Entropy Monitor (Knowledge Entropy)                         │
    │       │                                                      │
    │       ▼                                                      │
    │  Assumptions                                                 │
    │       │                                                      │
    │       ▼                                                      │
    │  Mengpo（遗忘 → 降温）                                        │
    │       │                                                      │
    │       ▼                                                      │
    │  Civilization Graph                                           │
    │       │                                                      │
    │       ▼                                                      │
    │  Contracts (5个契约)                                         │
    │       │                                                      │
    │       ▼                                                      │
    │  Knowledge Governor                                          │
    │       │                                                      │
    │       ▼                                                      │
    │  Repository Governor                                         │
    │       │                                                      │
    │       ▼                                                      │
    │  Knowledge Revision                                          │
    │       │                                                      │
    │       ▼                                                      │
    │  Daily Civilization Report                                   │
    └─────────────────────────────────────────────────────────────┘

不是 Runtime。
是 Knowledge Civilization OS。

核心原则：
    任何新增模块，都必须回答一个问题：它是在增加文明，还是在增加熵？
"""

# ═══════════════════════════════════════════════════════════════════════════
# CONSTITUTION（宪法层）- 不可违背的根本原则
# ═══════════════════════════════════════════════════════════════════════════

from .constitution import (
    ConstitutionalPrinciple,
    Principle,
    Constitution,
)

# ═══════════════════════════════════════════════════════════════════════════
# POLICY（策略层）- 版本化可调整的规则
# ═══════════════════════════════════════════════════════════════════════════

from .policy import (
    PolicyRule,
    PolicyEvaluation,
    Policy,
)

# ═══════════════════════════════════════════════════════════════════════════
# INTENT CONTRACT（意图契约）- 记录为什么做，比记录做了什么更重要
# ═══════════════════════════════════════════════════════════════════════════

from .intent_contract import (
    Intent,
    IntentRecord,
    IntentContract,
)

# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE STATUS（知识状态系统）- 现在是什么
# ═══════════════════════════════════════════════════════════════════════════

from .knowledge_status import (
    KnowledgeStatus,
    KnowledgeMetadata,
    KnowledgeRegistry,
)

# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE LIFECYCLE（知识生命周期）- 下一步去哪
# ═══════════════════════════════════════════════════════════════════════════

from .knowledge_lifecycle import (
    LifecycleStage,
    LifecycleTransition,
    KnowledgeLifecycle,
    LifecycleManager,
)

# ═══════════════════════════════════════════════════════════════════════════
# EVIDENCE REGISTRY（证据登记处）- 证据独立成对象
# ═══════════════════════════════════════════════════════════════════════════

from .evidence_registry import (
    Evidence,
    EvidenceRegistry,
)

# ═══════════════════════════════════════════════════════════════════════════
# REPOSITORY MEMORY（仓库记忆）- 记录为什么
# ═══════════════════════════════════════════════════════════════════════════

from .repository_memory import (
    RepositoryMemoryEntry,
    RepositoryMemory,
    RepositoryJournal,
)

# ═══════════════════════════════════════════════════════════════════════════
# DECISION LOG（决策日志）- 记录决策过程
# ═══════════════════════════════════════════════════════════════════════════

from .decision_log import (
    DecisionEntry,
    DecisionLog,
)

# ═══════════════════════════════════════════════════════════════════════════
# ENTROPY MONITOR（熵监控器）- 知识熵（语义层）
# ═══════════════════════════════════════════════════════════════════════════

from .entropy_monitor import (
    EntropyReport,
    EntropyMonitor,
)

# ═══════════════════════════════════════════════════════════════════════════
# ASSUMPTIONS（假说系统）- 目前相信但尚未证实
# ═══════════════════════════════════════════════════════════════════════════

from .assumptions import (
    Assumption,
    AssumptionManager,
    initialize_core_assumptions,
)

# ═══════════════════════════════════════════════════════════════════════════
# MENGPO（遗忘机制）- 降温而非删除
# ═══════════════════════════════════════════════════════════════════════════

from .mengpo import (
    MengpoMemoryDecay,
    ForgettingCandidate,
    MemoryLine,
    MengpoRecord,
)

# ═══════════════════════════════════════════════════════════════════════════
# CIVILIZATION GRAPH（文明图）- 知识关系网络
# ═══════════════════════════════════════════════════════════════════════════

from .civilization_graph import (
    RelationType,
    KnowledgeNode,
    KnowledgeRelation,
    CivilizationGraph,
)

# ═══════════════════════════════════════════════════════════════════════════
# CONTRACTS（契约层）- 5个契约
# ═══════════════════════════════════════════════════════════════════════════

from .contracts import (
    ContractType,
    ContractDecision,
    ContractRecord,
    EvidenceContract,
    AuthorityContract,
    CuratorContract,
    RepositoryContract,
    PublicationContract,
    ContractManager,
)

# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE GOVERNOR（知识馆长）- 能不能进文明？
# ═══════════════════════════════════════════════════════════════════════════

from .knowledge_governor import (
    AdmissionDecision,
    AdmissionCriteria,
    AdmissionRecord,
    KnowledgeGovernor,
)

# ═══════════════════════════════════════════════════════════════════════════
# REPOSITORY GOVERNOR（仓库治理官）- 应该去哪？
# ═══════════════════════════════════════════════════════════════════════════

from .repository_governor import (
    RepositoryTier,
    PlacementDecision,
    RepositoryGovernor,
)

# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE EVOLUTION TRACKER（知识演化追踪器）- 知识的一生
# ═══════════════════════════════════════════════════════════════════════════

from .knowledge_evolution import (
    EvolutionType,
    EvolutionEvent,
    KnowledgeLineage,
    KnowledgeEvolutionTracker,
    Actor,
    ContextSnapshot,
    KnowledgeVersion,
)

# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE REVISION（知识修订器）- 修订 > 新增
# ═══════════════════════════════════════════════════════════════════════════

from .knowledge_revision import (
    RevisionRecord,
    DailyRevisionReport,
    KnowledgeRevision,
)

# ═══════════════════════════════════════════════════════════════════════════
# DAILY CIVILIZATION REPORT（每日文明报告）- 四类变化
# ═══════════════════════════════════════════════════════════════════════════

from .daily_civilization_report import (
    DailyChange,
    CivilizationReport,
    DailyCivilizationReporter,
)

from .civilization_status import (
    CivilizationStatus,
)

from .experience_health import (
    ExperienceHealthMonitor,
)

from .concept_health import (
    ConceptHealthMonitor,
)


__all__ = [
    # Constitution（宪法层）
    'ConstitutionalPrinciple',
    'Principle',
    'Constitution',

    # Policy（策略层）
    'PolicyRule',
    'PolicyEvaluation',
    'Policy',

    # Intent Contract（意图契约）
    'Intent',
    'IntentRecord',
    'IntentContract',

    # Knowledge Status
    'KnowledgeStatus',
    'KnowledgeMetadata',
    'KnowledgeRegistry',

    # Knowledge Lifecycle
    'LifecycleStage',
    'LifecycleTransition',
    'KnowledgeLifecycle',
    'LifecycleManager',

    # Evidence Registry
    'Evidence',
    'EvidenceRegistry',

    # Repository Memory
    'RepositoryMemoryEntry',
    'RepositoryMemory',
    'RepositoryJournal',

    # Decision Log
    'DecisionEntry',
    'DecisionLog',

    # Entropy Monitor
    'EntropyReport',
    'EntropyMonitor',

    # Assumptions
    'Assumption',
    'AssumptionManager',
    'initialize_core_assumptions',

    # Mengpo（遗忘 → 降温）
    'MengpoMemoryDecay',
    'ForgettingCandidate',
    'MemoryLine',
    'MengpoRecord',

    # Civilization Graph
    'RelationType',
    'KnowledgeNode',
    'KnowledgeRelation',
    'CivilizationGraph',

    # Contracts
    'ContractType',
    'ContractDecision',
    'ContractRecord',
    'EvidenceContract',
    'AuthorityContract',
    'CuratorContract',
    'RepositoryContract',
    'PublicationContract',
    'ContractManager',

    # Knowledge Governor
    'AdmissionDecision',
    'AdmissionCriteria',
    'AdmissionRecord',
    'KnowledgeGovernor',

    # Repository Governor
    'RepositoryTier',
    'PlacementDecision',
    'RepositoryGovernor',

    # Knowledge Evolution Tracker
    'EvolutionType',
    'EvolutionEvent',
    'KnowledgeLineage',
    'KnowledgeEvolutionTracker',
    'Actor',
    'ContextSnapshot',
    'KnowledgeVersion',

    # Knowledge Revision
    'RevisionRecord',
    'DailyRevisionReport',
    'KnowledgeRevision',

    # Daily Civilization Report
    'DailyChange',
    'CivilizationReport',
    'DailyCivilizationReporter',

    # Civilization Status
    'CivilizationStatus',

    # Experience Health
    'ExperienceHealthMonitor',

    # Concept Health
    'ConceptHealthMonitor',
]
