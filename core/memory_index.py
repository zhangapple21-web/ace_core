"""
记忆索引（Memory Index）

不是简单的文件列表，是结构化的记忆索引。
每条记忆有：ID、类型、分类、标签、相关概念、时间戳、摘要。

设计原则（来自R1考古）：
- 记忆是手段，不是目的（Axiom_005）
- 记忆绑定Continuum（连续性优先）
- append-only，不覆盖历史
- 可追溯，每条记忆都能找到来源
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

from .identity import Identity
from .lexicon import Lexicon


class MemoryIndex:
    """结构化记忆索引 — 让记忆可检索、可关联、可追溯"""

    def __init__(self, index_dir: Path, identity: Identity, lexicon: Lexicon):
        self.index_dir = index_dir
        self.identity = identity
        self.lexicon = lexicon
        self.index_dir.mkdir(parents=True, exist_ok=True)

        self.index_file = index_dir / "memory_index.json"
        self._index: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._index = data.get("entries", [])
            except Exception:
                self._index = []

    def _save(self):
        data = {
            "version": "0.1.0",
            "identity": self.identity.name,
            "updated_at": datetime.now().isoformat(),
            "entry_count": len(self._index),
            "entries": self._index,
        }
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(
        self,
        title: str,
        content: str,
        memory_type: str = "note",
        category: str = "未分类",
        source: str = "system",
        source_path: Optional[str] = None,
        tags: Optional[List[str]] = None,
        related_event_id: Optional[str] = None,
    ) -> str:
        """
        添加一条记忆到索引。
        自动用lexicon进行分类和概念关联。
        """
        import uuid
        mem_id = str(uuid.uuid4())[:8]

        related_concepts = []
        classifications = self.lexicon.classify(content + " " + title)
        for c in classifications[:5]:
            related_concepts.append({
                "name": c["name"],
                "relevance": c.get("match_score", 0),
                "category": c.get("category", ""),
            })

        entry = {
            "id": mem_id,
            "title": title,
            "type": memory_type,
            "category": category,
            "source": source,
            "source_path": source_path,
            "related_event_id": related_event_id,
            "tags": tags or [],
            "related_concepts": related_concepts,
            "summary": content[:200] + "..." if len(content) > 200 else content,
            "created_at": datetime.now().isoformat(),
            "continuity": self.identity.continuity_mark(),
            "access_count": 0,
        }

        self._index.append(entry)
        self._save()
        return mem_id

    def search(
        self,
        keyword: Optional[str] = None,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        concept: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        搜索记忆。支持多维度过滤：
        - 关键词
        - 类型
        - 分类
        - 标签
        - 相关概念
        """
        results = []

        for entry in self._index:
            if memory_type and entry.get("type") != memory_type:
                continue
            if category and entry.get("category") != category:
                continue
            if tag and tag not in entry.get("tags", []):
                continue
            if concept:
                concepts = [c.get("name") for c in entry.get("related_concepts", [])]
                if concept not in concepts:
                    continue
            if keyword:
                kw = keyword.lower()
                text = (entry.get("title", "") + " " + entry.get("summary", "")).lower()
                if kw not in text:
                    continue

            results.append(entry)

        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return results[:limit]

    def get_by_concept(self, concept_name: str, limit: int = 20) -> List[Dict[str, Any]]:
        """按相关概念查找记忆"""
        return self.search(concept=concept_name, limit=limit)

    def get_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取最近的记忆"""
        sorted_entries = sorted(
            self._index, key=lambda x: x.get("created_at", ""), reverse=True
        )
        return sorted_entries[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆索引统计"""
        type_counts = {}
        category_counts = {}
        concept_counts = {}

        for entry in self._index:
            t = entry.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

            c = entry.get("category", "未分类")
            category_counts[c] = category_counts.get(c, 0) + 1

            for concept in entry.get("related_concepts", []):
                name = concept.get("name", "unknown")
                concept_counts[name] = concept_counts.get(name, 0) + 1

        top_concepts = sorted(
            concept_counts.items(), key=lambda x: x[1], reverse=True
        )[:10]

        return {
            "total": len(self._index),
            "by_type": type_counts,
            "by_category": category_counts,
            "top_concepts": [{"name": n, "count": c} for n, c in top_concepts],
        }

    def get_concept_graph(self, depth: int = 2) -> Dict[str, Any]:
        """
        获取概念关联图 — 记忆是怎么通过概念连在一起的。
        v0.1简单实现，返回概念和关联记忆的关系。
        """
        graph = {
            "nodes": [],
            "edges": [],
        }

        concept_memories = {}
        for entry in self._index:
            for concept in entry.get("related_concepts", []):
                name = concept.get("name")
                if not name:
                    continue
                if name not in concept_memories:
                    concept_memories[name] = []
                concept_memories[name].append(entry["id"])

        node_set = set()
        edge_set = set()

        for concept, mem_ids in concept_memories.items():
            if concept not in node_set:
                node_set.add(concept)
                c_data = self.lexicon.get_concept(concept)
                graph["nodes"].append({
                    "id": concept,
                    "type": "concept",
                    "importance": c_data.get("importance", 50) if c_data else 50,
                    "memory_count": len(mem_ids),
                })

            for mem_id in mem_ids:
                mem_node_id = f"mem_{mem_id}"
                if mem_node_id not in node_set:
                    node_set.add(mem_node_id)
                    entry = next(
                        (e for e in self._index if e["id"] == mem_id), None
                    )
                    if entry:
                        graph["nodes"].append({
                            "id": mem_node_id,
                            "type": "memory",
                            "title": entry.get("title", ""),
                            "category": entry.get("category", ""),
                        })

                edge_key = (concept, mem_node_id)
                if edge_key not in edge_set:
                    edge_set.add(edge_key)
                    graph["edges"].append({
                        "source": concept,
                        "target": mem_node_id,
                        "type": "related_to",
                    })

        return graph
