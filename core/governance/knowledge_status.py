"""
Knowledge Status (Evidence Level) System

证据等级系统：
- FACT: 已证实的事实
- EVIDENCE: 有证据支撑
- HYPOTHESIS: 假说
- VALIDATED: 已验证
- REJECTED: 已驳回
- SUPERSEDED: 已替代
"""

from enum import Enum
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List
import json
import uuid

class KnowledgeStatus(Enum):
    """证据等级枚举"""
    FACT = "FACT"           # 已证实的事实
    EVIDENCE = "EVIDENCE"   # 有证据支撑
    HYPOTHESIS = "HYPOTHESIS"  # 假说
    VALIDATED = "VALIDATED"  # 已验证
    REJECTED = "REJECTED"   # 已驳回
    SUPERSEDED = "SUPERSEDED"  # 已替代


@dataclass
class KnowledgeMetadata:
    """知识元数据 - 所有知识必须包含的字段"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    status: KnowledgeStatus = KnowledgeStatus.HYPOTHESIS  # 默认是假说
    confidence: float = 0.0  # 0.0 - 1.0
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    updated: str = field(default_factory=lambda: datetime.now().isoformat())
    source: str = ""
    evidence: List[str] = field(default_factory=list)
    owner: str = "ACE"
    
    # 引用系统
    references: List[str] = field(default_factory=list)    # 相关引用
    derived_from: List[str] = field(default_factory=list)  # 来源
    supersedes: List[str] = field(default_factory=list)    # 替代了谁
    related_to: List[str] = field(default_factory=list)    # 相关
    
    # 血缘追踪
    lineage: List[str] = field(default_factory=list)  # 血缘链
    
    def to_dict(self) -> dict:
        """转换为字典"""
        d = asdict(self)
        d['status'] = self.status.value
        return d
    
    @classmethod
    def from_dict(cls, d: dict) -> 'KnowledgeMetadata':
        """从字典创建"""
        if 'status' in d and isinstance(d['status'], str):
            d['status'] = KnowledgeStatus(d['status'])
        return cls(**d)
    
    def update_status(self, new_status: KnowledgeStatus, reason: str, evidence: str = "") -> bool:
        """
        更新状态 - 带有严格验证
        禁止直接把 HYPOTHESIS 写成 FACT
        """
        # 升级规则验证
        if self.status == KnowledgeStatus.HYPOTHESIS and new_status == KnowledgeStatus.FACT:
            # HYPOTHESIS 不能直接升级为 FACT，必须经过 VALIDATED
            if self.confidence < 0.9:
                return False
            new_status = KnowledgeStatus.VALIDATED
        
        if new_status == KnowledgeStatus.FACT and self.status != KnowledgeStatus.VALIDATED:
            # FACT 必须先经过 VALIDATED
            return False
        
        self.status = new_status
        self.updated = datetime.now().isoformat()
        self.evidence.append(f"[{self.updated}] {reason}: {evidence}")
        
        return True
    
    def add_evidence(self, evidence: str) -> None:
        """添加证据"""
        self.evidence.append(f"[{datetime.now().isoformat()}] {evidence}")
        # 动态更新置信度
        self._recalculate_confidence()
    
    def _recalculate_confidence(self) -> None:
        """根据证据数量重新计算置信度"""
        base = 0.3  # 基础置信度
        evidence_bonus = min(len(self.evidence) * 0.05, 0.4)  # 每个证据最多+5%
        self.confidence = min(base + evidence_bonus, 0.95)


class KnowledgeRegistry:
    """知识注册表 - 管理所有知识的元数据"""
    
    def __init__(self, registry_path: str = "08_GOVERNANCE/evidence/knowledge_registry.jsonl"):
        self.registry_path = registry_path
        self.knowledge: dict[str, KnowledgeMetadata] = {}
        self._load()
    
    def _load(self) -> None:
        """加载注册表"""
        try:
            with open(self.registry_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        km = KnowledgeMetadata.from_dict(d)
                        self.knowledge[km.id] = km
        except FileNotFoundError:
            pass
    
    def _save(self) -> None:
        """保存注册表 - append only"""
        with open(self.registry_path, 'a', encoding='utf-8') as f:
            # 保存所有知识（append模式）
            for k in self.knowledge.values():
                f.write(json.dumps(k.to_dict(), ensure_ascii=False) + '\n')
    
    def register(self, knowledge: KnowledgeMetadata) -> str:
        """注册新知识"""
        self.knowledge[knowledge.id] = knowledge
        # 追加到注册表
        with open(self.registry_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(knowledge.to_dict(), ensure_ascii=False) + '\n')
        return knowledge.id
    
    def get(self, knowledge_id: str) -> Optional[KnowledgeMetadata]:
        """获取知识"""
        return self.knowledge.get(knowledge_id)
    
    def update(self, knowledge_id: str, **kwargs) -> bool:
        """更新知识"""
        if knowledge_id not in self.knowledge:
            return False
        
        km = self.knowledge[knowledge_id]
        for key, value in kwargs.items():
            if hasattr(km, key):
                setattr(km, key, value)
        km.updated = datetime.now().isoformat()
        return True
    
    def get_by_status(self, status: KnowledgeStatus) -> List[KnowledgeMetadata]:
        """按状态获取知识"""
        return [k for k in self.knowledge.values() if k.status == status]
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        stats = {
            "total": len(self.knowledge),
            "by_status": {},
            "average_confidence": 0,
            "with_evidence": 0
        }
        
        for k in self.knowledge.values():
            status_name = k.status.value
            stats["by_status"][status_name] = stats["by_status"].get(status_name, 0) + 1
            stats["average_confidence"] += k.confidence
            if k.evidence:
                stats["with_evidence"] += 1
        
        if self.knowledge:
            stats["average_confidence"] /= len(self.knowledge)
        
        return stats
