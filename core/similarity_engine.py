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
