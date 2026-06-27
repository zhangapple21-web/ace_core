"""
Task Creator — 自发现考古任务生成器

职责：
  每日运行时自动检查 08_ARCHAEOLOGY/ 中的新 .md 报告，
  或 09_KNOWLEDGE/ 中的新沉积经验模式，
  若发现新结构则自动创建考古任务。

触发条件：
  - 08_ARCHAEOLOGY/ 中有新的 .md 文件（不在最近已处理列表中）
  - 09_KNOWLEDGE/ axiom/constraint/pattern/ 中有新经验记录
  - 词库中有新的薄弱分类（概念数 <= 2）

去重规则：
  - 检查是否有相同标题的任务在 pending/active/review 状态
  - 若有则不重复创建

输出：
  - 新创建的任务列表
  - 日志记录（有无新发现）
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Set


class TaskCreator:
    """
    Task Creator — 自发现考古任务生成器

    工作流程：
    1. 扫描 08_ARCHAEOLOGY/ 中最近 N 天的新报告
    2. 扫描 09_KNOWLEDGE/ 中最近 N 天的新经验模式
    3. 扫描词库中的薄弱分类
    4. 去重检查
    5. 生成考古任务
    """

    def __init__(
        self,
        task_pool,
        base_dir: Path,
        lexicon=None,
        memory_index=None,
        history_file: Optional[str] = None,
        scan_days: int = 7,
    ):
        self.task_pool = task_pool
        self.base_dir = Path(base_dir)
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.scan_days = scan_days
        self.history_file = Path(history_file) if history_file else self.base_dir / ".task_creator_history.json"
        self._load_history()

    def _load_history(self):
        """加载历史记录（已处理过的文件/经验ID）"""
        if self.history_file.exists():
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    self.history = json.load(f)
            except Exception:
                self.history = {}
        else:
            self.history = {}

        self.processed_files: Set[str] = set(self.history.get("processed_files", []))
        self.processed_experiences: Set[str] = set(self.history.get("processed_experiences", []))
        self.processed_gaps: Set[str] = set(self.history.get("processed_gaps", []))
        self.last_scan_at = self.history.get("last_scan_at", "")

    def _save_history(self):
        """保存历史记录"""
        self.history = {
            "processed_files": list(self.processed_files),
            "processed_experiences": list(self.processed_experiences),
            "processed_gaps": list(self.processed_gaps),
            "last_scan_at": datetime.now().isoformat(),
        }
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _is_recent(self, path: Path) -> bool:
        """检查文件是否在最近 scan_days 天内修改过"""
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime)
            cutoff = datetime.now() - timedelta(days=self.scan_days)
            return mtime >= cutoff
        except Exception:
            return False

    def _task_exists(self, title: str) -> bool:
        """检查是否有相同标题的任务在 pending/active/review 状态"""
        for status in ["pending", "active", "review"]:
            tasks = self.task_pool.list_tasks(status=status, limit=100)
            for t in tasks:
                if t.title == title or title in t.title:
                    return True
        return False

    def scan_for_new_structures(self) -> Dict[str, Any]:
        """
        扫描所有来源，发现新结构，返回生成的任务列表
        """
        result = {
            "tasks_created": [],
            "new_archaeology_reports": [],
            "new_experiences": [],
            "new_lexicon_gaps": [],
            "skipped_duplicates": [],
            "scan_summary": "",
        }

        self._load_history()

        result["new_archaeology_reports"] = self._scan_archaeology_reports()
        result["new_experiences"] = self._scan_knowledge_experiences()
        result["new_lexicon_gaps"] = self._scan_lexicon_gaps()

        all_new = (
            result["new_archaeology_reports"]
            + result["new_experiences"]
            + result["new_lexicon_gaps"]
        )

        if not all_new:
            result["scan_summary"] = f"最近{self.scan_days}天无新结构发现"
        else:
            result["scan_summary"] = (
                f"发现{len(all_new)}个新结构："
                f"{len(result['new_archaeology_reports'])}个新报告，"
                f"{len(result['new_experiences'])}个新经验，"
                f"{len(result['new_lexicon_gaps'])}个新缺口"
            )

        self._save_history()
        return result

    def _scan_archaeology_reports(self) -> List[Dict]:
        """扫描 08_ARCHAEOLOGY/ 中最近的新报告"""
        new_reports = []
        arch_dir = self.base_dir / "08_ARCHAEOLOGY"
        if not arch_dir.exists():
            return new_reports

        for fpath in arch_dir.rglob("*.md"):
            if fpath.name in self.processed_files:
                continue
            if not self._is_recent(fpath):
                continue

            rel_path = str(fpath.relative_to(self.base_dir))
            title = fpath.stem

            if self._task_exists(f"考古报告分析: {title}"):
                self.processed_files.add(fpath.name)
                continue

            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
                content_preview = content[:200].replace("\n", " ")
            except Exception:
                content_preview = ""

            new_reports.append({
                "type": "archaeology_report",
                "title": title,
                "path": rel_path,
                "preview": content_preview,
                "task_title": f"考古报告分析: {title}",
                "priority": "medium",
                "hypothesis": f"该报告揭示了有价值的研究方向：{content_preview[:50]}",
                "tags": ["archaeology", "report"],
            })
            self.processed_files.add(fpath.name)

        return new_reports

    def _scan_knowledge_experiences(self) -> List[Dict]:
        """扫描 09_KNOWLEDGE/ 中最近的新经验模式"""
        new_experiences = []
        knowledge_dir = self.base_dir / "09_KNOWLEDGE"
        if not knowledge_dir.exists():
            return new_experiences

        for subdir in ["axiom", "constraint", "pattern"]:
            exp_dir = knowledge_dir / subdir
            if not exp_dir.exists():
                continue
            for fpath in exp_dir.glob("EXP-*.json"):
                if fpath.name in self.processed_experiences:
                    continue
                if not self._is_recent(fpath):
                    continue

                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception:
                    continue

                exp_id = data.get("experience_id", fpath.stem)
                conclusion = data.get("conclusion", "")
                source_task = data.get("source_task_id", "")

                task_title = f"经验验证: {conclusion[:40]}" if conclusion else f"经验模式研究: {exp_id}"

                if self._task_exists(task_title):
                    self.processed_experiences.add(fpath.name)
                    continue

                new_experiences.append({
                    "type": "experience_pattern",
                    "experience_id": exp_id,
                    "experience_type": subdir,
                    "conclusion": conclusion,
                    "source_task": source_task,
                    "task_title": task_title,
                    "priority": "high" if subdir in ("axiom", "constraint") else "medium",
                    "hypothesis": f"该经验模式（{subdir}）可以推广到更广泛的场景",
                    "tags": ["experience", subdir, source_task],
                })
                self.processed_experiences.add(fpath.name)

        return new_experiences

    def _scan_lexicon_gaps(self) -> List[Dict]:
        """扫描词库中的薄弱分类，生成补全任务"""
        new_gaps = []
        if not self.lexicon:
            return new_gaps

        try:
            stats = self.lexicon.get_stats()
        except Exception:
            return new_gaps

        weak_categories = []
        if "categories" in stats:
            for cat_name, cat_data in stats["categories"].items():
                count = cat_data.get("count", 0) if isinstance(cat_data, dict) else 0
                if count <= 2:
                    weak_categories.append(cat_name)

        for cat in weak_categories:
            if cat in self.processed_gaps:
                continue

            task_title = f"词库补全: {cat}分类"
            if self._task_exists(task_title):
                self.processed_gaps.add(cat)
                continue

            new_gaps.append({
                "type": "lexicon_gap",
                "category": cat,
                "task_title": task_title,
                "priority": "medium",
                "hypothesis": f"{cat}分类概念积累不足（<=2个），影响系统对该领域的理解能力",
                "tags": ["lexicon", "gap", cat],
            })
            self.processed_gaps.add(cat)

        return new_gaps

    def create_tasks_from_candidates(self, candidates: List[Dict]) -> List:
        """根据候选列表创建任务"""
        created_tasks = []
        for cand in candidates:
            task = self.task_pool.create_task(
                title=cand["task_title"],
                hypothesis=cand.get("hypothesis", ""),
                creator="task_creator",
                priority=cand.get("priority", "medium"),
                tags=cand.get("tags", []) + [cand["type"]],
            )

            if cand.get("source_task"):
                task.parent_task = cand["source_task"]
                self.task_pool.update_task(task)

            task.outputs = {
                "source_type": cand["type"],
                "trigger": {k: v for k, v in cand.items() if k not in ("type", "task_title", "priority", "hypothesis", "tags")},
            }
            self.task_pool.update_task(task)
            created_tasks.append(task)
        return created_tasks

    def scan_and_create(self, max_new: int = 3) -> Dict[str, Any]:
        """
        完整流程：扫描 → 去重 → 创建 → 返回结果
        """
        candidates = self.scan_for_new_structures()
        all_candidates = (
            candidates["new_archaeology_reports"]
            + candidates["new_experiences"]
            + candidates["new_lexicon_gaps"]
        )

        created = self.create_tasks_from_candidates(all_candidates[:max_new])

        candidates["tasks_created"] = [t.task_id for t in created]
        return candidates
