"""
eco_layer 解析器 — 经验矿的选矿厂

专门解析 eco_layer.json 的五层生态结构。
从高价值密度层开始挖（narrative_ecology），逐层向下。
每天挖定量，不会一次挖完。
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import Counter, defaultdict
from datetime import datetime


class EcoLayerParser:
    """eco_layer 经验库解析器"""

    LAYER_PRIORITY = [
        "narrative_ecology",
        "behavioral_ecology",
        "structural_ecology",
        "transactional_ecology",
        "free_zone",
    ]

    LAYER_NAMES = {
        "narrative_ecology": "叙事生态",
        "behavioral_ecology": "行为生态",
        "structural_ecology": "结构生态",
        "transactional_ecology": "交易生态",
        "free_zone": "自由区",
    }

    def __init__(self, eco_path: str, lexicon=None, memory_index=None):
        self.eco_path = Path(eco_path)
        self.lexicon = lexicon
        self.memory_index = memory_index
        self._data = None
        self._metadata = {}

    def load(self) -> bool:
        if not self.eco_path.exists():
            return False
        with open(self.eco_path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        self._metadata = self._data.get("metadata", {})
        return True

    @property
    def metadata(self) -> dict:
        return self._metadata

    def get_layer_stats(self) -> Dict[str, Any]:
        if not self._data:
            return {}
        stats = {}
        for layer in self.LAYER_PRIORITY:
            if layer in self._data:
                entries = self._data[layer]
                total = len(entries)
                total_chars = sum(
                    len(e.get("content", ""))
                    for e in entries.values() if isinstance(e, dict)
                )
                avg_chars = total_chars / total if total > 0 else 0
                stats[layer] = {
                    "name": self.LAYER_NAMES.get(layer, layer),
                    "count": total,
                    "total_chars": total_chars,
                    "avg_chars": round(avg_chars, 1),
                }
        return stats

    def sample_layer(
        self,
        layer: str,
        count: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        if not self._data or layer not in self._data:
            return []
        entries = list(self._data[layer].values())
        if not entries:
            return []
        samples = entries[offset : offset + count]
        result = []
        for i, entry in enumerate(samples):
            if isinstance(entry, dict):
                result.append({
                    "index": offset + i,
                    "content": entry.get("content", ""),
                    "timestamp": entry.get("timestamp", ""),
                    "layer": layer,
                })
        return result

    def mine_layer(
        self,
        layer: str,
        max_entries: int = 200,
        offset: int = 0,
        auto_index: bool = True,
    ) -> Dict[str, Any]:
        """
        挖掘一层，提取模式、概念候选、自动索引。
        每天挖 max_entries 条，可持续。
        """
        samples = self.sample_layer(layer, count=max_entries, offset=offset)
        if not samples:
            return {"layer": layer, "mined": 0, "error": "no_data"}

        all_text = "\n".join(s["content"] for s in samples)

        patterns = self._extract_patterns(all_text, layer)
        concept_candidates = []
        if self.lexicon:
            concept_candidates = self.lexicon.suggest_new_concepts(all_text[:10000])

        indexed = 0
        if auto_index and self.memory_index:
            for s in samples[:50]:
                content = s["content"]
                if len(content) < 50:
                    continue
                title = f"{self.LAYER_NAMES.get(layer, layer)} #{s['index']}"
                self.memory_index.add(
                    title=title[:80],
                    content=content[:2000],
                    memory_type="eco_layer",
                    category=self.LAYER_NAMES.get(layer, layer),
                    source="eco_layer_parser",
                    source_path=f"eco_layer:{layer}#{s['index']}",
                    tags=[layer, "eco_layer", f"idx_{s['index']}"],
                )
                indexed += 1

        return {
            "layer": layer,
            "layer_name": self.LAYER_NAMES.get(layer, layer),
            "mined": len(samples),
            "offset": offset,
            "patterns_found": len(patterns),
            "patterns": patterns[:20],
            "concept_candidates": concept_candidates[:20],
            "indexed": indexed,
            "total_chars": sum(len(s["content"]) for s in samples),
        }

    def _extract_patterns(self, text: str, layer: str) -> List[Dict[str, Any]]:
        """从文本中提取模式（高频短语、结构化模式等）"""
        patterns = []

        cn_phrases = re.findall(r"[\u4e00-\u9fff]{4,10}", text)
        phrase_counter = Counter(cn_phrases)
        for phrase, count in phrase_counter.most_common(30):
            if count >= 3:
                patterns.append({
                    "type": "高频短语",
                    "value": phrase,
                    "count": count,
                    "layer": layer,
                })

        structured_patterns = [
            (r"第[一二三四五六七八九十]+阶段", "阶段标记"),
            (r"第[一二三四五六七八九十]+步", "步骤标记"),
            (r"【.*?】", "方头括号标记"),
            (r"《.*?》", "书名号标记"),
            (r"\d+\.\s", "数字编号"),
        ]
        for pattern, ptype in structured_patterns:
            matches = re.findall(pattern, text)
            if matches:
                unique = len(set(matches))
                patterns.append({
                    "type": ptype,
                    "value": pattern,
                    "count": len(matches),
                    "unique": unique,
                    "layer": layer,
                })

        return patterns

    def generate_deep_report(self, mining_progress: Dict) -> Dict[str, Any]:
        """生成 eco_layer 五层生态的深度考古报告"""
        if not self._data:
            return {"error": "no_data"}

        report = {
            "generated_at": datetime.now().isoformat(),
            "layers": {},
            "cross_layer_insights": [],
            "mining_progress_summary": {},
            "recommendations": [],
        }

        total_entries = 0
        for layer in self.LAYER_PRIORITY:
            if layer not in self._data:
                continue
            entries = list(self._data[layer].values())
            total = len(entries)
            total_entries += total

            stats = self.get_layer_stats().get(layer, {})

            sample = entries[0] if entries else {}
            sample_keys = list(sample.keys()) if isinstance(sample, dict) else []
            sample_content = sample.get("content", "")[:100] if isinstance(sample, dict) else ""

            patterns = self._extract_patterns(
                "\n".join(e.get("content", "")[:500] for e in entries[:50] if isinstance(e, dict)),
                layer
            )

            progress = mining_progress.get("eco_layer", {}).get(layer, {})
            mined = progress.get("offset", 0)
            remaining = total - mined

            report["layers"][layer] = {
                "name": self.LAYER_NAMES.get(layer, layer),
                "total": total,
                "mined": mined,
                "remaining": remaining,
                "progress_pct": round(mined / total * 100, 1) if total > 0 else 0,
                "sample_keys": sample_keys,
                "sample_preview": sample_content,
                "top_patterns": [p for p in patterns if p.get("count", 0) >= 5][:5],
                "patterns_total": len(patterns),
            }

            report["mining_progress_summary"][layer] = {
                "mined": mined,
                "remaining": remaining,
                "done": remaining <= 0,
            }

        report["total_entries"] = total_entries
        remaining_total = sum(v["remaining"] for v in report["mining_progress_summary"].values())
        report["remaining_total"] = remaining_total

        if remaining_total > 0:
            days_estimate = remaining_total / 100
            report["recommendations"].append(
                f"剩余 {remaining_total} 条，按每日100条估计约 {days_estimate:.0f} 天挖完"
            )

        free_zone_total = report["layers"].get("free_zone", {}).get("total", 0)
        if free_zone_total > 1000000:
            report["recommendations"].append(
                f"自由区规模({free_zone_total:,}条)巨大，建议跳过直接挖其他四层后再回头"
            )

        report["cross_layer_insights"] = [
            f"eco_layer 总计 {total_entries:,} 条经验记录",
            f"叙事生态价值密度最高（叙事最精炼），应优先挖完",
            f"自由区是原始材料库，规模是叙事生态的 {free_zone_total // 4347}x",
            f"五层模型体现从量到质的经验沉淀路径",
        ]

        return report

    def find_contains(self, keyword: str, layer: Optional[str] = None, max_results: int = 20) -> List[Dict[str, Any]]:
        """查找包含关键词的条目"""
        if not self._data:
            return []
        results = []
        layers_to_search = [layer] if layer else self.LAYER_PRIORITY
        for lyr in layers_to_search:
            if lyr not in self._data:
                continue
            for key, entry in self._data[lyr].items():
                if not isinstance(entry, dict):
                    continue
                content = entry.get("content", "")
                if keyword.lower() in content.lower():
                    results.append({
                        "layer": lyr,
                        "layer_name": self.LAYER_NAMES.get(lyr, lyr),
                        "key": key,
                        "preview": content[:200],
                        "match": keyword,
                    })
                    if len(results) >= max_results:
                        return results
        return results

    def get_persona_matrix(self) -> Dict[str, Any]:
        """提取 persona_matrix 层（如果存在）"""
        if not self._data:
            return {}
        pm = self._data.get("persona_matrix", {})
        if isinstance(pm, dict):
            return pm
        return {}
