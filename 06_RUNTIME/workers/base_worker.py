"""
Worker 基类 — 统一任务执行接口

所有 Worker 必须实现 execute(task) 方法，返回统一格式结果：

{
    "status": "success" | "failed" | "blocked",
    "outputs": {...},
    "error": "错误信息（如果有）",
    "next_tasks": ["task_id1", ...],  # 建议的后续任务
}

Worker 分类：
  - research_worker: 研究型任务
  - pattern_worker: 模式分析型任务
  - synthesis_worker: 综合报告型任务
  - scan_worker: 扫描型任务
  - lexicon_worker: 词库操作型任务
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseWorker(ABC):
    """
    Worker 基类

    所有 Worker 接收一个 Task 对象，执行后返回结果。
    Worker 不负责状态管理，只负责执行逻辑。
    """

    WORKER_NAME = "base_worker"
    WORKER_TYPE = "generic"

    def __init__(self, lexicon=None, memory_index=None, eco_parser=None, slice_clusterer=None):
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.eco_parser = eco_parser
        self.slice_clusterer = slice_clusterer

    @abstractmethod
    def execute(self, task) -> Dict[str, Any]:
        """
        执行任务，子类必须实现

        Args:
            task: Task 对象

        Returns:
            {
                "status": "success" | "failed" | "blocked",
                "outputs": {...},
                "error": "...",
                "next_tasks": [...],
            }
        """
        pass

    def can_execute(self, task) -> bool:
        """检查是否可以执行该任务"""
        return True

    def validate_task(self, task) -> Optional[str]:
        """验证任务是否可以执行，返回错误信息或None"""
        if not task.title:
            return "任务标题为空"
        return None


class ResearchWorker(BaseWorker):
    """研究型 Worker — 收集证据、形成结论"""

    WORKER_NAME = "research_worker"
    WORKER_TYPE = "research"

    def execute(self, task) -> Dict[str, Any]:
        """研究型执行：根据任务标题和假设，从各数据源收集证据"""
        validation = self.validate_task(task)
        if validation:
            return {"status": "failed", "error": validation, "outputs": {}, "next_tasks": []}

        keywords = self._extract_keywords(task.title + " " + (task.hypothesis or ""))
        evidence = []
        outputs = {}

        if self.memory_index:
            for kw in keywords[:5]:
                hits = self.memory_index.search(keyword=kw, limit=10)
                for hit in hits[:3]:
                    evidence.append({
                        "content": hit.get("content", "")[:300],
                        "source": hit.get("source", "memory"),
                    })
            outputs["memory_evidence_count"] = len(evidence)

        if self.lexicon:
            concept_hits = []
            for kw in keywords[:5]:
                c = self.lexicon.get_concept(kw)
                if c:
                    concept_hits.append(c)
            outputs["concept_matches"] = [c["name"] for c in concept_hits]

        if self.eco_parser:
            eco_hits = 0
            for kw in keywords[:3]:
                hits = self.eco_parser.find_contains(kw, max_results=5)
                eco_hits += len(hits)
            outputs["eco_hits"] = eco_hits

        next_tasks = []
        if outputs.get("eco_hits", 0) > 10:
            next_tasks.append({
                "title": f"深度研究 eco 模式: {keywords[0] if keywords else task.title}",
                "priority": "high",
                "depends_on": [task.task_id],
            })

        return {
            "status": "success",
            "outputs": outputs,
            "evidence": evidence,
            "evidence_count": len(evidence),
            "keywords_used": keywords[:5],
            "next_tasks": next_tasks,
        }

    def _extract_keywords(self, text: str) -> List[str]:
        import re
        cn_chunks = re.findall(r"[\u4e00-\u9fff]+", text)
        keywords = []
        for chunk in cn_chunks:
            if len(chunk) >= 2:
                keywords.append(chunk[:4] if len(chunk) > 4 else chunk)
        en_words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text)
        keywords.extend(en_words)
        seen = set()
        result = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                result.append(w)
        return result[:10]


class PatternWorker(BaseWorker):
    """模式分析型 Worker — 分析 eco_layer 中的模式"""

    WORKER_NAME = "pattern_worker"
    WORKER_TYPE = "pattern"

    def execute(self, task) -> Dict[str, Any]:
        validation = self.validate_task(task)
        if validation:
            return {"status": "failed", "error": validation, "outputs": {}, "next_tasks": []}

        if not self.eco_parser:
            return {
                "status": "failed",
                "error": "eco_parser 未初始化",
                "outputs": {},
                "next_tasks": [],
            }

        keywords = self._extract_keywords(task.title)
        outputs = {}

        pattern_hits = {}
        for kw in keywords[:3]:
            hits = self.eco_parser.find_contains(kw, max_results=20)
            if hits:
                pattern_hits[kw] = len(hits)

        outputs["patterns"] = pattern_hits
        outputs["total_hits"] = sum(pattern_hits.values())

        return {
            "status": "success",
            "outputs": outputs,
            "next_tasks": [],
        }

    def _extract_keywords(self, text: str) -> List[str]:
        import re
        return [w for w in re.findall(r"[\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z0-9_]{1,}", text)][:5]


class SynthesisWorker(BaseWorker):
    """综合报告型 Worker — 汇总多个数据源生成综合报告"""

    WORKER_NAME = "synthesis_worker"
    WORKER_TYPE = "synthesis"

    def execute(self, task) -> Dict[str, Any]:
        validation = self.validate_task(task)
        if validation:
            return {"status": "failed", "error": validation, "outputs": {}, "next_tasks": []}

        sections = []
        evidence = []

        if self.slice_clusterer and hasattr(self.slice_clusterer, "total_slices"):
            content = f"当前系统共有 {self.slice_clusterer.total_slices} 个切片"
            sections.append({
                "title": "切片统计",
                "content": content,
            })
            evidence.append({
                "content": content,
                "source": "slice_clusterer",
            })

        if self.memory_index:
            stats = self.memory_index.get_stats()
            content = f"当前索引 {stats.get('total', 0)} 条记忆"
            sections.append({
                "title": "记忆索引",
                "content": content,
            })
            evidence.append({
                "content": content,
                "source": "memory_index",
            })

        if self.lexicon:
            stats = self.lexicon.get_stats()
            content = f"当前词库 {stats.get('total_concepts', 0)} 个概念"
            sections.append({
                "title": "词库",
                "content": content,
            })
            evidence.append({
                "content": content,
                "source": "lexicon",
            })

        return {
            "status": "success",
            "outputs": {
                "sections": sections,
                "section_count": len(sections),
            },
            "evidence": evidence,
            "evidence_count": len(evidence),
            "next_tasks": [],
        }

    def _extract_keywords(self, text: str) -> List[str]:
        import re
        return [w for w in re.findall(r"[\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z0-9_]{1,}", text)][:5]


def create_worker(worker_type: str, **kwargs) -> BaseWorker:
    """工厂方法：根据类型创建 Worker"""
    worker_map = {
        "research": ResearchWorker,
        "pattern": PatternWorker,
        "synthesis": SynthesisWorker,
    }
    worker_cls = worker_map.get(worker_type, ResearchWorker)
    return worker_cls(**kwargs)
