"""
HypothesisTree — 轻量假设树

假设树 = 多候选假设 + 选择机制

不是重构现有组件，而是串联已有的：
- Researcher.generate_candidates()  → 生成假设分支
- Validator.assess_prospect()    → 评估前景
- Archivist.archive_tree()        → 记录演化

使用方式：
    tree = HypothesisTree(ace_daemon)
    tree.grow(task)  # expand → evaluate → commit
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class HypothesisNode:
    """假设树节点"""
    node_id: str
    hypothesis: str           # 假设内容
    keywords: List[str]        # 关联关键词
    confidence: float         # 置信度 (0-1)
    reasoning: str            # 推导过程
    node_type: str            # primary/lexicon_related/negation/cross_layer
    evidence_count: int       # 关联证据数
    parent_id: Optional[str]  # 父节点 ID
    depth: int               # 深度
    
    def to_dict(self) -> Dict:
        return asdict(self)


class HypothesisTree:
    """
    轻量假设树
    
    串联已有的组件，不替代它们：
    - Researcher.generate_candidates() → expand
    - Validator.assess_prospect()    → evaluate
    - Archivist                      → commit (记录)
    """
    
    def __init__(self, ace_daemon=None, data_dir: str = None):
        self.ace_daemon = ace_daemon
        self.current_root: Optional[HypothesisNode] = None
        self.history: List[HypothesisNode] = []
        self.candidates: List[HypothesisNode] = []
        self.commit_count: int = 0
        
        # 持久化目录
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(__file__).parent.parent / "06_RUNTIME" / "ace" / "data" / "tree"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = self.data_dir / "tree_state.json"
        self._load()
    
    def _load(self):
        """加载持久化状态"""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    state = json.load(f)
                    self.commit_count = state.get("commit_count", 0)
                    # 加载当前根
                    if state.get("current_root"):
                        cr = state["current_root"]
                        self.current_root = HypothesisNode(**cr)
            except Exception:
                pass
    
    def _save(self):
        """保存状态"""
        state = {
            "commit_count": self.commit_count,
            "current_root": self.current_root.to_dict() if self.current_root else None,
            "history_count": len(self.history),
            "last_updated": datetime.now().isoformat(),
        }
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    
    def set_root(self, task) -> HypothesisNode:
        """设置根节点（从任务创建初始假设）"""
        # 从 Researcher 获取初始假设
        if self.ace_daemon and hasattr(self.ace_daemon, "researcher"):
            candidates = self.ace_daemon.researcher.generate_candidates(task, max_candidates=1)
            if candidates:
                cand = candidates[0]
                self.current_root = HypothesisNode(
                    node_id="root",
                    hypothesis=cand["hypothesis"],
                    keywords=cand["keywords"],
                    confidence=cand["confidence"],
                    reasoning=cand["reasoning"],
                    node_type="root",
                    evidence_count=len(task.evidence) if task.evidence else 0,
                    parent_id=None,
                    depth=0,
                )
                self._save()
                return self.current_root
        
        # 兜底：从任务标题生成
        self.current_root = HypothesisNode(
            node_id="root",
            hypothesis=task.title,
            keywords=[],
            confidence=0.5,
            reasoning="从任务标题生成",
            node_type="root",
            evidence_count=0,
            parent_id=None,
            depth=0,
        )
        self._save()
        return self.current_root
    
    def expand(self, task) -> List[HypothesisNode]:
        """
        Expand: 生成候选子假设
        调用 Researcher.generate_candidates()
        """
        if not self.current_root:
            self.set_root(task)
        
        if not self.ace_daemon or not hasattr(self.ace_daemon, "researcher"):
            return []
        
        # 生成候选
        raw_candidates = self.ace_daemon.researcher.generate_candidates(task, max_candidates=3)
        
        # 转换为节点
        self.candidates = []
        for i, cand in enumerate(raw_candidates):
            node = HypothesisNode(
                node_id=f"{self.current_root.node_id}.{i+1}",
                hypothesis=cand["hypothesis"],
                keywords=cand["keywords"],
                confidence=cand["confidence"],
                reasoning=cand["reasoning"],
                node_type=cand["type"],
                evidence_count=len(task.evidence) if task.evidence else 0,
                parent_id=self.current_root.node_id,
                depth=self.current_root.depth + 1,
            )
            self.candidates.append(node)
        
        return self.candidates
    
    def evaluate(self, task) -> List[Dict[str, Any]]:
        """
        Evaluate: 评估候选前景
        调用 Validator.assess_prospect()
        """
        if not self.candidates:
            return []
        
        if not self.ace_daemon or not hasattr(self.ace_daemon, "validator"):
            # 兜底：按置信度排序
            return sorted(
                [{"node": c, "prospect_score": c.confidence * 100} for c in self.candidates],
                key=lambda x: x["prospect_score"],
                reverse=True,
            )
        
        # 使用 Validator 评估
        evaluations = []
        for cand in self.candidates:
            # 临时添加到任务
            task.evidence = task.evidence or []
            task.result = {"candidates": [cand]}
            
            prospect = self.ace_daemon.validator.assess_prospect(task)
            evaluations.append({
                "node": cand,
                "prospect_score": prospect["prospect_score"],
                "prospect_level": prospect["prospect_level"],
                "prune": prospect["prune"],
                "recommendations": prospect["recommendations"],
            })
        
        # 按前景评分排序
        return sorted(evaluations, key=lambda x: x["prospect_score"], reverse=True)
    
    def commit(self, selected_node: HypothesisNode) -> HypothesisNode:
        """
        Commit: 选择最优候选作为新根
        记录演化历史
        """
        # 记录旧根到历史
        if self.current_root:
            self.history.append(self.current_root)
        
        # 设置新根
        self.current_root = selected_node
        self.current_root.node_type = "root"  # 标记为根
        self.current_root.parent_id = self.history[-1].node_id if self.history else None
        
        self.commit_count += 1
        self._save()
        
        return self.current_root
    
    def step(self, task) -> Dict[str, Any]:
        """
        单步执行：expand → evaluate → commit
        
        Returns:
            {
                "step": int,
                "candidates": [...],
                "evaluations": [...],
                "selected": HypothesisNode,
                "root": HypothesisNode,
                "converged": bool,
            }
        """
        result = {
            "step": self.commit_count + 1,
            "candidates": [],
            "evaluations": [],
            "selected": None,
            "root": self.current_root,
            "converged": False,
        }
        
        # Expand
        candidates = self.expand(task)
        result["candidates"] = [c.to_dict() for c in candidates]
        
        if not candidates:
            result["converged"] = True
            return result
        
        # Evaluate
        evaluations = self.evaluate(task)
        result["evaluations"] = evaluations
        
        # Commit 最优候选
        best = evaluations[0] if evaluations else None
        if best and not best.get("prune", False):
            selected = self.commit(best["node"])
            result["selected"] = selected.to_dict()
            result["root"] = selected.to_dict()
        
        # 收敛检测：如果候选之间相似度很高
        if len(candidates) >= 2:
            avg_confidence = sum(c.confidence for c in candidates) / len(candidates)
            if avg_confidence > 0.8:
                result["converged"] = True
        
        return result
    
    def get_path(self) -> List[Dict]:
        """获取从根到当前节点的完整路径"""
        path = [self.current_root.to_dict()] if self.current_root else []
        return list(reversed(self.history + [self.current_root] if self.current_root else self.history))
    
    def get_stats(self) -> Dict[str, Any]:
        """获取树状态统计"""
        return {
            "commit_count": self.commit_count,
            "history_depth": len(self.history),
            "current_root": self.current_root.hypothesis if self.current_root else None,
            "candidates_count": len(self.candidates),
            "converged": self.commit_count > 0 and not self.candidates,
        }
