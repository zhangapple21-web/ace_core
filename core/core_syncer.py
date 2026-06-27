"""
核心代码同步器 — CoreSyncer

职责：
  每次任务归档后，自动将 core/、06_RUNTIME/、08_ARCHAEOLOGY/ 中的 .py 文件
  同步到独立的 ace_core 仓库（与 mine-seed 分开）。

推送规则：
  - 只推送 .py 文件
  - 目录：core/, 06_RUNTIME/, 08_ARCHAEOLOGY/
  - Debounce：距离上次推送 < DEBOUNCE_MINUTES 时，不推送
  - 推送失败不阻塞主循环，只记录错误

防抖理由：
  不要因为每次小变更就触发推送。
  积累一批变更再推送，降低 GitHub API 消耗。
"""

import subprocess
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, Optional


class CoreSyncer:
    """
    核心代码同步器 — push to ace_core remote
    """

    def __init__(
        self,
        repo_path: str,
        remote: str = "ace-core",
        branch: str = "main",
        debounce_minutes: int = 60,
    ):
        self.repo_path = Path(repo_path)
        self.remote = remote
        self.branch = branch
        self.debounce_minutes = debounce_minutes
        self._state_file = self.repo_path / ".core_sync_state.json"
        self._last_push: Optional[str] = None
        self._load_state()

    def _load_state(self):
        if self._state_file.exists():
            try:
                import json
                with open(self._state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._last_push = data.get("last_push")
            except Exception:
                pass

    def _save_state(self):
        try:
            import json
            with open(self._state_file, "w", encoding="utf-8") as f:
                json.dump({"last_push": self._last_push}, f)
        except Exception:
            pass

    def _run_git(self, *args) -> str:
        env = os.environ.copy()
        env["GIT_TERMINAL_PROMPT"] = "0"
        result = subprocess.run(
            ["git"] + list(args),
            cwd=self.repo_path,
            capture_output=True,
            text=True,
            env=env,
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip())
        return result.stdout.strip()

    def has_core_changes(self) -> bool:
        """检查核心代码目录是否有变更"""
        dirs_to_check = ["core", "06_RUNTIME", "08_ARCHAEOLOGY"]
        try:
            result = self._run_git(
                "status", "--porcelain",
                *[d + "/" for d in dirs_to_check]
            )
            return bool(result.strip())
        except Exception:
            return False

    def get_changed_files(self) -> list:
        """获取变更的 Python 文件列表"""
        changed = []
        for subdir in ["core", "06_RUNTIME", "08_ARCHAEOLOGY"]:
            d = self.repo_path / subdir
            if not d.exists():
                continue
            try:
                result = self._run_git(
                    "status", "--porcelain", subdir + "/",
                )
                for line in result.strip().split("\n"):
                    if line and line[0] in ("M", "A", "??"):
                        filepath = line[3:].strip()
                        if filepath.endswith(".py"):
                            changed.append(filepath)
            except Exception:
                pass
        return changed

    def should_push(self) -> bool:
        """检查是否应该推送（debounce）"""
        if not self._last_push:
            return True
        try:
            last = datetime.fromisoformat(self._last_push)
            elapsed = datetime.now() - last
            return elapsed.total_seconds() >= self.debounce_minutes * 60
        except Exception:
            return True

    def sync(self, force: bool = False) -> Dict[str, Any]:
        """
        执行同步：add → commit → push
        """
        result = {
            "repo": str(self.repo_path),
            "remote": self.remote,
            "branch": self.branch,
            "at": datetime.now().isoformat(),
            "changed_files": [],
            "added": False,
            "committed": False,
            "pushed": False,
            "commit_hash": None,
            "error": None,
            "skipped": False,
        }

        try:
            changed = self.get_changed_files()
            result["changed_files"] = changed

            if not changed:
                result["error"] = "no_changes"
                return result

            if not force and not self.should_push():
                result["skipped"] = True
                result["error"] = "debounced"
                return result

            for subdir in ["core", "06_RUNTIME", "08_ARCHAEOLOGY"]:
                d = self.repo_path / subdir
                if d.exists():
                    self._run_git("add", subdir + "/")

            today = datetime.now().strftime("%Y-%m-%d %H:%M")
            files_summary = ", ".join(changed[:5])
            if len(changed) > 5:
                files_summary += f" ... +{len(changed) - 5}"
            commit_msg = f"core: auto-sync {today}\n\nFiles: {files_summary}"

            self._run_git("commit", "-m", commit_msg)
            result["committed"] = True

            self._run_git("push", self.remote, self.branch)
            result["pushed"] = True

            self._last_push = datetime.now().isoformat()
            self._save_state()

            result["commit_hash"] = self._run_git("rev-parse", "HEAD")[:8]

        except Exception as e:
            result["error"] = str(e)

        return result
