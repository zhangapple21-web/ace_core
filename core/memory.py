"""
统一记忆层（Unified Memory Layer）

所有节点共享同一套记忆。
这是ACE和多Agent系统的核心区别之一——不是每个Agent各有各的记忆，
而是大家都用同一套记忆，只是访问角度和权限不同。

对接 mine-seed 现有的记忆结构：
  02_MEMORY/
  ├── recent_memory/    ← 短期记忆（最近的事件、任务、对话）
  │   ├── daily/        ← 每日记录
  │   ├── cases/        ← 案例库
  │   └── research/     ← 研究笔记
  ├── knowledge/        ← 长期记忆（提炼后的知识、原则）
  └── MEMORY.md         ← 记忆锚点
"""

import json
from datetime import datetime, date
from pathlib import Path
from typing import List, Optional, Dict, Any

from .identity import Identity


class Memory:
    """统一记忆层 — 所有节点共享"""

    def __init__(self, base_dir: Path, config: dict, identity: Identity):
        self.base_dir = base_dir
        self.config = config
        self.identity = identity
        self.memory_config = config.get("memory", {})

        self.recent_path = base_dir / self.memory_config.get(
            "recent_memory_path", "02_MEMORY/recent_memory"
        )
        self.knowledge_path = base_dir / self.memory_config.get(
            "knowledge_path", "02_MEMORY/knowledge"
        )

        self._cache_dir = base_dir / config.get("data", {}).get(
            "memory_cache_dir", "06_RUNTIME/ace/data/memory"
        )
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def write_daily(self, content: str, title: str = "") -> Path:
        """写入每日记忆"""
        today = date.today().strftime("%Y-%m-%d")
        daily_dir = self.recent_path / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)

        filepath = daily_dir / f"{today}-ace.md"

        header = f"# {title or today + ' ACE记录'}\n\n"
        header += f"> 记录时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        header += f"> 身份: {self.identity.name}\n\n"
        header += "---\n\n"

        if filepath.exists():
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(f"\n\n---\n\n{content}\n")
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(header + content + "\n")

        return filepath

    def write_research_note(self, title: str, content: str, tags: Optional[List[str]] = None) -> Path:
        """写入研究笔记"""
        research_dir = self.recent_path / "research"
        research_dir.mkdir(parents=True, exist_ok=True)

        today = date.today().strftime("%Y%m%d")
        safe_title = "".join(c if c.isalnum() or c in "-_ " else "_" for c in title)
        filename = f"{today}_{safe_title[:50]}.md"
        filepath = research_dir / filename

        header = f"# {title}\n\n"
        header += f"> 日期: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        header += f"> 身份: {self.identity.name}\n"
        if tags:
            header += f"> 标签: {', '.join(tags)}\n"
        header += "\n---\n\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header + content + "\n")

        return filepath

    def write_case(self, case_id: str, title: str, content: str) -> Path:
        """写入案例"""
        cases_dir = self.recent_path / "cases"
        cases_dir.mkdir(parents=True, exist_ok=True)

        filename = f"case_{case_id}.md"
        filepath = cases_dir / filename

        header = f"# {title}\n\n"
        header += f"> 案例ID: {case_id}\n"
        header += f"> 记录时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        header += f"> 身份: {self.identity.name}\n\n"
        header += "---\n\n"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(header + content + "\n")

        return filepath

    def search_recent(self, keyword: str, limit: int = 10) -> List[Dict[str, Any]]:
        """搜索近期记忆"""
        results = []
        search_dirs = [
            self.recent_path / "daily",
            self.recent_path / "cases",
            self.recent_path / "research",
        ]

        for search_dir in search_dirs:
            if not search_dir.exists():
                continue
            for filepath in sorted(search_dir.glob("*.md"), reverse=True)[:50]:
                try:
                    content = filepath.read_text(encoding="utf-8")
                    if keyword.lower() in content.lower():
                        results.append({
                            "path": str(filepath),
                            "title": filepath.stem,
                            "snippet": content[:200],
                        })
                        if len(results) >= limit:
                            return results
                except Exception:
                    continue

        return results

    def get_index(self) -> Dict[str, Any]:
        """获取记忆索引（概览）"""
        index = {
            "identity": self.identity.name,
            "generated_at": datetime.now().isoformat(),
            "recent": {},
            "knowledge": {},
        }

        for category in ["daily", "cases", "research"]:
            dirpath = self.recent_path / category
            if dirpath.exists():
                files = list(dirpath.glob("*.md"))
                index["recent"][category] = {
                    "count": len(files),
                    "latest": [f.stem for f in sorted(files, reverse=True)[:5]],
                }

        if self.knowledge_path.exists():
            files = list(self.knowledge_path.glob("*.md"))
            index["knowledge"] = {
                "count": len(files),
                "items": [f.stem for f in sorted(files, reverse=True)[:10]],
            }

        return index

    def remember(self, key: str, value: Any):
        """临时记住一个键值对（运行时缓存）"""
        cache_file = self._cache_dir / "runtime_cache.json"
        data = {}
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        data[key] = {
            "value": value,
            "remembered_at": datetime.now().isoformat(),
            "identity": self.identity.name,
        }

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def recall(self, key: str) -> Optional[Any]:
        """从运行时缓存中回忆"""
        cache_file = self._cache_dir / "runtime_cache.json"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if key in data:
                return data[key]["value"]
        except Exception:
            pass

        return None
