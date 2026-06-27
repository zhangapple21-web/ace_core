"""
仓库同步器 — 自动提交并推送考古产物到 GitHub

流程：
1. 检查目标目录是否有变更
2. git add 变更文件
3. git commit（自动生成提交信息）
4. git push origin main
"""

import subprocess
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional


class RepoSyncer:
    """Git 仓库同步器"""

    def __init__(self, repo_path: str, branch: str = "main", remote: str = "origin"):
        self.repo_path = Path(repo_path)
        self.branch = branch
        self.remote = remote

    def has_changes(self, subdir: Optional[str] = None) -> bool:
        """检查是否有未提交的变更"""
        try:
            result = self._run_git("status", "--porcelain", subdir or ".")
            return bool(result.strip())
        except Exception:
            return False

    def get_changed_files(self, subdir: Optional[str] = None) -> list:
        """获取变更文件列表"""
        try:
            result = self._run_git("status", "--porcelain", subdir or ".")
            files = []
            for line in result.strip().split("\n"):
                if line.strip():
                    status = line[:2].strip()
                    filepath = line[3:].strip()
                    files.append({"status": status, "file": filepath})
            return files
        except Exception:
            return []

    def sync(
        self,
        commit_message: Optional[str] = None,
        subdir: Optional[str] = None,
        push: bool = True,
    ) -> Dict[str, Any]:
        """
        执行完整同步：add → commit → push

        返回同步结果字典。
        """
        result = {
            "repo": str(self.repo_path),
            "branch": self.branch,
            "started_at": datetime.now().isoformat(),
            "changed_files": [],
            "added": False,
            "committed": False,
            "pushed": False,
            "commit_hash": None,
            "error": None,
        }

        try:
            changed = self.get_changed_files(subdir)
            result["changed_files"] = changed

            if not changed:
                result["error"] = "no_changes"
                return result

            add_target = subdir or "."
            self._run_git("add", add_target)
            result["added"] = True

            if not commit_message:
                today = datetime.now().strftime("%Y-%m-%d")
                result["commit_message"] = (
                    f"r1_archaeology: 自动同步考古产物 - {today} "
                    f"({len(changed)} 个文件变更)"
                )
            else:
                result["commit_message"] = commit_message

            commit_out = self._run_git(
                "commit", "-m", result["commit_message"]
            )
            result["committed"] = True

            for line in commit_out.strip().split("\n"):
                if line.startswith("[") and "]" in line:
                    parts = line.split("]")[0].split(" ")
                    if len(parts) >= 2:
                        result["commit_hash"] = parts[-1]
                    break

            if push:
                self._run_git("push", self.remote, self.branch)
                result["pushed"] = True

        except subprocess.CalledProcessError as e:
            result["error"] = f"{e.cmd}: {e.stderr or e.stdout}"
        except Exception as e:
            result["error"] = str(e)

        result["finished_at"] = datetime.now().isoformat()
        return result

    def _run_git(self, *args: str) -> str:
        """执行 git 命令，返回 stdout"""
        cmd = ["git"] + list(args)
        result = subprocess.run(
            cmd,
            cwd=str(self.repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, cmd,
                output=result.stdout,
                stderr=result.stderr,
            )
        return result.stdout

    def pull(self) -> Dict[str, Any]:
        """从远程拉取最新代码"""
        result = {"pulled": False, "error": None}
        try:
            self._run_git("pull", self.remote, self.branch)
            result["pulled"] = True
        except Exception as e:
            result["error"] = str(e)
        return result
