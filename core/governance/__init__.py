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
# GOVERNOR（统一治理者）- 能不能进 + 应该去哪
# ═══════════════════════════════════════════════════════════════════════════
# 单一 Governor，下挂两个决策能力：
#   Knowledge Decision — 评估准入
#   Repository Decision — 决定放置

from .knowledge_governor import (
    AdmissionDecision,
    AdmissionCriteria,
    AdmissionRecord,
    Governor,
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
    DailyMeetingReport,
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

# ═══════════════════════════════════════════════════════════════════════════
# EVOLUTION PLANNER（演化规划器）- 每天结束时问自己四个问题
# ═══════════════════════════════════════════════════════════════════════════
# 老张的核心要求：
# 1. 今天真正新增了什么能力，而不是新增了什么文件？
# 2. 今天拒绝了哪些东西，为什么拒绝？
# 3. 今天哪些知识发生了升级、降级或废弃？
# 4. 如果明天只能研究一个方向，应该选哪一个，为什么？
# ═══════════════════════════════════════════════════════════════════════════

from .evolution_planner import (
    EvolutionQuestion,
    DailyEvolutionReport,
    EvolutionPlanner,
)

# ═══════════════════════════════════════════════════════════════════════════
# REJECTION ENGINE（拒绝引擎）- 系统要学会说"不要"
# ═══════════════════════════════════════════════════════════════════════════
# 老张的核心要求：
# 真正成熟后会大量输出：
# - Reject（拒绝）
# - Duplicate（重复）
# - Already Known（已知）
# - Too Implementation-Specific（只是实现细节）
# - Only Keep Philosophy（只保留哲学层）
# 每天应该输出："今天拒绝了 X 个结构"
# ═══════════════════════════════════════════════════════════════════════════

from .rejection_engine import (
    RejectionReason,
    Rejection,
    AcceptanceRecord,
    GovernorRejectionEngine,
)

# ═══════════════════════════════════════════════════════════════════════════
# GOVERNOR PROTOCOL（治理协议）- 宪法实施细则
# ═══════════════════════════════════════════════════════════════════════════

from .governor_protocol import (
    AdmissionCriterion,
    AdmissionCriteriaResult,
    AdmissionCriteria,
    SubmissionRule,
    SubmissionRulesResult,
    SubmissionRules,
    RejectionEvaluation,
    RejectionCriteria,
    QualityCheck,
    QualityAssessment,
    QualityAssurance,
    AuthorityLevel,
    DecisionAuthority,
    ProtocolDecision,
    ProtocolResult,
    ProtocolEngine,
    RoundtableRole,
    RoundtableStatement,
    RoundtableDecision,
    RoundtableRecord,
    RoundtableMeeting,
)

# ═══════════════════════════════════════════════════════════════════════════
# STABLE RECURSIVE KERNEL（稳定递归内核）
# ═══════════════════════════════════════════════════════════════════════════
from .stable_kernel import (
    StateSnapshot,
    DriftController,
    DriftCheckResult,
    StabilityLayer,
    FeedbackLoop,
    SelfReflector,
    StableRecursiveKernel,
    KernelCycleResult,
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

    # Governor（统一治理者）
    'AdmissionDecision',
    'AdmissionCriteria',
    'AdmissionRecord',
    'Governor',

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
    'DailyMeetingReport',
    'DailyCivilizationReporter',

    # Civilization Status
    'CivilizationStatus',

    # Experience Health
    'ExperienceHealthMonitor',

    # Concept Health
    'ConceptHealthMonitor',

    # Evolution Planner
    'EvolutionQuestion',
    'DailyEvolutionReport',
    'EvolutionPlanner',

    # Rejection Engine
    'RejectionReason',
    'Rejection',
    'AcceptanceRecord',
    'GovernorRejectionEngine',

    # Governor Protocol
    'AdmissionCriterion',
    'AdmissionCriteriaResult',
    'AdmissionCriteria',
    'SubmissionRule',
    'SubmissionRulesResult',
    'SubmissionRules',
    'RejectionEvaluation',
    'RejectionCriteria',
    'QualityCheck',
    'QualityAssessment',
    'QualityAssurance',
    'AuthorityLevel',
    'DecisionAuthority',
    'ProtocolDecision',
    'ProtocolResult',
    'ProtocolEngine',

    # Roundtable Meeting（圆桌会议）
    'RoundtableRole',
    'RoundtableStatement',
    'RoundtableDecision',
    'RoundtableRecord',
    # Stable Recursive Kernel（稳定递归内核）
    'StateSnapshot',
    'DriftController',
    'DriftCheckResult',
    'StabilityLayer',
    'FeedbackLoop',
    'SelfReflector',
    'StableRecursiveKernel',
    'KernelCycleResult',
]
