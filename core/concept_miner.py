"""
概念提取引擎 v3 — 词库的自动生长机制

v3 重构：分层架构
    Tokenizer (语言层) → ConceptFilter (文明层) → ConceptMiner (沉淀层)

Tokenizer 只负责分词，不决定什么是概念。
ConceptFilter 负责判断什么值得成为概念。
ConceptMiner 负责分类、关联、写入词库。

主次关系：ACE 利用 NLP，不是 NLP 驱动 ACE。
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict

from .tokenizers import BaseTokenizer, RegexTokenizer
from .concept_filter import ConceptFilter


class ConceptMiner:
    """
    概念矿工 — 词库的自动生长机制

    不直接分词，不直接过滤。
    只负责：拿到候选 → 分类 → 关联 → 写入词库。

    底层的分词和过滤是可替换的。
    """

    def __init__(self, lexicon, tokenizer: BaseTokenizer = None):
        self.lexicon = lexicon
        self.tokenizer = tokenizer or RegexTokenizer()
        self.filter = ConceptFilter(lexicon)
        self._discovery_cache = []

    def set_tokenizer(self, tokenizer: BaseTokenizer):
        """切换分词器 — Governor 可以根据质量自动切换"""
        self.tokenizer = tokenizer

    def mine_concepts(
        self,
        text: str,
        source: str = "unknown",
        min_occurrence: int = 3,
        max_new_concepts: int = 10,
        auto_add: bool = True,
    ) -> Dict[str, Any]:
        if not text or len(text) < 100:
            return {"mined": 0, "new_concepts": [], "reason": "text_too_short"}

        candidates = self.tokenizer.tokenize(text)
        scored = self.filter.filter(candidates, text, min_occurrence, source)

        for s in scored:
            s["context"] = self._get_context_window(text, s["name"])
            s["source"] = source

        new_concepts = []
        added = 0

        for candidate in scored[:max_new_concepts]:
            name = candidate["name"]
            if self.lexicon.get_concept(name):
                continue

            if auto_add and candidate["score"] >= 55:
                category = self._guess_category(candidate, text)
                related = self._guess_related(candidate, text)
                definition = self._build_definition(candidate, text, source)

                result = self.lexicon.add_concept(
                    name=name,
                    definition=definition,
                    category=category,
                    related=related,
                    source=f"concept_miner:{source}",
                    importance=candidate["score"],
                )
                if result:
                    added += 1
                    new_concepts.append({
                        "name": name,
                        "category": category,
                        "score": candidate["score"],
                        "related_count": len(related),
                    })

        return {
            "mined": len(scored),
            "new_concepts": new_concepts,
            "added": added,
            "candidates_considered": len(candidates),
            "source": source,
            "tokenizer": self.tokenizer.name,
        }

    def _get_context_window(self, text: str, term: str, window: int = 60) -> str:
        idx = text.find(term)
        if idx < 0:
            return ""
        start = max(0, idx - window)
        end = min(len(text), idx + len(term) + window)
        raw = text[start:end].strip()
        lines = raw.split("\n")
        return "\n".join(l.strip() for l in lines if l.strip())[:300]

    def _build_definition(self, candidate: Dict, text: str, source: str) -> str:
        ctx = candidate.get("context", "")
        term = candidate["name"]

        if ctx:
            lines = [l.strip() for l in ctx.split("\n") if l.strip()]
            for line in lines[:3]:
                if term in line and any(w in line for w in ["是", "指", "定义", "称为", "：", "【", "《"]):
                    clean = re.sub(r"[【】《》【】]", "", line).strip()
                    if len(clean) > 5:
                        return clean[:200]

        definition_templates = [
            f"{term}是从{source}材料中自动提取的概念",
            f"{term}，自动提取（来源：{source}）",
            f"从{source}数据中识别的术语",
        ]
        return definition_templates[0]

    def _guess_category(self, candidate: Dict, text: str) -> str:
        name = candidate["name"]
        ctx = candidate.get("context", "")
        combined = ctx + text[:1000]

        category_hints = {
            "架构分层": ["层", "架构", "结构", "模块", "组件", "系统", "界", "域", "stack", "layer", "tier"],
            "核心机制": ["机制", "模式", "算法", "引擎", "路由", "调度", "处理", "engine", "mechanism", "protocol"],
            "治理原则": ["原则", "规则", "约束", "限制", "权限", "安全", "治理", "policy", "constraint", "rule"],
            "灵魂资产": ["资产", "经验", "记忆", "知识", "协议", "公理", "真理", "axiom", "protocol"],
            "演化机制": ["进化", "演化", "生长", "迭代", "适应", "学习", "evolve", "growth"],
            "恢复机制": ["恢复", "重建", "修复", "备份", "快照", "复活", "recovery", "rebuild"],
            "ACE概念": ["persona", "ace", "ACE", "生态位", "认知生态", "人格", "角色"],
            "考古发现": ["考古", "发现", "遗迹", "化石", "残骸", "fragment", "trace"],
            "身体层": ["模型", "API", "接口", "插件", "平台", "工具", "model", "api", "plugin"],
            "身份系统": ["身份", "角色", "人格", "名字", "别名", "identity", "persona"],
            "方法论": ["方法", "方法论", "框架", "范式", "approach", "method", "framework", "paradigm"],
        }

        best_cat = "待分类"
        best_score = 0

        for cat, hints in category_hints.items():
            score = 0
            name_lower = name.lower()
            for hint in hints:
                if hint.lower() in name_lower:
                    score += 4
                if hint.lower() in combined.lower():
                    score += 1
            if score > best_score:
                best_score = score
                best_cat = cat

        if candidate["score"] >= 80 and best_score < 4:
            best_cat = "核心概念"

        return best_cat if best_score >= 2 else "待分类"

    def _guess_related(self, candidate: Dict, text: str, max_related: int = 5) -> List[str]:
        related = []
        name = candidate["name"]
        existing = self.lexicon.list_concepts(limit=300)
        for concept in existing:
            cname = concept["name"]
            if cname == name:
                continue
            if cname in text or name in concept.get("definition", ""):
                related.append(cname)
            elif any(
                part in cname or cname in part
                for part in [name, name[:3], name[-3:]]
                if len(part) >= 2
            ):
                related.append(cname)
            if len(related) >= max_related:
                break
        return related

    def batch_mine(
        self,
        entries: List[Dict[str, str]],
        source: str = "batch",
        max_total_concepts: int = 15,
    ) -> Dict[str, Any]:
        all_text = "\n".join(
            e.get("content", e.get("text", "")) for e in entries
        )
        return self.mine_concepts(
            all_text,
            source=source,
            min_occurrence=2,
            max_new_concepts=max_total_concepts,
            auto_add=True,
        )
