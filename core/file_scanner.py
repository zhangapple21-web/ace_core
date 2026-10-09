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

import hashlib
import json
import os
import zipfile
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional, Set

from .fragment_index import FragmentIndex


SCAN_EXTENSIONS = {".zip", ".json", ".md", ".txt"}

# Windows refuses paths beyond this length.  Probing such a path raises instead
# of returning False, so the scanner has to know the limit.
MAX_PATH = 250

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

    def scan_and_create(
        self,
        max_new: int = 3,
        allowed_priorities: Optional[Set[str]] = None,
        allow_task_creation: bool = True,
    ) -> Dict[str, Any]:
        result = {
            "scanned": 0,
            "new_files": 0,
            "tasks_created": 0,
            "tasks": [],
            "unadmitted_observations": 0,
            "scan_roots": [str(r) for r in self.scan_roots],
        }

        new_fragments = self._scan_new_fragments()
        result["scanned"] = new_fragments["total_scanned"]
        result["new_files"] = len(new_fragments["new"])
        # Unreadable material is reported, never raised: a scanner that dies on
        # one bad path also stops finding the good ones.
        result["unreadable"] = len(new_fragments.get("skipped") or [])
        if new_fragments.get("skipped"):
            result["unreadable_examples"] = list(new_fragments["skipped"])[:3]

        if not new_fragments["new"]:
            return result

        sorted_new = sorted(
            new_fragments["new"],
            key=lambda p: self._priority_score(p),
            reverse=True,
        )
        if allowed_priorities is not None:
            sorted_new = [
                path for path in sorted_new
                if EXT_PRIORITY.get(path.suffix.lower(), "low") in allowed_priorities
            ]

        # A newly observed file is one source, not independently corroborated
        # Work.  Production can retain the fingerprint as an observation while
        # refusing to manufacture a TaskPool item.  Explicit offline callers
        # keep the legacy opt-in task-creation behavior for bounded research.
        if not allow_task_creation:
            for frag_path in sorted_new:
                self.fragment_index.mark_seen(
                    frag_path, status="observed_unadmitted"
                )
            result["unadmitted_observations"] = len(sorted_new)
            return result

        created = 0
        handled_paths: Set[Path] = set()
        for frag_path in sorted_new:
            if created >= max_new:
                break

            if self._task_exists_for(frag_path):
                self.fragment_index.mark_seen(frag_path, status="duplicate_skip")
                handled_paths.add(frag_path)
                continue

            if self._in_churn_cooloff(frag_path):
                self.fragment_index.mark_seen(frag_path, status="churn_cooloff")
                result["churn_cooled"] = result.get("churn_cooled", 0) + 1
                handled_paths.add(frag_path)
                continue

            task = self._create_archaeology_task(frag_path)
            if task:
                result["tasks"].append(task)
                result["tasks_created"] += 1
                created += 1
                self.fragment_index.mark_archaeologized(
                    frag_path, task_id=task.task_id
                )
                handled_paths.add(frag_path)

        # `created` is not a cursor: duplicate skips do not increment it.
        # Mark only the paths the loop did not inspect as pending, otherwise a
        # duplicate at the front can regress later files to pending_scan.
        for frag_path in sorted_new:
            if frag_path not in handled_paths:
                self.fragment_index.mark_seen(frag_path, status="pending_scan")

        return result

    CHURN_TERMINAL_STRIKES = 3
    CHURN_COOLOFF_DAYS = 30

    def _in_churn_cooloff(self, path: Path) -> bool:
        """True when this source path keeps dying terminally.

        A path whose last few filings all ended terminal_non_convergent is
        churning runtime state, not yielding archaeology: state.json was
        filed 141 times, each burning four validator reviews. After three
        recent terminal strikes the path cools off for thirty days instead
        of filing again. A path that ever produced an approved task is not
        churn, no matter how many terminals surround it. Only terminal
        records younger than the cool-off window count, so an old spree
        cannot silence a path forever.
        """
        try:
            resolved = str(path.resolve())
        except OSError:
            return False
        try:
            import time as _time

            cutoff = _time.time() - self.CHURN_COOLOFF_DAYS * 86400
        except Exception:
            return False
        strikes = 0
        approved = False
        for status_dir in ("archived", "blocked", "graveyard", "rejected"):
            status_path = self.task_pool.pool_dir / status_dir
            try:
                candidates = sorted(
                    status_path.glob("*.json"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
            except OSError:
                continue
            for record in candidates[:400]:
                try:
                    import json as _json

                    payload = _json.loads(record.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                outputs = payload.get("outputs") or {}
                if str(outputs.get("source_file", "")) != resolved:
                    continue
                try:
                    fresh = record.stat().st_mtime >= cutoff
                except OSError:
                    continue
                if not fresh:
                    continue
                if str(payload.get("status", "")) == "approved" or (
                    status_dir == "archived"
                    and not outputs.get("terminal_non_convergent")
                ):
                    approved = True
                    break
                if outputs.get("terminal_non_convergent"):
                    strikes += 1
            if approved:
                break
        return (not approved) and strikes >= self.CHURN_TERMINAL_STRIKES

    def _scan_new_fragments(self) -> Dict[str, Any]:
        new_files: List[Path] = []
        total = 0
        skipped: List[str] = []
        seen_names: Set[str] = set()  # 基于文件名的去重

        for root in self.scan_roots:
            # One unreadable subtree must not abort the whole scan.  Windows
            # raises on paths beyond MAX_PATH, and a single deep node_modules
            # under C:\tmp otherwise fails every cycle, fills daemon_state with
            # the same error, and hides every real fragment behind it.
            for f in self._walk(root, skipped):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in SCAN_EXTENSIONS:
                    continue
                if len(str(f)) > MAX_PATH:
                    skipped.append(f"{f}: path_too_long")
                    continue
                if self._is_ignored(f):
                    continue
                try:
                    parts = f.relative_to(root).parts
                except ValueError:
                    continue
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

        return {"total_scanned": total, "new": new_files, "skipped": skipped}

    def _walk(self, root: Path, skipped: List[str]) -> Iterator[Path]:
        """Yield every path under ``root``, tolerating unreadable subtrees."""
        stack: List[Path] = [root]
        while stack:
            current = stack.pop()
            try:
                entries = list(os.scandir(current))
            except (OSError, ValueError) as error:
                skipped.append(f"{current}: {type(error).__name__}")
                continue
            for entry in entries:
                path = Path(entry.path)
                try:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(path)
                        continue
                except OSError:
                    continue
                yield path

    def _own_output_paths(self) -> List[Path]:
        """Directories whose contents are this scanner's own bookkeeping.

        ``02_FRAGMENT_INDEX/`` and the TaskPool it writes to are ACE's own
        ledgers.  Scanning them turns the scanner's output into its next input,
        which is how a single repeated observation kept producing fresh
        archaeology tasks.  They are excluded by identity, not only by living
        inside the ACE root, so a Free Zone or scratch pool cannot feed itself.
        """
        own = [self.fragment_index.index_dir]
        pool_dir = getattr(self.task_pool, "pool_dir", None)
        if pool_dir is not None:
            own.append(Path(pool_dir))
        return own

    def _is_ignored(self, path: Path) -> bool:
        p = str(path).lower()
        # FileScanner is the broad environmental scanner.  ACE's own tree has
        # dedicated LocalArchaeologist, TaskCreator and Experience paths; its
        # runtime ledgers mutate every cycle.  Feeding those artefacts back
        # into broad scanning creates work from the scanner's own output.
        # Keep sibling sources such as mine-seed and Downloads in scope.
        try:
            resolved = path.resolve()
            for own_root in self._own_output_paths():
                own_root = Path(own_root).resolve()
                if resolved == own_root or own_root in resolved.parents:
                    return True
            ace_root = self.fragment_index.index_dir.resolve().parent
            if resolved.is_relative_to(ace_root):
                return True
        except (OSError, ValueError):
            pass
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
        """Avoid exact duplicate observations without collapsing same-name files."""
        try:
            source = str(path.resolve())
            fingerprint = self._content_fingerprint(path)
        except OSError:
            return False
        for task in self.task_pool.list_tasks(limit=10000):
            # Identity = file path + content fingerprint. A task that records
            # only a path (or only a fingerprint) cannot be proven identical to
            # this file, so it must not suppress creation.
            outputs = task.outputs if isinstance(task.outputs, dict) else {}
            recorded = outputs.get("source_fingerprint") or outputs.get("fingerprint")
            if str(outputs.get("source_file", "")) == source and recorded == fingerprint:
                return True
        return False

    @staticmethod
    def _content_fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"sha256:{digest.hexdigest()}"

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

        file_size = int(path.stat().st_size)
        file_mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        source_fingerprint = self._content_fingerprint(path)
        evidence = {
            "path": str(path),
            "extension": ext,
            "size_bytes": file_size,
            "modified_at": file_mtime,
            "preview": preview,
        }
        task = self.task_pool.create_task(
            title=title,
            hypothesis=hypothesis,
            creator="file_scanner",
            priority=pri,
            tags=tags,
            admission={
                "source_type": "archaeology",
                "source_ref": str(path.resolve()),
                "source_fingerprint": source_fingerprint,
                "why_now": "A new or changed local fragment matched the archaeology scan.",
                "evidence": [evidence],
                "expected_result": "The fragment is analyzed and its reusable structures are recorded or bounded.",
                "verification_method": "Recheck the source file and the resulting archaeology record.",
                "risk": "Read-only local fragment analysis.",
                "estimated_scope": "one local file",
            },
            outputs={
                "source_file": str(path.resolve()),
                "source_fingerprint": source_fingerprint,
                "file_size": file_size,
                "file_mtime": file_mtime,
                "preview": preview,
            },
        )

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
