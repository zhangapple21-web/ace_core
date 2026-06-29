"""
Repository Memory System

不是记录"上传了什么"，而是记录"为什么"。

每次决策都记录原因，不只是记录结果。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict
import json
from pathlib import Path


@dataclass
class RepositoryMemoryEntry:
    """
    仓库记忆条目
    
    记录的不是"上传了什么"，而是"为什么"。
    """
    # 基础信息
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 产物信息
    artifact: str = ""           # 文件名/产物名
    artifact_path: str = ""      # 产物路径
    artifact_type: str = ""      # concept/experience/protocol/constraint/blueprint/etc.
    
    # 决策信息
    decision: str = ""           # merge/update/reject/split/delay/append/ignore
    reason: str = ""             # 为什么做这个决定
    
    # 来源追溯
    sources: List[str] = field(default_factory=list)  # 来源任务
    evidence: List[str] = field(default_factory=list)  # 支撑证据
    
    # 替代关系
    supersedes: List[str] = field(default_factory=list)  # 替代了哪些
    superseded_by: str = ""      # 被谁替代
    
    # 血缘
    lineage: List[str] = field(default_factory=list)    # 血缘链
    
    # 决策者
    curator: str = "ACE"         # 谁做的决定
    contract: str = ""           # 经过了哪些契约检查
    
    # 额外信息
    alternatives_considered: List[str] = field(default_factory=list)  # 考虑过的替代方案
    conflicts: List[str] = field(default_factory=list)  # 发现的冲突
    warnings: List[str] = field(default_factory=list)    # 警告
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "artifact": self.artifact,
            "artifact_path": self.artifact_path,
            "artifact_type": self.artifact_type,
            "decision": self.decision,
            "reason": self.reason,
            "sources": self.sources,
            "evidence": self.evidence,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "lineage": self.lineage,
            "curator": self.curator,
            "contract": self.contract,
            "alternatives_considered": self.alternatives_considered,
            "conflicts": self.conflicts,
            "warnings": self.warnings,
        }


class RepositoryMemory:
    """
    仓库记忆系统
    
    Append-only 日志，记录所有决策的原因。
    """
    
    def __init__(self, memory_path: str = "08_GOVERNANCE/repository/repository_memory.jsonl"):
        self.memory_path = memory_path
        self._ensure_path()
    
    def _ensure_path(self) -> None:
        """确保路径存在"""
        Path(self.memory_path).parent.mkdir(parents=True, exist_ok=True)
    
    def record(self, entry: RepositoryMemoryEntry) -> None:
        """
        记录一条记忆 - append only
        """
        with open(self.memory_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + '\n')
    
    def query_by_artifact(self, artifact: str) -> List[RepositoryMemoryEntry]:
        """查询某个产物的所有记录"""
        entries = []
        try:
            with open(self.memory_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        if d.get('artifact') == artifact:
                            entries.append(RepositoryMemoryEntry(**d))
        except FileNotFoundError:
            pass
        return entries
    
    def query_by_decision(self, decision: str) -> List[RepositoryMemoryEntry]:
        """查询某种决策的所有记录"""
        entries = []
        try:
            with open(self.memory_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        if d.get('decision') == decision:
                            entries.append(RepositoryMemoryEntry(**d))
        except FileNotFoundError:
            pass
        return entries
    
    def query_by_source(self, source: str) -> List[RepositoryMemoryEntry]:
        """查询某个来源任务的所有记录"""
        entries = []
        try:
            with open(self.memory_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        if source in d.get('sources', []):
                            entries.append(RepositoryMemoryEntry(**d))
        except FileNotFoundError:
            pass
        return entries
    
    def get_rejection_reasons(self) -> Dict[str, int]:
        """获取所有拒绝原因及次数"""
        reasons = {}
        try:
            with open(self.memory_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        d = json.loads(line)
                        if d.get('decision') == 'reject':
                            reason = d.get('reason', 'unknown')
                            reasons[reason] = reasons.get(reason, 0) + 1
        except FileNotFoundError:
            pass
        return reasons
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        stats = {
            "total_records": 0,
            "by_decision": {},
            "rejection_rate": 0.0,
            "rejection_reasons": {},
            "sources_count": {},
        }
        
        try:
            with open(self.memory_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        stats["total_records"] += 1
                        d = json.loads(line)
                        
                        # 按决策统计
                        decision = d.get('decision', 'unknown')
                        stats["by_decision"][decision] = stats["by_decision"].get(decision, 0) + 1
                        
                        # 拒绝率
                        if decision == 'reject':
                            stats["rejection_rate"] += 1
                        
                        # 来源统计
                        for source in d.get('sources', []):
                            stats["sources_count"][source] = stats["sources_count"].get(source, 0) + 1
        except FileNotFoundError:
            pass
        
        if stats["total_records"] > 0:
            stats["rejection_rate"] = stats["rejection_rate"] / stats["total_records"]
        
        stats["rejection_reasons"] = self.get_rejection_reasons()
        return stats


class RepositoryJournal:
    """
    仓库日志 - 每日自动生成
    
    包含：新增/修改/删除/重复/冲突/拒绝/拆分/延期/归档
    """
    
    def __init__(self, journal_path: str = "08_GOVERNANCE/journals"):
        self.journal_path = journal_path
        Path(self.journal_path).mkdir(parents=True, exist_ok=True)
    
    def generate_daily_journal(self, date: str = None) -> dict:
        """生成每日日志"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        memory = RepositoryMemory()
        stats = memory.get_statistics()
        
        journal = {
            "date": date,
            "summary": {
                "total_decisions": stats["total_records"],
                "new_artifacts": stats["by_decision"].get("merge", 0) + stats["by_decision"].get("create", 0),
                "rejected": stats["by_decision"].get("reject", 0),
                "delayed": stats["by_decision"].get("delay", 0),
                "split": stats["by_decision"].get("split", 0),
                "archived": stats["by_decision"].get("archive", 0),
            },
            "文明增长": 0,
            "文明熵": 0,
            "今日新增知识": [],
            "今日淘汰知识": [],
            "今日重复率": 0.0,
            "rejection_reasons": stats["rejection_reasons"],
        }
        
        # 计算文明增长/熵
        journal["文明增长"] = journal["summary"]["new_artifacts"]
        journal["文明熵"] = journal["summary"]["rejected"] + stats["rejection_rate"] * 100
        
        # 计算重复率
        total = stats["total_records"]
        if total > 0:
            journal["今日重复率"] = (stats["by_decision"].get("merge", 0) + 
                                    stats["by_decision"].get("append", 0)) / total
        
        return journal
    
    def save_journal(self, journal: dict, date: str = None) -> str:
        """保存日志"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        filename = f"{self.journal_path}/journal_{date}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(journal, f, ensure_ascii=False, indent=2)
        
        return filename
