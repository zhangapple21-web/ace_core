"""
Lineage 血缘系统 — 知识演化路径追踪

职责：
  - 记录知识的版本血缘关系
  - 追踪约束→协议→蓝图→实现 的演化路径
  - 识别知识的祖先和后代
  - 防止知识丢失（知道它从哪里来）

血缘关系类型：
  - VERSION: 版本迭代 (v1 → v2 → v3)
  - DERIVATION: 衍生关系 (A基于B开发)
  - EVOLUTION: 演化关系 (A演化为B)
  - REPLACEMENT: 替代关系 (A替代B)
  - IMPLEMENTATION: 实现关系 (协议→蓝图→代码)
  - INHERITANCE: 继承关系 (B继承A的特点)
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class LineageType(Enum):
    """血缘关系类型"""
    VERSION = "version"           # 版本迭代
    DERIVATION = "derivation"     # 衍生
    EVOLUTION = "evolution"       # 演化
    REPLACEMENT = "replacement"  # 替代
    IMPLEMENTATION = "implementation"  # 实现
    INHERITANCE = "inheritance"  # 继承


@dataclass
class LineageNode:
    """血缘节点"""
    id: str
    name: str
    type: str  # concept/experience/constraint/protocol/axiom/blueprint/code
    version: str = ""
    parent_ids: List[str] = field(default_factory=list)
    child_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created: str = ""
    source: str = ""  # 来源：archaeology/manual/inference


@dataclass
class LineageEdge:
    """血缘边"""
    from_id: str
    to_id: str
    lineage_type: str
    confidence: float = 1.0  # 置信度
    reason: str = ""
    created: str = ""


class LineageGraph:
    """血缘图"""

    def __init__(self):
        self.nodes: Dict[str, LineageNode] = {}
        self.edges: List[LineageEdge] = []

    def add_node(self, node: LineageNode) -> bool:
        """添加节点"""
        if node.id in self.nodes:
            logger.warning(f"节点已存在: {node.id}")
            return False
        self.nodes[node.id] = node
        return True

    def add_edge(self, edge: LineageEdge) -> bool:
        """添加边"""
        if edge.from_id not in self.nodes:
            logger.warning(f"边的起始节点不存在: {edge.from_id}")
            return False
        if edge.to_id not in self.nodes:
            logger.warning(f"边的目标节点不存在: {edge.to_id}")
            return False

        # 避免重复边
        for existing in self.edges:
            if existing.from_id == edge.from_id and existing.to_id == edge.to_id:
                return False

        self.edges.append(edge)

        # 更新节点的父子关系
        self.nodes[edge.from_id].child_ids.append(edge.to_id)
        self.nodes[edge.to_id].parent_ids.append(edge.from_id)

        return True

    def get_ancestors(self, node_id: str, max_depth: int = 10) -> List[LineageNode]:
        """获取祖先节点"""
        if node_id not in self.nodes:
            return []

        ancestors = []
        visited = set()
        queue = [(node_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            node = self.nodes.get(current_id)
            if not node:
                continue

            for parent_id in node.parent_ids:
                if parent_id not in visited:
                    visited.add(parent_id)
                    parent = self.nodes.get(parent_id)
                    if parent:
                        ancestors.append(parent)
                        queue.append((parent_id, depth + 1))

        return ancestors

    def get_descendants(self, node_id: str, max_depth: int = 10) -> List[LineageNode]:
        """获取后代节点"""
        if node_id not in self.nodes:
            return []

        descendants = []
        visited = set()
        queue = [(node_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            node = self.nodes.get(current_id)
            if not node:
                continue

            for child_id in node.child_ids:
                if child_id not in visited:
                    visited.add(child_id)
                    child = self.nodes.get(child_id)
                    if child:
                        descendants.append(child)
                        queue.append((child_id, depth + 1))

        return descendants

    def get_path(self, from_id: str, to_id: str) -> Optional[List[str]]:
        """获取两个节点之间的路径"""
        if from_id not in self.nodes or to_id not in self.nodes:
            return None

        # BFS 找最短路径
        visited = {from_id}
        queue = [(from_id, [from_id])]

        while queue:
            current_id, path = queue.pop(0)

            if current_id == to_id:
                return path

            node = self.nodes.get(current_id)
            if not node:
                continue

            for child_id in node.child_ids:
                if child_id not in visited:
                    visited.add(child_id)
                    queue.append((child_id, path + [child_id]))

        return None

    def to_dict(self) -> Dict:
        """导出为字典"""
        return {
            "nodes": {
                node_id: {
                    "id": node.id,
                    "name": node.name,
                    "type": node.type,
                    "version": node.version,
                    "parent_ids": node.parent_ids,
                    "child_ids": node.child_ids,
                    "metadata": node.metadata,
                    "created": node.created,
                    "source": node.source,
                }
                for node_id, node in self.nodes.items()
            },
            "edges": [
                {
                    "from_id": edge.from_id,
                    "to_id": edge.to_id,
                    "lineage_type": edge.lineage_type,
                    "confidence": edge.confidence,
                    "reason": edge.reason,
                    "created": edge.created,
                }
                for edge in self.edges
            ]
        }


class LineageSystem:
    """
    血缘系统 - 知识演化路径追踪

    核心职责：
    1. 记录知识的血缘关系
    2. 查询知识的祖先和后代
    3. 推断未知的血缘关系
    4. 生成血缘报告
    """

    def __init__(self, data_dir: str):
        """
        初始化血缘系统

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.lineage_dir = self.data_dir / "lineage"
        self.lineage_dir.mkdir(parents=True, exist_ok=True)

        self.graph_file = self.lineage_dir / "lineage_graph.json"
        self.graph = LineageGraph()

        # 加载已有血缘数据
        self._load_graph()

    def _load_graph(self):
        """加载血缘图"""
        if self.graph_file.exists():
            try:
                with open(self.graph_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 加载节点
                for node_id, node_data in data.get("nodes", {}).items():
                    node = LineageNode(
                        id=node_data["id"],
                        name=node_data["name"],
                        type=node_data["type"],
                        version=node_data.get("version", ""),
                        parent_ids=node_data.get("parent_ids", []),
                        child_ids=node_data.get("child_ids", []),
                        metadata=node_data.get("metadata", {}),
                        created=node_data.get("created", ""),
                        source=node_data.get("source", ""),
                    )
                    self.graph.add_node(node)

                # 加载边
                for edge_data in data.get("edges", []):
                    edge = LineageEdge(
                        from_id=edge_data["from_id"],
                        to_id=edge_data["to_id"],
                        lineage_type=edge_data["lineage_type"],
                        confidence=edge_data.get("confidence", 1.0),
                        reason=edge_data.get("reason", ""),
                        created=edge_data.get("created", ""),
                    )
                    self.graph.add_edge(edge)

                logger.info(f"加载血缘图: {len(self.graph.nodes)} 节点, {len(self.graph.edges)} 边")

            except Exception as e:
                logger.error(f"加载血缘图失败: {e}")

    def _save_graph(self):
        """保存血缘图"""
        try:
            with open(self.graph_file, "w", encoding="utf-8") as f:
                json.dump(self.graph.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存血缘图失败: {e}")

    def register(
        self,
        artifact_id: str,
        artifact_name: str,
        artifact_type: str,
        parent_ids: List[str] = None,
        metadata: Dict[str, Any] = None,
        source: str = "archaeology"
    ) -> bool:
        """
        注册一个新知识及其血缘

        Args:
            artifact_id: 知识ID
            artifact_name: 知识名称
            artifact_type: 知识类型
            parent_ids: 父节点ID列表
            metadata: 元数据
            source: 来源

        Returns:
            是否成功
        """
        if parent_ids is None:
            parent_ids = []
        if metadata is None:
            metadata = {}

        # 创建节点
        node = LineageNode(
            id=artifact_id,
            name=artifact_name,
            type=artifact_type,
            parent_ids=parent_ids,
            metadata=metadata,
            created=datetime.now().isoformat(),
            source=source,
        )

        success = self.graph.add_node(node)

        # 添加血缘边
        for parent_id in parent_ids:
            edge = LineageEdge(
                from_id=parent_id,
                to_id=artifact_id,
                lineage_type="derivation",
                confidence=1.0,
                reason=f"衍生自动注册: {artifact_name}",
                created=datetime.now().isoformat(),
            )
            self.graph.add_edge(edge)

        self._save_graph()
        return success

    def infer_lineage(
        self,
        artifact_id: str,
        candidates: List[Dict[str, Any]]
    ) -> List[LineageEdge]:
        """
        推断血缘关系

        当发现新知识时，根据名称相似度、类型、关键词等推断其可能的父节点

        Args:
            artifact_id: 目标知识ID
            candidates: 可能的父节点候选列表

        Returns:
            推断出的血缘边列表
        """
        inferred_edges = []

        if artifact_id not in self.graph.nodes:
            logger.warning(f"节点不存在: {artifact_id}")
            return inferred_edges

        target_node = self.graph.nodes[artifact_id]

        for candidate in candidates:
            candidate_id = candidate.get("id", "")
            if candidate_id not in self.graph.nodes:
                continue

            candidate_node = self.graph.nodes[candidate_id]

            # 类型相同且名称相似
            if target_node.type == candidate_node.type:
                similarity = self._name_similarity(target_node.name, candidate_node.name)
                if similarity >= 0.6:
                    edge = LineageEdge(
                        from_id=candidate_id,
                        to_id=artifact_id,
                        lineage_type="evolution",
                        confidence=similarity,
                        reason=f"名称相似度推断: {similarity:.2f}",
                        created=datetime.now().isoformat(),
                    )
                    inferred_edges.append(edge)

        return inferred_edges

    def _name_similarity(self, name1: str, name2: str) -> float:
        """计算名称相似度"""
        # 简单的字符级相似度
        name1 = name1.lower()
        name2 = name2.lower()

        if name1 == name2:
            return 1.0

        # 检查包含关系
        if name1 in name2 or name2 in name1:
            return 0.8

        # 版本号推断
        import re
        v1_match = re.search(r'v(\d+)', name1)
        v2_match = re.search(r'v(\d+)', name2)

        if v1_match and v2_match:
            v1 = int(v1_match.group(1))
            v2 = int(v2_match.group(1))
            base1 = re.sub(r'v\d+', '', name1).strip()
            base2 = re.sub(r'v\d+', '', name2).strip()

            if base1 == base2 and v2 == v1 + 1:
                return 0.9  # 版本迭代

        return 0.0

    def query_lineage(self, artifact_id: str) -> Dict[str, Any]:
        """
        查询知识的血缘信息

        Args:
            artifact_id: 知识ID

        Returns:
            血缘信息报告
        """
        if artifact_id not in self.graph.nodes:
            return {"error": f"节点不存在: {artifact_id}"}

        node = self.graph.nodes[artifact_id]
        ancestors = self.graph.get_ancestors(artifact_id)
        descendants = self.graph.get_descendants(artifact_id)

        return {
            "artifact_id": artifact_id,
            "name": node.name,
            "type": node.type,
            "version": node.version,
            "ancestors": [
                {"id": a.id, "name": a.name, "type": a.type}
                for a in ancestors
            ],
            "descendants": [
                {"id": d.id, "name": d.name, "type": d.type}
                for d in descendants
            ],
            "lineage_chain": self._build_lineage_chain(artifact_id),
        }

    def _build_lineage_chain(self, artifact_id: str) -> List[Dict]:
        """构建完整的血缘链"""
        if artifact_id not in self.graph.nodes:
            return []

        chain = []
        current_id = artifact_id

        # 向上追溯
        ancestors = self.graph.get_ancestors(artifact_id)
        if ancestors:
            root = ancestors[-1]  # 最远的祖先
            path = self.graph.get_path(root.id, artifact_id)
            if path:
                for node_id in path:
                    node = self.graph.nodes.get(node_id)
                    if node:
                        chain.append({
                            "id": node.id,
                            "name": node.name,
                            "type": node.type,
                        })

        return chain

    def generate_lineage_report(self) -> Dict[str, Any]:
        """
        生成血缘系统报告

        Returns:
            血缘报告
        """
        # 统计
        type_counts = {}
        for node in self.graph.nodes.values():
            type_counts[node.type] = type_counts.get(node.type, 0) + 1

        # 查找孤立节点
        orphans = []
        for node in self.graph.nodes.values():
            if not node.parent_ids and not node.child_ids:
                orphans.append({"id": node.id, "name": node.name, "type": node.type})

        # 查找最长链
        longest_chain = []
        for node_id in self.graph.nodes:
            ancestors = self.graph.get_ancestors(node_id)
            if len(ancestors) > len(longest_chain):
                longest_chain = ancestors + [self.graph.nodes[node_id]]

        return {
            "generated_at": datetime.now().isoformat(),
            "total_nodes": len(self.graph.nodes),
            "total_edges": len(self.graph.edges),
            "nodes_by_type": type_counts,
            "orphan_nodes": orphans,
            "longest_lineage_chain_length": len(longest_chain),
            "longest_lineage_chain": [
                {"id": n.id, "name": n.name}
                for n in longest_chain
            ],
        }

    def export_for_knowledge(self, artifact_id: str) -> Dict[str, Any]:
        """
        导出知识的血缘信息，添加到知识元数据中

        Returns:
            血缘信息字典，可直接添加到知识的metadata中
        """
        if artifact_id not in self.graph.nodes:
            return {}

        node = self.graph.nodes[artifact_id]
        ancestors = self.graph.get_ancestors(artifact_id)
        descendants = self.graph.get_descendants(artifact_id)

        return {
            "lineage": {
                "id": artifact_id,
                "ancestor_ids": [a.id for a in ancestors],
                "descendant_ids": [d.id for d in descendants],
                "lineage_type": "tracked",
            }
        }
