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

    # 知识链路 — 结构化引用，记录这次决策用了哪些 Lexicon/Experience/Constraint 节点
    knowledge_references: Dict[str, List[str]] = field(default_factory=dict)
    # 格式: {"lexicon": ["concept_id_1", ...], "experience": ["exp_id_1", ...], "constraint": ["constraint_id_1", ...]}
    
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
            "knowledge_references": self.knowledge_references,
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
    
    def query_by_knowledge(self, knowledge_type: str, knowledge_id: str) -> List[DecisionEntry]:
        """
        查询引用了某个知识节点的所有决策

        Args:
            knowledge_type: "lexicon" / "experience" / "constraint"
            knowledge_id: 知识节点 ID

        Returns:
            引用了该知识节点的决策列表
        """
        entries = []
        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        refs = d.get('knowledge_references', {})
                        if knowledge_id in refs.get(knowledge_type, []):
                            entries.append(DecisionEntry(**d))
        except FileNotFoundError:
            pass
        return entries

    def get_knowledge_linkage_report(self) -> dict:
        """
        知识链路报告 — 统计决策与知识的关联情况

        Returns:
            知识链路统计
        """
        report = {
            "total_decisions": 0,
            "decisions_with_knowledge_refs": 0,
            "decisions_without_knowledge_refs": 0,
            "ref_counts_by_type": {"lexicon": 0, "experience": 0, "constraint": 0},
            "most_referenced": {"lexicon": [], "experience": [], "constraint": []},
            "orphan_decisions": [],  # 没有知识引用的决策
        }

        ref_freq = {"lexicon": {}, "experience": {}, "constraint": {}}

        try:
            with open(self.log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        report["total_decisions"] += 1
                        d = json.loads(line)
                        refs = d.get('knowledge_references', {})

                        if refs and any(refs.get(t) for t in ref_freq):
                            report["decisions_with_knowledge_refs"] += 1
                        else:
                            report["decisions_without_knowledge_refs"] += 1
                            report["orphan_decisions"].append({
                                "who": d.get('who', ''),
                                "what": d.get('what', ''),
                                "when": d.get('when', ''),
                            })

                        for ktype in ref_freq:
                            for kid in refs.get(ktype, []):
                                report["ref_counts_by_type"][ktype] += 1
                                ref_freq[ktype][kid] = ref_freq[ktype].get(kid, 0) + 1

            # 最常被引用的知识
            for ktype in ref_freq:
                sorted_refs = sorted(ref_freq[ktype].items(), key=lambda x: -x[1])[:10]
                report["most_referenced"][ktype] = [
                    {"id": kid, "count": count} for kid, count in sorted_refs
                ]
        except FileNotFoundError:
            pass

        return report

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
            "with_knowledge_refs": 0,
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

                        # 有知识引用的
                        refs = d.get('knowledge_references', {})
                        if refs and any(refs.get(t) for t in ("lexicon", "experience", "constraint")):
                            stats["with_knowledge_refs"] += 1
        except FileNotFoundError:
            pass
        
        return stats
