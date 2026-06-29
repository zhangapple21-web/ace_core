"""
相似度检测引擎 — Repository Curator 配套模块

用途：
  - 检测新产物是否与仓库已有内容重复
  - 识别需要去重的文件
  - 为馆长决策提供相似度数据

算法：
  - 字符级 n-gram（n=3）Jaccard 相似度
  - 轻量级，无需外部 API
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from collections import Counter
import hashlib
import os
import time


class SimilarityEngine:
    """
    轻量级文本相似度引擎
    
    不依赖外部 embedding API，使用 n-gram Jaccard 算法
    """
    
    def __init__(self, data_dir: str = None):
        """
        初始化相似度引擎
        
        Args:
            data_dir: 用于存储文档指纹缓存的目录
        """
        if data_dir is None:
            data_dir = os.path.dirname(__file__)
        self.data_dir = Path(data_dir)
        self.cache_dir = self.data_dir / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.fingerprint_cache_file = self.cache_dir / "fingerprint_cache.json"
        self._fingerprint_cache: Dict[str, Dict] = {}
        self._load_cache()
    
    def _load_cache(self) -> None:
        """加载指纹缓存，处理损坏的缓存文件"""
        try:
            if self.fingerprint_cache_file.exists():
                with open(self.fingerprint_cache_file, 'r', encoding='utf-8') as f:
                    self._fingerprint_cache = json.load(f)
        except (json.JSONDecodeError, IOError):
            self._fingerprint_cache = {}
    
    def _save_cache(self) -> None:
        """保存指纹缓存"""
        try:
            with open(self.fingerprint_cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._fingerprint_cache, f, ensure_ascii=False, indent=2)
        except IOError:
            pass
    
    def _get_file_key(self, path: str) -> str:
        """获取文件的唯一标识（path + mtime）"""
        try:
            mtime = os.path.getmtime(path)
            return f"{path}@{mtime}"
        except OSError:
            return path
    
    def _generate_ngrams(self, text: str, n: int = 3) -> set:
        """
        生成字符级 n-gram
        
        Args:
            text: 输入文本
            n: n-gram 大小，默认 3
        
        Returns:
            set: n-gram 集合
        """
        text = text.strip().replace('\r\n', '\n').replace('\r', '\n')
        if len(text) < n:
            return {text} if text else set()
        return {text[i:i+n] for i in range(len(text) - n + 1)}
    
    def compute_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的相似度
        
        Args:
            text1: 第一个文本
            text2: 第二个文本
        
        Returns:
            float: 0.0 - 1.0（相似度百分比）
        """
        if not text1 or not text2:
            return 0.0
        
        ngrams1 = self._generate_ngrams(text1)
        ngrams2 = self._generate_ngrams(text2)
        
        if not ngrams1 or not ngrams2:
            return 0.0
        
        intersection = len(ngrams1 & ngrams2)
        union = len(ngrams1 | ngrams2)
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def get_fingerprint(self, text: str) -> str:
        """
        获取文本指纹（用于快速缓存匹配）
        
        Args:
            text: 输入文本
        
        Returns:
            str: 文本的 MD5 指纹
        """
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def compute_with_cache(self, text: str, path: str = None) -> str:
        """
        计算文本相似度（带缓存）
        
        Args:
            text: 输入文本
            path: 文件路径（用于缓存键）
        
        Returns:
            str: 文本指纹
        """
        if path:
            file_key = self._get_file_key(path)
            if file_key in self._fingerprint_cache:
                cached = self._fingerprint_cache[file_key]
                if cached.get('text') == text:
                    return cached.get('fingerprint', '')
        
        fingerprint = self.get_fingerprint(text)
        
        if path:
            self._fingerprint_cache[self._get_file_key(path)] = {
                'fingerprint': fingerprint,
                'text': text,
                'timestamp': time.time()
            }
            self._save_cache()
        
        return fingerprint
    
    def find_similar(
        self, 
        text: str, 
        candidates: List[Dict[str, str]],
        threshold: float = 0.7,
        top_k: int = 3
    ) -> List[Dict]:
        """
        从候选文档中找到最相似的
        
        Args:
            text: 待匹配的文本
            candidates: 候选文档列表 [{path, title, content}]
            threshold: 相似度阈值，默认 0.7
            top_k: 返回最多 top_k 个结果，默认 3
        
        Returns:
            List[Dict] - 按相似度排序的结果 [{path, title, similarity, reason}]
        """
        if not text or not candidates:
            return []
        
        results = []
        title_weight = 0.3
        content_weight = 0.7
        
        for candidate in candidates:
            candidate_text = candidate.get('content', '')
            candidate_title = candidate.get('title', '')
            
            if not candidate_text:
                continue
            
            title_sim = 0.0
            if candidate_title:
                title_sim = self.compute_similarity(text[:200], candidate_title)
            
            content_sim = self.compute_similarity(text, candidate_text)
            
            combined_sim = title_weight * title_sim + content_weight * content_sim
            
            if combined_sim >= threshold:
                results.append({
                    'path': candidate.get('path', ''),
                    'title': candidate_title,
                    'similarity': round(combined_sim, 4),
                    'reason': self._generate_reason(title_sim, content_sim)
                })
        
        results.sort(key=lambda x: x['similarity'], reverse=True)
        return results[:top_k]
    
    def _generate_reason(self, title_sim: float, content_sim: float) -> str:
        """生成相似原因说明"""
        reasons = []
        if title_sim > 0.7:
            reasons.append("标题相似度高")
        if content_sim > 0.7:
            reasons.append("内容高度相似")
        elif content_sim > 0.5:
            reasons.append("内容部分相似")
        
        if not reasons:
            reasons.append("存在一定相似性")
        
        return "; ".join(reasons)
    
    def is_duplicate(self, text: str, candidates: List[Dict], threshold: float = 0.85) -> bool:
        """
        判断文本是否与已有文档重复（相似度 > threshold）
        
        Args:
            text: 待检测文本
            candidates: 候选文档列表
            threshold: 重复阈值，默认 0.85
        
        Returns:
            bool: True 表示重复
        """
        if not text or not candidates:
            return False
        
        for candidate in candidates:
            candidate_content = candidate.get('content', '')
            if not candidate_content:
                continue
            
            similarity = self.compute_similarity(text, candidate_content)
            if similarity >= threshold:
                return True
        
        return False
    
    def detect_patterns(self, filename: str) -> Dict[str, Any]:
        """
        识别文件名中的反模式
        
        Args:
            filename: 文件名
        
        Returns:
            Dict: 检测结果 {is_duplicate_pattern, pattern_type, suggestion}
        """
        result = {
            'is_duplicate_pattern': False,
            'pattern_type': None,
            'suggestion': None
        }
        
        version_patterns = [
            r'\(\s*\d+\s*\)',      # (2), (3), etc.
            r'_\s*v\s*\d+',        # _v2, _v3
            r'_\s*version\s*\d+',  # _version2
        ]
        
        fuzzy_patterns = [
            r'\bnew\b',            # new
            r'\bfinal\b',          # final
            r'\blatest\b',         # latest
            r'\bcopy\b',           # copy
            r'\bdraft\b',          # draft
        ]
        
        date_pattern = r'_\d{8}'   # _YYYYMMDD
        
        for pattern in version_patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                result['is_duplicate_pattern'] = True
                result['pattern_type'] = 'version_suffix'
                result['suggestion'] = '可能为版本副本，建议检查是否需要合并'
                return result
        
        for pattern in fuzzy_patterns:
            if re.search(pattern, filename, re.IGNORECASE):
                result['is_duplicate_pattern'] = True
                result['pattern_type'] = 'fuzzy_naming'
                result['suggestion'] = '命名模糊，建议使用描述性名称'
                return result
        
        if re.search(date_pattern, filename):
            result['is_duplicate_pattern'] = True
            result['pattern_type'] = 'date_suffix'
            result['suggestion'] = '日期后缀文件，建议移动到对应日期目录'
            return result
        
        return result
    
    def batch_compute_similarity(self, texts: List[str]) -> List[List[float]]:
        """
        批量计算文本间的相似度矩阵
        
        Args:
            texts: 文本列表
        
        Returns:
            List[List[float]]: 相似度矩阵
        """
        n = len(texts)
        matrix = [[0.0] * n for _ in range(n)]
        
        for i in range(n):
            for j in range(i + 1, n):
                sim = self.compute_similarity(texts[i], texts[j])
                matrix[i][j] = sim
                matrix[j][i] = sim
        
        return matrix
    
    def find_duplicates_in_collection(
        self, 
        documents: List[Dict[str, str]], 
        threshold: float = 0.85
    ) -> List[Dict]:
        """
        在文档集合中查找重复文档对
        
        Args:
            documents: 文档列表 [{path, title, content}]
            threshold: 重复阈值
        
        Returns:
            List[Dict]: 重复文档对列表
        """
        duplicates = []
        n = len(documents)
        
        for i in range(n):
            for j in range(i + 1, n):
                doc1 = documents[i]
                doc2 = documents[j]
                
                content1 = doc1.get('content', '')
                content2 = doc2.get('content', '')
                
                if not content1 or not content2:
                    continue
                
                sim = self.compute_similarity(content1, content2)
                
                if sim >= threshold:
                    duplicates.append({
                        'doc1_path': doc1.get('path', ''),
                        'doc1_title': doc1.get('title', ''),
                        'doc2_path': doc2.get('path', ''),
                        'doc2_title': doc2.get('title', ''),
                        'similarity': round(sim, 4),
                        'recommendation': self._get_merge_recommendation(doc1, doc2)
                    })
        
        return duplicates
    
    def _get_merge_recommendation(self, doc1: Dict, doc2: Dict) -> str:
        """获取合并建议"""
        path1 = doc1.get('path', '')
        path2 = doc2.get('path', '')

        name1 = Path(path1).stem if path1 else ''
        name2 = Path(path2).stem if path2 else ''

        if self.detect_patterns(name1)['is_duplicate_pattern']:
            return f"建议保留 {path2}，删除 {path1}"
        elif self.detect_patterns(name2)['is_duplicate_pattern']:
            return f"建议保留 {path1}，删除 {path2}"
        else:
            return f"建议人工确认保留哪个"

    # ========== Phase-1.5 跨类型相似度比较 ==========

    ARTIFACT_TYPES = ["concept", "experience", "constraint", "protocol", "axiom", "blueprint"]

    def compare_knowledge_types(
        self,
        lexicon_data: Dict,
        experiences_data: List[Dict],
        constraints_data: List[Dict] = None,
        protocols_data: List[Dict] = None
    ) -> Dict[str, Any]:
        """
        跨类型知识相似度比较

        检测：
        - 重复：同类知识高度相似
        - 冲突：同一概念不同定义
        - 包含：一个知识包含另一个
        - 替代：一个知识替代另一个
        - 继承：一个知识从另一个演化
        - 演化：知识版本的演进关系

        Args:
            lexicon_data: 词库数据，包含concepts字典
            experiences_data: 经验列表
            constraints_data: 约束列表（可选）
            protocols_data: 协议列表（可选）

        Returns:
            跨类型比较报告
        """
        report = {
            "compared_at": datetime.now().isoformat(),
            "relationships": {
                "duplicate": [],
                "conflict": [],
                "containment": [],
                "supersession": [],
                "inheritance": [],
                "evolution": [],
            },
            "summary": {
                "total_relationships": 0,
                "by_type": {},
            }
        }

        # 1. 概念间重复检测
        if "concepts" in lexicon_data:
            concept_dupes = self._find_concept_duplicates(lexicon_data["concepts"])
            report["relationships"]["duplicate"].extend(concept_dupes)

        # 2. 经验间重复检测
        if experiences_data:
            exp_dupes = self._find_experience_duplicates(experiences_data)
            report["relationships"]["duplicate"].extend(exp_dupes)

        # 3. 概念与经验间关系检测
        if "concepts" in lexicon_data and experiences_data:
            concept_exp_relations = self._find_concept_experience_relations(
                lexicon_data["concepts"],
                experiences_data
            )
            for rel_type, items in concept_exp_relations.items():
                report["relationships"][rel_type].extend(items)

        # 4. 版本演化关系检测
        if experiences_data:
            evolution_relations = self._find_evolution_relations(experiences_data)
            report["relationships"]["evolution"].extend(evolution_relations)

        # 统计
        for rel_type, items in report["relationships"].items():
            if items:
                report["summary"]["by_type"][rel_type] = len(items)
                report["summary"]["total_relationships"] += len(items)

        return report

    def _find_concept_duplicates(self, concepts: Dict) -> List[Dict]:
        """检测概念重复"""
        duplicates = []
        concept_list = list(concepts.items())

        for i, (name1, concept1) in enumerate(concept_list):
            if not isinstance(concept1, dict):
                continue

            def1 = concept1.get("definition", "")
            if not def1:
                continue

            for name2, concept2 in concept_list[i+1:]:
                if not isinstance(concept2, dict):
                    continue

                def2 = concept2.get("definition", "")
                if not def2:
                    continue

                sim = self.compute_similarity(def1, def2)
                if sim >= 0.85:
                    duplicates.append({
                        "type": "concept_duplicate",
                        "item1": name1,
                        "item2": name2,
                        "similarity": round(sim, 4),
                        "recommendation": "考虑合并或删除其中一个"
                    })

        return duplicates

    def _find_experience_duplicates(self, experiences: List[Dict]) -> List[Dict]:
        """检测经验重复"""
        duplicates = []

        for i, exp1 in enumerate(experiences):
            if not isinstance(exp1, dict):
                continue

            title1 = exp1.get("title", "")
            conclusion1 = exp1.get("conclusion", "")
            key1 = title1 + conclusion1[:100]

            for exp2 in experiences[i+1:]:
                if not isinstance(exp2, dict):
                    continue

                title2 = exp2.get("title", "")
                conclusion2 = exp2.get("conclusion", "")
                key2 = title2 + conclusion2[:100]

                sim = self.compute_similarity(key1, key2)
                if sim >= 0.75:
                    duplicates.append({
                        "type": "experience_duplicate",
                        "id1": exp1.get("id", ""),
                        "id2": exp2.get("id", ""),
                        "title1": title1,
                        "title2": title2,
                        "similarity": round(sim, 4),
                    })

        return duplicates

    def _find_concept_experience_relations(
        self,
        concepts: Dict,
        experiences: List[Dict]
    ) -> Dict[str, List]:
        """检测概念与经验间的关系"""
        relations = {
            "containment": [],
            "supersession": [],
            "inheritance": [],
        }

        for name, concept in concepts.items():
            if not isinstance(concept, dict):
                continue

            concept_def = concept.get("definition", "")
            if not concept_def:
                continue

            for exp in experiences:
                if not isinstance(exp, dict):
                    continue

                exp_text = exp.get("conclusion", "") + exp.get("title", "")

                # 包含关系：经验引用了概念
                if name in exp_text:
                    relations["containment"].append({
                        "type": "concept_experience_containment",
                        "concept": name,
                        "experience_id": exp.get("id", ""),
                        "relation": "经验引用了概念定义"
                    })

                # 继承关系：经验体现了概念
                sim = self.compute_similarity(concept_def, exp_text)
                if sim >= 0.6:
                    relations["inheritance"].append({
                        "type": "concept_experience_inheritance",
                        "concept": name,
                        "experience_id": exp.get("id", ""),
                        "similarity": round(sim, 4),
                    })

        return relations

    def _find_evolution_relations(self, items: List[Dict]) -> List[Dict]:
        """检测版本演化关系"""
        evolutions = []

        # 按标题分组
        groups = {}
        for item in items:
            if not isinstance(item, dict):
                continue

            title = item.get("title", "")
            # 提取基础名称（去除版本号等）
            base_name = title
            for pattern in [r'v\d+$', r'\d+$', r'_v\d+$']:
                import re
                base_name = re.sub(pattern, '', base_name).strip()

            if base_name not in groups:
                groups[base_name] = []
            groups[base_name].append(item)

        # 生成演化链
        for base_name, group_items in groups.items():
            if len(group_items) < 2:
                continue

            # 按时间排序
            group_items.sort(key=lambda x: x.get("created", ""))

            for i in range(len(group_items) - 1):
                evolutions.append({
                    "type": "evolution",
                    "from_id": group_items[i].get("id", ""),
                    "from_title": group_items[i].get("title", ""),
                    "to_id": group_items[i+1].get("id", ""),
                    "to_title": group_items[i+1].get("title", ""),
                    "relation": "版本演化"
                })

        return evolutions

    def find_cross_repository_duplicates(
        self,
        repo1_path: str,
        repo2_path: str,
        artifact_type: str = "concept"
    ) -> List[Dict]:
        """
        跨仓库重复检测

        Args:
            repo1_path: 第一个仓库路径
            repo2_path: 第二个仓库路径
            artifact_type: 产物类型

        Returns:
            重复列表
        """
        duplicates = []

        # 扫描两个仓库的指定类型产物
        items1 = self._scan_artifact_type(repo1_path, artifact_type)
        items2 = self._scan_artifact_type(repo2_path, artifact_type)

        for item1 in items1:
            for item2 in items2:
                if not item1.get("content") or not item2.get("content"):
                    continue

                sim = self.compute_similarity(item1["content"], item2["content"])
                if sim >= 0.8:
                    duplicates.append({
                        "type": f"{artifact_type}_cross_repo_duplicate",
                        "item1": item1,
                        "item2": item2,
                        "similarity": round(sim, 4),
                    })

        return duplicates

    def _scan_artifact_type(self, repo_path: str, artifact_type: str) -> List[Dict]:
        """扫描特定类型的产物"""
        items = []
        path = Path(repo_path)

        if not path.exists():
            return items

        if artifact_type == "concept":
            # 扫描词库
            lexicon_file = path / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
            if lexicon_file.exists():
                try:
                    with open(lexicon_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for name, concept in data.get("concepts", {}).items():
                        if isinstance(concept, dict):
                            items.append({
                                "id": name,
                                "title": name,
                                "content": concept.get("definition", ""),
                            })
                except Exception:
                    pass

        elif artifact_type == "experience":
            # 扫描经验
            exp_file = path / "09_KNOWLEDGE" / "experiences.json"
            if exp_file.exists():
                try:
                    with open(exp_file, "r", encoding="utf-8") as f:
                        experiences = json.load(f)
                    for exp in experiences:
                        if isinstance(exp, dict):
                            items.append({
                                "id": exp.get("id", ""),
                                "title": exp.get("title", ""),
                                "content": exp.get("conclusion", ""),
                            })
                except Exception:
                    pass

        return items
