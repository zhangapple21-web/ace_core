"""
Lexicon 三级分类体系

借鉴 public-apis 仓库的 51 个领域分类思路，按用户意图组织，而非按技术组织。

三级结构：
- Level 1: domain（领域）→ 51个领域
- Level 2: type（类型）→ knowledge/pattern/principle/law/paradigm
- Level 3: attribute（属性）→ verified/hypothesis/deprecated
"""

from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field


DOMAINS: Dict[str, str] = {
    "Animals": "动物相关知识、物种、生态",
    "Anime": "动漫、二次元文化",
    "Anti-Malware": "反恶意软件、安全防护",
    "Art & Design": "艺术与设计、美学、创意",
    "Authentication & Authorization": "认证与授权、身份验证",
    "Blockchain": "区块链、分布式账本",
    "Books": "书籍、文学、阅读",
    "Business": "商业、商务、企业管理",
    "Calendar": "日历、时间管理、日程",
    "Cloud Storage & File Sharing": "云存储与文件共享",
    "Continuous Integration": "持续集成、CI/CD",
    "Cryptocurrency": "加密货币、数字资产",
    "Currency Exchange": "货币兑换、汇率",
    "Data Validation": "数据验证、数据质量",
    "Development": "开发工具、开发流程",
    "Dictionaries": "词典、词汇、翻译",
    "Documents & Productivity": "文档与生产力工具",
    "Email": "电子邮件、通信",
    "Entertainment": "娱乐、休闲",
    "Environment": "环境、生态、气候",
    "Events": "事件、活动、票务",
    "Finance": "金融、财务、投资",
    "Food & Drink": "食品与饮料、烹饪",
    "Games & Comics": "游戏与漫画",
    "Geocoding": "地理编码、位置服务",
    "Government": "政府、政务、公共服务",
    "Health": "健康、医疗、保健",
    "Jobs": "就业、招聘、职业",
    "Machine Learning": "机器学习、AI",
    "Music": "音乐、音频",
    "News": "新闻、资讯",
    "Open Data": "开放数据、公开数据集",
    "Open Source Projects": "开源项目、社区",
    "Patent": "专利、知识产权",
    "Personality": "人格、性格、心理",
    "Phone": "电话、通讯",
    "Photography": "摄影、图像",
    "Programming": "编程、软件开发",
    "Science & Math": "科学与数学",
    "Security": "安全、网络安全",
    "Shopping": "购物、电商",
    "Social": "社交、社交媒体",
    "Sports & Fitness": "运动与健身",
    "Test Data": "测试数据、模拟数据",
    "Text Analysis": "文本分析、NLP",
    "Tracking": "追踪、监控",
    "Transportation": "交通、运输",
    "URL Shorteners": "URL短链接",
    "Vehicle": "车辆、汽车",
    "Video": "视频、流媒体",
    "Weather": "天气、气象",
}


TYPES: Dict[str, str] = {
    "knowledge": "知识性概念：事实、定义、描述性内容",
    "pattern": "模式性概念：重复出现的结构、形态、套路",
    "principle": "原则性概念：指导行为的准则、价值观",
    "law": "定律性概念：被验证的规律、铁律",
    "paradigm": "范式性概念：世界观级别的认知框架",
}


ATTRIBUTES: Dict[str, str] = {
    "verified": "已验证：经过实践或证据确认",
    "hypothesis": "假设性：推测中，有待验证",
    "deprecated": "已废弃：不再使用或被取代",
}


@dataclass
class CategoryNode:
    """分类节点"""
    name: str
    level: int
    description: str = ""
    parent: Optional[str] = None
    children: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


class LexiconCategoryRegistry:
    """
    Lexicon 分类注册表

    管理三级分类体系，支持：
    - 获取某一级分类
    - 获取子分类
    - 新增分类
    - 给概念打分类标签
    """

    def __init__(self):
        self._nodes: Dict[str, CategoryNode] = {}
        self._level_map: Dict[int, List[str]] = {1: [], 2: [], 3: []}
        self._parent_map: Dict[str, List[str]] = {}
        self._bootstrap_defaults()

    def _bootstrap_defaults(self):
        """初始化默认分类体系"""
        for name, desc in DOMAINS.items():
            self._add_node(1, name, desc, parent=None)

        for name, desc in TYPES.items():
            self._add_node(2, name, desc, parent=None)

        for name, desc in ATTRIBUTES.items():
            self._add_node(3, name, desc, parent=None)

    def _add_node(self, level: int, name: str, description: str = "",
                  parent: Optional[str] = None) -> bool:
        """内部添加节点"""
        key = f"L{level}:{name}"
        if key in self._nodes:
            return False

        node = CategoryNode(
            name=name,
            level=level,
            description=description,
            parent=parent,
        )
        self._nodes[key] = node

        if name not in self._level_map[level]:
            self._level_map[level].append(name)

        if parent:
            parent_key = f"L{level - 1}:{parent}"
            if parent_key in self._nodes:
                if name not in self._nodes[parent_key].children:
                    self._nodes[parent_key].children.append(name)

        return True

    def get_categories(self, level: int) -> List[Dict[str, str]]:
        """
        获取某一级分类

        Args:
            level: 分类级别 (1=domain, 2=type, 3=attribute)

        Returns:
            分类列表，每项包含 name 和 description
        """
        if level not in self._level_map:
            return []

        result = []
        for name in self._level_map[level]:
            key = f"L{level}:{name}"
            node = self._nodes.get(key)
            if node:
                result.append({
                    "name": name,
                    "description": node.description,
                })
        return result

    def get_subcategories(self, category: str, level: Optional[int] = None) -> List[Dict[str, str]]:
        """
        获取子分类

        Args:
            category: 分类名称
            level: 可选，指定父分类所在级别。不指定则自动查找。

        Returns:
            子分类列表
        """
        if level:
            key = f"L{level}:{category}"
            node = self._nodes.get(key)
            if node:
                child_level = level + 1
                result = []
                for child_name in node.children:
                    child_key = f"L{child_level}:{child_name}"
                    child_node = self._nodes.get(child_key)
                    if child_node:
                        result.append({
                            "name": child_name,
                            "description": child_node.description,
                        })
                return result
        else:
            for lvl in range(1, 3):
                key = f"L{lvl}:{category}"
                if key in self._nodes:
                    return self.get_subcategories(category, level=lvl)

        return []

    def add_category(self, level: int, name: str, description: str = "",
                     parent: Optional[str] = None) -> bool:
        """
        新增分类

        Args:
            level: 分类级别 (1/2/3)
            name: 分类名称
            description: 分类描述
            parent: 父分类名称（可选）

        Returns:
            是否添加成功
        """
        if level not in (1, 2, 3):
            return False

        if level > 1 and not parent:
            return False

        if parent and level > 1:
            parent_level = level - 1
            parent_key = f"L{parent_level}:{parent}"
            if parent_key not in self._nodes:
                return False

        return self._add_node(level, name, description, parent)

    def categorize_concept(self, concept: str, description: str = "",
                           domain_hints: Optional[List[str]] = None) -> Dict[str, List[str]]:
        """
        给概念打分类标签

        基于概念名称和描述，自动推断其所属的 domain、type、attribute。

        Args:
            concept: 概念名称
            description: 概念描述
            domain_hints: 可选的领域提示词

        Returns:
            分类标签字典：{"domains": [...], "types": [...], "attributes": [...]}
        """
        text = f"{concept} {description}".lower()

        matched_domains = self._match_domains(text, domain_hints)
        matched_types = self._match_types(text)
        matched_attributes = self._match_attributes(text)

        return {
            "domains": matched_domains,
            "types": matched_types,
            "attributes": matched_attributes,
        }

    def _match_domains(self, text: str, hints: Optional[List[str]] = None) -> List[str]:
        """匹配领域分类"""
        scores: Dict[str, int] = {}

        domain_keywords = {
            "Animals": ["animal", "pet", "wildlife", "zoo", "species", "动物", "宠物", "物种"],
            "Anime": ["anime", "manga", "otaku", "动漫", "二次元", "漫画"],
            "Anti-Malware": ["malware", "virus", "antivirus", "恶意软件", "病毒", "杀毒"],
            "Art & Design": ["art", "design", "creative", "美学", "艺术", "设计", "创意"],
            "Authentication & Authorization": ["auth", "login", "token", "oauth", "认证", "授权", "登录"],
            "Blockchain": ["blockchain", "ledger", "smart contract", "区块链", "分布式账本", "智能合约"],
            "Books": ["book", "novel", "literature", "read", "书籍", "文学", "阅读"],
            "Business": ["business", "enterprise", "company", "management", "商业", "企业", "管理"],
            "Calendar": ["calendar", "schedule", "date", "event", "日历", "日程", "时间"],
            "Cloud Storage & File Sharing": ["cloud", "storage", "file", "share", "云存储", "文件共享"],
            "Continuous Integration": ["ci", "cd", "pipeline", "build", "持续集成", "部署"],
            "Cryptocurrency": ["crypto", "bitcoin", "ethereum", "token", "加密货币", "比特币"],
            "Currency Exchange": ["exchange", "currency", "forex", "rate", "汇率", "货币兑换"],
            "Data Validation": ["validation", "verify", "data quality", "数据验证", "数据质量"],
            "Development": ["develop", "dev", "tool", "开发", "工具"],
            "Dictionaries": ["dictionary", "word", "translate", "词典", "词汇", "翻译"],
            "Documents & Productivity": ["document", "productivity", "office", "文档", "生产力"],
            "Email": ["email", "mail", "smtp", "邮件", "电子邮件"],
            "Entertainment": ["entertainment", "fun", "leisure", "娱乐", "休闲"],
            "Environment": ["environment", "climate", "eco", "环境", "气候", "生态"],
            "Events": ["event", "ticket", "conference", "事件", "活动", "票务"],
            "Finance": ["finance", "financial", "bank", "金融", "财务", "银行"],
            "Food & Drink": ["food", "drink", "cook", "recipe", "食品", "饮料", "烹饪"],
            "Games & Comics": ["game", "comic", "gaming", "游戏", "漫画"],
            "Geocoding": ["geo", "location", "map", "address", "地理", "位置", "地图"],
            "Government": ["government", "public", "policy", "政府", "政务", "公共"],
            "Health": ["health", "medical", "medicine", "健康", "医疗", "保健"],
            "Jobs": ["job", "career", "recruit", "hiring", "工作", "招聘", "职业"],
            "Machine Learning": ["machine learning", "ml", "ai", "model", "neural", "机器学习", "人工智能"],
            "Music": ["music", "audio", "song", "音乐", "音频"],
            "News": ["news", "headline", "media", "新闻", "资讯"],
            "Open Data": ["open data", "dataset", "开放数据", "数据集"],
            "Open Source Projects": ["open source", "oss", "github", "开源", "开源项目"],
            "Patent": ["patent", "ip", "intellectual property", "专利", "知识产权"],
            "Personality": ["personality", "character", "psychology", "人格", "性格", "心理"],
            "Phone": ["phone", "call", "sms", "telephone", "电话", "通讯"],
            "Photography": ["photo", "image", "photography", "摄影", "图像", "图片"],
            "Programming": ["programming", "code", "developer", "编程", "代码", "开发"],
            "Science & Math": ["science", "math", "research", "科学", "数学", "研究"],
            "Security": ["security", "secure", "cyber", "安全", "网络安全"],
            "Shopping": ["shop", "ecommerce", "product", "购物", "电商"],
            "Social": ["social", "community", "network", "社交", "社区"],
            "Sports & Fitness": ["sports", "fitness", "exercise", "运动", "健身"],
            "Test Data": ["test data", "mock", "fixture", "测试数据", "模拟数据"],
            "Text Analysis": ["text analysis", "nlp", "text mining", "文本分析", "自然语言"],
            "Tracking": ["tracking", "monitor", "trace", "追踪", "监控"],
            "Transportation": ["transportation", "traffic", "transit", "交通", "运输"],
            "URL Shorteners": ["url shortener", "short link", "短链接"],
            "Vehicle": ["vehicle", "car", "automotive", "车辆", "汽车"],
            "Video": ["video", "streaming", "media", "视频", "流媒体"],
            "Weather": ["weather", "forecast", "climate", "天气", "气象"],
        }

        for domain, keywords in domain_keywords.items():
            score = 0
            for kw in keywords:
                if kw.lower() in text:
                    score += 1
            if score > 0:
                scores[domain] = score

        if hints:
            for hint in hints:
                if hint in DOMAINS and hint not in scores:
                    scores[hint] = scores.get(hint, 0) + 1

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [domain for domain, score in ranked if score > 0]

    def _match_types(self, text: str) -> List[str]:
        """匹配类型分类"""
        type_keywords = {
            "knowledge": ["是", "定义", "描述", "事实", "known", "knowledge", "fact", "definition"],
            "pattern": ["模式", "套路", "结构", "形态", "重复", "pattern", "structure", "repeat"],
            "principle": ["原则", "准则", "应该", "必须", "principle", "should", "must", "rule"],
            "law": ["定律", "规律", "必然", "总是", "law", "always", "inevitable", "never"],
            "paradigm": ["范式", "世界观", "框架", "认知", "paradigm", "framework", "worldview"],
        }

        scores: Dict[str, int] = {}
        for type_name, keywords in type_keywords.items():
            score = 0
            for kw in keywords:
                if kw.lower() in text:
                    score += 1
            if score > 0:
                scores[type_name] = score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [t for t, score in ranked if score > 0]

    def _match_attributes(self, text: str) -> List[str]:
        """匹配属性分类"""
        attr_keywords = {
            "verified": ["验证", "确认", "证实", "经过", "verified", "confirmed", "proven"],
            "hypothesis": ["假设", "推测", "可能", "也许", "有待", "hypothesis", "maybe", "possibly"],
            "deprecated": ["废弃", "过时", "不再使用", "deprecated", "obsolete", "legacy"],
        }

        scores: Dict[str, int] = {}
        for attr, keywords in attr_keywords.items():
            score = 0
            for kw in keywords:
                if kw.lower() in text:
                    score += 1
            if score > 0:
                scores[attr] = score

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [a for a, score in ranked if score > 0]

    def get_category_info(self, name: str, level: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """获取分类详细信息"""
        if level:
            key = f"L{level}:{name}"
            node = self._nodes.get(key)
            if node:
                return {
                    "name": node.name,
                    "level": node.level,
                    "description": node.description,
                    "parent": node.parent,
                    "children": node.children,
                }
        else:
            for lvl in range(1, 4):
                key = f"L{lvl}:{name}"
                if key in self._nodes:
                    return self.get_category_info(name, lvl)
        return None

    def list_all(self) -> Dict[int, List[Dict[str, str]]]:
        """列出所有分类"""
        result = {}
        for level in range(1, 4):
            result[level] = self.get_categories(level)
        return result

    def get_stats(self) -> Dict[str, int]:
        """获取分类统计"""
        return {
            "domain_count": len(self._level_map.get(1, [])),
            "type_count": len(self._level_map.get(2, [])),
            "attribute_count": len(self._level_map.get(3, [])),
            "total": sum(len(v) for v in self._level_map.values()),
        }


default_registry = LexiconCategoryRegistry()


def get_categories(level: int) -> List[Dict[str, str]]:
    """便捷函数：获取某一级分类"""
    return default_registry.get_categories(level)


def get_subcategories(category: str, level: Optional[int] = None) -> List[Dict[str, str]]:
    """便捷函数：获取子分类"""
    return default_registry.get_subcategories(category, level)


def add_category(level: int, name: str, description: str = "",
                 parent: Optional[str] = None) -> bool:
    """便捷函数：新增分类"""
    return default_registry.add_category(level, name, description, parent)


def categorize_concept(concept: str, description: str = "",
                       domain_hints: Optional[List[str]] = None) -> Dict[str, List[str]]:
    """便捷函数：给概念打分类标签"""
    return default_registry.categorize_concept(concept, description, domain_hints)
