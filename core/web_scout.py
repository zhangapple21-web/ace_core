"""
外网学习模块（Web Scout）

结构核版本 — 去叙事化，state 为唯一真源。

设计原则：
- 只返回结构化数据，不输出执行日志
- state 是唯一真源（single source of truth）
- 执行接口（scout）和描述接口（describe）分离
- 失败不阻塞，静默记录到 state.errors
"""

import json
import re
import hashlib
from datetime import datetime, date
from pathlib import Path
from typing import Dict, List, Any, Optional


class WebScout:
    """外网学习模块 — 结构核版本

    输入：词库、记忆索引、任务池（可选）
    输出：更新 state，返回结构化结果
    副作用：写入词库、写入记忆、创建任务
    """

    def __init__(
        self,
        base_dir: Path,
        lexicon,
        memory_index,
        task_pool=None,
        state_file: Optional[Path] = None,
    ):
        self.base_dir = base_dir
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.task_pool = task_pool

        if state_file is None:
            state_file = base_dir / "06_RUNTIME" / "ace" / "data" / "web_scout_state.json"
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # 信息源注册表
        self._sources = {
            "github_trending": {
                "type": "github_trending",
                "priority": 2,
                "url": "https://github.com/trending",
            },
            "github_ai_agents": {
                "type": "github_search",
                "priority": 3,
                "query": "AI agent framework",
                "sort": "stars",
            },
            "github_runtimes": {
                "type": "github_search",
                "priority": 2,
                "query": "runtime cognitive system",
                "sort": "updated",
            },
            "github_protocols": {
                "type": "github_search",
                "priority": 1,
                "query": "protocol distributed system",
                "sort": "stars",
            },
            # === 逆向工程领域狩猎源 ===
            "github_reverse_android": {
                "type": "github_search",
                "priority": 1,
                "query": "android reverse engineering frida xposed",
                "sort": "stars",
            },
            "github_unpacking": {
                "type": "github_search",
                "priority": 1,
                "query": "unpacking packer binary analysis",
                "sort": "stars",
            },
            "github_rpc_injection": {
                "type": "github_search",
                "priority": 1,
                "query": "rpc injection frida sekiro unidbg",
                "sort": "stars",
            },
            "github_binary_protocol": {
                "type": "github_search",
                "priority": 2,
                "query": "binary protocol reverse engineering parser",
                "sort": "stars",
            },
            "github_obfuscation": {
                "type": "github_search",
                "priority": 2,
                "query": "obfuscation deobfuscation control flow flattening",
                "sort": "stars",
            },
            "github_emulation": {
                "type": "github_search",
                "priority": 2,
                "query": "emulation unicorn qemu angr symbolic execution",
                "sort": "stars",
            },
        }

        # 每日预算
        self._budget = {
            "max_sources_per_day": 5,
            "max_findings_per_source": 10,
            "min_novelty_score": 0.3,
        }

        # 关键词过滤器
        self._interest_keywords = [
            # 系统架构
            "agent", "ai", "system", "framework", "runtime", "protocol",
            "cognitive", "memory", "architecture", "kernel", "core",
            "dispatch", "routing", "engine", "loop", "layer",
            # 逆向工程
            "reverse", "unpack", "packer", "binary", "native", "frida",
            "xposed", "unidbg", "sekiro", "rpc", "injection", "hook",
            "obfuscation", "deobfuscation", "emulation", "unicorn",
            "angr", "symbolic", "protocol", "parser", "decrypt",
            "encrypt", "signature", "anti", "tamper",
        ]

        self._state = self._load_state()

    # ── state 层（唯一真源） ──────────────────────────────────

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                raw = json.loads(self.state_file.read_text(encoding="utf-8"))
                raw["known_repos"] = set(raw.get("known_repos", []))
                raw["known_concepts"] = set(raw.get("known_concepts", []))
                return raw
            except Exception:
                pass

        return {
            "version": 1,
            "last_run": None,
            "today_date": None,
            "today_sources": [],
            "known_repos": set(),
            "known_concepts": set(),
            "total_findings": 0,
            "total_concepts_added": 0,
            "total_tasks_created": 0,
            "errors": [],
            "history": [],  # 最近100次运行记录
        }

    def _save_state(self):
        save_data = dict(self._state)
        save_data["known_repos"] = list(save_data["known_repos"])
        save_data["known_concepts"] = list(save_data["known_concepts"])
        self.state_file.write_text(
            json.dumps(save_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _ensure_today(self):
        today = date.today().isoformat()
        if self._state.get("today_date") != today:
            self._state["today_date"] = today
            self._state["today_sources"] = []

    def get_stats(self) -> Dict[str, Any]:
        """只读统计接口"""
        s = self._state
        return {
            "last_run": s.get("last_run"),
            "today_sources_count": len(s.get("today_sources", [])),
            "budget_used": len(s.get("today_sources", [])) >= self._budget["max_sources_per_day"],
            "total_findings": s.get("total_findings", 0),
            "total_concepts_added": s.get("total_concepts_added", 0),
            "total_tasks_created": s.get("total_tasks_created", 0),
            "known_repos_count": len(s.get("known_repos", set())),
            "known_concepts_count": len(s.get("known_concepts", set())),
            "error_count": len(s.get("errors", [])),
        }

    # ── 决策层 ───────────────────────────────────────────────

    def _decide_source(self) -> Optional[str]:
        """决定下一个要访问的信息源

        决策逻辑（优先级从高到低）：
        1. 今天还没访问过的最高优先级源
        """
        self._ensure_today()
        today_done = set(self._state.get("today_sources", []))
        available = [s for s in self._sources if s not in today_done]

        if not available:
            return None

        available.sort(key=lambda s: -self._sources[s].get("priority", 1))
        return available[0]

    # ── 执行层 ───────────────────────────────────────────────

    def scout(self, force: bool = False) -> Dict[str, Any]:
        """执行一次外网学习

        返回结构化数据，不输出日志。
        state 会被更新。
        """
        self._ensure_today()

        # 预算检查
        if not force and len(self._state["today_sources"]) >= self._budget["max_sources_per_day"]:
            return {
                "status": "budget_exhausted",
                "source": None,
                "findings_count": 0,
                "concepts_added": [],
                "tasks_created": 0,
            }

        source_name = self._decide_source()
        if not source_name:
            return {
                "status": "no_sources_available",
                "source": None,
                "findings_count": 0,
                "concepts_added": [],
                "tasks_created": 0,
            }

        # 执行采集
        try:
            findings = self._fetch_source(source_name)
        except Exception as e:
            self._record_error(source_name, str(e))
            return {
                "status": "error",
                "source": source_name,
                "error": str(e),
                "findings_count": 0,
                "concepts_added": [],
                "tasks_created": 0,
            }

        # 过滤 + 新颖度评估
        new_structures = self._filter_findings(findings)

        # 沉淀
        concepts_added = []
        tasks_created = 0

        if new_structures:
            concepts_added = self._deposit_concepts(new_structures, source_name)
            self._deposit_memory(new_structures, source_name)
            tasks_created = self._maybe_create_task(new_structures, source_name)

        # 更新 state
        self._state["today_sources"].append(source_name)
        self._state["last_run"] = datetime.now().isoformat()
        self._state["total_findings"] += len(new_structures)
        self._state["total_concepts_added"] += len(concepts_added)
        self._state["total_tasks_created"] += tasks_created

        # 历史记录
        self._state.setdefault("history", []).insert(0, {
            "at": datetime.now().isoformat(),
            "source": source_name,
            "findings_count": len(findings),
            "new_count": len(new_structures),
            "concepts_added_count": len(concepts_added),
            "tasks_created": tasks_created,
        })
        self._state["history"] = self._state["history"][:100]

        self._save_state()

        return {
            "status": "success" if new_structures else "no_new_findings",
            "source": source_name,
            "findings_count": len(findings),
            "new_count": len(new_structures),
            "new_structures": new_structures[:self._budget["max_findings_per_source"]],
            "concepts_added": concepts_added,
            "tasks_created": tasks_created,
        }

    # ── 采集层 ───────────────────────────────────────────────

    def _fetch_source(self, source_name: str) -> List[Dict[str, Any]]:
        """从指定信息源采集原始数据"""
        source = self._sources[source_name]
        source_type = source["type"]

        if source_type == "github_trending":
            return self._fetch_github_trending(source["url"])
        elif source_type == "github_search":
            return self._fetch_github_search(
                query=source["query"],
                sort=source.get("sort", "stars"),
            )
        else:
            return []

    def _fetch_github_search(self, query: str, sort: str = "stars") -> List[Dict[str, Any]]:
        """GitHub API 搜索，失败时返回空列表"""
        try:
            from urllib.request import urlopen, Request
            import ssl

            ctx = ssl._create_unverified_context()
            url = f"https://api.github.com/search/repositories?q={query}&sort={sort}&per_page=30"
            req = Request(url, headers={
                "User-Agent": "ACE-Scout/2.0",
                "Accept": "application/vnd.github.v3+json",
            })
            with urlopen(req, timeout=8, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("items", [])
        except Exception:
            return []

    def _fetch_github_trending(self, url: str) -> List[Dict[str, Any]]:
        """解析 GitHub Trending 页面"""
        try:
            from urllib.request import urlopen, Request
            import ssl

            ctx = ssl._create_unverified_context()
            req = Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            })
            with urlopen(req, timeout=10, context=ctx) as resp:
                html = resp.read().decode("utf-8")

            items = []

            name_pattern = r'<h2[^>]*><a[^>]*href="/([^"]+)"[^>]*>'
            desc_pattern = r'<p[^>]*class="[^"]*col-9[^"]*"[^>]*>([^<]+)</p>'
            star_pattern = r'aria-label="([^"]*stars?[^"]*)"'

            names = re.findall(name_pattern, html)
            descs = re.findall(desc_pattern, html)
            stars = re.findall(star_pattern, html)

            for i, name in enumerate(names[:25]):
                if "/" not in name:
                    continue
                desc = descs[i].strip() if i < len(descs) else ""
                star_str = stars[i] if i < len(stars) else "0"
                try:
                    star_count = int("".join(filter(str.isdigit, star_str.replace(",", ""))))
                except ValueError:
                    star_count = 0

                items.append({
                    "full_name": name,
                    "name": name.split("/")[-1],
                    "description": desc,
                    "stargazers_count": star_count,
                    "html_url": f"https://github.com/{name}",
                    "source": "trending",
                })

            return items
        except Exception:
            return []

    # ── 过滤层 ───────────────────────────────────────────────

    def _filter_findings(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """过滤发现，返回有意义且新颖的结果"""
        result = []

        for item in findings:
            if not self._is_relevant(item):
                continue

            novelty = self._compute_novelty(item)
            if novelty < self._budget["min_novelty_score"]:
                continue

            item["novelty_score"] = novelty

            # 记录已知仓库
            repo_key = item.get("full_name", "").lower()
            if repo_key:
                self._state["known_repos"].add(repo_key)

            result.append(item)

        return result

    def _is_relevant(self, item: Dict[str, Any]) -> bool:
        """判断是否与我们的兴趣相关"""
        desc = (item.get("description") or "").lower()
        name = (item.get("name") or "").lower()
        combined = f"{name} {desc}"

        if len(desc) < 20:
            return False

        return any(kw in combined for kw in self._interest_keywords)

    def _compute_novelty(self, item: Dict[str, Any]) -> float:
        """计算新颖度分数 0.0 ~ 1.0"""
        score = 0.0

        # 新仓库 = +0.4
        repo_key = item.get("full_name", "").lower()
        if repo_key not in self._state["known_repos"]:
            score += 0.4

        # 描述包含已知概念 = 相关度加分（最高+0.3）
        desc = (item.get("description") or "").lower()
        known_concepts = self._state["known_concepts"]
        hits = sum(1 for c in known_concepts if c.lower() in desc)
        score += min(hits * 0.1, 0.3)

        # 新热门项目 = +0.3
        stars = item.get("stargazers_count", 0)
        created_at = item.get("created_at", "")
        if created_at:
            try:
                age_days = (datetime.now() - datetime.fromisoformat(
                    created_at.replace("Z", "+00:00").replace("+00:00", "")
                )).days
                if age_days < 90 and stars > 100:
                    score += 0.3
            except Exception:
                pass
        elif stars > 10000:
            score += 0.15  # 非常热门也算加分

        return min(score, 1.0)

    # ── 沉淀层 ───────────────────────────────────────────────

    def _deposit_concepts(self, items: List[Dict[str, Any]], source: str) -> List[str]:
        """将发现的概念入库"""
        added = []

        for item in items:
            concept_name = self._extract_concept_name(item)
            if not concept_name:
                continue

            if concept_name.lower() in {c.lower() for c in self._state["known_concepts"]}:
                continue

            try:
                self.lexicon.add_concept(
                    name=concept_name,
                    category=self._classify_item(item),
                    description=item.get("description", ""),
                    tags=["external", "web_scout", source],
                    metadata={
                        "source": source,
                        "url": item.get("html_url", ""),
                        "stars": item.get("stargazers_count", 0),
                        "novelty": item.get("novelty_score", 0),
                    },
                )
                added.append(concept_name)
                self._state["known_concepts"].add(concept_name.lower())
            except Exception:
                pass

        return added

    def _deposit_memory(self, items: List[Dict[str, Any]], source: str):
        """将发现写入记忆索引"""
        if not items:
            return

        lines = [f"# 外网发现 - {source}"]
        lines.append(f"")
        lines.append(f"来源: {source}")
        lines.append(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"发现数: {len(items)}")
        lines.append(f"")
        lines.append("---")
        lines.append("")

        for i, item in enumerate(items[:10], 1):
            name = item.get("full_name", "unknown")
            desc = item.get("description", "无描述")
            stars = item.get("stargazers_count", 0)
            url = item.get("html_url", "")
            novelty = item.get("novelty_score", 0)

            lines.append(f"## {i}. {name}")
            lines.append(f"- Stars: {stars:,}")
            lines.append(f"- 描述: {desc}")
            lines.append(f"- 新颖度: {novelty:.1%}")
            lines.append(f"- 链接: {url}")
            lines.append("")

        try:
            self.memory_index.add(
                title=f"外网发现 - {source}",
                content="\n".join(lines),
                memory_type="web_scout_finding",
                category="外部知识",
                source="web_scout",
                tags=["web_scout", source, f"findings_{len(items)}"],
            )
        except Exception:
            pass

    def _maybe_create_task(self, items: List[Dict[str, Any]], source: str) -> int:
        """如果发现足够多，创建深入研究任务"""
        if not self.task_pool or len(items) < 3:
            return 0

        try:
            task = self.task_pool.create_task(
                title=f"外网深挖: {source}",
                hypothesis=f"来自{source}的{len(items)}个发现需要进一步研究和吸收",
                creator="web_scout",
                priority="medium",
                tags=["external", "web_scout", source, "deep_research"],
            )
            return 1 if task else 0
        except Exception:
            return 0

    # ── 工具方法 ─────────────────────────────────────────────

    def _extract_concept_name(self, item: Dict[str, Any]) -> Optional[str]:
        """从仓库信息中提取概念名"""
        name = item.get("name", "")
        if not name:
            return None

        # 清理名称
        name = re.sub(r'[-_]', ' ', name)
        name = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
        words = name.split()

        if len(words) > 4:
            return None

        return name.title()

    def _classify_item(self, item: Dict[str, Any]) -> str:
        """分类发现项"""
        desc = (item.get("description") or "").lower()
        name = (item.get("name") or "").lower()
        combined = f"{desc} {name}"

        if any(kw in combined for kw in ["agent", "bot", "assistant"]):
            return "AI Agent"
        elif any(kw in combined for kw in ["runtime", "engine", "executor", "scheduler"]):
            return "Runtime"
        elif any(kw in combined for kw in ["protocol", "api", "interface"]):
            return "Protocol"
        elif any(kw in combined for kw in ["memory", "cache", "store"]):
            return "Memory System"
        elif any(kw in combined for kw in ["framework", "library", "toolkit"]):
            return "Framework"
        else:
            return "External Tool"

    def _record_error(self, source: str, error: str):
        """记录错误到 state"""
        self._state.setdefault("errors", []).insert(0, {
            "at": datetime.now().isoformat(),
            "source": source,
            "error": error[:200],
        })
        self._state["errors"] = self._state["errors"][:20]
        self._save_state()
