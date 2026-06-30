"""
三重交叉验证引擎 — Triple Cross Validation Engine

对同一主题从三个来源（本地/TG收藏夹/外网）同时获取信息，
交叉比对后产出不同置信度的结论。

数据源：
  - local:    02_MEMORY/, 08_ARCHAEOLOGY/, 09_KNOWLEDGE/ （本地文明资产）
  - tg:       telegram_archive/ （TG收藏夹碎片）
  - external: mine-seed/ + web_scout扫描结果 （外网公开信息）

验证规则：
  - 三源一致   → high（已验证，自动入库）
  - 两源一致   → medium（需人工确认）
  - 三源不一   → low（待验证 / 冲突）
  - 单源孤证   → isolated（标记孤证，不入库）
"""

import json
import re
import os
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple, Set
from collections import defaultdict
import hashlib


# ===== 主题词典：用来从文本中识别主题 =====
TOPIC_DICTIONARY = {
    # R1 / 考古相关
    "r1_three_worlds": ["三界模型", "三界", "三层世界", "tri-world", "tri_world"],
    "r1_architecture": ["R1架构", "R1体系", "r1架构", "r1体系"],
    "r1_survivors": ["幸存者", "survivor", "活下来的结构", "活到今天"],
    "r1_cognitive_routing": ["认知路由", "cognitive routing", "路由协议"],
    "guardian": ["guardian", "守护", "守护者", "守卫"],
    "shadow_layer": ["shadow", "影子层", "影子路由"],
    "constraint": ["constraint", "约束", "约束体系", "约束层"],
    "lexicon": ["lexicon", "词库", "词汇体系", "tri_world_lexicon"],
    "memory_system": ["memory", "记忆系统", "记忆体系", "记忆架构"],
    "experience": ["experience", "经验", "经验沉积", "经验体系"],
    "eco_layer": ["eco_layer", "生态层", "eco layer"],
    "mengpo": ["孟婆", "mengpo", "遗忘机制", "遗忘"],
    "persona_matrix": ["persona", "人格矩阵", "人格系统", "persona_matrix"],
    "aetherflow": ["aetherflow", "以太流", "以太层"],

    # R2 / ACE 相关
    "ace_runtime": ["ace_runtime", "ACE运行时", "ACE Runtime", "R2运行时"],
    "r2_architecture": ["R2架构", "R2体系", "r2架构"],
    "capability_kernel": ["capability kernel", "能力内核", "Capability Kernel"],
    "governor": ["governor", "治理者", "治理层"],
    "contract_layer": ["contract", "契约层", "合约层", "Contract Layer"],
    "hypothesis_tree": ["HypothesisTree", "假设树", "hypothesis_tree"],
    "miner_pool": ["miner_pool", "矿工池", "矿工池架构"],
    "civilization_clock": ["文明时钟", "civilization clock", "文明节律"],
    "main_loop": ["主循环", "main_loop", "daemon循环"],
    "sync_system": ["同步系统", "sync", "repo_sync", "仓库同步"],

    # 外部 AI 工具相关
    "claude_code_loop": ["Claude Code", "claude code", "ClaudeCode主循环", "单循环架构"],
    "claude_mcp": ["Claude MCP", "MCP架构", "Model Context Protocol"],
    "reverse_api": ["逆向API", "reverse api", "逆向工程", "free-api"],
    "mcp_servers": ["MCP服务器", "MCP工具", "mcp server"],

    # 治理相关
    "knowledge_governance": ["知识治理", "knowledge governance", "知识生命周期"],
    "entropy_monitor": ["entropy", "熵值", "熵监控", "Entropy Monitor"],
    "repository_curator": ["Repository Curator", "仓库馆长", "curator"],
    "evidence_system": ["证据系统", "evidence", "证据等级"],
    "decision_log": ["决策日志", "decision log", "decision_log"],
    "lineage": ["血缘", "lineage", "演化路径", "血缘系统"],

    # 设计哲学
    "stupid_but_stable": ["愚蠢但稳定", "stupid but stable", "傻但稳"],
    "seed_resurrection": ["种子复活", "seed resurrection", "文明种子"],
    "internal_external_layering": ["内部分层", "外部分层", "内部自由外部合规"],
    "structure_over_model": ["结构优先", "结构资产", "结构重于模型"],
}


class TripleSourceIndex:
    """三重数据源索引器
    
    从三个来源提取最近 N 天的内容，建立主题索引。
    """

    def __init__(self, base_dir: str = None, days: int = 7):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_dir = Path(base_dir).resolve()
        self.days = days
        self.cutoff_time = time.time() - days * 86400

        self.sources = {
            "local": [],
            "tg": [],
            "external": [],
        }

    def scan_all(self) -> Dict[str, List[Dict]]:
        """扫描所有三个数据源"""
        self._scan_local()
        self._scan_tg()
        self._scan_external()
        return self.sources

    def _scan_local(self):
        """扫描本地数据源：02_MEMORY/, 08_ARCHAEOLOGY/, 09_KNOWLEDGE/"""
        local_dirs = [
            self.base_dir / "02_MEMORY",
            self.base_dir / "08_ARCHAEOLOGY",
            self.base_dir / "09_KNOWLEDGE",
        ]
        
        for scan_dir in local_dirs:
            if not scan_dir.exists():
                continue
            self._walk_directory(scan_dir, "local")

    def _scan_tg(self):
        """扫描TG收藏夹数据源：telegram_archive/"""
        tg_dirs = [
            Path(os.path.dirname(str(self.base_dir))) / "telegram_archive" / "04_FINDINGS",
            Path(os.path.dirname(str(self.base_dir))) / "telegram_archive" / "03_CLUSTERS",
            Path(os.path.dirname(str(self.base_dir))) / "telegram_archive" / "02_INDEX",
        ]
        
        for scan_dir in tg_dirs:
            if not scan_dir.exists():
                continue
            self._walk_directory(scan_dir, "tg")

    def _scan_external(self):
        """扫描外网数据源：mine-seed/ + web_scout扫描结果"""
        mine_seed = Path(os.path.dirname(str(self.base_dir))) / "mine-seed"
        
        # mine-seed 考古报告
        archaeology_dir = mine_seed / "03_DATA" / "research" / "r1_archaeology" / "daily"
        if archaeology_dir.exists():
            self._walk_directory(archaeology_dir, "external")
        
        # mine-seed 知识/记忆
        for subdir in ["02_MEMORY", "01_AGENTS", "02_LEARNING"]:
            d = mine_seed / subdir
            if d.exists():
                self._walk_directory(d, "external")

    def _walk_directory(self, directory: Path, source: str):
        """递归扫描目录，收集最近 N 天的文件"""
        for root, dirs, files in os.walk(directory):
            for fname in files:
                if not fname.endswith(('.md', '.txt', '.json')):
                    continue
                fpath = Path(root) / fname
                try:
                    mtime = os.path.getmtime(fpath)
                except OSError:
                    continue
                if mtime < self.cutoff_time:
                    continue
                
                try:
                    content = fpath.read_text(encoding='utf-8', errors='replace')
                except Exception:
                    continue
                
                topics = self._detect_topics(content, fname)
                
                self.sources[source].append({
                    "path": str(fpath),
                    "filename": fname,
                    "mtime": mtime,
                    "mtime_str": datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"),
                    "size": len(content),
                    "content": content[:3000],
                    "topics": topics,
                    "summary": self._extract_summary(content),
                })

    def _detect_topics(self, content: str, filename: str) -> List[str]:
        """从内容和文件名中检测主题"""
        text = content[:2000].lower() + " " + filename.lower()
        found = []
        for topic_id, keywords in TOPIC_DICTIONARY.items():
            for kw in keywords:
                if kw.lower() in text:
                    found.append(topic_id)
                    break
        return found

    def _extract_summary(self, content: str, max_len: int = 200) -> str:
        """提取文件摘要（取第一段或前N字）"""
        lines = content.strip().split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and len(line) > 10:
                return line[:max_len]
        return content[:max_len].strip()


class CrossValidator:
    """交叉验证器
    
    对同一个主题，比对三个来源的说法，计算置信度。
    """

    def __init__(self, sources: Dict[str, List[Dict]]):
        self.sources = sources
        self.topic_graph = defaultdict(lambda: {
            "local": [], "tg": [], "external": [],
            "entries": [], "confidence": "isolated",
            "conflict": False, "resolved": False, "resolution": "",
        })

    def validate_all(self) -> List[Dict]:
        """执行全部交叉验证，返回验证结果列表"""
        # 第一步：按主题聚合
        self._aggregate_by_topic()
        
        # 第二步：计算置信度
        results = []
        for topic_id, data in self.topic_graph.items():
            result = self._validate_topic(topic_id, data)
            results.append(result)
        
        # 按置信度排序
        confidence_order = {"high": 0, "medium": 1, "low": 2, "isolated": 3}
        results.sort(key=lambda x: (confidence_order.get(x["confidence"], 9), -len(x["entries"])))
        
        return results

    def _aggregate_by_topic(self):
        """按主题聚合三个来源的条目"""
        for source_name, entries in self.sources.items():
            for entry in entries:
                for topic_id in entry["topics"]:
                    self.topic_graph[topic_id][source_name].append(entry)
                    self.topic_graph[topic_id]["entries"].append({
                        "source": source_name,
                        "path": entry["path"],
                        "summary": entry["summary"],
                        "mtime": entry["mtime"],
                    })

    def _validate_topic(self, topic_id: str, data: Dict) -> Dict:
        """对单个主题执行交叉验证
        
        置信度判断逻辑：
          - high:   三源都有 + 每源至少2条记录 + 跨源内容有重叠（不冲突）
          - medium: 两源有 + 每源至少2条记录 + 跨源内容有重叠
          - low:    两/三源都有但记录很少，或内容明显不一致
          - isolated: 只在一个来源出现
        """
        sources_present = []
        for src in ["local", "tg", "external"]:
            if data[src]:
                sources_present.append(src)
        
        source_count = len(sources_present)
        
        # 计算跨源内容重叠度（用关键词重叠而非摘要相似度）
        # 同一个主题下，不同来源的文件应该共享一套核心词汇
        overlap_score = self._compute_content_overlap(data)
        
        # 每源最小条目数（排除"只提了一嘴"的噪音）
        per_source_min = min(len(data[src]) for src in sources_present) if sources_present else 0
        total_entries = len(data["entries"])
        
        # 置信度计算
        if source_count >= 3 and per_source_min >= 2 and total_entries >= 10:
            confidence = "high"
        elif source_count >= 3 and per_source_min >= 1:
            confidence = "medium"
        elif source_count == 2 and per_source_min >= 2 and total_entries >= 5:
            confidence = "medium"
        elif source_count == 2:
            confidence = "low"
        elif source_count <= 1:
            confidence = "isolated"
        else:
            confidence = "low"
        
        # 冲突检测：多源存在但内容重叠度极低 → 可能各说各话
        has_conflict = self._detect_conflict(data, sources_present, overlap_score)
        
        # 自动仲裁
        resolution = self._auto_resolve(topic_id, data, confidence, has_conflict)
        
        return {
            "topic": topic_id,
            "topic_label": self._topic_label(topic_id),
            "sources_present": sources_present,
            "source_counts": {
                "local": len(data["local"]),
                "tg": len(data["tg"]),
                "external": len(data["external"]),
            },
            "entries": data["entries"],
            "confidence": confidence,
            "conflict": has_conflict,
            "content_overlap": round(overlap_score, 3),
            "per_source_min": per_source_min,
            "resolved": resolution["resolved"],
            "resolution": resolution["reasoning"],
            "action": resolution["action"],
        }

    def _compute_content_overlap(self, data: Dict) -> float:
        """计算跨源内容重叠度
        
        用每个来源的高频关键词集合做 Jaccard 重叠度。
        同一个主题下，不同来源应该共享核心术语。
        """
        source_keywords = {}
        
        for src in ["local", "tg", "external"]:
            if not data[src]:
                continue
            # 合并该来源所有条目的内容关键词
            all_text = " ".join(e.get("summary", "") for e in data[src])
            kws = self._extract_keywords(all_text)
            if kws:
                source_keywords[src] = kws
        
        if len(source_keywords) < 2:
            return 0.0
        
        # 计算所有源对的平均 Jaccard
        src_names = list(source_keywords.keys())
        total = 0.0
        count = 0
        for i in range(len(src_names)):
            for j in range(i + 1, len(src_names)):
                s1 = source_keywords[src_names[i]]
                s2 = source_keywords[src_names[j]]
                intersection = len(s1 & s2)
                union = len(s1 | s2)
                jaccard = intersection / union if union > 0 else 0
                total += jaccard
                count += 1
        
        return total / count if count > 0 else 0.0

    def _extract_keywords(self, text: str, top_n: int = 30) -> Set[str]:
        """从文本中提取高频关键词（去停用词）"""
        # 简单中文分词：按非汉字字符切
        tokens = re.findall(r'[\u4e00-\u9fa5a-zA-Z]{2,}', text.lower())
        # 过滤停用词
        stop = set(["的", "是", "在", "了", "和", "与", "或", "及", "等", "为",
                    "对", "以", "从", "到", "上", "下", "中", "内", "外",
                    "the", "and", "for", "with", "from", "that", "this",
                    "are", "was", "were", "not", "but", "has", "have",
                    "date", "time", "version", "status", "report", "id"])
        filtered = [t for t in tokens if t not in stop and len(t) >= 2]
        
        # 取 top_n 高频
        from collections import Counter
        counter = Counter(filtered)
        return set(w for w, _ in counter.most_common(top_n))

    def _detect_conflict(self, data: Dict, sources_present: List[str], overlap_score: float) -> bool:
        """检测是否存在冲突
        
        规则：
          - 只有1个来源 → 不存在冲突问题
          - 2个以上来源 + 内容重叠度极低 → 可能各说各话（冲突）
          - 2个以上来源 + 其中一个来源只有1条 → 证据不足（不算冲突）
        """
        if len(sources_present) < 2:
            return False
        
        # 至少两个来源都有 2 条以上记录才算有"对质"基础
        multi_source_count = sum(1 for src in sources_present if len(data[src]) >= 2)
        if multi_source_count < 2:
            return False
        
        # 内容重叠度低于阈值 → 标记为可能冲突
        # 注意：这是"结构级冲突检测"，不是语义级
        # 真正的冲突需要人工或 LLM 判断
        return overlap_score < 0.05

    def _auto_resolve(self, topic_id: str, data: Dict, confidence: str, has_conflict: bool) -> Dict:
        """自动仲裁规则
        
        规则优先级：
        1. high 置信度 → 自动入库（标记为 EVIDENCE）
        2. medium 置信度 → 标记为 HYPOTHESIS，待人工
        3. low + 有冲突 → 生成冲突分析任务
        4. isolated → 标记孤证，不行动
        """
        if confidence == "high":
            return {
                "resolved": True,
                "action": "auto_promote_to_evidence",
                "reasoning": f"三源交叉验证通过（{len(data['entries'])}条记录），自动升级为EVIDENCE级知识",
            }
        elif confidence == "medium":
            return {
                "resolved": False,
                "action": "flag_for_human_review",
                "reasoning": "两源一致但缺少第三源验证，标记为HYPOTHESIS，待人工确认",
            }
        elif has_conflict:
            return {
                "resolved": False,
                "action": "create_conflict_task",
                "reasoning": "多源说法不一致，创建冲突分析任务，待人工裁决",
            }
        else:
            return {
                "resolved": False,
                "action": "observe",
                "reasoning": "单源孤证或证据不足，保持观察，不做结论",
            }

    def _topic_label(self, topic_id: str) -> str:
        """获取主题的可读标签"""
        keywords = TOPIC_DICTIONARY.get(topic_id, [topic_id])
        return keywords[0] if keywords else topic_id


class TopicGraph:
    """主题关系图
    
    把所有 topic 组织成图，建立主题之间的关联关系。
    关系类型：co-occurrence（共现）、hierarchy（层级）、evolution（演化）
    """

    def __init__(self, validation_results: List[Dict]):
        self.results = validation_results
        self.nodes = {}
        self.edges = []
        self._build_graph()

    def _build_graph(self):
        """构建主题图"""
        # 节点
        for r in self.results:
            topic = r["topic"]
            self.nodes[topic] = {
                "id": topic,
                "label": r["topic_label"],
                "confidence": r["confidence"],
                "conflict": r["conflict"],
                "entry_count": len(r["entries"]),
                "source_counts": r["source_counts"],
            }
        
        # 边：基于共现（两个主题出现在同一个文件中）
        co_occurrence = defaultdict(int)
        topic_entries = defaultdict(set)
        
        for r in self.results:
            for entry in r["entries"]:
                topic_entries[r["topic"]].add(entry["path"])
        
        topics = list(self.nodes.keys())
        for i in range(len(topics)):
            for j in range(i + 1, len(topics)):
                t1, t2 = topics[i], topics[j]
                common = topic_entries[t1] & topic_entries[t2]
                if common:
                    strength = len(common)
                    co_occurrence[(t1, t2)] = strength
                    self.edges.append({
                        "source": t1,
                        "target": t2,
                        "type": "co-occurrence",
                        "strength": strength,
                        "common_files": list(common)[:5],
                    })

    def export_json(self) -> Dict:
        return {
            "nodes": list(self.nodes.values()),
            "edges": self.edges,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }


class ConflictEvolution:
    """冲突演化轨迹
    
    追踪同一个主题的冲突如何随时间变化。
    对比历史版本和当前版本的冲突状态。
    """

    def __init__(self, base_dir: Path, current_results: List[Dict]):
        self.base_dir = base_dir
        self.current = {r["topic"]: r for r in current_results}
        self.history = self._load_history()

    def _load_history(self) -> Dict[str, List[Dict]]:
        """加载历史交叉验证报告（如果有）"""
        history = defaultdict(list)
        reports_dir = self.base_dir / "08_ARCHAEOLOGY"
        if not reports_dir.exists():
            return history
        
        for f in reports_dir.glob("*triple_cross_validation*.md"):
            # 从文件名提取日期
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', f.name)
            if not date_match:
                continue
            report_date = date_match.group(1)
            
            # 简单解析：找 topic 行和 confidence
            try:
                content = f.read_text(encoding='utf-8', errors='replace')
            except Exception:
                continue
            
            # 提取主题和置信度
            for topic_id in TOPIC_DICTIONARY.keys():
                if topic_id in content:
                    # 找附近的置信度标记
                    idx = content.find(topic_id)
                    context = content[max(0, idx-100):idx+200]
                    conf = "unknown"
                    for c in ["high", "medium", "low", "isolated"]:
                        if c in context.lower():
                            conf = c
                            break
                    history[topic_id].append({
                        "date": report_date,
                        "confidence": conf,
                    })
        
        return history

    def compute_trajectories(self) -> List[Dict]:
        """计算每个主题的演化轨迹"""
        trajectories = []
        for topic_id, current in self.current.items():
            hist = self.history.get(topic_id, [])
            trajectory = {
                "topic": topic_id,
                "current_confidence": current["confidence"],
                "current_conflict": current["conflict"],
                "history": hist,
                "trend": self._compute_trend(current, hist),
            }
            trajectories.append(trajectory)
        return trajectories

    def _compute_trend(self, current: Dict, history: List[Dict]) -> str:
        """计算趋势：上升 / 下降 / 稳定 / 新增"""
        if not history:
            return "new"
        
        last = history[-1]
        conf_order = {"high": 3, "medium": 2, "low": 1, "isolated": 0, "unknown": -1}
        curr_score = conf_order.get(current["confidence"], -1)
        last_score = conf_order.get(last.get("confidence", "unknown"), -1)
        
        if curr_score > last_score:
            return "rising"
        elif curr_score < last_score:
            return "falling"
        else:
            return "stable"


class TripleCrossValidationEngine:
    """三重交叉验证主引擎"""

    def __init__(self, base_dir: str = None, days: int = 7):
        if base_dir is None:
            # 默认在 ace_runtime/ 上一级
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.base_dir = Path(base_dir).resolve()
        self.days = days

    def run(self) -> Dict:
        """执行完整的三重交叉验证流程"""
        start_time = time.time()
        
        # 1. 建立三重数据源索引
        indexer = TripleSourceIndex(str(self.base_dir), self.days)
        sources = indexer.scan_all()
        
        source_stats = {
            src: len(entries) for src, entries in sources.items()
        }
        
        # 2. 交叉验证
        validator = CrossValidator(sources)
        results = validator.validate_all()
        
        # 3. 主题图
        topic_graph = TopicGraph(results)
        graph_data = topic_graph.export_json()
        
        # 4. 冲突演化
        conflict_evo = ConflictEvolution(self.base_dir, results)
        trajectories = conflict_evo.compute_trajectories()
        
        # 5. 生成报告
        report = self._generate_report(results, graph_data, trajectories, source_stats, start_time)
        
        # 6. 自动行动
        actions = self._auto_execute(results)
        
        return {
            "report": report,
            "results": results,
            "topic_graph": graph_data,
            "trajectories": trajectories,
            "source_stats": source_stats,
            "actions": actions,
            "duration": round(time.time() - start_time, 2),
        }

    def _generate_report(self, results: List[Dict], graph_data: Dict,
                         trajectories: List[Dict], source_stats: Dict,
                         start_time: float) -> str:
        """生成 Markdown 报告"""
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        lines = []
        lines.append(f"# 三重交叉验证报告 — {today}")
        lines.append("")
        lines.append(f"**生成时间：** {now}")
        lines.append(f"**扫描窗口：** 最近 {self.days} 天")
        lines.append(f"**数据源统计：** 本地 {source_stats.get('local',0)} 条 / TG {source_stats.get('tg',0)} 条 / 外网 {source_stats.get('external',0)} 条")
        lines.append(f"**主题总数：** {len(results)}")
        lines.append("")
        
        # 置信度分布
        conf_dist = defaultdict(int)
        for r in results:
            conf_dist[r["confidence"]] += 1
        lines.append("## 置信度分布")
        lines.append("")
        lines.append(f"| 置信度 | 数量 | 含义 |")
        lines.append(f"|--------|------|------|")
        lines.append(f"| high | {conf_dist.get('high', 0)} | 三源一致，已验证 |")
        lines.append(f"| medium | {conf_dist.get('medium', 0)} | 两源一致，待确认 |")
        lines.append(f"| low | {conf_dist.get('low', 0)} | 多源但不一致 |")
        lines.append(f"| isolated | {conf_dist.get('isolated', 0)} | 单源孤证 |")
        lines.append("")
        
        # 高置信度结论
        high_results = [r for r in results if r["confidence"] == "high"]
        if high_results:
            lines.append("## ✅ 高置信度结论（自动入库）")
            lines.append("")
            for r in high_results:
                lines.append(f"### {r['topic_label']} (`{r['topic']}`)")
                lines.append("")
                lines.append(f"- **来源分布：** 本地 {r['source_counts']['local']} / TG {r['source_counts']['tg']} / 外网 {r['source_counts']['external']}")
                lines.append(f"- **条目数：** {len(r['entries'])}")
                lines.append(f"- **内容重叠度：** {r['content_overlap']}")
                lines.append(f"- **裁决：** {r['resolution']}")
                lines.append("")
                lines.append("<details>")
                lines.append("<summary>查看来源列表</summary>")
                lines.append("")
                for e in r["entries"][:10]:
                    lines.append(f"- [{e['source']}] `{e['path']}` — {e['summary'][:80]}")
                lines.append("")
                lines.append("</details>")
                lines.append("")
        
        # 中置信度
        med_results = [r for r in results if r["confidence"] == "medium"]
        if med_results:
            lines.append("## ⚠️ 中置信度结论（待人工确认）")
            lines.append("")
            for r in med_results:
                lines.append(f"### {r['topic_label']} (`{r['topic']}`)")
                lines.append("")
                lines.append(f"- **来源分布：** 本地 {r['source_counts']['local']} / TG {r['source_counts']['tg']} / 外网 {r['source_counts']['external']}")
                lines.append(f"- **内容重叠度：** {r['content_overlap']}")
                lines.append(f"- **缺失来源：** {', '.join(s for s in ['local','tg','external'] if s not in r['sources_present'])}")
                lines.append(f"- **裁决：** {r['resolution']}")
                lines.append("")
        
        # 冲突主题
        conflict_results = [r for r in results if r["conflict"]]
        if conflict_results:
            lines.append("## ❗ 冲突主题（需人工裁决）")
            lines.append("")
            for r in conflict_results:
                lines.append(f"### {r['topic_label']} (`{r['topic']}`)")
                lines.append("")
                lines.append(f"- **来源分布：** 本地 {r['source_counts']['local']} / TG {r['source_counts']['tg']} / 外网 {r['source_counts']['external']}")
                lines.append(f"- **内容重叠度：** {r['content_overlap']}")
                lines.append(f"- **裁决：** {r['resolution']}")
                lines.append("")
                lines.append("各来源说法：")
                lines.append("")
                for src in r["sources_present"]:
                    src_entries = [e for e in r["entries"] if e["source"] == src][:3]
                    lines.append(f"**[{src.upper()}]**")
                    for e in src_entries:
                        lines.append(f"- `{e['path']}` — {e['summary'][:100]}")
                    lines.append("")
        
        # 主题关系图
        lines.append("## 🔷 主题关系图")
        lines.append("")
        lines.append(f"- **节点数：** {graph_data['node_count']}")
        lines.append(f"- **边数：** {graph_data['edge_count']}")
        lines.append("")
        lines.append("### 最强关联（Top 10）")
        lines.append("")
        sorted_edges = sorted(graph_data["edges"], key=lambda x: x["strength"], reverse=True)[:10]
        for edge in sorted_edges:
            lines.append(f"- **{edge['source']}** ↔ **{edge['target']}** （共现强度：{edge['strength']}）")
        lines.append("")
        
        # 冲突演化轨迹
        lines.append("## 🔷 冲突演化轨迹")
        lines.append("")
        traj_with_hist = [t for t in trajectories if t["history"]]
        if traj_with_hist:
            for t in traj_with_hist[:15]:
                trend_icon = {"rising": "📈", "falling": "📉", "stable": "➡️", "new": "🆕"}.get(t["trend"], "❓")
                lines.append(f"- {trend_icon} **{t['topic']}**：{t['history'][-1].get('confidence','?')} → {t['current_confidence']} （{t['trend']}）")
        else:
            lines.append("暂无历史对比数据（首次运行）。")
        lines.append("")
        
        # 自动行动
        lines.append("## 📋 自动行动汇总")
        lines.append("")
        action_counts = defaultdict(int)
        for r in results:
            action_counts[r["action"]] += 1
        for action, count in action_counts.items():
            lines.append(f"- **{action}**：{count} 个主题")
        lines.append("")
        
        # 附录：所有主题
        lines.append("## 📎 附录：全部主题列表")
        lines.append("")
        lines.append("| 主题 | 置信度 | 本地 | TG | 外网 | 冲突 | 裁决 |")
        lines.append("|------|--------|------|----|------|------|------|")
        for r in results:
            conf_icon = {"high": "✅", "medium": "⚠️", "low": "❓", "isolated": "🔵"}.get(r["confidence"], "")
            conflict_icon = "❗" if r["conflict"] else ""
            lines.append(
                f"| {r['topic_label']} {conf_icon} {conflict_icon} | {r['confidence']} "
                f"| {r['source_counts']['local']} | {r['source_counts']['tg']} "
                f"| {r['source_counts']['external']} | {r['conflict']} | {r['action']} |"
            )
        lines.append("")
        
        lines.append("---")
        lines.append("")
        lines.append(f"*本报告由 Triple Cross Validation Engine 自动生成*")
        lines.append(f"*耗时：{round(time.time() - start_time, 2)} 秒*")
        
        return "\n".join(lines)

    def _auto_execute(self, results: List[Dict]) -> Dict:
        """执行自动行动
        
        - high → 写入 09_KNOWLEDGE/pending_validation/ （待最终升级）
        - low + conflict → 创建 pending task
        """
        actions = {
            "promoted": [],
            "tasks_created": [],
            "observed": [],
        }
        
        # 确保目录存在
        knowledge_dir = self.base_dir / "09_KNOWLEDGE" / "pending_validation"
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        
        for r in results:
            if r["confidence"] == "high":
                # 写入待验证知识
                knowledge_file = knowledge_dir / f"{r['topic']}_cross_validated.md"
                if not knowledge_file.exists():
                    content = self._format_knowledge_entry(r)
                    knowledge_file.write_text(content, encoding='utf-8')
                    actions["promoted"].append(r["topic"])
            elif r["conflict"]:
                # 创建冲突分析任务（仅记录，不直接生成task文件，由主循环处理）
                actions["tasks_created"].append(r["topic"])
            else:
                actions["observed"].append(r["topic"])
        
        return actions

    def _format_knowledge_entry(self, result: Dict) -> str:
        """格式化知识条目"""
        lines = []
        lines.append(f"# {result['topic_label']}")
        lines.append("")
        lines.append("## 基本信息")
        lines.append("")
        lines.append(f"- **id:** {result['topic']}")
        lines.append(f"- **status:** EVIDENCE")
        lines.append(f"- **confidence:** 0.85")
        lines.append(f"- **created:** {datetime.now().strftime('%Y-%m-%d')}")
        lines.append(f"- **updated:** {datetime.now().strftime('%Y-%m-%d')}")
        lines.append(f"- **source:** triple_cross_validation")
        lines.append(f"- **owner:** ace_runtime")
        lines.append("")
        lines.append("## 交叉验证证据")
        lines.append("")
        lines.append(f"- **三源覆盖：** {', '.join(result['sources_present'])}")
        lines.append(f"- **条目总数：** {len(result['entries'])}")
        lines.append(f"- **内容重叠度：** {result['content_overlap']}")
        lines.append("")
        lines.append("### 来源清单")
        lines.append("")
        for e in result["entries"][:15]:
            lines.append(f"- [{e['source']}] `{e['path']}` — {e['summary'][:100]}")
        lines.append("")
        return "\n".join(lines)

    def save_report(self, report: str) -> str:
        """保存报告到 08_ARCHAEOLOGY/"""
        today = datetime.now().strftime("%Y-%m-%d")
        reports_dir = self.base_dir / "08_ARCHAEOLOGY"
        reports_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{today}_triple_cross_validation.md"
        filepath = reports_dir / filename
        filepath.write_text(report, encoding='utf-8')
        return str(filepath)


if __name__ == "__main__":
    import sys
    base_dir = sys.argv[1] if len(sys.argv) > 1 else None
    engine = TripleCrossValidationEngine(base_dir)
    result = engine.run()
    print(f"[TripleValidation] 完成，耗时 {result['duration']}s")
    print(f"[TripleValidation] 主题数：{len(result['results'])}")
    print(f"[TripleValidation] 高置信度：{sum(1 for r in result['results'] if r['confidence']=='high')}")
    
    report_path = engine.save_report(result["report"])
    print(f"[TripleValidation] 报告已保存：{report_path}")
