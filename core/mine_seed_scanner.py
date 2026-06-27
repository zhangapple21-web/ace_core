"""
矿场扫描器 — MineSeedScanner

定期扫描 mine-seed 仓库，拉取其他智能体的最新产出，
对比自己已经处理过的 commit，自动创建跨智能体考古任务。

不是替换自己的考古工作。
是补充视野盲区。

设计原则：
  - 慢启动：只处理新的 commit，不回溯历史
  - 按 commit 为单位跟踪，不按文件跟踪
  - 发现新发现 → 建任务 → 交给 Researcher 去分析
  - 防抖：同一个 commit 只处理一次（用 last_processed_commit 记忆）
"""

import subprocess
import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List, Set


class MineSeedScanner:
    """
    矿场扫描器 — 向其他智能体学习的入口
    """

    def __init__(
        self,
        mine_seed_path: str,
        state_file: Optional[str] = None,
        max_new_commits: int = 5,
    ):
        self.mine_seed_path = Path(mine_seed_path)
        self.state_file = Path(state_file) if state_file else None
        self.max_new_commits = max_new_commits
        self._last_commit: Optional[str] = None
        self._processed_commits: Set[str] = set()
        self._load_state()

    def _load_state(self):
        if self.state_file and self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._last_commit = data.get("last_commit")
                    self._processed_commits = set(data.get("processed_commits", []))
            except Exception:
                pass

    def _save_state(self):
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "last_commit": self._last_commit,
                        "processed_commits": list(self._processed_commits),
                    },
                    f,
                    ensure_ascii=False,
                )
        except Exception:
            pass

    def _run_git(self, *args) -> str:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git"] + list(args),
            cwd=str(self.mine_seed_path),
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip()[:200])
        return result.stdout.strip()

    def fetch_and_get_new_commits(self, remote: str = "origin") -> List[Dict[str, str]]:
        """拉取远程更新，返回新的 commit 列表"""
        try:
            self._run_git("fetch", remote)
        except Exception:
            return []

        if not self._last_commit:
            try:
                current = self._run_git("rev-parse", f"{remote}/main")
                self._last_commit = current
                return []
            except Exception:
                return []

        try:
            newer_commits = self._run_git(
                "log", "--format=%H|%s|%an", f"{self._last_commit}..{remote}/main"
            )
        except Exception:
            return []

        if not newer_commits.strip():
            return []

        commits = []
        for line in newer_commits.strip().split("\n"):
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                commits.append({
                    "hash": parts[0],
                    "subject": parts[1],
                    "author": parts[2],
                })
        return commits[: self.max_new_commits]

    def get_commit_files(self, commit_hash: str) -> List[str]:
        """获取某个 commit 变更的文件列表"""
        try:
            result = self._run_git("show", "--format=", "--name-only", commit_hash)
            return [f for f in result.strip().split("\n") if f.strip()]
        except Exception:
            return []

    def get_file_content(self, commit_hash: str, file_path: str) -> str:
        """获取某个 commit 中某个文件的内容（前 3KB）"""
        try:
            result = self._run_git("show", f"{commit_hash}:{file_path}")
            return result[: 3 * 1024]
        except Exception:
            return ""

    def scan_and_create_tasks(
        self, task_pool, max_tasks: int = 2
    ) -> Dict[str, Any]:
        """
        扫描 mine-seed 新 commit，为新发现创建考古任务
        """
        result = {
            "fetched": False,
            "new_commits": 0,
            "tasks_created": 0,
            "commits": [],
            "error": None,
        }

        if not self.mine_seed_path.exists():
            result["error"] = "mine_seed_not_found"
            return result

        try:
            commits = self.fetch_and_get_new_commits()
            result["fetched"] = True
            result["new_commits"] = len(commits)
            result["commits"] = commits
        except Exception as e:
            result["error"] = str(e)
            return result

        if not commits:
            return result

        tasks = []
        for commit in commits:
            h = commit["hash"]
            if h in self._processed_commits:
                continue

            files = self.get_commit_files(h)
            md_files = [f for f in files if f.endswith(".md")]

            if not md_files:
                self._processed_commits.add(h)
                continue

            task = self._create_cross_agent_task(commit, md_files, task_pool)
            if task:
                tasks.append(task)
                self._processed_commits.add(h)

            if len(tasks) >= max_tasks:
                break

        result["tasks_created"] = len(tasks)
        result["tasks"] = [
            {"hash": t.task_id, "title": t.title} for t in tasks
        ]

        if commits:
            self._last_commit = commits[0]["hash"]
        self._save_state()

        return result

    def _create_cross_agent_task(
        self, commit: Dict[str, Any], md_files: List[str], task_pool
    ) -> Optional[Any]:
        """为跨智能体发现创建考古任务"""
        h = commit["hash"]
        subject = commit["subject"]
        author = commit["author"]

        title = f"跨智能体考古: {author} — {subject[:60]}"

        hypothesis = (
            f"mine-seed 上 {author} 提交了新发现（commit: {h[:8]}）。"
            f"主题：{subject}。"
            f"涉及 {len(md_files)} 个 .md 文件。"
            f"需要对比我的工作，分析 Gap 和补充可能。"
        )

        tags = ["cross_agent", "mine_seed", f"author:{author}"]

        try:
            task = task_pool.create_task(
                title=title,
                hypothesis=hypothesis,
                creator="mine_seed_scanner",
                priority="medium",
                tags=tags,
            )
            if task:
                task.outputs = {
                    "commit_hash": h,
                    "commit_subject": subject,
                    "commit_author": author,
                    "md_files": md_files,
                }
                task_pool.update_task(task)
            return task
        except Exception:
            return None
