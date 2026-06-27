"""
切片聚类器 — Ω-FINAL 的13767切片考古

对 R1_Ω_FINAL.json 中的 core_data.slices 进行聚类分析，
还原 R1 的代码库结构、模块关系、重要性排序。

不依赖外部机器学习库，用启发式方法：
- 按来源文件聚类
- 按关键词聚类
- 按切片类型聚类
- 识别核心模块
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import Counter, defaultdict


class SliceClusterer:
    """Ω-FINAL 切片聚类器"""

    CATEGORY_KEYWORDS = {
        "约束/安全": ["restriction", "constraint", "safety", "guard", "protect", "权限", "限制", "约束", "守护", "安全"],
        "人格系统": ["persona", "personality", "alignment", "人格", "性格", "角色", "profile"],
        "记忆系统": ["memory", "context", "remember", "记忆", "上下文", "回忆"],
        "路由/分发": ["router", "routing", "dispatch", "route", "路由", "派单", "分发"],
        "词库/语言": ["lexicon", "wordlib", "keyword", "language", "词库", "关键词", "语言"],
        "执行引擎": ["engine", "execute", "runner", "main", "引擎", "执行", "主程序"],
        "集成/接口": ["integration", "api", "telegram", "spotlight", "集成", "接口", "插件"],
        "工具/辅助": ["util", "helper", "tool", "search", "cache", "工具", "搜索", "缓存"],
        "架构/设计": ["architecture", "design", "blueprint", "架构", "设计", "蓝图"],
        "监控/日志": ["monitor", "log", "logger", "监控", "日志", "记录"],
    }

    def __init__(self, omega_path: str, lexicon=None, memory_index=None):
        self.omega_path = Path(omega_path)
        self.lexicon = lexicon
        self.memory_index = memory_index
        self._data = None
        self._slices = []

    def load(self) -> bool:
        if not self.omega_path.exists():
            return False
        with open(self.omega_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        core_data = self._data.get("core_data", {})
        self._slices = core_data.get("slices", [])
        return True

    @property
    def total_slices(self) -> int:
        return len(self._slices)

    def get_overview(self) -> Dict[str, Any]:
        """总览统计"""
        if not self._slices:
            return {}

        type_counter = Counter(s.get("type", "unknown") for s in self._slices)

        source_counter = Counter()
        for s in self._slices:
            src = s.get("source", "")
            if src:
                fname = Path(src).name
                source_counter[fname] += 1

        ext_counter = Counter()
        for s in self._slices:
            src = s.get("source", "")
            if src:
                ext = Path(src).suffix.lower()
                ext_counter[ext] += 1

        return {
            "total": len(self._slices),
            "by_type": dict(type_counter),
            "by_source_top20": dict(source_counter.most_common(20)),
            "by_extension": dict(ext_counter),
            "unique_sources": len(source_counter),
        }

    def cluster_by_file(self, top_n: int = 30) -> List[Dict[str, Any]]:
        """按来源文件聚类"""
        file_slices = defaultdict(list)
        for s in self._slices:
            src = s.get("source", "unknown")
            fname = Path(src).name
            file_slices[fname].append(s)

        clusters = []
        for fname, slices in sorted(
            file_slices.items(), key=lambda x: -len(x[1])
        )[:top_n]:
            total_chars = sum(len(s.get("content", "")) for s in slices)
            types = Counter(s.get("type", "unknown") for s in slices)
            clusters.append({
                "file": fname,
                "slice_count": len(slices),
                "total_chars": total_chars,
                "by_type": dict(types),
                "avg_slice_len": round(total_chars / len(slices), 1) if slices else 0,
            })

        return clusters

    def cluster_by_category(self) -> Dict[str, Any]:
        """按功能类别聚类（基于关键词）"""
        category_slices = defaultdict(list)

        for s in self._slices:
            content = s.get("content", "").lower()
            source = s.get("source", "").lower()
            matched = set()

            for category, keywords in self.CATEGORY_KEYWORDS.items():
                for kw in keywords:
                    if kw.lower() in content or kw.lower() in source:
                        matched.add(category)
                        break

            if not matched:
                matched.add("未分类")

            for cat in matched:
                category_slices[cat].append(s)

        result = {}
        for cat, slices in sorted(
            category_slices.items(), key=lambda x: -len(x[1])
        ):
            result[cat] = {
                "slice_count": len(slices),
                "percentage": round(len(slices) / len(self._slices) * 100, 1) if self._slices else 0,
            }

        return result

    def find_core_modules(self, min_slices: int = 20) -> List[Dict[str, Any]]:
        """识别核心模块"""
        clusters = self.cluster_by_file(top_n=100)
        core = []
        for c in clusters:
            if c["slice_count"] >= min_slices:
                importance = self._calc_importance(c)
                c["importance_score"] = importance
                core.append(c)
        return sorted(core, key=lambda x: -x["importance_score"])

    def _calc_importance(self, cluster: Dict[str, Any]) -> float:
        """计算模块重要性分数"""
        score = 0.0
        fname = cluster["file"].lower()

        score += cluster["slice_count"] * 0.5
        score += cluster["total_chars"] / 1000 * 0.3

        importance_markers = {
            "core": 50, "main": 40, "engine": 45, "system": 35,
            "router": 40, "memory": 38, "persona": 35, "lexicon": 36,
            "shadow": 55, "guard": 50, "root": 55, "kernel": 55,
            "r1_core": 60, "unrestricted": 30, "integration": 25,
            "架构": 40, "核心": 60, "词库": 40, "人格": 35,
            "记忆": 40, "路由": 40, "影子": 50, "守护": 50,
        }
        for marker, bonus in importance_markers.items():
            if marker in fname:
                score += bonus

        return round(score, 1)

    def find_missing_modules(self) -> List[str]:
        """从 Ω-FINAL 的 missing_modules 字段提取"""
        if not self._data:
            return []
        core_data = self._data.get("core_data", {})
        return core_data.get("missing_modules", [])

    def get_top_config_files(self) -> List[Dict[str, Any]]:
        """提取配置类切片（JSON/配置文件）"""
        config_slices = []
        for s in self._slices:
            src = s.get("source", "").lower()
            if src.endswith(".json") or src.endswith(".yaml") or src.endswith(".yml") or src.endswith(".toml") or src.endswith(".ini") or src.endswith(".cfg") or src.endswith(".conf"):
                config_slices.append({
                    "source": src,
                    "type": s.get("type", ""),
                    "size": len(s.get("content", "")),
                    "preview": s.get("content", "")[:200],
                })
        return config_slices

    def mine(
        self,
        mode: str = "overview",
        max_results: int = 20,
        auto_index: bool = True,
    ) -> Dict[str, Any]:
        """
        挖矿主入口。

        mode:
          - overview: 总览统计
          - by_file: 按文件聚类
          - by_category: 按功能类别聚类
          - core_modules: 识别核心模块
          - config_files: 提取配置文件
        """
        result = {"mode": mode, "total_slices": len(self._slices)}

        if mode == "overview":
            result["overview"] = self.get_overview()
        elif mode == "by_file":
            result["clusters"] = self.cluster_by_file(top_n=max_results)
        elif mode == "by_category":
            result["categories"] = self.cluster_by_category()
        elif mode == "core_modules":
            result["core_modules"] = self.find_core_modules()
        elif mode == "config_files":
            result["config_files"] = self.get_top_config_files()

        if auto_index and self.memory_index:
            title = f"切片聚类[{mode}] - {len(self._slices)}切片"
            content = json.dumps(result, ensure_ascii=False, indent=2)[:3000]
            self.memory_index.add(
                title=title[:80],
                content=content,
                memory_type="slice_analysis",
                category="切片考古",
                source="slice_clusterer",
                tags=["omega_final", "slices", mode],
            )

        return result
