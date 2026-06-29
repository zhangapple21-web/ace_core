"""
Civilization Graph（文明图）

核心职责：
    知识不是独立的JSON，而是有节点和关系的图。

知识关系类型：
    - supports: 支持
    - contradicts: 矛盾
    - supersedes: 替代
    - derived_from: 衍生自
    - inspired_by: 启发自
    - same_as: 等同于
    - merged_into: 合并入
    - references: 引用
    - part_of: 部分属于
    - depends_on: 依赖于

设计原则：
    - 关系是一等公民，和节点一样重要
    - Revision知道修改一个知识影响哪些知识
    - 图是append-only的，关系不会被删除，只会被标记为失效
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class RelationType(Enum):
    """知识关系类型"""
    SUPPORTS = "supports"           # 支持
    CONTRADICTS = "contradicts"     # 矛盾
    SUPERSEDES = "supersedes"       # 替代
    DERIVED_FROM = "derived_from"   # 衍生自
    INSPIRED_BY = "inspired_by"     # 启发自
    SAME_AS = "same_as"             # 等同于
    MERGED_INTO = "merged_into"     # 合并入
    REFERENCES = "references"       # 引用
    PART_OF = "part_of"             # 部分属于
    DEPENDS_ON = "depends_on"       # 依赖于


@dataclass
class KnowledgeNode:
    """知识节点"""
    id: str
    title: str
    type: str  # concept/experience/constraint/protocol/axiom/blueprint/assumption
    status: str = "HYPOTHESIS"
    confidence: float = 0.0
    content: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created: str = ""
    updated: str = ""
    source: str = ""
    is_active: bool = True


@dataclass
class KnowledgeRelation:
    """知识关系"""
    id: str
    from_node: str
    to_node: str
    relation_type: str  # RelationType.value
    confidence: float = 1.0
    reason: str = ""
    created: str = ""
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class CivilizationGraph:
    """
    文明图

    核心能力：
        - 管理知识节点和关系
        - 查询节点的邻居
        - 追踪关系演化
        - 支持图遍历（修改一个知识时知道影响哪些知识）
    """

    def __init__(self, data_dir: str):
        """
        初始化文明图

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.graph_dir = self.data_dir / "civilization_graph"
        self.graph_dir.mkdir(parents=True, exist_ok=True)

        self.nodes_file = self.graph_dir / "nodes.jsonl"
        self.relations_file = self.graph_dir / "relations.jsonl"

        # 内存中的图索引
        self.nodes: Dict[str, KnowledgeNode] = {}
        self.relations: List[KnowledgeRelation] = []
        self.outgoing: Dict[str, List[KnowledgeRelation]] = {}  # node_id -> relations
        self.incoming: Dict[str, List[KnowledgeRelation]] = {}  # node_id -> relations

        # 加载已有数据
        self._load_nodes()
        self._load_relations()

    def _load_nodes(self):
        """加载节点"""
        if not self.nodes_file.exists():
            return

        try:
            with open(self.nodes_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        node = KnowledgeNode(
                            id=data["id"],
                            title=data["title"],
                            type=data["type"],
                            status=data.get("status", "HYPOTHESIS"),
                            confidence=data.get("confidence", 0),
                            content=data.get("content", ""),
                            metadata=data.get("metadata", {}),
                            created=data.get("created", ""),
                            updated=data.get("updated", ""),
                            source=data.get("source", ""),
                            is_active=data.get("is_active", True),
                        )
                        self.nodes[node.id] = node
                    except Exception:
                        continue
            logger.info(f"加载了 {len(self.nodes)} 个节点")
        except Exception as e:
            logger.error(f"加载节点失败: {e}")

    def _load_relations(self):
        """加载关系"""
        if not self.relations_file.exists():
            return

        try:
            with open(self.relations_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        relation = KnowledgeRelation(
                            id=data["id"],
                            from_node=data["from_node"],
                            to_node=data["to_node"],
                            relation_type=data["relation_type"],
                            confidence=data.get("confidence", 1.0),
                            reason=data.get("reason", ""),
                            created=data.get("created", ""),
                            is_active=data.get("is_active", True),
                            metadata=data.get("metadata", {}),
                        )
                        self.relations.append(relation)

                        # 建立索引
                        if relation.from_node not in self.outgoing:
                            self.outgoing[relation.from_node] = []
                        self.outgoing[relation.from_node].append(relation)

                        if relation.to_node not in self.incoming:
                            self.incoming[relation.to_node] = []
                        self.incoming[relation.to_node].append(relation)
                    except Exception:
                        continue
            logger.info(f"加载了 {len(self.relations)} 个关系")
        except Exception as e:
            logger.error(f"加载关系失败: {e}")

    def add_node(self, node: KnowledgeNode) -> bool:
        """
        添加节点

        Args:
            node: 知识节点

        Returns:
            是否成功
        """
        if node.id in self.nodes:
            logger.warning(f"节点已存在: {node.id}")
            return False

        if not node.created:
            node.created = datetime.now().isoformat()
        if not node.updated:
            node.updated = datetime.now().isoformat()

        self.nodes[node.id] = node
        self._save_node(node)
        return True

    def _save_node(self, node: KnowledgeNode):
        """保存节点到文件"""
        try:
            with open(self.nodes_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": node.id,
                    "title": node.title,
                    "type": node.type,
                    "status": node.status,
                    "confidence": node.confidence,
                    "content": node.content,
                    "metadata": node.metadata,
                    "created": node.created,
                    "updated": node.updated,
                    "source": node.source,
                    "is_active": node.is_active,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存节点失败: {e}")

    def add_relation(
        self,
        from_node: str,
        to_node: str,
        relation_type: str,
        confidence: float = 1.0,
        reason: str = ""
    ) -> bool:
        """
        添加关系

        Args:
            from_node: 起始节点ID
            to_node: 目标节点ID
            relation_type: 关系类型
            confidence: 置信度
            reason: 原因

        Returns:
            是否成功
        """
        if from_node not in self.nodes:
            logger.warning(f"起始节点不存在: {from_node}")
            return False
        if to_node not in self.nodes:
            logger.warning(f"目标节点不存在: {to_node}")
            return False

        relation_id = f"{from_node}->{to_node}:{relation_type}"

        relation = KnowledgeRelation(
            id=relation_id,
            from_node=from_node,
            to_node=to_node,
            relation_type=relation_type,
            confidence=confidence,
            reason=reason,
            created=datetime.now().isoformat(),
        )

        self.relations.append(relation)

        # 更新索引
        if from_node not in self.outgoing:
            self.outgoing[from_node] = []
        self.outgoing[from_node].append(relation)

        if to_node not in self.incoming:
            self.incoming[to_node] = []
        self.incoming[to_node].append(relation)

        self._save_relation(relation)
        return True

    def _save_relation(self, relation: KnowledgeRelation):
        """保存关系到文件"""
        try:
            with open(self.relations_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": relation.id,
                    "from_node": relation.from_node,
                    "to_node": relation.to_node,
                    "relation_type": relation.relation_type,
                    "confidence": relation.confidence,
                    "reason": relation.reason,
                    "created": relation.created,
                    "is_active": relation.is_active,
                    "metadata": relation.metadata,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存关系失败: {e}")

    def get_neighbors(
        self,
        node_id: str,
        relation_types: List[str] = None,
        direction: str = "both"
    ) -> List[Dict[str, Any]]:
        """
        获取节点的邻居

        Args:
            node_id: 节点ID
            relation_types: 关系类型过滤（可选）
            direction: 方向：outgoing/incoming/both

        Returns:
            邻居列表，包含节点和关系信息
        """
        if node_id not in self.nodes:
            return []

        neighbors = []
        seen = set()

        # 出向关系
        if direction in ["outgoing", "both"]:
            for rel in self.outgoing.get(node_id, []):
                if not rel.is_active:
                    continue
                if relation_types and rel.relation_type not in relation_types:
                    continue

                target = self.nodes.get(rel.to_node)
                if target and target.id not in seen:
                    seen.add(target.id)
                    neighbors.append({
                        "node": target,
                        "relation": rel,
                        "direction": "outgoing",
                    })

        # 入向关系
        if direction in ["incoming", "both"]:
            for rel in self.incoming.get(node_id, []):
                if not rel.is_active:
                    continue
                if relation_types and rel.relation_type not in relation_types:
                    continue

                source = self.nodes.get(rel.from_node)
                if source and source.id not in seen:
                    seen.add(source.id)
                    neighbors.append({
                        "node": source,
                        "relation": rel,
                        "direction": "incoming",
                    })

        return neighbors

    def get_impacted_nodes(self, node_id: str, max_depth: int = 2) -> List[Dict[str, Any]]:
        """
        获取修改一个节点时会影响的所有节点

        这是Revision系统的关键：修改A时，知道会影响B、C、D...

        Args:
            node_id: 修改的节点ID
            max_depth: 最大遍历深度

        Returns:
            受影响的节点列表（带深度信息）
        """
        if node_id not in self.nodes:
            return []

        impacted = []
        visited = set()
        queue = [(node_id, 0)]

        while queue:
            current_id, depth = queue.pop(0)
            if depth >= max_depth:
                continue

            neighbors = self.get_neighbors(current_id)
            for nb in neighbors:
                nb_id = nb["node"].id
                if nb_id not in visited:
                    visited.add(nb_id)
                    impacted.append({
                        "node": nb["node"],
                        "relation": nb["relation"],
                        "direction": nb["direction"],
                        "depth": depth + 1,
                    })
                    queue.append((nb_id, depth + 1))

        return impacted

    def get_related_by_type(self, relation_type: str) -> List[KnowledgeRelation]:
        """获取特定类型的所有关系"""
        return [
            rel for rel in self.relations
            if rel.relation_type == relation_type and rel.is_active
        ]

    def update_node_status(self, node_id: str, new_status: str):
        """更新节点状态"""
        if node_id not in self.nodes:
            return False

        node = self.nodes[node_id]
        node.status = new_status
        node.updated = datetime.now().isoformat()

        # append-only：写入新的状态记录
        self._save_node(node)
        return True

    def deactivate_relation(self, relation_id: str):
        """停用关系（不删除，只标记）"""
        for rel in self.relations:
            if rel.id == relation_id:
                rel.is_active = False

                # 写入新记录（append-only）
                rel_copy = KnowledgeRelation(
                    id=rel.id,
                    from_node=rel.from_node,
                    to_node=rel.to_node,
                    relation_type=rel.relation_type,
                    confidence=rel.confidence,
                    reason=f"{rel.reason} | deactivated",
                    created=datetime.now().isoformat(),
                    is_active=False,
                )
                self._save_relation(rel_copy)
                return True

        return False

    def get_graph_stats(self) -> Dict[str, Any]:
        """获取图统计"""
        active_nodes = sum(1 for n in self.nodes.values() if n.is_active)
        active_relations = sum(1 for r in self.relations if r.is_active)

        # 按类型统计节点
        node_types = {}
        for node in self.nodes.values():
            if node.is_active:
                node_types[node.type] = node_types.get(node.type, 0) + 1

        # 按类型统计关系
        relation_types = {}
        for rel in self.relations:
            if rel.is_active:
                relation_types[rel.relation_type] = relation_types.get(rel.relation_type, 0) + 1

        # 计算平均连接度
        avg_degree = (active_relations * 2) / active_nodes if active_nodes > 0 else 0

        return {
            "active_nodes": active_nodes,
            "active_relations": active_relations,
            "total_nodes": len(self.nodes),
            "total_relations": len(self.relations),
            "node_types": node_types,
            "relation_types": relation_types,
            "average_degree": round(avg_degree, 2),
        }

    def get_supporters(self, node_id: str) -> List[KnowledgeNode]:
        """获取支持某个节点的所有节点"""
        neighbors = self.get_neighbors(node_id, [RelationType.SUPPORTS.value], "incoming")
        return [n["node"] for n in neighbors]

    def get_contradictions(self, node_id: str) -> List[KnowledgeNode]:
        """获取与某个节点矛盾的所有节点"""
        neighbors = self.get_neighbors(node_id, [RelationType.CONTRADICTS.value], "both")
        return [n["node"] for n in neighbors]

    def get_dependents(self, node_id: str) -> List[KnowledgeNode]:
        """获取依赖某个节点的所有节点"""
        neighbors = self.get_neighbors(node_id, [RelationType.DEPENDS_ON.value], "incoming")
        return [n["node"] for n in neighbors]

    def get_dependencies(self, node_id: str) -> List[KnowledgeNode]:
        """获取某个节点依赖的所有节点"""
        neighbors = self.get_neighbors(node_id, [RelationType.DEPENDS_ON.value], "outgoing")
        return [n["node"] for n in neighbors]
