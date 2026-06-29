"""
Decision Log System

记录决策过程，不是记录结果。

谁、为什么、依据什么、什么时候、决定了什么。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict
import json
from pathlib import Path


@dataclass
class DecisionEntry:
    """
    决策条目
    
    记录的是决策过程，不只是结果。
    """
    # 决策者
    who: str = ""                    # 谁做的决策
    who_role: str = ""               # 决策者角色（Governor/Validator/etc.）
    
    # 决策内容
    what: str = ""                   # 决定了什么
    decision_type: str = ""          # accept/reject/delay/split/merge/etc.
    
    # 决策原因
    why: str = ""                    # 为什么做这个决定
    reasons: List[str] = field(default_factory=list)  # 具体原因列表
    
    # 决策依据
    based_on: List[str] = field(default_factory=list)  # 依据什么
    evidence: List[str] = field(default_factory=list)   # 支撑证据
    constraints: List[str] = field(default_factory=list)  # 参考的约束
    
    # 时间
    when: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 相关产物
    artifact: str = ""                # 涉及的产物
    artifact_id: str = ""             # 产物ID
    
    # 替代方案
    alternatives_considered: List[str] = field(default_factory=list)  # 考虑过的替代方案
    why_not_alternatives: List[str] = field(default_factory=list)  # 为什么没有选其他方案
    
    # 影响
    impact: str = ""                  # 这个决策的影响
    affected_items: List[str] = field(default_factory=list)  # 受影响的项目
    
    # 元数据
    contract_checked: str = ""        # 经过了哪些契约检查
    signature: str = ""               # 签名验证
    
    def to_dict(self) -> dict:
        return {
            "who": self.who,
            "who_role": self.who_role,
            "what": self.what,
            "decision_type": self.decision_type,
            "why": self.why,
            "reasons": self.reasons,
            "based_on": self.based_on,
            "evidence": self.evidence,
            "constraints": self.constraints,
            "when": self.when,
            "artifact": self.artifact,
            "artifact_id": self.artifact_id,
            "alternatives_considered": self.alternatives_considered,
            "why_not_alternatives": self.why_not_alternatives,
            "impact": self.impact,
            "affected_items": self.affected_items,
            "contract_checked": self.contract_checked,
            "signature": self.signature,
        }


class DecisionLog:
    """
    决策日志
    
    Append-only，记录所有决策的完整过程。
    """
    
    def __init__(self, log_path: str = "08_GOVERNANCE/decisions/decision_log.jsonl"):
        self.log_path = log_path
        Path(self.log_path).parent.mkdir(parents=True, exist_ok=True)
    
    def record(self, entry: DecisionEntry) -> None:
        """记录一条决策"""
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + '\n')
    
    def query_by_who(self, who: str) -> List[DecisionEntry]:
        """查询某人的所有决策"""
        entries = []
        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        if d.get('who') == who:
                            entries.append(DecisionEntry(**d))
        except FileNotFoundError:
            pass
        return entries
    
    def query_by_artifact(self, artifact: str) -> List[DecisionEntry]:
        """查询某个产物的所有相关决策"""
        entries = []
        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        if d.get('artifact') == artifact:
                            entries.append(DecisionEntry(**d))
        except FileNotFoundError:
            pass
        return entries
    
    def query_by_type(self, decision_type: str) -> List[DecisionEntry]:
        """按决策类型查询"""
        entries = []
        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        if d.get('decision_type') == decision_type:
                            entries.append(DecisionEntry(**d))
        except FileNotFoundError:
            pass
        return entries
    
    def get_rejection_analysis(self) -> dict:
        """分析所有拒绝决策"""
        rejections = self.query_by_type('reject')
        analysis = {
            "total_rejections": len(rejections),
            "reasons_distribution": {},
            "artifacts_rejected": [],
            "alternatives_offered": [],
        }
        
        for r in rejections:
            for reason in r.reasons:
                analysis["reasons_distribution"][reason] = \
                    analysis["reasons_distribution"].get(reason, 0) + 1
            
            if r.artifact:
                analysis["artifacts_rejected"].append(r.artifact)
            
            analysis["alternatives_offered"].extend(r.alternatives_considered)
        
        return analysis
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        stats = {
            "total_decisions": 0,
            "by_type": {},
            "by_role": {},
            "with_evidence": 0,
            "with_alternatives": 0,
        }
        
        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        stats["total_decisions"] += 1
                        d = json.loads(line)
                        
                        # 按类型
                        dtype = d.get('decision_type', 'unknown')
                        stats["by_type"][dtype] = stats["by_type"].get(dtype, 0) + 1
                        
                        # 按角色
                        role = d.get('who_role', 'unknown')
                        stats["by_role"][role] = stats["by_role"].get(role, 0) + 1
                        
                        # 有证据的
                        if d.get('evidence'):
                            stats["with_evidence"] += 1
                        
                        # 有替代方案的
                        if d.get('alternatives_considered'):
                            stats["with_alternatives"] += 1
        except FileNotFoundError:
            pass
        
        return stats
