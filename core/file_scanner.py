"""
文件扫描器 — FileScanner

主动扫描环境中的文件碎片，发现新结构自动创建考古任务。

扫描范围：
  - Downloads/Telegram Desktop/
  - Downloads/
  - （可扩展）

扫描目标：
  - .zip — 压缩包碎片（可能包含R1核心、DAG、系统架构）
  - .json — 配置、数据、结构定义
  - .md — 文档、考古报告、设计说明
  - .txt — 日志、说明、纯文本碎片

工作原则：
  - 慢启动：第一次全量标记，不建任务（避免任务池爆炸）
  - 增量发现：之后每次只处理新出现/变化的文件
  - 按优先级：.zip > .json > .md > .txt
  - 限批量：每次最多创建 N 个新任务，不一次堆满

不是内容分析器。
是发现器。
发现了新东西 → 建任务 → 交给 Researcher 去挖。
"""

import json
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Set

from .fragment_index import FragmentIndex


SCAN_EXTENSIONS = {".zip", ".json", ".md", ".txt"}

EXT_PRIORITY = {
    ".zip": "high",
    ".json": "medium",
    ".md": "medium",
    ".txt": "low",
}


class FileScanner:
    """
    文件扫描器 — 环境感知，发现新碎片

    调用方式：
      scanner.scan_and_create(max_new=3) → {new_tasks: [...], scanned: N, new_files: N}
    """

    def __init__(
        self,
        task_pool,
        fragment_index: FragmentIndex,
        scan_roots: List[Path],
        max_depth: int = 4,
    ):
        self.task_pool = task_pool
        self.fragment_index = fragment_index
        self.scan_roots = [Path(r) for r in scan_roots if Path(r).exists()]
        self.max_depth = max_depth

    def scan_and_create(self, max_new: int = 3) -> Dict[str, Any]:
        result = {
            "scanned": 0,
            "new_files": 0,
            "tasks_created": 0,
            "tasks": [],
            "scan_roots": [str(r) for r in self.scan_roots],
        }

        new_fragments = self._scan_new_fragments()
        result["scanned"] = new_fragments["total_scanned"]
        result["new_files"] = len(new_fragments["new"])

        if not new_fragments["new"]:
            return result

        sorted_new = sorted(
            new_fragments["new"],
            key=lambda p: self._priority_score(p),
            reverse=True,
        )

        created = 0
        for frag_path in sorted_new:
            if created >= max_new:
                break

            if self._task_exists_for(frag_path):
                self.fragment_index.mark_seen(frag_path, status="duplicate_skip")
                continue

            task = self._create_archaeology_task(frag_path)
            if task:
                result["tasks"].append(task)
                result["tasks_created"] += 1
                created += 1
                self.fragment_index.mark_archaeologized(
                    frag_path, task_id=task.task_id
                )

        for frag_path in sorted_new[created:]:
            self.fragment_index.mark_seen(frag_path, status="pending_scan")

        return result

    def _scan_new_fragments(self) -> Dict[str, Any]:
        new_files: List[Path] = []
        total = 0
        seen_names: Set[str] = set()  # 基于文件名的去重

        for root in self.scan_roots:
            for f in root.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in SCAN_EXTENSIONS:
                    continue
                if self._is_ignored(f):
                    continue
                parts = f.relative_to(root).parts
                if len(parts) > self.max_depth:
                    continue

                total += 1

                # 基于文件名的去重：同名文件只处理一次
                file_key = f.name.lower()
                if file_key in seen_names:
                    continue
                seen_names.add(file_key)

                if not self.fragment_index.is_known(f):
                    new_files.append(f)

        return {"total_scanned": total, "new": new_files}

    def _is_ignored(self, path: Path) -> bool:
        p = str(path).lower()
        ignore_patterns = [
            "node_modules", ".git", "__pycache__", ".venv",
            "ace_runtime", ".idea", ".vscode",
            "Log-iOS", "takeout-2026", "TikTok_Data",
        ]
        for pat in ignore_patterns:
            if pat.lower() in p:
                return True
        return False

    def _priority_score(self, path: Path) -> int:
        ext = path.suffix.lower()
        pri = EXT_PRIORITY.get(ext, "low")
        score_map = {"critical": 40, "high": 30, "medium": 20, "low": 10}
        score = score_map.get(pri, 10)

        name = path.name.lower()
        boost_keywords = [
            "dag", "reason", "graph", "r1", "core", "kernel",
            "architecture", "sip", "guardian", "eco_layer",
            "offshore", "dispatch", "memory", "shadow",
            "lexicon", "constraint", "experience",
            "archaeology", "考古", "survivor", "存活",
            "cluster", "index", "finding", "发现",
            "structure", "结构", "alignment", "对齐",
        ]
        for kw in boost_keywords:
            if kw in name:
                score += 5

        path_str = str(path).lower()
        if "telegram_archive" in path_str or "04_findings" in path_str:
            score += 15
        if "03_clusters" in path_str or "02_index" in path_str:
            score += 10

        size = path.stat().st_size if path.exists() else 0
        if size > 1024 * 1024:
            score += 3
        elif size > 100 * 1024:
            score += 1

        return score

    def _task_exists_for(self, path: Path) -> bool:
        name_key = path.stem[:30].lower()
        all_tasks = self.task_pool.list_tasks(limit=200)
        for t in all_tasks:
            if t.status in ("pending", "active", "review", "approved"):
                if name_key in t.title[:30].lower():
                    return True
        return False

    def _create_archaeology_task(self, path: Path) -> Optional[Any]:
        ext = path.suffix.lower()
        pri = EXT_PRIORITY.get(ext, "medium")
        size_kb = path.stat().st_size / 1024

        preview = ""
        if ext == ".zip":
            preview = self._zip_preview(path)
        elif ext in (".md", ".txt"):
            preview = self._text_preview(path)
        elif ext == ".json":
            preview = self._json_preview(path)

        title = f"碎片考古: {path.name}"
        hypothesis = (
            f"该文件（{path.name}, {size_kb:.0f}KB）可能包含有价值的"
            f"R1结构或认知架构碎片，需要考古分析。"
        )

        tags = ["fragment_archaeology", f"ext:{ext[1:]}"]

        task = self.task_pool.create_task(
            title=title,
            hypothesis=hypothesis,
            creator="file_scanner",
            priority=pri,
            tags=tags,
        )

        if task:
            task.outputs = {
                "source_file": str(path),
                "file_size": int(path.stat().st_size),
                "file_mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                "preview": preview,
            }
            self.task_pool.update_task(task)

        return task

    def _zip_preview(self, path: Path, max_items: int = 20) -> str:
        try:
            with zipfile.ZipFile(path, "r") as z:
                names = z.namelist()
                lines = [f"共 {len(names)} 个文件:"]
                for n in names[:max_items]:
                    lines.append(f"  - {n}")
                if len(names) > max_items:
                    lines.append(f"  ... 等 {len(names) - max_items} 个")
                return "\n".join(lines)
        except Exception as e:
            return f"[无法读取] {e}"

    def _text_preview(self, path: Path, max_chars: int = 500) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(max_chars)
            return content.strip()[:max_chars]
        except Exception as e:
            return f"[无法读取] {e}"

    def _json_preview(self, path: Path, max_chars: int = 500) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)
            if isinstance(data, dict):
                keys = list(data.keys())[:15]
                return f"JSON 对象，顶层键: {', '.join(keys)}"
            elif isinstance(data, list):
                return f"JSON 数组，长度: {len(data)}"
            else:
                return f"JSON 类型: {type(data).__name__}"
        except Exception as e:
            return f"[无法解析] {e}"
