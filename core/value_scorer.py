"""
价值评分模块 — Repository Curator 决策支持

在同步前，对每个产物进行多维度评分：
- Novelty: 新颖度（与已有知识的差异程度）
- Similarity: 相似度（来自 similarity_engine）
- Stability: 成熟度（是否已经过验证/迭代）
- Reusability: 可复用性

馆长根据评分决定：create / update / merge / discard / split
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple


@dataclass
class ArtifactScore:
    """产物评分结果"""
    novelty: float = 0.0       # 0-100，新颖度（与已有知识的差异程度）
    similarity: float = 0.0     # 0-100，与已有内容的相似度
    stability: float = 0.0     # 0-100，成熟度（是否已经过验证/迭代）
    reusability: float = 0.0   # 0-100，可复用性
    composite: float = 0.0     # 综合评分 0-100
    action: str = "create"     # create / update / merge / discard / split
    target_repo: str = ""      # 目标仓库
    target_path: str = ""       # 目标路径
    split_candidates: List[Dict] = field(default_factory=list)  # 如果需要拆分，候选列表
    reason: str = ""           # 决策理由


class ValueScorer:
    """
    价值评分器 — Repository Curator 决策支持
    
    在同步前，对每个产物进行多维度评分
    """
    
    # 知识分类定义
    CATEGORY_PATTERNS = {
        "axiom": ["公理", "axiom", "第一性原理", "R2公理", "第一原理"],
        "constraint": ["约束", "constraint", "限制", "规则", "定律", "constraint"],
        "protocol": ["协议", "protocol", "规范", "接口", "interface"],
        "experience": ["经验", "experience", "案例", "case", "最佳实践"],
        "architecture": ["架构", "architecture", "设计", "蓝图", "design"],
        "research": ["研究", "research", "分析", "考古", "investigation"],
        "runtime": ["运行时", "runtime", "执行", "进程", ".py"],
        "ops": ["运维", "ops", "监控", "健康检查", "deployment"],
    }
    
    # 仓库分类规则
    REPO_RULES = {
        "09_KNOWLEDGE": ["axiom", "constraint", "protocol", "experience"],
        "08_ARCHAEOLOGY": ["research", "architecture"],
        "04_PROTOCOLS": ["protocol"],
        "02_MEMORY": ["runtime", "ops"],
        "06_RUNTIME": ["runtime"],
        "core/": ["runtime"],  # Python 代码
    }
    
    # 评分阈值
    THRESHOLDS = {
        "discard_novelty": 10,
        "discard_similarity": 95,
        "update_similarity": 85,
        "split_stability": 30,
    }
    
    def __init__(self, data_dir: Optional[Path] = None):
        """
        初始化价值评分器
        
        Args:
            data_dir: 数据目录，用于存储评分缓存等
        """
        self.data_dir = Path(data_dir) if data_dir else Path("06_RUNTIME/ace/data/curator")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # 缓存已有知识特征（用于新颖度计算）
        self._knowledge_cache: Dict[str, List[str]] = {}
    
    def score(self, artifact: Dict[str, Any]) -> ArtifactScore:
        """
        对产物进行评分
        
        artifact = {
            "path": str,
            "title": str,
            "content": str,
            "author": str,  # agent name
            "type": str,    # md / json / py
            "size": int,
            "mtime": str,
            "similar_docs": List[Dict],  # 来自 similarity_engine
        }
        
        Returns: ArtifactScore
        """
        # 计算各维度评分
        novelty = self._score_novelty(artifact)
        stability = self._score_stability(artifact)
        reusability = self._score_reusability(artifact)
        
        # 从 similar_docs 获取相似度
        similarity = 0.0
        similar_docs = artifact.get("similar_docs", [])
        if similar_docs:
            similarity = similar_docs[0].get("similarity", 0.0)
        
        # 分类识别
        category = self._classify_category(artifact)
        
        # 确定目标仓库和路径
        target_repo, target_path = self._determine_target(artifact, category)
        
        # 检测是否需要拆分
        split_candidates = self._detect_need_split(artifact)
        
        # 计算综合评分
        composite = (novelty * 0.3 + (100 - similarity) * 0.2 + 
                     stability * 0.25 + reusability * 0.25)
        
        # 决定动作
        action, reason = self._decide_action(novelty, similarity, stability, 
                                              category, split_candidates)
        
        return ArtifactScore(
            novelty=novelty,
            similarity=similarity,
            stability=stability,
            reusability=reusability,
            composite=composite,
            action=action,
            target_repo=target_repo,
            target_path=target_path,
            split_candidates=split_candidates,
            reason=reason,
        )
    
    def _score_novelty(self, artifact: Dict) -> float:
        """
        新颖度：内容与已有知识的差异程度
        
        基于以下因素：
        1. 是否包含新的关键词/短语
        2. 与已有知识库的重复程度
        3. 是否是独特观点
        """
        content = artifact.get("content", "")
        title = artifact.get("title", "")
        
        if not content:
            return 50.0  # 默认中等新颖度
        
        # 提取内容中的关键词（简化版）
        words = re.findall(r'[\w\u4e00-\u9fff]{2,}', content.lower())
        unique_words = set(words)
        
        # 计算内容长度相关的新颖度
        content_length = len(content)
        length_factor = min(100, content_length / 100)  # 长度因子
        
        # 稀有词汇比例（相对于常见词）
        # 这里简化处理：假设短内容更容易是重复的
        if content_length < 200:
            novelty = 30.0 + length_factor * 0.5
        elif content_length < 1000:
            novelty = 50.0 + length_factor * 0.3
        else:
            novelty = 60.0 + min(20, length_factor * 0.2)
        
        # 标题新颖度检测
        title_words = set(re.findall(r'[\w\u4e00-\u9fff]{2,}', title.lower()))
        if title_words and unique_words:
            title_overlap = len(title_words & unique_words) / len(title_words)
            novelty += (1 - title_overlap) * 15  # 标题与内容差异贡献
        
        return min(100.0, max(0.0, novelty))
    
    def _score_stability(self, artifact: Dict) -> float:
        """
        成熟度：是否经过验证
        
        基于：
        1. mtime（越老越稳定）
        2. 作者数量（多作者更稳定）
        3. 内容长度（长文档更稳定）
        4. 是否经过多次修改
        """
        stability = 50.0  # 默认中等
        
        # 1. 基于时间的稳定性
        mtime_str = artifact.get("mtime", "")
        if mtime_str:
            try:
                if isinstance(mtime_str, str):
                    # 尝试解析时间
                    mtime = datetime.fromisoformat(mtime_str.replace("Z", "+00:00"))
                else:
                    mtime = datetime.fromtimestamp(mtime_str)
                
                age_days = (datetime.now() - mtime.replace(tzinfo=None) if mtime.tzinfo else datetime.now() - mtime).days
                
                if age_days > 90:
                    stability += 20  # 超过3个月，很稳定
                elif age_days > 30:
                    stability += 10  # 超过1个月
                elif age_days < 7:
                    stability -= 10  # 不满1周，不够稳定
            except Exception:
                pass
        
        # 2. 作者因素
        author = artifact.get("author", "")
        if author:
            # 知名长期运行的 agent 贡献更稳定
            known_agents = ["archaeology", "curator", "scheduler", "memory"]
            if any(a.lower() in author.lower() for a in known_agents):
                stability += 10
        
        # 3. 内容长度因子
        content_length = len(artifact.get("content", ""))
        if content_length > 5000:
            stability += 10  # 长文档通常更成熟
        elif content_length < 200:
            stability -= 10  # 短内容可能不够成熟
        
        # 4. 类型因素
        artifact_type = artifact.get("type", "")
        if artifact_type == "md":
            stability += 5  # Markdown 文档相对稳定
        elif artifact_type == "json":
            stability += 0  # JSON 配置，中等
        
        return min(100.0, max(0.0, stability))
    
    def _score_reusability(self, artifact: Dict) -> float:
        """
        可复用性：是否值得长期保留
        
        基于：
        1. 是否为通用模式
        2. 是否包含可抽取的规则/协议
        3. 是否具有普遍适用性
        """
        content = artifact.get("content", "")
        title = artifact.get("title", "")
        
        if not content:
            return 30.0
        
        reusability = 50.0  # 默认中等
        
        # 1. 检查是否包含可复用元素
        reusable_patterns = [
            r"^\d+\.",  # 编号列表（规则/步骤）
            r"^\-\s",   # 短横列表
            r"```\w+",  # 代码块
            r"\|.+\|",  # 表格
            r"#{1,3}\s",  # 标题层级
            r"\*\*.+\*\*",  # 强调
        ]
        
        pattern_matches = 0
        for pattern in reusable_patterns:
            if re.search(pattern, content, re.MULTILINE):
                pattern_matches += 1
        
        if pattern_matches >= 3:
            reusability += 20
        elif pattern_matches >= 1:
            reusability += 10
        
        # 2. 检查是否包含通用词汇
        generic_terms = ["系统", "模块", "接口", "配置", "规则", "协议", 
                        "原则", "方法", "流程", "规范", "标准"]
        title_lower = title.lower()
        content_lower = content.lower()
        
        generic_count = sum(1 for term in generic_terms 
                           if term in title_lower or term in content_lower)
        
        if generic_count >= 3:
            reusability += 15
        elif generic_count >= 1:
            reusability += 5
        
        # 3. 特定类型高可复用性
        category = self._classify_category(artifact)
        if category in ["protocol", "constraint", "axiom"]:
            reusability += 15  # 协议、约束、公理高可复用
        elif category in ["experience", "architecture"]:
            reusability += 10
        
        # 4. 代码类内容
        if artifact.get("type") == "py":
            if "def " in content or "class " in content:
                reusability += 10
        
        return min(100.0, max(0.0, reusability))
    
    def _classify_category(self, artifact: Dict) -> str:
        """分类识别"""
        content = artifact.get("content", "")
        title = artifact.get("title", "")
        path = artifact.get("path", "")
        
        # 合并文本用于匹配
        text = f"{title} {content} {path}".lower()
        
        scores: Dict[str, float] = {}
        
        for category, patterns in self.CATEGORY_PATTERNS.items():
            score = 0.0
            for pattern in patterns:
                if pattern.lower() in text:
                    score += 1
            scores[category] = score
        
        if not scores or max(scores.values()) == 0:
            return "unknown"
        
        # 返回得分最高的分类
        return max(scores, key=scores.get)
    
    def _determine_target(self, artifact: Dict, category: str) -> Tuple[str, str]:
        """
        确定目标仓库和路径
        
        Returns:
            (target_repo, target_path)
        """
        path = artifact.get("path", "")
        title = artifact.get("title", "")
        
        # 1. 如果是 Python 代码，指向 core/
        if artifact.get("type") == "py" or path.endswith(".py"):
            return "core/", Path(path).name
        
        # 2. 基于类别选择仓库
        for repo, categories in self.REPO_RULES.items():
            if category in categories:
                # 生成目标路径
                filename = Path(path).name if path else f"{title}.md"
                return repo, filename
        
        # 3. 默认仓库
        filename = Path(path).name if path else f"{title}.md"
        return "09_KNOWLEDGE/", filename
    
    def _detect_need_split(self, artifact: Dict) -> List[Dict]:
        """
        检测是否需要拆分
        
        如果文档包含多个类型的内容（axiom + constraint + protocol），建议拆分
        """
        content = artifact.get("content", "")
        title = artifact.get("title", "")
        
        if not content or len(content) < 500:
            return []  # 短内容不需要拆分
        
        # 检测内容中的类别分布
        text = f"{title} {content}".lower()
        
        detected_categories: Dict[str, List[str]] = {}
        
        for category, patterns in self.CATEGORY_PATTERNS.items():
            matches = []
            for pattern in patterns:
                if pattern.lower() in text:
                    matches.append(pattern)
            if matches:
                detected_categories[category] = matches
        
        # 如果检测到2个以上不同类别，建议拆分
        if len(detected_categories) >= 2:
            candidates = []
            for cat, keywords in detected_categories.items():
                # 简单按章节拆分（以 ## 标题分隔）
                sections = re.split(r'^##\s+', content, flags=re.MULTILINE)
                
                for i, section in enumerate(sections[1:], 1):  # 跳过第一部分（通常是引言）
                    section_title = section.split('\n')[0].strip()
                    section_content = '\n'.join(section.split('\n')[1:]).strip()
                    
                    # 检查这个 section 是否包含该类别
                    section_text = f"{section_title} {section_content}".lower()
                    if any(kw.lower() in section_text for kw in keywords):
                        match_idx = next((keywords.index(kw) for kw in keywords if kw.lower() in section_text), 0)
                        candidates.append({
                            "category": cat,
                            "title": section_title or f"Part {i}",
                            "content": section_content[:500],  # 截断预览
                            "confidence": match_idx + 1,
                        })
            
            return candidates
        
        return []
    
    def _decide_action(self, novelty: float, similarity: float, 
                       stability: float, category: str,
                       split_candidates: List[Dict]) -> Tuple[str, str]:
        """
        根据评分决定动作
        
        决策规则：
        - novelty < 10 AND similarity > 95: discard（基本重复，无价值）
        - similarity > 85: update（高度相似，更新）
        - stability < 30: split（不成熟，可能需要拆分）
        - category == "mixed": split（混合内容，必须拆分）
        - 否则: create（新增）
        """
        thresholds = self.THRESHOLDS
        
        # 规则1：基本重复
        if novelty < thresholds["discard_novelty"] and similarity > thresholds["discard_similarity"]:
            return "discard", f"新颖度{novelty:.1f}低且相似度{similarity:.1f}高，内容重复"
        
        # 规则2：高度相似，需要更新
        if similarity > thresholds["update_similarity"]:
            return "update", f"相似度{similarity:.1f}高，更新已有内容"
        
        # 规则3：不成熟，可能需要拆分
        if stability < thresholds["split_stability"]:
            if split_candidates:
                return "split", f"稳定性{stability:.1f}低，发现{len(split_candidates)}个可拆分部分"
            return "split", f"稳定性{stability:.1f}低，建议检查内容完整性"
        
        # 规则4：混合内容
        if category == "unknown" and len(split_candidates) >= 2:
            return "split", f"内容混合多样，建议按主题拆分"
        
        # 规则5：创建新产品
        return "create", f"新内容(新颖度{novelty:.1f}，稳定性{stability:.1f})"
