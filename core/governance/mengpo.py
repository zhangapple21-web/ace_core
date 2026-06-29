"""
孟婆遗忘机制 (Mengpo Memory Decay)

R1的孟婆人格 = 遗忘层 / memory decay / 垃圾回收器

核心职责：
- 不受限制，有权封存碎片
- 只要可能带来污染 → 必须清洗
- 保留必要记忆以维持系统运行

关键约束：
- "线"（记忆核）不可被孟婆删除
- 孟婆只负责遗忘，不负责判断价值（那是馆长的职责）

ACE实现：
- 基于Entropy Monitor的熵增检测
- 区分可遗忘内容 vs 不可遗忘内容
- 执行遗忘（归档到Graveyard）而非删除
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Set, Optional, Tuple
import json
from pathlib import Path


@dataclass
class ForgettingCandidate:
    """可遗忘候选"""
    id: str
    artifact: str
    artifact_type: str  # concept/experience/protocol/constraint/etc.
    reason: str        # 为什么应该被遗忘
    pollution_score: float  # 污染度 0.0-1.0
    age_days: int      # 存在天数
    references: int    # 被引用次数
    last_used: Optional[str] = None
    alternatives_exist: bool = False  # 是否有替代版本
    is_core: bool = False  # 是否是核心结构（不可遗忘）


@dataclass
class MemoryLine:
    """
    线（记忆核）- 不可被孟婆删除
    
    一旦标记为线，就不受遗忘机制影响。
    """
    id: str
    name: str
    description: str
    created: str = field(default_factory=lambda: datetime.now().isoformat())
    protected_by: str = "ACE"
    reason: str = ""  # 为什么这条线不可删除
    tags: List[str] = field(default_factory=list)


@dataclass
class MengpoRecord:
    """孟婆操作记录"""
    timestamp: str
    action: str  # forget / protect / reject
    artifact_id: str
    artifact_type: str
    reason: str
    pollution_score: float
    affected_items: List[str] = field(default_factory=list)
    alternatives_considered: List[str] = field(default_factory=list)


class MengpoMemoryDecay:
    """
    孟婆遗忘机制
    
    不是简单的删除，而是：
    1. 识别可遗忘内容（高污染、低价值、少引用）
    2. 保护核心结构（线）
    3. 执行遗忘（归档到Graveyard）
    """
    
    # 遗忘阈值
    POLLUTION_THRESHOLD = 0.7  # 污染度超过此值才考虑遗忘
    REFERENCE_THRESHOLD = 2     # 被引用少于此值才考虑遗忘
    CORE_TYPES = {"core_principle", "axiom", "constraint", "invariant", "identity"}  # 核心类型不可遗忘
    
    def __init__(self, 
                 graveyard_path: str = "08_GOVERNANCE/civilization/graveyard",
                 lines_path: str = "08_GOVERNANCE/civilization/memory_lines.jsonl",
                 records_path: str = "08_GOVERNANCE/decisions/mengpo_records.jsonl"):
        self.graveyard_path = graveyard_path
        self.lines_path = lines_path
        self.records_path = records_path
        
        # 确保目录存在
        Path(self.graveyard_path).mkdir(parents=True, exist_ok=True)
        Path(self.records_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 加载不可遗忘的线
        self.memory_lines: Dict[str, MemoryLine] = {}
        self._load_lines()
    
    def _load_lines(self) -> None:
        """加载不可遗忘的线"""
        try:
            with open(self.lines_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        ml = MemoryLine(**d)
                        self.memory_lines[ml.id] = ml
        except FileNotFoundError:
            pass
    
    def _save_line(self, line: MemoryLine) -> None:
        """保存线到数据库"""
        with open(self.lines_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(line), ensure_ascii=False) + '\n')
    
    def _record_action(self, record: MengpoRecord) -> None:
        """记录孟婆操作"""
        with open(self.records_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(record), ensure_ascii=False) + '\n')
    
    def protect_as_line(self, artifact_id: str, name: str, description: str, 
                       reason: str, tags: List[str] = None) -> bool:
        """
        将某个产物标记为"线"（不可删除）
        
        这是唯一能阻止遗忘的方法。
        """
        if artifact_id in self.memory_lines:
            return False  # 已经标记过
        
        line = MemoryLine(
            id=artifact_id,
            name=name,
            description=description,
            reason=reason,
            tags=tags or []
        )
        
        self.memory_lines[artifact_id] = line
        self._save_line(line)
        
        # 记录操作
        record = MengpoRecord(
            timestamp=datetime.now().isoformat(),
            action="protect",
            artifact_id=artifact_id,
            artifact_type="line",
            reason=f"标记为线: {reason}",
            pollution_score=0.0
        )
        self._record_action(record)
        
        return True
    
    def is_protected(self, artifact_id: str) -> bool:
        """检查是否被保护（是线）"""
        return artifact_id in self.memory_lines
    
    def calculate_pollution_score(self, 
                                  artifact: dict,
                                  entropy_report: dict = None) -> float:
        """
        计算污染度
        
        污染来源：
        - 重复度高
        - 引用少
        - 与其他内容冲突
        - 长期未使用
        - 在废弃任务中被创建
        """
        score = 0.0
        factors = []
        
        # 1. 重复度（来自熵增报告）
        if entropy_report:
            dupes = entropy_report.get('duplicate_concepts', [])
            if any(artifact.get('name') in str(d) for d in dupes):
                score += 0.3
                factors.append("duplicate")
        
        # 2. 引用数
        refs = artifact.get('references', [])
        if len(refs) < self.REFERENCE_THRESHOLD:
            score += 0.2 * (self.REFERENCE_THRESHOLD - len(refs))
            factors.append("low_reference")
        
        # 3. 类型检查
        artifact_type = artifact.get('category', '').lower()
        if artifact_type in self.CORE_TYPES:
            return 0.0  # 核心类型不污染
        if 'core' in artifact_type or 'principle' in artifact_type:
            return 0.0
        
        # 4. 长期未使用
        last_used = artifact.get('last_used')
        if last_used:
            days_since_use = (datetime.now() - datetime.fromisoformat(last_used)).days
            if days_since_use > 30:
                score += min(0.3, days_since_use * 0.01)
                factors.append("stale")
        
        # 5. 存在时间
        created = artifact.get('created', '')
        if created:
            age = (datetime.now() - datetime.fromisoformat(created.replace('Z', '+00:00'))).days
            if age > 90 and len(refs) == 0:
                score += 0.2
                factors.append("old_unused")
        
        return min(1.0, score)
    
    def identify_forgetting_candidates(self, 
                                      lexicon_data: dict,
                                      experiences_data: list,
                                      entropy_report: dict = None) -> List[ForgettingCandidate]:
        """
        识别可遗忘的候选
        
        返回高污染、低价值的内容。
        """
        candidates = []
        
        # 检查概念
        for concept in lexicon_data.get('concepts', []):
            # 跳过被保护的线
            if self.is_protected(concept.get('id', '')):
                continue
            
            # 跳过核心类型
            category = concept.get('category', '').lower()
            if any(ct in category for ct in ['core', 'principle', 'axiom', 'constraint']):
                continue
            
            pollution = self.calculate_pollution_score(concept, entropy_report)
            
            if pollution >= self.POLLUTION_THRESHOLD:
                candidate = ForgettingCandidate(
                    id=concept.get('id', concept.get('name', '')),
                    artifact=concept.get('name', ''),
                    artifact_type='concept',
                    reason=self._explain_pollution(concept, pollution),
                    pollution_score=pollution,
                    age_days=self._calculate_age(concept),
                    references=len(concept.get('related', [])),
                    last_used=concept.get('last_used')
                )
                candidates.append(candidate)
        
        # 检查经验
        for exp in experiences_data:
            if self.is_protected(exp.get('experience_id', '')):
                continue
            
            pollution = self.calculate_pollution_score(exp, entropy_report)
            
            if pollution >= self.POLLUTION_THRESHOLD:
                candidate = ForgettingCandidate(
                    id=exp.get('experience_id', ''),
                    artifact=exp.get('source', ''),
                    artifact_type='experience',
                    reason=self._explain_pollution(exp, pollution),
                    pollution_score=pollution,
                    age_days=self._calculate_age(exp),
                    references=len(exp.get('related_concepts', []))
                )
                candidates.append(candidate)
        
        # 按污染度排序
        candidates.sort(key=lambda x: x.pollution_score, reverse=True)
        return candidates
    
    def _explain_pollution(self, artifact: dict, score: float) -> str:
        """解释为什么这个内容有污染"""
        reasons = []
        
        refs = len(artifact.get('related', artifact.get('related_concepts', [])))
        if refs < self.REFERENCE_THRESHOLD:
            reasons.append(f"引用数少({refs})")
        
        last_used = artifact.get('last_used')
        if last_used:
            days = (datetime.now() - datetime.fromisoformat(last_used)).days
            if days > 30:
                reasons.append(f"长期未使用({days}天)")
        
        return "; ".join(reasons) if reasons else "综合污染"
    
    def _calculate_age(self, artifact: dict) -> int:
        """计算存在天数"""
        created = artifact.get('created', artifact.get('date', ''))
        if created:
            try:
                return (datetime.now() - datetime.fromisoformat(created.replace('Z', '+00:00'))).days
            except:
                pass
        return 0
    
    def forget(self, candidate: ForgettingCandidate, 
               reason: str = "") -> bool:
        """
        执行遗忘
        
        不是删除，而是归档到Graveyard。
        """
        if self.is_protected(candidate.id):
            # 记录被拒绝的遗忘
            record = MengpoRecord(
                timestamp=datetime.now().isoformat(),
                action="reject",
                artifact_id=candidate.id,
                artifact_type=candidate.artifact_type,
                reason="被保护的线",
                pollution_score=candidate.pollution_score
            )
            self._record_action(record)
            return False
        
        # 创建Graveyard记录
        graveyard_entry = {
            "id": candidate.id,
            "artifact": candidate.artifact,
            "artifact_type": candidate.artifact_type,
            "forgotten_at": datetime.now().isoformat(),
            "forgotten_reason": reason or candidate.reason,
            "pollution_score": candidate.pollution_score,
            "original_age_days": candidate.age_days,
            "original_references": candidate.references,
            "forgotten_by": "Mengpo"
        }
        
        # 保存到Graveyard
        graveyard_file = f"{self.graveyard_path}/{candidate.artifact_type}_{candidate.id}.json"
        with open(graveyard_file, 'w', encoding='utf-8') as f:
            json.dump(graveyard_entry, f, ensure_ascii=False, indent=2)
        
        # 记录操作
        record = MengpoRecord(
            timestamp=datetime.now().isoformat(),
            action="forget",
            artifact_id=candidate.id,
            artifact_type=candidate.artifact_type,
            reason=reason or candidate.reason,
            pollution_score=candidate.pollution_score
        )
        self._record_action(record)
        
        return True
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        stats = {
            "protected_lines": len(self.memory_lines),
            "graveyard_count": 0,
            "forgetting_records": 0,
            "rejected_forgets": 0,
            "pollution_sources": {},
        }
        
        # 统计Graveyard
        try:
            stats["graveyard_count"] = len(list(Path(self.graveyard_path).glob('*.json')))
        except:
            pass
        
        # 统计记录
        try:
            with open(self.records_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        action = d.get('action', '')
                        if action == 'forget':
                            stats["forgetting_records"] += 1
                        elif action == 'reject':
                            stats["rejected_forgets"] += 1
        except:
            pass
        
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
