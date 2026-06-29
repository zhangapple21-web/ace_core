"""
Knowledge Evolution Tracker（知识演化追踪器）

核心职责：
    追踪知识的一生。

    今天一个知识进入Repository。
    未来一年它会：
    - 升级？降级？冻结？失效？替代？分裂？融合？

    谁在负责？

    Knowledge Evolution Tracker。

设计原则：
    - 知识不是静态的，是活的
    - 知识会演化，演化需要被记录
    - 每次状态变化都是一次Evolution Event
    - append-only：所有演化记录永久保留
    - Decision产生Event：所有Event都能回答"是谁批准的"

知识生命链：
    Knowledge → Version → Decision → Evolution Event → Lineage → Repository → Civilization
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class EvolutionType:
    """演化类型"""
    CREATED = "created"                   # 创建
    PROMOTED = "promoted"               # 升级（HYPOTHESIS→EVIDENCE→FACT）
    DEMOTED = "demoted"                 # 降级（FACT→EVIDENCE→HYPOTHESIS）
    CONFLICTED = "conflicted"           # 冲突发现
    SUPERSEDED = "superseded"           # 被替代
    MERGED = "merged"                   # 合并
    SPLIT = "split"                     # 分裂
    FROZEN = "frozen"                   # 冻结
    REVIVED = "revived"                 # 复活
    ARCHIVED = "archived"                # 归档
    DEPRECATED = "deprecated"            # 废弃
    VALIDATED = "validated"              # 验证通过
    VERSIONED = "versioned"              # 内容版本更新


@dataclass
class Actor:
    """
    行为主体（Actor）

    不是一个字符串"system"。
    而是一个完整的对象，回答：
        是谁？
        什么角色？
        什么版本？
        运行在什么runtime？
        授权来自哪里？
    """
    actor_type: str = ""           # 类型：governor/validator/user/system/curator/researcher
    actor_id: str = ""             # 唯一标识
    actor_role: str = ""           # 角色
    version: str = ""              # 模块版本
    runtime: str = ""              # 运行时模型（如 GPT-4o / Claude 3.5）
    authority: str = ""            # 授权来源（如 Contract#89）
    signature: str = ""            # 签名

    def to_dict(self) -> dict:
        return {
            "actor_type": self.actor_type,
            "actor_id": self.actor_id,
            "actor_role": self.actor_role,
            "version": self.version,
            "runtime": self.runtime,
            "authority": self.authority,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'Actor':
        return cls(
            actor_type=d.get("actor_type", ""),
            actor_id=d.get("actor_id", ""),
            actor_role=d.get("actor_role", ""),
            version=d.get("version", ""),
            runtime=d.get("runtime", ""),
            authority=d.get("authority", ""),
            signature=d.get("signature", ""),
        )

    @classmethod
    def system(cls) -> 'Actor':
        """系统默认Actor"""
        return cls(
            actor_type="system",
            actor_id="system_001",
            actor_role="system",
            version="1.0",
            runtime="ace_runtime",
            authority="constitution#001",
        )


@dataclass
class ContextSnapshot:
    """
    上下文快照

    知识为什么升级？
    不是因为reason。
    是因为当时的Context。

    例如：
        Market: 2026 Bull → Evidence++
        到了2028 Bear → 可能又变

    保存Context Snapshot，未来才能复现。
    """
    timestamp: str = ""
    context_type: str = ""          # 上下文类型：market/environment/system_state/external_event
    summary: str = ""               # 上下文摘要
    factors: Dict[str, Any] = field(default_factory=dict)  # 关键因素
    source: str = ""                # 上下文来源

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "context_type": self.context_type,
            "summary": self.summary,
            "factors": self.factors,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'ContextSnapshot':
        return cls(
            timestamp=d.get("timestamp", ""),
            context_type=d.get("context_type", ""),
            summary=d.get("summary", ""),
            factors=d.get("factors", {}),
            source=d.get("source", ""),
        )


@dataclass
class KnowledgeVersion:
    """
    知识内容版本

    不是状态版本。
    是内容版本。

    同一个知识ID，内容可能变。
    Fact V3 和 Fact V5 都是同一个知识，但内容不同。

    以后才能回答：
        哪个版本是真的？
    """
    version_id: str
    knowledge_id: str
    version_number: int
    content_hash: str = ""          # 内容哈希
    content_summary: str = ""       # 内容摘要
    change_description: str = ""    # 变更描述
    status: str = ""                # 该版本对应的状态
    actor: Optional[Actor] = None   # 谁创建了这个版本
    created_at: str = ""
    previous_version: str = ""      # 上一个版本ID
    next_versions: List[str] = field(default_factory=list)  # 后续版本ID列表

    def to_dict(self) -> dict:
        return {
            "version_id": self.version_id,
            "knowledge_id": self.knowledge_id,
            "version_number": self.version_number,
            "content_hash": self.content_hash,
            "content_summary": self.content_summary,
            "change_description": self.change_description,
            "status": self.status,
            "actor": self.actor.to_dict() if self.actor else {},
            "created_at": self.created_at,
            "previous_version": self.previous_version,
            "next_versions": self.next_versions,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'KnowledgeVersion':
        return cls(
            version_id=d["version_id"],
            knowledge_id=d["knowledge_id"],
            version_number=d.get("version_number", 1),
            content_hash=d.get("content_hash", ""),
            content_summary=d.get("content_summary", ""),
            change_description=d.get("change_description", ""),
            status=d.get("status", ""),
            actor=Actor.from_dict(d["actor"]) if d.get("actor") else None,
            created_at=d.get("created_at", ""),
            previous_version=d.get("previous_version", ""),
            next_versions=d.get("next_versions", []),
        )


@dataclass
class EvolutionEvent:
    """
    演化事件

    关键变化：
        - triggered_by 从字符串变成 Actor 对象
        - evidence 从字符串变成 evidence_ids 列表（引用Evidence Registry）
        - 增加 decision_id：这个Event是由哪个Decision产生的
        - 增加 context_snapshot：当时的上下文快照
        - 增加 version_id：涉及的内容版本（如果是内容变化）
    """
    event_id: str
    knowledge_id: str
    evolution_type: str  # EvolutionType
    old_status: str
    new_status: str
    reason: str  # 为什么发生变化
    actor: Actor  # 谁触发了这个变化（替代triggered_by字符串）
    decision_id: str = ""  # 由哪个决策产生
    evidence_ids: List[str] = field(default_factory=list)  # 证据ID列表（替代evidence字符串）
    related_knowledge: List[str] = field(default_factory=list)  # 涉及的相关知识
    context_snapshot: Optional[ContextSnapshot] = None  # 上下文快照
    version_id: str = ""  # 涉及的内容版本ID
    timestamp: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "knowledge_id": self.knowledge_id,
            "evolution_type": self.evolution_type,
            "old_status": self.old_status,
            "new_status": self.new_status,
            "reason": self.reason,
            "actor": self.actor.to_dict(),
            "decision_id": self.decision_id,
            "evidence_ids": self.evidence_ids,
            "related_knowledge": self.related_knowledge,
            "context_snapshot": self.context_snapshot.to_dict() if self.context_snapshot else None,
            "version_id": self.version_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'EvolutionEvent':
        # 向后兼容：旧数据只有triggered_by字符串
        actor = Actor.from_dict(d["actor"]) if "actor" in d and isinstance(d["actor"], dict) else Actor.system()
        if not actor.actor_type and d.get("triggered_by"):
            actor = Actor.system()
            actor.actor_type = d["triggered_by"]

        context = ContextSnapshot.from_dict(d["context_snapshot"]) if d.get("context_snapshot") else None

        return cls(
            event_id=d["event_id"],
            knowledge_id=d["knowledge_id"],
            evolution_type=d["evolution_type"],
            old_status=d["old_status"],
            new_status=d["new_status"],
            reason=d["reason"],
            actor=actor,
            decision_id=d.get("decision_id", ""),
            evidence_ids=d.get("evidence_ids", [d.get("evidence", "")] if d.get("evidence") else []),
            related_knowledge=d.get("related_knowledge", []),
            context_snapshot=context,
            version_id=d.get("version_id", ""),
            timestamp=d["timestamp"],
        )


@dataclass
class KnowledgeLineage:
    """
    知识血缘

    增加：
        - versions: 内容版本历史
        - current_version_id: 当前最新版本ID
    """
    knowledge_id: str
    created_at: str
    current_status: str
    events: List[EvolutionEvent] = field(default_factory=list)
    parent_ids: List[str] = field(default_factory=list)  # 父知识
    child_ids: List[str] = field(default_factory=list)  # 子知识
    merged_from: List[str] = field(default_factory=list)  # 合并来源
    superseded_by: str = ""  # 被谁替代
    versions: List[KnowledgeVersion] = field(default_factory=list)  # 内容版本历史
    current_version_id: str = ""  # 当前最新版本ID

    def to_dict(self) -> dict:
        return {
            "knowledge_id": self.knowledge_id,
            "created_at": self.created_at,
            "current_status": self.current_status,
            "events": [e.to_dict() for e in self.events],
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
            "merged_from": self.merged_from,
            "superseded_by": self.superseded_by,
            "versions": [v.to_dict() for v in self.versions],
            "current_version_id": self.current_version_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'KnowledgeLineage':
        return cls(
            knowledge_id=d["knowledge_id"],
            created_at=d["created_at"],
            current_status=d["current_status"],
            events=[EvolutionEvent.from_dict(e) for e in d.get("events", [])],
            parent_ids=d.get("parent_ids", []),
            child_ids=d.get("child_ids", []),
            merged_from=d.get("merged_from", []),
            superseded_by=d.get("superseded_by", ""),
            versions=[KnowledgeVersion.from_dict(v) for v in d.get("versions", [])],
            current_version_id=d.get("current_version_id", ""),
        )

    def get_version(self, version_id: str) -> Optional[KnowledgeVersion]:
        """获取指定版本"""
        for v in self.versions:
            if v.version_id == version_id:
                return v
        return None

    def get_latest_version(self) -> Optional[KnowledgeVersion]:
        """获取最新版本"""
        if not self.versions:
            return None
        return self.versions[-1]


class KnowledgeEvolutionTracker:
    """
    知识演化追踪器

    核心问题：
        一个知识进入Repository后，它会经历什么？
        谁在追踪它的演化？

    演化闭环：
        KnowledgeStatus → KnowledgeEvolutionTracker → KnowledgeRevision
            ↑                                              ↓
            └──────────────────────────────────────────────┘

    关键变化：
        Decision 产生 EvolutionEvent，而不是直接写Event。
        所有Event都能回答：是谁批准的？
    """

    def __init__(self, data_dir: str):
        """
        初始化演化追踪器

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.evolution_dir = self.data_dir / "evolution_tracker"
        self.evolution_dir.mkdir(parents=True, exist_ok=True)

        self.events_file = self.evolution_dir / "evolution_events.jsonl"
        self.lineage_file = self.evolution_dir / "knowledge_lineage.json"
        self.versions_file = self.evolution_dir / "knowledge_versions.jsonl"

        # 内存索引
        self.lineages: Dict[str, KnowledgeLineage] = {}
        self.events: List[EvolutionEvent] = []
        self.versions: Dict[str, KnowledgeVersion] = {}

        # 加载已有数据
        self._load_lineages()
        self._load_events()
        self._load_versions()

    # ═══════════════════════════════════════════════════════════════════════
    # 加载与保存
    # ═══════════════════════════════════════════════════════════════════════

    def _load_lineages(self):
        """加载血缘关系"""
        if not self.lineage_file.exists():
            return

        try:
            with open(self.lineage_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                for kp_id, kp_data in data.items():
                    lineage = KnowledgeLineage.from_dict(kp_data)
                    self.lineages[kp_id] = lineage
            logger.info(f"加载了 {len(self.lineages)} 个知识血缘")
        except Exception as e:
            logger.error(f"加载血缘失败: {e}")

    def _load_events(self):
        """加载演化事件"""
        if not self.events_file.exists():
            return

        try:
            with open(self.events_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        event = EvolutionEvent.from_dict(data)
                        self.events.append(event)
                    except Exception:
                        continue
            logger.info(f"加载了 {len(self.events)} 个演化事件")
        except Exception as e:
            logger.error(f"加载事件失败: {e}")

    def _load_versions(self):
        """加载版本记录"""
        if not self.versions_file.exists():
            return

        try:
            with open(self.versions_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        version = KnowledgeVersion.from_dict(data)
                        self.versions[version.version_id] = version
                    except Exception:
                        continue
            logger.info(f"加载了 {len(self.versions)} 个知识版本")
        except Exception as e:
            logger.error(f"加载版本失败: {e}")

    def _save_event(self, event: EvolutionEvent):
        """保存事件"""
        try:
            with open(self.events_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存事件失败: {e}")

    def _save_version(self, version: KnowledgeVersion):
        """保存版本"""
        try:
            with open(self.versions_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(version.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存版本失败: {e}")

    def _save_lineages(self):
        """保存所有血缘"""
        try:
            data = {}
            for kp_id, lineage in self.lineages.items():
                data[kp_id] = lineage.to_dict()

            with open(self.lineage_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存血缘失败: {e}")

    # ═══════════════════════════════════════════════════════════════════════
    # 核心API：Decision产生Event
    # ═══════════════════════════════════════════════════════════════════════

    def record_decision_and_event(
        self,
        knowledge_id: str,
        old_status: str,
        new_status: str,
        reason: str,
        actor: Actor,
        decision_id: str = "",
        evidence_ids: List[str] = None,
        related_knowledge: List[str] = None,
        context_snapshot: ContextSnapshot = None,
        version_id: str = "",
    ) -> EvolutionEvent:
        """
        记录决策并产生演化事件

        这是核心方法：Decision → EvolutionEvent

        不是直接写Event。
        而是：Decision产生Event。

        以后所有Event都能回答：
            是谁批准的？
        """
        if evidence_ids is None:
            evidence_ids = []
        if related_knowledge is None:
            related_knowledge = []

        # 判断演化类型
        evolution_type = self._determine_evolution_type(old_status, new_status)

        event = EvolutionEvent(
            event_id=f"EVT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(self.events):04d}",
            knowledge_id=knowledge_id,
            evolution_type=evolution_type,
            old_status=old_status,
            new_status=new_status,
            reason=reason,
            actor=actor,
            decision_id=decision_id,
            evidence_ids=evidence_ids,
            related_knowledge=related_knowledge,
            context_snapshot=context_snapshot,
            version_id=version_id,
            timestamp=datetime.now().isoformat(),
        )

        # 更新血缘
        self._update_lineage_with_event(knowledge_id, event)

        # 保存
        self.events.append(event)
        self._save_event(event)
        self._save_lineages()

        logger.info(f"追踪状态变化: {knowledge_id} {old_status} → {new_status} (决策: {decision_id})")
        return event

    def _update_lineage_with_event(self, knowledge_id: str, event: EvolutionEvent):
        """用事件更新血缘"""
        if knowledge_id not in self.lineages:
            # 如果不存在，创建一个
            self.lineages[knowledge_id] = KnowledgeLineage(
                knowledge_id=knowledge_id,
                created_at=event.timestamp,
                current_status=event.new_status,
                events=[event],
            )
            return

        lineage = self.lineages[knowledge_id]
        lineage.current_status = event.new_status
        lineage.events.append(event)

        # 更新父子关系
        if event.evolution_type == EvolutionType.SUPERSEDED and event.related_knowledge:
            lineage.superseded_by = event.related_knowledge[0]
        if event.evolution_type == EvolutionType.MERGED:
            lineage.merged_from.extend(event.related_knowledge)

    # ═══════════════════════════════════════════════════════════════════════
    # 版本管理
    # ═══════════════════════════════════════════════════════════════════════

    def create_version(
        self,
        knowledge_id: str,
        content_hash: str,
        content_summary: str,
        change_description: str,
        status: str,
        actor: Actor,
        previous_version_id: str = "",
    ) -> KnowledgeVersion:
        """
        创建知识的一个新版本

        Args:
            knowledge_id: 知识ID
            content_hash: 内容哈希
            content_summary: 内容摘要
            change_description: 变更描述
            status: 该版本对应的状态
            actor: 创建者
            previous_version_id: 上一个版本ID

        Returns:
            新版本对象
        """
        # 计算版本号
        version_count = sum(1 for v in self.versions.values() if v.knowledge_id == knowledge_id)
        version_number = version_count + 1

        version_id = f"VER-{datetime.now().strftime('%Y%m%d%H%M%S')}-{version_number:04d}"

        version = KnowledgeVersion(
            version_id=version_id,
            knowledge_id=knowledge_id,
            version_number=version_number,
            content_hash=content_hash,
            content_summary=content_summary,
            change_description=change_description,
            status=status,
            actor=actor,
            created_at=datetime.now().isoformat(),
            previous_version=previous_version_id,
        )

        # 更新上一个版本的next_versions
        if previous_version_id and previous_version_id in self.versions:
            prev = self.versions[previous_version_id]
            if version_id not in prev.next_versions:
                prev.next_versions.append(version_id)
            self._save_version(prev)  # 追加更新

        # 保存
        self.versions[version_id] = version
        self._save_version(version)

        # 更新血缘
        if knowledge_id in self.lineages:
            lineage = self.lineages[knowledge_id]
            lineage.versions.append(version)
            lineage.current_version_id = version_id
            self._save_lineages()

        logger.info(f"创建新版本: {knowledge_id} v{version_number} ({version_id})")
        return version

    def get_version(self, version_id: str) -> Optional[KnowledgeVersion]:
        """获取指定版本"""
        return self.versions.get(version_id)

    def get_versions_for_knowledge(self, knowledge_id: str) -> List[KnowledgeVersion]:
        """获取知识的所有版本"""
        return [v for v in self.versions.values() if v.knowledge_id == knowledge_id]

    def get_latest_version(self, knowledge_id: str) -> Optional[KnowledgeVersion]:
        """获取知识的最新版本"""
        if knowledge_id in self.lineages:
            lineage = self.lineages[knowledge_id]
            return lineage.get_latest_version()
        versions = self.get_versions_for_knowledge(knowledge_id)
        return versions[-1] if versions else None

    # ═══════════════════════════════════════════════════════════════════════
    # 向后兼容的API（保留旧接口，内部调用新接口）
    # ═══════════════════════════════════════════════════════════════════════

    def track_creation(
        self,
        knowledge_id: str,
        initial_status: str,
        reason: str = "",
        actor: Actor = None,
    ) -> EvolutionEvent:
        """
        追踪知识创建（向后兼容）

        Args:
            knowledge_id: 知识ID
            initial_status: 初始状态
            reason: 创建原因
            actor: 行为主体（默认system）

        Returns:
            演化事件
        """
        if actor is None:
            actor = Actor.system()

        event = EvolutionEvent(
            event_id=f"EVT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(self.events):04d}",
            knowledge_id=knowledge_id,
            evolution_type=EvolutionType.CREATED,
            old_status="",
            new_status=initial_status,
            reason=reason,
            actor=actor,
            decision_id="auto_creation",
            timestamp=datetime.now().isoformat(),
        )

        # 创建血缘记录
        lineage = KnowledgeLineage(
            knowledge_id=knowledge_id,
            created_at=datetime.now().isoformat(),
            current_status=initial_status,
            events=[event],
        )
        self.lineages[knowledge_id] = lineage

        # 保存
        self.events.append(event)
        self._save_event(event)
        self._save_lineages()

        return event

    def track_status_change(
        self,
        knowledge_id: str,
        old_status: str,
        new_status: str,
        reason: str,
        evidence: str = "",
        triggered_by: str = "system",
        related_knowledge: List[str] = None,
    ) -> EvolutionEvent:
        """
        追踪状态变化（向后兼容）

        注意：推荐使用 record_decision_and_event() 替代
        """
        # 从triggered_by字符串构建Actor
        actor = Actor.system()
        actor.actor_type = triggered_by

        # 旧的evidence是字符串，转成evidence_ids列表
        evidence_ids = [evidence] if evidence else []

        return self.record_decision_and_event(
            knowledge_id=knowledge_id,
            old_status=old_status,
            new_status=new_status,
            reason=reason,
            actor=actor,
            decision_id=f"legacy_{triggered_by}",
            evidence_ids=evidence_ids,
            related_knowledge=related_knowledge,
        )

    # ═══════════════════════════════════════════════════════════════════════
    # 内部方法
    # ═══════════════════════════════════════════════════════════════════════

    def _determine_evolution_type(self, old_status: str, new_status: str) -> str:
        """判断演化类型"""
        status_order = ["HYPOTHESIS", "EVIDENCE", "VALIDATED", "FACT"]

        try:
            old_idx = status_order.index(old_status)
            new_idx = status_order.index(new_status)

            if new_idx > old_idx:
                return EvolutionType.PROMOTED
            elif new_idx < old_idx:
                return EvolutionType.DEMOTED
            else:
                return EvolutionType.VALIDATED
        except ValueError:
            # 非标准状态变化
            if old_status == "":
                return EvolutionType.CREATED
            return EvolutionType.VALIDATED

    # ═══════════════════════════════════════════════════════════════════════
    # 查询API
    # ═══════════════════════════════════════════════════════════════════════

    def get_knowledge_history(self, knowledge_id: str) -> List[EvolutionEvent]:
        """获取知识演化历史"""
        if knowledge_id in self.lineages:
            return self.lineages[knowledge_id].events
        return []

    def get_lineage(self, knowledge_id: str) -> Optional[KnowledgeLineage]:
        """获取知识血缘"""
        return self.lineages.get(knowledge_id)

    def get_descendants(self, knowledge_id: str) -> List[str]:
        """获取知识的所有后代"""
        descendants = []
        visited = set()

        def traverse(kid):
            if kid in visited:
                return
            visited.add(kid)

            lineage = self.lineages.get(kid)
            if not lineage:
                return

            for child_id in lineage.child_ids:
                descendants.append(child_id)
                traverse(child_id)

        traverse(knowledge_id)
        return descendants

    def get_ancestors(self, knowledge_id: str) -> List[str]:
        """获取知识的所有祖先"""
        ancestors = []
        visited = set()

        def traverse(kid):
            if kid in visited:
                return
            visited.add(kid)

            lineage = self.lineages.get(kid)
            if not lineage:
                return

            for parent_id in lineage.parent_ids:
                ancestors.append(parent_id)
                traverse(parent_id)

        traverse(knowledge_id)
        return ancestors

    def get_knowledge_timeline(self, knowledge_id: str) -> str:
        """获取知识的演化时间线（人类可读）"""
        events = self.get_knowledge_history(knowledge_id)

        if not events:
            return "无演化记录"

        timeline = []
        for event in events:
            ts = datetime.fromisoformat(event.timestamp).strftime("%Y-%m-%d %H:%M")
            actor_str = event.actor.actor_type if event.actor else "unknown"
            timeline.append(f"{ts} | {event.evolution_type:12} | {event.old_status} → {event.new_status} | by {actor_str}")

        return "\n".join(timeline)

    def get_active_knowledge(self) -> List[str]:
        """获取当前活跃的知识（未被归档/废弃/替代）"""
        active = []

        inactive_statuses = [EvolutionType.ARCHIVED, EvolutionType.DEPRECATED, "SUPERSEDED"]

        for kp_id, lineage in self.lineages.items():
            is_active = True
            for event in lineage.events:
                if event.evolution_type in inactive_statuses:
                    is_active = False
                    break

            if is_active:
                active.append(kp_id)

        return active

    def get_stale_knowledge(self, days: int = 90) -> List[str]:
        """获取长期未更新的知识"""
        stale = []
        cutoff = datetime.now() - timedelta(days=days)

        for kp_id, lineage in self.lineages.items():
            if lineage.events:
                last_event_time = datetime.fromisoformat(lineage.events[-1].timestamp)
                if last_event_time < cutoff:
                    stale.append(kp_id)

        return stale

    def get_evolution_summary(self) -> Dict[str, Any]:
        """获取演化摘要"""
        summary = {
            "total_knowledge": len(self.lineages),
            "total_events": len(self.events),
            "total_versions": len(self.versions),
            "by_type": {},
            "active_count": len(self.get_active_knowledge()),
            "stale_count": len(self.get_stale_knowledge()),
        }

        # 统计各类型事件
        for event in self.events:
            ev_type = event.evolution_type
            summary["by_type"][ev_type] = summary["by_type"].get(ev_type, 0) + 1

        return summary

    # ═══════════════════════════════════════════════════════════════════════
    # 知识护照（Knowledge Passport）
    # ═══════════════════════════════════════════════════════════════════════

    def get_knowledge_passport(self, knowledge_id: str) -> Dict[str, Any]:
        """
        获取知识护照

        每个知识都有一本"身份证"，回答：
            我是谁？
            我从哪里来？
            我为什么存在？
            是谁创造了我？
            后来发生了什么？
            为什么今天我变成这样？
        """
        lineage = self.lineages.get(knowledge_id)
        if not lineage:
            return {}

        latest_version = lineage.get_latest_version()
        first_event = lineage.events[0] if lineage.events else None
        last_event = lineage.events[-1] if lineage.events else None

        # 计算置信度（基于证据数量）
        evidence_count = set()
        for event in lineage.events:
            evidence_count.update(event.evidence_ids)
        evidence_count = len([e for e in evidence_count if e])

        # 计算熵（基于事件数量和复杂度）
        entropy_score = min(1.0, len(lineage.events) * 0.1)

        return {
            "knowledge_id": knowledge_id,
            "birth": lineage.created_at,
            "creator": first_event.actor.actor_type if first_event and first_event.actor else "unknown",
            "first_evidence": lineage.events[0].evidence_ids[0] if lineage.events and lineage.events[0].evidence_ids else "",
            "current_version": latest_version.version_number if latest_version else 0,
            "current_version_id": lineage.current_version_id,
            "current_status": lineage.current_status,
            "governor": last_event.actor.actor_type if last_event and last_event.actor else "unknown",
            "confidence": min(0.3 + evidence_count * 0.05, 0.95),
            "entropy": entropy_score,
            "total_events": len(lineage.events),
            "total_versions": len(lineage.versions),
            "parent_count": len(lineage.parent_ids),
            "child_count": len(lineage.child_ids),
            "last_review": last_event.timestamp if last_event else "",
            "next_review": "",  # 可以根据策略计算
            "risk_level": "low" if entropy_score < 0.3 else "medium" if entropy_score < 0.7 else "high",
            "civilization_value": self._calculate_civilization_value(lineage),
        }

    def _calculate_civilization_value(self, lineage: KnowledgeLineage) -> float:
        """计算文明价值（简化版）"""
        # 基于：状态等级、版本数、后代数、证据数
        status_value = {
            "FACT": 1.0,
            "VALIDATED": 0.8,
            "EVIDENCE": 0.6,
            "HYPOTHESIS": 0.3,
        }
        base = status_value.get(lineage.current_status, 0.1)
        version_bonus = min(len(lineage.versions) * 0.05, 0.2)
        child_bonus = min(len(lineage.child_ids) * 0.02, 0.1)
        return min(base + version_bonus + child_bonus, 1.0)
