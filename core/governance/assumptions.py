"""
Assumptions System - 假说追踪器

永久保留目录，记录所有"目前相信但尚未证实"的东西。

以后每次考古不是推翻自己，而是不断提高或降低假说的可信度。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict
import json
from pathlib import Path


@dataclass
class Assumption:
    """
    假说条目
    
    记录目前相信但尚未证实的东西。
    """
    # 基础信息
    id: str = ""
    title: str = ""
    
    # 状态和置信度
    status: str = "hypothesis"  # hypothesis/validating/validated/rejected/superseded
    confidence: float = 0.5     # 0.0 - 1.0
    
    # 内容
    description: str = ""
    assertion: str = ""         # 核心断言
    
    # 证据
    evidence: List[str] = field(default_factory=list)
    counter_evidence: List[str] = field(default_factory=list)
    
    # 来源
    sources: List[str] = field(default_factory=list)  # 来源考古发现
    source_files: List[str] = field(default_factory=list)  # 来源文件
    
    # 验证计划
    next_validation: List[str] = field(default_factory=list)  # 下一步验证计划
    validation_history: List[Dict] = field(default_factory=list)  # 验证历史
    
    # 时间
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    updated: str = field(default_factory=lambda: datetime.now().isoformat())
    last_validated: Optional[str] = None
    
    # 元数据
    owner: str = "ACE"
    tags: List[str] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "confidence": self.confidence,
            "description": self.description,
            "assertion": self.assertion,
            "evidence": self.evidence,
            "counter_evidence": self.counter_evidence,
            "sources": self.sources,
            "source_files": self.source_files,
            "next_validation": self.next_validation,
            "validation_history": self.validation_history,
            "created": self.created,
            "updated": self.updated,
            "last_validated": self.last_validated,
            "owner": self.owner,
            "tags": self.tags,
        }
    
    @classmethod
    def from_dict(cls, d: dict) -> 'Assumption':
        return cls(**d)
    
    def add_evidence(self, evidence: str, is_counter: bool = False) -> None:
        """添加证据"""
        if is_counter:
            self.counter_evidence.append(f"[{datetime.now().isoformat()}] {evidence}")
        else:
            self.evidence.append(f"[{datetime.now().isoformat()}] {evidence}")
        self._recalculate_confidence()
        self.updated = datetime.now().isoformat()
    
    def add_validation_step(self, step: str) -> None:
        """添加验证步骤"""
        self.next_validation.append(f"[{datetime.now().isoformat()}] {step}")
        self.updated = datetime.now().isoformat()
    
    def record_validation(self, result: str, notes: str = "") -> None:
        """记录验证结果"""
        validation = {
            "timestamp": datetime.now().isoformat(),
            "result": result,  # confirmed/rejected/modified
            "notes": notes,
            "evidence_snapshot": list(self.evidence),
            "confidence_before": self.confidence,
        }
        
        self.validation_history.append(validation)
        self.last_validated = datetime.now().isoformat()
        self.updated = datetime.now().isoformat()
        
        # 根据结果调整置信度
        if result == "confirmed":
            self.confidence = min(self.confidence + 0.1, 1.0)
            if self.confidence >= 0.9 and self.status == "hypothesis":
                self.status = "validated"
        elif result == "rejected":
            self.confidence = max(self.confidence - 0.2, 0.0)
            if self.confidence <= 0.1:
                self.status = "rejected"
        elif result == "modified":
            self.confidence = (self.confidence + 0.5) / 2
        
        validation["confidence_after"] = self.confidence
    
    def _recalculate_confidence(self) -> None:
        """根据证据重新计算置信度"""
        evidence_weight = 0.1
        counter_weight = -0.15
        
        base = 0.5
        for e in self.evidence:
            base += evidence_weight
        for e in self.counter_evidence:
            base += counter_weight
        
        self.confidence = max(0.0, min(1.0, base))


class AssumptionManager:
    """
    假说管理器
    
    管理所有假说，提供查询和更新接口。
    """
    
    def __init__(self, db_path: str = "08_GOVERNANCE/assumptions/assumptions_db.jsonl"):
        self.db_path = db_path
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.assumptions: Dict[str, Assumption] = {}
        self._load()
    
    def _load(self) -> None:
        """加载数据库"""
        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        a = Assumption.from_dict(d)
                        self.assumptions[a.id] = a
        except FileNotFoundError:
            pass
    
    def _save(self, assumption: Assumption) -> None:
        """保存到数据库 - append only"""
        with open(self.db_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(assumption.to_dict(), ensure_ascii=False) + '\n')
    
    def create(self, title: str, assertion: str, sources: List[str] = None, 
               confidence: float = 0.5) -> str:
        """创建新假说"""
        import uuid
        a = Assumption(
            id=str(uuid.uuid4())[:8],
            title=title,
            assertion=assertion,
            sources=sources or [],
            confidence=confidence,
            status="hypothesis",
        )
        self.assumptions[a.id] = a
        self._save(a)
        return a.id
    
    def get(self, assumption_id: str) -> Optional[Assumption]:
        """获取假说"""
        return self.assumptions.get(assumption_id)
    
    def get_by_status(self, status: str) -> List[Assumption]:
        """按状态获取假说"""
        return [a for a in self.assumptions.values() if a.status == status]
    
    def get_high_confidence(self, threshold: float = 0.8) -> List[Assumption]:
        """获取高置信度假说"""
        return [a for a in self.assumptions.values() if a.confidence >= threshold]
    
    def get_needing_validation(self) -> List[Assumption]:
        """获取需要验证的假说"""
        return [a for a in self.assumptions.values() 
                if a.status in ("hypothesis", "validating") and a.next_validation]
    
    def update(self, assumption_id: str, **kwargs) -> bool:
        """更新假说"""
        a = self.assumptions.get(assumption_id)
        if not a:
            return False
        
        for key, value in kwargs.items():
            if hasattr(a, key):
                setattr(a, key, value)
        
        a.updated = datetime.now().isoformat()
        self._save(a)
        return True
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        stats = {
            "total": len(self.assumptions),
            "by_status": {},
            "average_confidence": 0,
            "high_confidence_count": 0,
            "needs_validation": 0,
        }
        
        for a in self.assumptions.values():
            stats["by_status"][a.status] = stats["by_status"].get(a.status, 0) + 1
            stats["average_confidence"] += a.confidence
            if a.confidence >= 0.8:
                stats["high_confidence_count"] += 1
            if a.next_validation:
                stats["needs_validation"] += 1
        
        if self.assumptions:
            stats["average_confidence"] /= len(self.assumptions)
        
        return stats


# 初始化一些核心假说
def initialize_core_assumptions(manager: AssumptionManager) -> None:
    """初始化核心假说"""
    core_assumptions = [
        {
            "title": "Repository is Civilization",
            "assertion": "Repository才是真正最后一层，因为它是文明。Runtime可以删、Agent可以换、模型可以换，但Repository不能丢。",
            "sources": ["用户（老张）考古发现", "Runtime vs Repository 对比"],
            "confidence": 0.74,
            "next_validation": [
                "搜索R1历史档案验证",
                "检查Telegram考古记录",
                "验证Runtime可替换性"
            ],
            "tags": ["架构", "核心假说", "Repository"]
        },
        {
            "title": "错误增加经验，重复增加熵",
            "assertion": "错误经过验证可以转化为Constraint/Experience/Axiom（提升系统），重复不会带来新信息只会增加熵。",
            "sources": ["用户（老张）核心洞察", "馆长职责分析"],
            "confidence": 0.85,
            "next_validation": [
                "统计系统中错误转化率",
                "计算重复造成的维护成本"
            ],
            "tags": ["核心原则", "熵增", "错误处理"]
        },
        {
            "title": "馆长最高职责是控制熵增",
            "assertion": "馆长（Governor）的最高职责不是保存知识，而是控制知识系统的熵增。",
            "sources": ["用户（老张）总结", "SimilarityEngine设计目的"],
            "confidence": 0.80,
            "tags": ["馆长", "Governor", "熵增"]
        },
        {
            "title": "活结构跨系统存在",
            "assertion": "不同的人、不同的项目、不同的名字，最后都会收敛到同一套骨架。因为这些骨架是认知系统的基本粒子。",
            "sources": ["Hermes Agent对比", "OpenClaw迁移清单", "跨系统活结构谱系"],
            "confidence": 0.78,
            "tags": ["活结构", "跨系统", "骨架"]
        },
        {
            "title": "Governor改名建议",
            "assertion": "Curator太像档案管理员，实际上馆长做的是Knowledge Governance/Civilization Governance。Contract是规则，Governor是执行规则的人。",
            "sources": ["用户（老张）建议"],
            "confidence": 0.70,
            "tags": ["馆长", "Governor", "命名"]
        },
    ]
    
    for a in core_assumptions:
        # 检查是否已存在
        existing = [x for x in manager.assumptions.values() if x.title == a["title"]]
        if not existing:
            manager.create(
                title=a["title"],
                assertion=a["assertion"],
                sources=a["sources"],
                confidence=a.get("confidence", 0.5)
            )
            # 添加验证计划
            if "next_validation" in a:
                new_assumption = list(manager.assumptions.values())[-1]
                for step in a["next_validation"]:
                    new_assumption.add_validation_step(step)
                # 重新保存
                with open(manager.db_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(new_assumption.to_dict(), ensure_ascii=False) + '\n')
