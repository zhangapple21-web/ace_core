"""
ConceptFilter — 概念过滤器（文明层）

这才是真正属于 ACE 的东西。
Tokenizer 只是语言层，Filter 才是文明的判断力。

职责：
- 从分词器输出的候选词里，筛选出值得成为概念的
- 评分、排序、分类
- 结合已有词库判断相关性

不是语言问题，是文明问题。
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter


class ConceptFilter:
    """
    概念过滤器 — 文明层的判断力

    输入：Tokenizer 输出的候选词 Counter
    输出：评分排序后的概念候选列表

    这一层跟语言无关，只跟文明有关。
    换任何分词器，Filter 的逻辑都不变。
    """

    STOP_WORDS = {
        "的", "了", "是", "在", "我", "有", "和", "就", "不", "人",
        "都", "一", "上", "也", "很", "到", "说", "要", "去",
        "你", "会", "着", "没有", "看", "好", "自己", "这", "那",
        "什么", "怎么", "为什么", "因为", "所以", "但是", "如果",
        "可以", "能", "已经", "还是", "还有", "然后", "就是", "这样",
        "那样", "一些", "一下", "一样", "一起", "不过", "只是", "可能",
        "比如", "或者", "以及", "而且", "虽然", "然而", "因此",
        "其实", "当然", "真的", "非常", "特别", "比较", "更", "最",
        "今天", "明天", "昨天", "现在", "时候", "时间", "地方", "东西",
        "大家", "我们", "你们", "他们", "它们", "这些", "那些",
        "每个", "所有", "全部", "部分", "其中", "之间",
        "之后", "之前", "以上", "以下", "进行", "通过", "使用",
        "根据", "按照", "对于", "关于", "由于", "为了", "从而",
        "一定", "必须", "应该", "需要", "出来", "进去",
        "开始", "结束", "完成", "成功", "失败",
        "增加", "减少", "提高", "降低", "改变",
        "支持", "提供", "实现", "执行", "处理",
        "包括", "包含", "涉及", "相关", "对应",
        "那么", "否则", "同时", "另外",
        "文件", "目录", "路径", "数据", "系统", "代码",
        "程序", "函数", "方法", "类", "内容", "信息", "结果",
        "问题", "方式", "情况", "状态", "模式", "功能", "作用",
        "效果", "影响", "原因", "过程", "步骤", "阶段",
        "数量", "大小", "第一", "第二", "第三", "首先", "其次",
        "主要", "重要", "关键", "核心", "基础", "当前", "目前",
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could",
        "should", "may", "might", "can", "shall", "to", "of", "in", "for",
        "on", "with", "at", "by", "from", "as", "into", "through", "during",
        "before", "after", "above", "below", "between", "out", "off", "over",
        "under", "again", "further", "then", "once", "here", "there", "when",
        "where", "why", "how", "all", "both", "each", "few", "more", "most",
        "other", "some", "such", "no", "nor", "not", "only", "own", "same",
        "so", "than", "too", "very", "just", "because", "but", "and", "or",
        "if", "while", "about", "up", "down", "it", "its", "this", "that",
        "these", "those", "i", "me", "my", "we", "our", "you", "your", "he",
        "him", "his", "she", "her", "they", "them", "their", "what", "which",
        "who", "whom",
        "ns", "nt", "rn", "ar", "de", "en", "an", "la", "que", "al", "el",
        "los", "las", "un", "una", "es", "se", "por", "para", "como",
        "pero", "mas", "si", "lo", "le", "les", "te",
        "su", "sus", "tu", "tus", "mi", "mis",
        "id", "name", "type", "value", "key", "count", "total",
        "size", "status", "list", "item", "data", "time", "date", "source",
        "result", "info", "config", "setting", "option", "flag", "mode",
        "state", "path", "file", "dir", "url", "link", "image", "text",
        "content", "title", "desc", "description", "tags", "category",
        "level", "score", "rate", "ratio", "percent", "number",
        "created", "updated", "modified", "deleted", "added", "removed",
        "start", "end", "begin", "finish", "first", "last", "next", "prev",
        "new", "old", "good", "bad", "high", "low", "big", "small",
        "yes", "non",
        "co", "ng", "ps", "re", "as",
    }

    JUNK_PATTERNS = [
        (re.compile(r"^(www|com|org|net|io|cc|app|html?|htm|php|cgi)$", re.I), "url_tld"),
        (re.compile(r"^(https?|ftp|mailto|tel):", re.I), "url_protocol"),
        (re.compile(r"^[a-z]{2,3}$"), "too_short_lower_en"),
        (re.compile(r"^_[a-zA-Z0-9_]+_?$"), "json_field_pattern"),
        (re.compile(r"^[a-z]{2,7}_[a-z_]{0,3}$"), "short_snake_generic"),
        (re.compile(r"^(www|com|https|http|html?|htm|php|cgi|api|sql|yml|yaml|toml|ini|cfg|conf)$", re.I), "tech_fragment"),
        (re.compile(r"^(question|answer|title|author|date|content|tag|category|comment|reply|post)$", re.I), "forum_term"),
        (re.compile(r"^(user|username|nickname|name|first|last|email|mobile|phone|addr)$", re.I), "field_name"),
        (re.compile(r"^[\u4e00-\u9fff]{1,2}$"), "too_short_cn"),
    ]

    NAME_PREFIX_CHARS = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹"

    TECH_SUFFIXES = r"_(layer|engine|system|protocol|model|kernel|shell|root|core|node|unit|loop|chain|flow|state|event|signal|bus|port|gate|switch|router|bridge|adapter|factory|builder|context|config|strategy|policy|rule|constraint|guard|watch|hook|trigger|action|dispatch|route|parse|render|compile|execute|evaluate|validate)"

    def __init__(self, lexicon=None):
        self.lexicon = lexicon

    def filter(
        self,
        candidates: Counter,
        text: str = "",
        min_occurrence: int = 3,
        source: str = "",
    ) -> List[Dict[str, Any]]:
        """
        过滤 + 评分候选词

        输入：Tokenizer 输出的 Counter
        输出：排序后的概念候选列表 [{"name": ..., "score": ..., ...}]
        """
        valid = []
        for term, count in candidates.most_common(300):
            if count < min_occurrence:
                continue
            if not self._is_valid_term(term):
                continue
            if self.lexicon and self.lexicon.get_concept(term):
                continue
            valid.append((term, count))

        scored = self._score_candidates(valid, text, source)
        return scored

    def _is_valid_term(self, term: str) -> bool:
        term = term.strip()
        if not term:
            return False

        if len(term) < 2:
            return False

        if len(term) > 25:
            return False

        term_lower = term.lower()
        if term_lower in self.STOP_WORDS:
            return False

        for junk_re, junk_type in self.JUNK_PATTERNS:
            if junk_re.match(term):
                return False

        has_cn = bool(re.search(r"[\u4e00-\u9fff]", term))
        has_en = bool(re.search(r"[A-Za-z]", term))
        has_num = bool(re.search(r"\d", term))

        if has_cn:
            cn_chars = re.findall(r"[\u4e00-\u9fff]", term)
            if len(cn_chars) == 1:
                return False
            if len(cn_chars) >= 3:
                first_char = cn_chars[0]
                if first_char in self.NAME_PREFIX_CHARS:
                    return False

        if has_num and has_cn:
            num_count = len(re.findall(r"\d", term))
            cn_count = len(cn_chars) if has_cn else 0
            if num_count >= cn_count:
                return False

        if term.lower() in ("app", "api", "url", "css", "html", "xml", "json", "sql", "git", "ssh", "tcp", "udp", "http", "ftp", "smtp", "dns", "cdn", "seo", "sem", "cms", "erp", "crm", "saas", "paas", "iaas", "k8s", "docker", "kubernetes"):
            return False

        if re.match(r"^[a-z]+\d+$", term.lower()):
            return False

        return True

    def _score_candidates(
        self,
        valid: List[Tuple[str, int]],
        text: str,
        source: str,
    ) -> List[Dict[str, Any]]:
        scored = []
        existing_names = set()
        if self.lexicon:
            existing_names = {c["name"] for c in self.lexicon.list_concepts(limit=1000)}

        for term, count in valid:
            score = 0
            bonuses = []
            penalties = []

            score += min(count * 6, 45)
            bonuses.append(f"freq({count})={min(count*6, 45)}")

            if re.search(r"[\u4e00-\u9fff]", term):
                cn_count = len(re.findall(r"[\u4e00-\u9fff]", term))
                if 3 <= cn_count <= 6:
                    score += 12
                    bonuses.append(f"cn_len({cn_count})=12")
                elif cn_count > 6:
                    score += 5
                    bonuses.append(f"cn_len({cn_count})=5")

            if re.search(r"[A-Z][a-z]", term) and re.search(r"[a-z][A-Z]", term):
                score += 12
                bonuses.append("camel_mix=12")
            if re.search(r"[A-Z]{2,}", term) and re.search(r"[a-z]{2,}", term):
                score += 8
                bonuses.append("mixed_case=8")

            if re.search(r"[Ω∞πλμΣΔΘ∇⊕⊗∈∉∀∃]", term):
                score += 18
                bonuses.append("greek_symbol=18")
            if re.search(self.TECH_SUFFIXES, term, re.I):
                score += 10
                bonuses.append("tech_suffix=10")

            def_score = self._score_definition_context(term, text)
            if def_score > 0:
                score += def_score
                bonuses.append(f"def_ctx={def_score}")

            related_existing = sum(
                1 for e in existing_names
                if e and e in term and e != term
            ) + sum(
                1 for e in existing_names
                if e and term in e and e != term
            )
            if related_existing > 0:
                score += related_existing * 6
                bonuses.append(f"related({related_existing})={related_existing*6}")

            has_num = bool(re.search(r"\d", term))
            if has_num:
                score -= 5
                penalties.append("has_num=-5")

            scored.append({
                "name": term,
                "score": score,
                "frequency": count,
                "bonuses": bonuses,
                "penalties": penalties,
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored

    def _score_definition_context(self, term: str, text: str) -> int:
        if not text:
            return 0
        score = 0
        patterns = [
            (rf"{re.escape(term)}\s*是(一?种|一个|一类|一套|一组)", 8),
            (rf"{re.escape(term)}\s*：", 5),
            (rf"【{re.escape(term)}】", 6),
            (rf"《{re.escape(term)}》", 4),
            (rf"{re.escape(term)}\s*(?:是指|指的是|定义为|被称为|简称为)", 7),
            (rf"{re.escape(term)}\s*=\s*", 4),
        ]
        for pattern, weight in patterns:
            if re.search(pattern, text):
                score += weight
        return min(score, 20)

    def guess_category(self, term: str, text: str = "") -> str:
        """猜测概念分类 — 简单规则，以后可以扩展"""
        if re.search(r"(原则|定律|公理|规则|约束)", term):
            return "核心原则"
        if re.search(r"(架构|分层|结构|模式)", term):
            return "架构分层"
        if re.search(r"(协议|契约|合同)", term):
            return "核心协议"
        if re.search(r"(记忆|索引|存储|归档)", term):
            return "记忆模型"
        if re.search(r"(考古|发现|挖掘|出土)", term):
            return "考古发现"
        if re.search(r"(系统|运行时|引擎|内核|核心)", term):
            return "核心组件"
        if re.search(r"(治理|决策|表决)", term):
            return "治理原则"
        if re.search(r"(角色|身份|人格)", term):
            return "身份系统"
        return "待分类"
