"""
概念提取引擎 v2 — 词库的自动生长机制

从挖到的材料中提取新概念，判断是否值得加入词库，
分类、关联、排序，然后加入词库。

v2 升级：强化过滤、低质量词识别、上下文模式感知。
"""

import re
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from collections import Counter, defaultdict


class ConceptMiner:
    """概念提取引擎 v2"""

    CN_TERM_PATTERN = re.compile(r"[\u4e00-\u9fffA-Za-z0-9_Ω∞πλμ]+")

    DEFINITION_PATTERNS = [
        (r"(?<!\w)([\u4e00-\u9fffA-Za-z0-9_Ω∞]{2,15})是(一?种|一个|一类|一套|一组|一套)", "is_a"),
        (r"(?<!\w)([\u4e00-\u9fffA-Za-z0-9_Ω∞]{2,15})：", "colon_def"),
        (r"【([\u4e00-\u9fffA-Za-z0-9_Ω∞]{2,15})】", "bracket_def"),
        (r"《([\u4e00-\u9fffA-Za-z0-9_Ω∞]{2,15})》", "booktitle_def"),
        (r"(?<!\w)([\u4e00-\u9fffA-Za-z0-9_Ω∞]{2,15})\s*(?:是指|指的是|定义为|被称为|简称为|又叫)", "meta_def"),
        (r"(?<!\w)([\u4e00-\u9fffA-Za-z0-9_Ω∞]{2,15})\s*=\s*", "assign_def"),
        (r"^\s*([\u4e00-\u9fffA-Za-z0-9_Ω∞]{2,15})\s*$", "isolated_line"),
    ]

    CONTEXT_PATTERNS = [
        (r"([A-Z][a-z]+(?:[A-Z][a-z]+)+)", "camel_case"),
        (r"\b([A-Z]{2,})\b", "all_caps"),
        (r"\b([a-z]+_[a-z_]+)\b", "snake_case"),
        (r"(?<!\w)([\u4e00-\u9fff]{2,8})(?:原则|机制|模式|理论|定律|架构|系统|协议)", "domain_suffix"),
        (r"(?:原则|机制|模式|理论|定律|架构|系统|协议)([\u4e00-\u9fff]{2,8})(?!\w)", "domain_prefix"),
    ]

    _STOP_WORDS = {
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
    }

    JUNK_PATTERNS = [
        (re.compile(r"^(www|com|org|net|io|cc|app|html?|htm|php|cgi)$", re.I), "url_tld"),
        (re.compile(r"^(https?|ftp|mailto|tel):", re.I), "url_protocol"),
        (re.compile(r"^(qq|wechat|wx|wb|zhihu|bilibili|douyin|xiaohongshu)$", re.I), "app_name"),
        (re.compile(r"[\u4e00-\u9fff]*(?:微|guan|号|号|号|号)(?:信|众)?$", re.I), "social_media"),
        (re.compile(r"^(.+?)\d{1,2}$"), "trailing_number"),
        (re.compile(r"^\d{1,2}(.+?)$"), "leading_number"),
        (re.compile(r"^(中午|下午|上午|早上|晚上|凌晨|上午)\d{1,2}$"), "time_of_day"),
        (re.compile(r"^(20|19)\d{2}年$"), "year_only"),
        (re.compile(r"^\d{1,2}月$"), "month_only"),
        (re.compile(r"^\d{1,2}日$"), "day_only"),
        (re.compile(r"^(周|星期)[一二三四五六日]$"), "weekday"),
        (re.compile(r"^[\u4e00-\u9fff]{1,2}$"), "too_short_cn"),
        (re.compile(r"^[a-z]\.[a-z]\.$", re.I), "initial_abbr"),
        (re.compile(r"^(www|com|https|http|html?|htm|php|cgi|api|sql|yml|yaml|toml|ini|cfg|conf)$", re.I), "tech_fragment"),
        (re.compile(r"^(question|answer|title|author|date|content|tag|category|comment|reply|post)$", re.I), "forum_term"),
        (re.compile(r"^(user|username|nickname|name|first|last|email|mobile|phone|addr)$", re.I), "field_name"),
    ]

    NAME_PREFIX_CHARS = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳酆鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹"

    def __init__(self, lexicon):
        self.lexicon = lexicon
        self._discovery_cache = []
        self._name_chars = set(self.NAME_PREFIX_CHARS)

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

        candidates = self._extract_candidates(text)
        filtered = self._filter_candidates(candidates, min_occurrence)
        scored = self._score_candidates(filtered, text, source)

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
        }

    def _extract_candidates(self, text: str) -> Counter:
        candidates = Counter()

        for pattern, ptype in self.DEFINITION_PATTERNS:
            matches = re.findall(pattern, text)
            for m in matches:
                term = m if isinstance(m, str) else m[0]
                term = term.strip()
                weight = 8 if ptype in ("is_a", "meta_def", "colon_def", "bracket_def") else 3
                if self._is_valid_term(term):
                    candidates[term] += weight

        for pattern, ptype in self.CONTEXT_PATTERNS:
            matches = re.findall(pattern, text)
            for m in matches:
                term = m if isinstance(m, str) else m[0]
                term = term.strip()
                weight = 5 if ptype in ("camel_case", "snake_case", "domain_suffix", "domain_prefix") else 3
                if self._is_valid_term(term):
                    candidates[term] += weight

        words = self.CN_TERM_PATTERN.findall(text)
        for w in words:
            if self._is_valid_term(w):
                candidates[w] += 1

        return candidates

    def _is_valid_term(self, term: str) -> bool:
        term = term.strip()
        if not term:
            return False

        if len(term) < 2:
            return False

        if len(term) > 25:
            return False

        term_lower = term.lower()
        if term_lower in self._STOP_WORDS:
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
                if first_char in self._name_chars:
                    return False

        if has_num and has_cn:
            num_count = len(re.findall(r"\d", term))
            cn_count = len(cn_chars) if has_cn else 0
            if num_count >= cn_count:
                return False

        if term.lower() in ("app", "api", "url", "css", "html", "xml", "json", "sql", "git", "ssh", "tcp", "udp", "http", "ftp", "smtp", "dns", "cdn", "cdn", "seo", "sem", "cms", "erp", "crm", "saas", "paas", "iaas", "k8s", "docker", "kubernetes"):
            return False

        if re.match(r"^[a-z]+\d+$", term.lower()):
            return False

        return True

    def _filter_candidates(
        self,
        candidates: Counter,
        min_occurrence: int,
    ) -> List[Tuple[str, int]]:
        filtered = []
        for term, count in candidates.most_common(300):
            if count < min_occurrence:
                continue
            if self.lexicon.get_concept(term):
                continue
            if not self._is_valid_term(term):
                continue
            filtered.append((term, count))
        return filtered

    def _score_candidates(
        self,
        filtered: List[Tuple[str, int]],
        text: str,
        source: str,
    ) -> List[Dict[str, Any]]:
        scored = []
        existing_names = {c["name"] for c in self.lexicon.list_concepts(limit=1000)}

        for term, count in filtered:
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
            if re.search(r"_(layer|engine|system|protocol|model|kernel|shell|root|core|node|unit|loop|chain|flow|state|event|signal|bus|port|gate|switch|router|bridge|adapter|factory|builder|context|config|strategy|policy|rule|constraint|guard|watch|hook|trigger|action|dispatch|route|parse|render|compile|execute|evaluate|validate)", term, re.I):
                score += 10
                bonuses.append("tech_suffix=10")

            definition_score = self._score_definition_context(term, text)
            if definition_score > 0:
                score += definition_score
                bonuses.append(f"def_ctx={definition_score}")

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
                penalties.append("has_number")
                score -= 8

            if re.match(r"^[a-z]+\d+$", term.lower()):
                penalties.append("alpha_number_suffix")
                score -= 15

            domain_suffixes = ["原则", "机制", "模式", "理论", "定律", "架构", "系统", "协议", "规范", "标准", "约束", "策略", "策略", "流程", "路径", "回路", "循环"]
            if any(term.endswith(s) or term.startswith(s) for s in domain_suffixes):
                score += 8
                bonuses.append("domain_term=8")

            if "_" in term or "-" in term:
                score += 4

            domain_terms = {"layer", "engine", "system", "protocol", "model", "kernel", "shell", "root", "core", "node", "bus", "port", "gate", "switch", "router", "bridge", "factory", "builder", "context", "config", "strategy", "policy", "rule", "constraint", "guard", "watch", "hook", "trigger", "action", "dispatch", "route", "parse", "render", "compile", "execute", "evaluate", "validate", "registry", "factory", "pool", "queue", "stack", "cache", "store", "index", "parser", "loader", "binder", "resolver", "connector", "adapter", "filter", "mapper", "reducer", "pipeline", "stream", "buffer", "channel", "actor", "agent", "worker", "client", "server", "host", "peer", "peer", "leader", "follower", "candidate", "replica"}
            term_lower = term.lower()
            for dt in domain_terms:
                if term_lower.endswith(dt) or term_lower.startswith(dt):
                    score += 3
                    bonuses.append(f"tech_word({dt})=3")
                    break

            context_window = self._get_context_window(text, term)

            scored.append({
                "name": term,
                "count": count,
                "score": max(0, min(score, 100)),
                "context": context_window[:300] if context_window else "",
                "source": source,
                "_bonuses": bonuses,
                "_penalties": penalties,
            })

        return sorted(scored, key=lambda x: -x["score"])

    def _score_definition_context(self, term: str, text: str) -> int:
        score = 0
        window = text[:5000]
        idx = window.find(term)
        if idx < 0:
            return 0

        for lookback in range(max(0, idx - 60), idx):
            chunk = window[lookback:idx + len(term) + 30]
            if any(p in chunk for p in ["是", "指", "定义", "称为", "名叫", "简称", "又叫"]):
                score += 15
                break
            if re.match(r"^\s*[\u4e00-\u9fff：:【】《》]", chunk):
                score += 12
                break

        for lookahead in range(idx, min(len(window), idx + 80)):
            chunk = window[idx:lookahead + 1]
            if any(p in chunk for p in ["：", "：", "【", "《", "=", "→"]):
                score += 10
                break

        return score

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
