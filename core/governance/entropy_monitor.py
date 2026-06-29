"""
Entropy Monitor System

监控知识系统的熵增。

不是只做文件Hash，而是做知识重复分析。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Set, Tuple
import json
from pathlib import Path
import hashlib


@dataclass
class EntropyReport:
    """熵增报告"""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    
    # 重复统计
    duplicate_files: List[Tuple[str, str]] = field(default_factory=list)  # (file1, file2)
    duplicate_concepts: List[Tuple[str, str]] = field(default_factory=list)
    duplicate_protocols: List[Tuple[str, str]] = field(default_factory=list)
    duplicate_constraints: List[Tuple[str, str]] = field(default_factory=list)
    duplicate_experiences: List[Tuple[str, str]] = field(default_factory=list)
    duplicate_lexicons: List[Tuple[str, str]] = field(default_factory=list)
    duplicate_tasks: List[Tuple[str, str]] = field(default_factory=list)
    
    # 冲突
    conflicts: List[Dict] = field(default_factory=list)
    
    # 孤立知识
    orphaned_knowledge: List[str] = field(default_factory=list)
    
    # 统计
    entropy_score: float = 0.0
    duplication_rate: float = 0.0
    total_duplicates: int = 0
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "duplicate_files": self.duplicate_files,
            "duplicate_concepts": self.duplicate_concepts,
            "duplicate_protocols": self.duplicate_protocols,
            "duplicate_constraints": self.duplicate_constraints,
            "duplicate_experiences": self.duplicate_experiences,
            "duplicate_lexicons": self.duplicate_lexicons,
            "duplicate_tasks": self.duplicate_tasks,
            "conflicts": self.conflicts,
            "orphaned_knowledge": self.orphaned_knowledge,
            "entropy_score": self.entropy_score,
            "duplication_rate": self.duplication_rate,
            "total_duplicates": self.total_duplicates,
        }


class EntropyMonitor:
    """
    熵增监控器
    
    不是只做文件Hash，而是做知识层面的重复分析。
    """
    
    def __init__(self, report_path: str = "08_GOVERNANCE/entropy"):
        self.report_path = report_path
        Path(self.report_path).mkdir(parents=True, exist_ok=True)
        
        # 已知内容缓存
        self.known_contents: Dict[str, Set[str]] = {
            "files": set(),
            "concepts": set(),
            "protocols": set(),
            "constraints": set(),
            "experiences": set(),
            "lexicons": set(),
        }
    
    def _compute_content_hash(self, content: str) -> str:
        """计算内容Hash"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
    
    def _is_duplicate(self, content_hash: str, category: str) -> bool:
        """检查是否重复"""
        return content_hash in self.known_contents.get(category, set())
    
    def _add_to_cache(self, content_hash: str, category: str) -> None:
        """添加到缓存"""
        if category not in self.known_contents:
            self.known_contents[category] = set()
        self.known_contents[category].add(content_hash)
    
    def check_file_duplicates(self, file_paths: List[str]) -> List[Tuple[str, str]]:
        """检查文件重复"""
        duplicates = []
        seen: Dict[str, List[str]] = {}
        
        for path in file_paths:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                content_hash = self._compute_content_hash(content)
                
                if content_hash in seen:
                    for existing in seen[content_hash]:
                        duplicates.append((existing, path))
                    seen[content_hash].append(path)
                else:
                    seen[content_hash] = [path]
                
                self._add_to_cache(content_hash, "files")
            except:
                pass
        
        return duplicates
    
    def check_concept_duplicates(self, concepts: List[Dict]) -> List[Tuple[str, str]]:
        """检查概念重复"""
        duplicates = []
        seen: Dict[str, List[str]] = {}
        
        for concept in concepts:
            name = concept.get('name', '')
            definition = concept.get('definition', '')
            content_hash = self._compute_content_hash(f"{name}:{definition}")
            
            if content_hash in seen:
                for existing in seen[content_hash]:
                    duplicates.append((existing, name))
                seen[content_hash].append(name)
            else:
                seen[content_hash] = [name]
        
        return duplicates
    
    def check_protocol_duplicates(self, protocols: List[Dict]) -> List[Tuple[str, str]]:
        """检查协议重复"""
        duplicates = []
        seen: Dict[str, List[str]] = {}
        
        for protocol in protocols:
            name = protocol.get('name', '')
            rules = json.dumps(protocol.get('rules', []), sort_keys=True)
            content_hash = self._compute_content_hash(f"{name}:{rules}")
            
            if content_hash in seen:
                for existing in seen[content_hash]:
                    duplicates.append((existing, name))
                seen[content_hash].append(name)
            else:
                seen[content_hash] = [name]
        
        return duplicates
    
    def check_experience_duplicates(self, experiences: List[Dict]) -> List[Tuple[str, str]]:
        """检查经验重复"""
        duplicates = []
        seen: Dict[str, List[str]] = {}
        
        for exp in experiences:
            eid = exp.get('experience_id', '')
            conclusion = exp.get('conclusion', '')
            content_hash = self._compute_content_hash(f"{eid}:{conclusion}")
            
            if content_hash in seen:
                for existing in seen[content_hash]:
                    duplicates.append((existing, eid))
                seen[content_hash].append(eid)
            else:
                seen[content_hash] = [eid]
        
        return duplicates

    def check_semantic_duplicates(self, knowledge_items: List[Dict]) -> List[Dict]:
        """
        检查语义重复（Knowledge Entropy）

        不是Duplicate File。

        而是Duplicate Meaning。

        例如：
        两个文件Hash不同，但表达的是同一个知识。

        应该提示：
            Potential Duplicate Knowledge

        这才是Knowledge Entropy的核心。

        Args:
            knowledge_items: 知识列表

        Returns:
            语义重复列表
        """
        duplicates = []
        processed = set()

        for i, item1 in enumerate(knowledge_items):
            id1 = item1.get('id', '') or item1.get('title', '')
            if id1 in processed:
                continue

            content1 = self._extract_semantic_content(item1)
            words1 = set(content1.lower().split())

            for item2 in knowledge_items[i+1:]:
                id2 = item2.get('id', '') or item2.get('title', '')
                if id2 in processed:
                    continue

                content2 = self._extract_semantic_content(item2)
                words2 = set(content2.lower().split())

                # 计算语义相似度（简单词集合Jaccard）
                if words1 and words2:
                    intersection = len(words1 & words2)
                    union = len(words1 | words2)
                    similarity = intersection / union if union > 0 else 0

                    # 语义重复阈值：相似度>0.5但内容不完全相同
                    if similarity > 0.5:
                        # 计算语义距离
                        semantic_distance = 1 - similarity

                        duplicates.append({
                            "type": "semantic_duplicate",
                            "id1": id1,
                            "id2": id2,
                            "similarity": round(similarity, 4),
                            "semantic_distance": round(semantic_distance, 4),
                            "reason": "内容高度相似但ID不同",
                            "suggestion": "建议MERGE而非新增",
                        })
                        processed.add(id1)
                        processed.add(id2)

        return duplicates

    def _extract_semantic_content(self, item: Dict) -> str:
        """提取语义内容"""
        parts = []

        # 标题
        if 'title' in item:
            parts.append(str(item['title']))

        # 描述
        if 'description' in item:
            parts.append(str(item['description']))

        # 结论
        if 'conclusion' in item:
            parts.append(str(item['conclusion']))

        # 定义
        if 'definition' in item:
            parts.append(str(item['definition']))

        # 名称
        if 'name' in item:
            parts.append(str(item['name']))

        return " ".join(parts)

    def check_knowledge_entropy(self, experiences_path: str, lexicon_path: str) -> Dict:
        """
        检查知识熵（Knowledge Entropy）

        升级版熵监控：
        - 不仅检查文件Hash
        - 检查语义重复
        - 检查孤立知识
        - 计算知识密度

        Returns:
            知识熵报告
        """
        report = {
            "timestamp": datetime.now().isoformat(),
            "knowledge_entropy_score": 0.0,
            "semantic_duplicates": [],
            "isolated_knowledge": [],
            "conflicts": [],
            "total_knowledge_items": 0,
        }

        # 加载知识
        experiences = []
        try:
            with open(experiences_path, 'r', encoding='utf-8') as f:
                experiences = json.load(f)
        except:
            pass

        concepts = []
        try:
            with open(lexicon_path, 'r', encoding='utf-8') as f:
                lexicon = json.load(f)
                concepts = lexicon.get('concepts', [])
        except:
            pass

        all_items = experiences + [
            {"id": name, "title": name, "definition": c.get('definition', '')}
            for name, c in concepts.items()
            if isinstance(c, dict)
        ]

        report["total_knowledge_items"] = len(all_items)

        # 检查语义重复
        semantic_dups = self.check_semantic_duplicates(all_items)
        report["semantic_duplicates"] = semantic_dups

        # 计算知识熵分数
        # 语义重复贡献熵
        if len(all_items) > 0:
            semantic_entropy = len(semantic_dups) * 2 / len(all_items)
        else:
            semantic_entropy = 0

        # 孤立知识贡献熵
        isolated_count = self._count_isolated_knowledge(all_items)
        isolated_entropy = isolated_count / len(all_items) if len(all_items) > 0 else 0

        # 冲突贡献熵
        conflict_count = len(report["conflicts"])
        conflict_entropy = conflict_count * 0.5

        # 综合熵分数
        report["knowledge_entropy_score"] = round(
            semantic_entropy + isolated_entropy + conflict_entropy, 4
        )

        report["isolated_knowledge"] = report["total_knowledge_items"] - isolated_count

        return report

    def _count_isolated_knowledge(self, items: List[Dict]) -> int:
        """计算孤立知识数量"""
        isolated = 0

        for item in items:
            has_relationship = False

            # 检查是否有引用
            if 'references' in item and item['references']:
                has_relationship = True
            if 'related' in item and item['related']:
                has_relationship = True
            if 'derived_from' in item and item['derived_from']:
                has_relationship = True

            # 检查是否有来源
            if 'source' in item and item['source']:
                has_relationship = True

            # 检查是否有血缘
            if 'lineage' in item and item['lineage']:
                has_relationship = True

            if not has_relationship:
                isolated += 1

        return isolated
    
    def generate_report(self, 
                       lexicon_path: str = "06_RUNTIME/ace/data/memory/lexicon.json",
                       experiences_path: str = "09_KNOWLEDGE/experiences.json",
                       evolution_path: str = "09_KNOWLEDGE/evolution.json") -> EntropyReport:
        """生成熵增报告"""
        report = EntropyReport()
        
        # 加载概念
        try:
            with open(lexicon_path, 'r', encoding='utf-8') as f:
                lexicon_data = json.load(f)
                concepts = lexicon_data.get('concepts', [])
                report.duplicate_concepts = self.check_concept_duplicates(concepts)
        except:
            concepts = []
        
        # 加载经验
        try:
            with open(experiences_path, 'r', encoding='utf-8') as f:
                experiences = json.load(f)
                report.duplicate_experiences = self.check_experience_duplicates(experiences)
        except:
            experiences = []
        
        # 加载演化记录
        try:
            with open(evolution_path, 'r', encoding='utf-8') as f:
                evolution_data = json.load(f)
                if isinstance(evolution_data, list):
                    report.duplicate_protocols = self.check_protocol_duplicates(evolution_data)
        except:
            pass
        
        # 计算统计
        total_items = (len(concepts) + len(experiences))
        total_duplicates = (
            len(report.duplicate_concepts) +
            len(report.duplicate_experiences) +
            len(report.duplicate_protocols) +
            len(report.duplicate_constraints) +
            len(report.duplicate_lexicons)
        )
        
        report.total_duplicates = total_duplicates
        report.duplication_rate = total_duplicates / total_items if total_items > 0 else 0.0
        
        # 熵分数 = 重复率 * 100
        report.entropy_score = report.duplication_rate * 100
        
        return report
    
    def save_report(self, report: EntropyReport, date: str = None) -> str:
        """保存报告"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        filename = f"{self.report_path}/entropy_report_{date}.json"
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)
        
        return filename
    
    def get_entropy_trend(self, days: int = 7) -> List[Dict]:
        """获取熵趋势"""
        trend = []
        
        for i in range(days):
            date = (datetime.now() - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            filename = f"{self.report_path}/entropy_report_{date}.json"
            
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                    trend.append({
                        "date": date,
                        "entropy_score": report.get("entropy_score", 0),
                        "duplication_rate": report.get("duplication_rate", 0),
                        "total_duplicates": report.get("total_duplicates", 0),
                    })
            except:
                pass
        
        return trend
