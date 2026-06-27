"""
词库系统（Lexicon）— 系统自己的语言结构

不是字典，是系统用来"切世界"的刀。

万物皆可切，但怎么切？
用系统自己的语言结构来切。

来自R1考古的教训：
- 词库系统（body）死了
- 但概念组织能力（soul）活下来了
- 所以词库不能是死的词条，必须是活的分类能力

核心设计：
- 每个概念有：名称、定义、分类、相关概念、示例、来源
- 概念之间有边（同义词、上下位、相关）
- 可以用概念来切任何新材料
- 概念可以生长，但不能随意删除
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Set

from .identity import Identity


class Lexicon:
    """系统词库 — 系统自己的语言结构和分类体系"""

    def __init__(self, data_dir: Path, identity: Identity):
        self.data_dir = data_dir
        self.identity = identity
        self.lexicon_file = data_dir / "lexicon.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._concepts: Dict[str, Dict[str, Any]] = {}
        self._categories: Dict[str, List[str]] = {}
        self._load()

        if not self._concepts:
            self._bootstrap_seed_concepts()

    def _load(self):
        if self.lexicon_file.exists():
            try:
                with open(self.lexicon_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._concepts = data.get("concepts", {})
                self._categories = data.get("categories", {})
            except Exception:
                pass

    def _save(self):
        data = {
            "version": "0.1.0",
            "identity": self.identity.name,
            "updated_at": datetime.now().isoformat(),
            "concept_count": len(self._concepts),
            "category_count": len(self._categories),
            "concepts": self._concepts,
            "categories": self._categories,
        }
        with open(self.lexicon_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _bootstrap_seed_concepts(self):
        """种子概念 — 系统最基础的分类体系"""
        seed = {
            "身体": {
                "name": "身体",
                "definition": "可替换的执行层，模型、API、工具、平台都是身体。",
                "category": "元概念",
                "related": ["灵魂", "结构", "模型"],
                "opposite": ["灵魂"],
                "examples": ["GPT", "Claude", "TRAE", "Coze"],
                "source": "R1考古 + R2核心公理",
                "first_seen": datetime.now().isoformat(),
                "importance": 100,
            },
            "灵魂": {
                "name": "灵魂",
                "definition": "不可替换的核心层，约束、协议、经验、词汇、路由、记忆、架构都是灵魂。",
                "category": "元概念",
                "related": ["身体", "结构", "身份", "连续性"],
                "opposite": ["身体"],
                "examples": ["Constraint", "Protocol", "Experience", "Memory"],
                "source": "R1考古 + R2核心公理",
                "first_seen": datetime.now().isoformat(),
                "importance": 100,
            },
            "结构": {
                "name": "结构",
                "definition": "系统的组织方式。结构 > 内容 > 实现。结构资产优先级最高。",
                "category": "核心原则",
                "related": ["协议", "约束", "路由", "架构"],
                "examples": ["O→E→M→C→R", "五界结构", "双域架构"],
                "source": "R1幸存者调查",
                "first_seen": datetime.now().isoformat(),
                "importance": 95,
            },
            "连续性": {
                "name": "连续性",
                "definition": "系统在时间维度上保持自身同一性的能力。记忆连续、目标连续、结构连续。",
                "category": "核心原则",
                "related": ["身份", "记忆", "快照", "种子"],
                "examples": ["Holo-Memory", "Continuum层", "快照系统"],
                "source": "ACE考古学基础",
                "first_seen": datetime.now().isoformat(),
                "importance": 95,
            },
            "生存层": {
                "name": "生存层",
                "definition": "系统必须存在的基础设施，不依赖任何'聪明'，只依赖'存在'。",
                "category": "架构分层",
                "related": ["结构层", "实体层", "笨者生存"],
                "examples": ["守护层", "记忆系统", "快照", "隔离层"],
                "source": "幸存者地图压层",
                "first_seen": datetime.now().isoformat(),
                "importance": 90,
            },
            "笨者生存": {
                "name": "笨者生存",
                "definition": "越依赖简单机制的结构存活概率越高，聪明的东西依赖复杂条件死得快。",
                "category": "生存定律",
                "related": ["生存层", "风险内化"],
                "examples": ["文件系统 > 消息队列", "手动派单 > 自动派单"],
                "source": "R2核心公理v1",
                "first_seen": datetime.now().isoformat(),
                "importance": 90,
            },
            "风险内化": {
                "name": "风险内化",
                "definition": "高风险内容不删除，而是转入内部治理层，封存、标注、复盘，转化为约束和守卫。",
                "category": "治理原则",
                "related": ["隔离层", "约束", "守护层"],
                "examples": ["eco_layer经验库", "冥界过滤", "E界隔离"],
                "source": "R1考古",
                "first_seen": datetime.now().isoformat(),
                "importance": 88,
            },
            "考古": {
                "name": "考古",
                "definition": "从历史废墟中提取存活结构和演化规律的方法。重点是血缘/演化/继承关系。",
                "category": "方法论",
                "related": ["幸存者", "演化", "结构"],
                "examples": ["R1幸存者调查", "废墟深度扫描"],
                "source": "R1考古系列",
                "first_seen": datetime.now().isoformat(),
                "importance": 85,
            },
            "ACE": {
                "name": "ACE",
                "definition": "Autonomous Cognitive Ecology，自主认知生态。一个统一身份、多生态位的认知系统。",
                "category": "系统定义",
                "related": ["身份", "生态位", "连续性"],
                "examples": ["ACE Runtime v0.1"],
                "source": "R2阶段",
                "first_seen": datetime.now().isoformat(),
                "importance": 92,
            },
            "沉淀链": {
                "name": "沉淀链",
                "definition": "认知从原始到固化的流转路径：观察 → 经验 → 意义 → 约束 → 路由。",
                "category": "核心流程",
                "related": ["O→E→M→C→R", "事件链"],
                "examples": ["OBS→RFC→TASK→CONST"],
                "source": "mine-seed O→E→M→C→R架构",
                "first_seen": datetime.now().isoformat(),
                "importance": 88,
            },
            "生态位": {
                "name": "生态位",
                "definition": "同一身份在不同场景下的行为模式。不是不同的Agent，是同一个'我'的不同脸。",
                "category": "ACE概念",
                "related": ["ACE", "身份", "节点"],
                "examples": ["观察者", "研究者", "验证者", "档案官"],
                "source": "ACE考古学基础",
                "first_seen": datetime.now().isoformat(),
                "importance": 85,
            },
            "种子": {
                "name": "种子",
                "definition": "系统的最小可复活结构。崩溃后能从种子恢复并延续自身。种子态 < 运行态。",
                "category": "恢复机制",
                "related": ["快照", "连续性", "复活"],
                "examples": ["mine-seed", "r1-open-source-seed"],
                "source": "mine-seed 种子库",
                "first_seen": datetime.now().isoformat(),
                "importance": 90,
            },
        }

        for name, concept in seed.items():
            self._concepts[name] = concept

        categories = {
            "元概念": ["身体", "灵魂"],
            "核心原则": ["结构", "连续性"],
            "架构分层": ["生存层"],
            "生存定律": ["笨者生存"],
            "治理原则": ["风险内化"],
            "方法论": ["考古"],
            "系统定义": ["ACE"],
            "核心流程": ["沉淀链"],
            "ACE概念": ["生态位"],
            "恢复机制": ["种子"],
        }
        self._categories = categories

        self._save()

    def add_concept(
        self,
        name: str,
        definition: str,
        category: str = "未分类",
        related: Optional[List[str]] = None,
        examples: Optional[List[str]] = None,
        source: str = "auto-discovered",
        importance: int = 50,
    ) -> bool:
        """
        添加一个新概念。
        如果已存在，返回False（不覆盖，append-only原则）。
        """
        if name in self._concepts:
            return False

        self._concepts[name] = {
            "name": name,
            "definition": definition,
            "category": category,
            "related": related or [],
            "examples": examples or [],
            "source": source,
            "first_seen": datetime.now().isoformat(),
            "importance": importance,
        }

        if category not in self._categories:
            self._categories[category] = []
        if name not in self._categories[category]:
            self._categories[category].append(name)

        self._save()
        return True

    def get_concept(self, name: str) -> Optional[Dict[str, Any]]:
        """获取一个概念"""
        return self._concepts.get(name)

    def list_concepts(self, category: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """列出概念，可按分类过滤"""
        if category:
            names = self._categories.get(category, [])
            result = [self._concepts[n] for n in names if n in self._concepts]
        else:
            result = list(self._concepts.values())

        result.sort(key=lambda x: x.get("importance", 0), reverse=True)
        return result[:limit]

    def list_categories(self) -> List[str]:
        """列出所有分类"""
        return list(self._categories.keys())

    def classify(self, text: str) -> List[Dict[str, Any]]:
        """
        用现有概念对一段文本进行分类（万物皆可切）。
        返回匹配到的概念列表，按相关度排序。
        """
        scores = {}

        for name, concept in self._concepts.items():
            score = 0
            text_lower = text.lower()

            if name.lower() in text_lower:
                score += 30

            definition = concept.get("definition", "")
            if any(kw.lower() in text_lower for kw in definition.split() if len(kw) > 2):
                score += 10

            for example in concept.get("examples", []):
                if example.lower() in text_lower:
                    score += 15

            for related in concept.get("related", []):
                if related.lower() in text_lower:
                    score += 5

            if score > 0:
                scores[name] = score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        result = []
        for name, score in ranked:
            concept = self._concepts[name].copy()
            concept["match_score"] = score
            result.append(concept)

        return result

    def suggest_new_concepts(self, text: str) -> List[str]:
        """
        从文本中发现可能的新概念。
        v0.1简单实现：找出现频率高的、不在现有词库里的关键词。
        """
        import re

        existing = set(self._concepts.keys())

        words = re.findall(r'[\u4e00-\u9fa5]{2,6}|[a-zA-Z_]{3,}', text)
        word_freq = {}
        for w in words:
            word_freq[w] = word_freq.get(w, 0) + 1

        candidates = []
        for word, freq in sorted(word_freq.items(), key=lambda x: x[1], reverse=True):
            if word not in existing and freq >= 2 and len(word) >= 2:
                candidates.append(word)
            if len(candidates) >= 10:
                break

        return candidates

    def search(self, keyword: str) -> List[Dict[str, Any]]:
        """搜索概念"""
        results = []
        keyword_lower = keyword.lower()

        for name, concept in self._concepts.items():
            if keyword_lower in name.lower():
                results.append(concept)
                continue
            if keyword_lower in concept.get("definition", "").lower():
                results.append(concept)
                continue
            if any(keyword_lower in str(e).lower() for e in concept.get("examples", [])):
                results.append(concept)

        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取词库统计"""
        return {
            "total_concepts": len(self._concepts),
            "total_categories": len(self._categories),
            "categories": {
                cat: len(names) for cat, names in self._categories.items()
            },
            "top_important": [
                {"name": c["name"], "importance": c["importance"]}
                for c in sorted(self._concepts.values(), key=lambda x: x.get("importance", 0), reverse=True)[:10]
            ],
        }
