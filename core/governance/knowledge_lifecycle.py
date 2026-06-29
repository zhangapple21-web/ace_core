"""
Knowledge Lifecycle System

知识生命周期：
Observation → Research → Validation → Contract → Repository Candidate → Published → Deprecated → Archived → Graveyard
"""

from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import json

class LifecycleStage(Enum):
    """生命周期阶段"""
    OBSERVATION = "Observation"           # 观察阶段
    RESEARCH = "Research"                 # 研究阶段
    VALIDATION = "Validation"             # 验证阶段
    CONTRACT = "Contract"                 # 契约阶段
    REPOSITORY_CANDIDATE = "Repository Candidate"  # 仓库候选
    PUBLISHED = "Published"               # 已发布
    DEPRECATED = "Deprecated"             # 已废弃
    ARCHIVED = "Archived"                 # 已归档
    GRAVEYARD = "Graveyard"               # 坟墓（最终状态）
    
    # 终止状态
    TERMINAL_STATES = {PUBLISHED, DEPRECATED, ARCHIVED, GRAVEYARD}
    
    # 活跃状态
    ACTIVE_STATES = {OBSERVATION, RESEARCH, VALIDATION, CONTRACT, REPOSITORY_CANDIDATE, PUBLISHED}


@dataclass
class LifecycleTransition:
    """生命周期转换记录"""
    from_stage: str
    to_stage: str
    timestamp: str
    reason: str
    triggered_by: str  # 谁触发的
    evidence: List[str] = field(default_factory=list)


@dataclass
class KnowledgeLifecycle:
    """知识的生命周期状态"""
    knowledge_id: str
    current_stage: LifecycleStage = LifecycleStage.OBSERVATION
    stage_history: List[LifecycleTransition] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    published_at: Optional[str] = None
    archived_at: Optional[str] = None
    
    # 阶段详情
    observation_notes: List[str] = field(default_factory=list)
    research_notes: List[str] = field(default_factory=list)
    validation_notes: List[str] = field(default_factory=list)
    contract_notes: List[str] = field(default_factory=list)
    
    def can_transition(self, to_stage: LifecycleStage) -> bool:
        """检查是否可以转换到目标阶段"""
        # 阶段顺序检查
        valid_transitions = {
            LifecycleStage.OBSERVATION: {LifecycleStage.RESEARCH, LifecycleStage.GRAVEYARD},
            LifecycleStage.RESEARCH: {LifecycleStage.VALIDATION, LifecycleStage.GRAVEYARD},
            LifecycleStage.VALIDATION: {LifecycleStage.CONTRACT, LifecycleStage.GRAVEYARD},
            LifecycleStage.CONTRACT: {LifecycleStage.REPOSITORY_CANDIDATE, LifecycleStage.GRAVEYARD},
            LifecycleStage.REPOSITORY_CANDIDATE: {LifecycleStage.PUBLISHED, LifecycleStage.GRAVEYARD},
            LifecycleStage.PUBLISHED: {LifecycleStage.DEPRECATED, LifecycleStage.ARCHIVED, LifecycleStage.GRAVEYARD},
            LifecycleStage.DEPRECATED: {LifecycleStage.ARCHIVED, LifecycleStage.GRAVEYARD},
            LifecycleStage.ARCHIVED: {LifecycleStage.GRAVEYARD, LifecycleStage.PUBLISHED},
            LifecycleStage.GRAVEYARD: set(),  # 最终状态，不能转换
        }
        
        return to_stage in valid_transitions.get(self.current_stage, set())
    
    def transition(self, to_stage: LifecycleStage, reason: str, triggered_by: str, evidence: List[str] = None) -> bool:
        """执行生命周期转换"""
        if not self.can_transition(to_stage):
            return False
        
        transition = LifecycleTransition(
            from_stage=self.current_stage.value,
            to_stage=to_stage.value,
            timestamp=datetime.now().isoformat(),
            reason=reason,
            triggered_by=triggered_by,
            evidence=evidence or []
        )
        
        self.stage_history.append(transition)
        self.current_stage = to_stage
        self.updated_at = datetime.now().isoformat()
        
        # 设置时间戳
        if to_stage == LifecycleStage.PUBLISHED:
            self.published_at = datetime.now().isoformat()
        elif to_stage == LifecycleStage.ARCHIVED:
            self.archived_at = datetime.now().isoformat()
        
        return True
    
    def add_note(self, note: str) -> None:
        """在当前阶段添加注释"""
        note_with_time = f"[{datetime.now().isoformat()}] {note}"
        stage_notes = {
            LifecycleStage.OBSERVATION: self.observation_notes,
            LifecycleStage.RESEARCH: self.research_notes,
            LifecycleStage.VALIDATION: self.validation_notes,
            LifecycleStage.CONTRACT: self.contract_notes,
        }
        notes = stage_notes.get(self.current_stage)
        if notes is not None:
            notes.append(note_with_time)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        d = {
            "knowledge_id": self.knowledge_id,
            "current_stage": self.current_stage.value,
            "stage_history": [asdict(t) for t in self.stage_history],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "published_at": self.published_at,
            "archived_at": self.archived_at,
            "observation_notes": self.observation_notes,
            "research_notes": self.research_notes,
            "validation_notes": self.validation_notes,
            "contract_notes": self.contract_notes,
        }
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> 'KnowledgeLifecycle':
        """从字典创建"""
        kl = cls(
            knowledge_id=d["knowledge_id"],
            current_stage=LifecycleStage(d.get("current_stage", "Observation")),
            created_at=d.get("created_at", datetime.now().isoformat()),
            updated_at=d.get("updated_at", datetime.now().isoformat()),
            published_at=d.get("published_at"),
            archived_at=d.get("archived_at"),
        )
        kl.observation_notes = d.get("observation_notes", [])
        kl.research_notes = d.get("research_notes", [])
        kl.validation_notes = d.get("validation_notes", [])
        kl.contract_notes = d.get("contract_notes", [])
        return kl


class LifecycleManager:
    """生命周期管理器"""
    
    def __init__(self, db_path: str = "08_GOVERNANCE/evidence/lifecycle_db.jsonl"):
        self.db_path = db_path
        self.lifecycle_map: dict[str, KnowledgeLifecycle] = {}
        self._load()
    
    def _load(self) -> None:
        """加载数据库"""
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        kl = KnowledgeLifecycle.from_dict(d)
                        self.lifecycle_map[kl.knowledge_id] = kl
        except FileNotFoundError:
            pass
    
    def create(self, knowledge_id: str) -> KnowledgeLifecycle:
        """创建新知识的生命周期"""
        kl = KnowledgeLifecycle(knowledge_id=knowledge_id)
        self.lifecycle_map[knowledge_id] = kl
        self._save(kl)
        return kl
    
    def get(self, knowledge_id: str) -> Optional[KnowledgeLifecycle]:
        """获取知识的生命周期"""
        return self.lifecycle_map.get(knowledge_id)
    
    def transition(self, knowledge_id: str, to_stage: LifecycleStage, reason: str, triggered_by: str) -> bool:
        """执行转换"""
        kl = self.lifecycle_map.get(knowledge_id)
        if not kl:
            return False
        
        if kl.transition(to_stage, reason, triggered_by):
            self._save(kl)
            return True
        return False
    
    def _save(self, kl: KnowledgeLifecycle) -> None:
        """保存到数据库 - append only"""
        with open(self.db_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(kl.to_dict(), ensure_ascii=False) + '\n')
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        stats = {
            "total": len(self.lifecycle_map),
            "by_stage": {},
            "terminal_count": 0,
            "active_count": 0
        }
        
        for kl in self.lifecycle_map.values():
            stage = kl.current_stage.value
            stats["by_stage"][stage] = stats["by_stage"].get(stage, 0) + 1
            
            if kl.current_stage in LifecycleStage.TERMINAL_STATES:
                stats["terminal_count"] += 1
            else:
                stats["active_count"] += 1
        
        return stats


# 辅助函数
def asdict(obj):
    """将对象转换为字典"""
    if hasattr(obj, '__dataclass_fields__'):
        result = {}
        for name, field in obj.__dataclass_fields__.items():
            value = getattr(obj, name)
            if isinstance(value, list):
                result[name] = [asdict(item) if hasattr(item, '__dataclass_fields__') else item for item in value]
            elif hasattr(value, '__dataclass_fields__'):
                result[name] = asdict(value)
            else:
                result[name] = value
        return result
    return obj
