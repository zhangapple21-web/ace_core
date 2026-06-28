"""
Sync Manager — Repository Curator 的执行手

职责边界（极度受限）：
  ✓ 只执行来自 Repository Curator 的指令
  ✓ 验证 sync plan 签名
  ✓ 批量合并相关文件到单次提交
  ✓ 执行 git add / commit / push
  ✓ 记录同步日志
  ✗ 不自己做决策
  ✗ 不接受其他 Agent 的直接调用
  ✗ 不主动同步

设计原则：
  - Curator 的每一条指令都必须来自 sync plan
  - 不接受即兴同步（no ad-hoc sync）
  - 合并同类型的多个文件到单次提交（减少碎片提交）
  - 防抖：同类提交 60 分钟内只执行一次

权限验证：
  - 每个 sync plan 必须包含 curator_signature
  - 签名 = sha256(curator_id + timestamp + plan_hash)
  - 没有有效签名的 plan 一律拒绝执行
"""

import json
import subprocess
import hashlib
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """同步执行结果"""
    success: bool
    repo: str
    action: str  # create / update / merge / discard
    files: List[str]
    commit_hash: Optional[str]
    error: Optional[str]
    duration_ms: float


class SyncManager:
    """
    同步执行器 — Curator 的手

    只做一件事：
      执行 Curator 生成的 Sync Plan

    防抖机制：
      - 同一仓库的同步，60 分钟内最多执行一次
      - 合并多个同类操作为单次提交
    """

    def __init__(
        self,
        data_dir: str = None,
        debounce_minutes: int = 60,
        curator_id: str = "ace_runtime_curator",
        curator_secret: str = "curator_secret_key",  # 本地验证用
    ):
        if data_dir is None:
            base = Path(__file__).resolve().parent.parent
            data_dir = base / "06_RUNTIME" / "ace" / "data" / "sync_manager"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.debounce_minutes = debounce_minutes
        self.curator_id = curator_id
        self.curator_secret = curator_secret

        self.last_sync_file = self.data_dir / "last_sync.json"
        self.sync_log_file = self.data_dir / "sync_log.jsonl"
        self._last_sync = self._load_last_sync()

    def _load_last_sync(self) -> Dict:
        if self.last_sync_file.exists():
            try:
                return json.load(open(self.last_sync_file, "r", encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_last_sync(self):
        with open(self.last_sync_file, "w", encoding="utf-8") as f:
            json.dump(self._last_sync, f, ensure_ascii=False)

    def _generate_signature(self, plan_hash: str, timestamp: str) -> str:
        """生成 sync plan 签名"""
        raw = f"{self.curator_id}:{timestamp}:{plan_hash}:{self.curator_secret}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _verify_signature(self, plan: Dict) -> bool:
        """验证 sync plan 签名"""
        plan_hash = plan.get("plan_hash", "")
        timestamp = plan.get("timestamp", "")
        signature = plan.get("curator_signature", "")

        if not plan_hash or not timestamp or not signature:
            logger.warning("Sync plan 缺少签名字段，拒绝执行")
            return False

        expected = self._generate_signature(plan_hash, timestamp)
        if expected != signature:
            logger.warning(f"Sync plan 签名不匹配: expected={expected}, got={signature}")
            return False
        return True

    def _is_debounced(self, repo: str) -> bool:
        """检查是否在防抖期内"""
        if repo not in self._last_sync:
            return False
        last = self._last_sync[repo]
        last_time = datetime.fromisoformat(last["timestamp"])
        elapsed = (datetime.now() - last_time).total_seconds() / 60
        if elapsed < self.debounce_minutes:
            logger.info(f"仓库 {repo} 防抖期内（已同步 {elapsed:.0f} 分钟前），跳过")
            return True
        return False

    def _run_git(self, cwd: str, *args) -> tuple:
        """执行 git 命令"""
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, "", str(e)

    def execute_plan(self, sync_plan: Dict) -> List[SyncResult]:
        """
        执行同步计划

        Args:
            sync_plan: 来自 Curator 的同步计划

        Returns:
            List[SyncResult]: 每个仓库的执行结果
        """
        # 验证签名
        if not self._verify_signature(sync_plan):
            logger.error("Sync plan 签名验证失败，拒绝执行")
            return [SyncResult(
                success=False, repo="*", action="verify",
                files=[], commit_hash=None,
                error="签名验证失败：plan 可能被篡改或过期",
                duration_ms=0,
            )]

        # 防抖检查
        decisions = sync_plan.get("decisions", [])
        repos_to_sync = set()
        for d in decisions:
            if d.get("action") in ("create", "update", "merge"):
                repos_to_sync.add(d.get("target_repo", ""))

        debounced = [r for r in repos_to_sync if self._is_debounced(r)]
        if debounced:
            logger.info(f"防抖跳过: {debounced}")

        results = []
        start = time.time()

        for repo, operations in self._group_by_repo(decisions).items():
            if repo in debounced:
                results.append(SyncResult(
                    success=True, repo=repo, action="debounced",
                    files=[], commit_hash=None, error=None,
                    duration_ms=0,
                ))
                continue

            result = self._sync_repo(repo, operations, sync_plan)
            results.append(result)

            # 更新防抖记录
            if result.success:
                self._last_sync[repo] = {
                    "timestamp": datetime.now().isoformat(),
                    "commit": result.commit_hash,
                    "files": len(result.files),
                }
                self._save_last_sync()

            # 记录日志
            self._log_sync(result)

        return results

    def _group_by_repo(self, decisions: List[Dict]) -> Dict[str, List[Dict]]:
        """按仓库分组操作"""
        grouped = {}
        for d in decisions:
            if d.get("action") not in ("create", "update", "merge"):
                continue
            repo = d.get("target_repo", "unknown")
            grouped.setdefault(repo, []).append(d)
        return grouped

    def _sync_repo(self, repo: str, operations: List[Dict], plan: Dict) -> SyncResult:
        """同步单个仓库"""
        import shutil
        start = time.time()
        repo_map = {
            "mine-seed": "C:\\Users\\USER\\.trae\\work\\6a3be8d2084d33999ccdf8c7\\repos\\mine-seed",
            "ace-core": "C:\\Users\\USER\\Downloads\\Telegram Desktop\\ace_runtime",
        }
        repo_dir = Path(repo_map.get(repo, repo))
        if not repo_dir.exists():
            return SyncResult(
                success=False, repo=repo, action="sync",
                files=[], commit_hash=None,
                error=f"仓库目录不存在: {repo_dir}",
                duration_ms=(time.time() - start) * 1000,
            )

        files_to_add = []
        files_removed = []

        for op in operations:
            action = op.get("action", "")
            src = op.get("source_path", "")
            dst = op.get("target_path", "")

            if action == "create" and src:
                dst_full = repo_dir / dst
                src_full = Path(src)

                # 跳过同一仓库内的相同文件（src == dst）
                try:
                    if src_full.resolve() == dst_full.resolve():
                        logger.info(f"[Sync] SKIP (same file): {dst}")
                        continue
                except Exception:
                    pass

                if src_full.exists():
                    dst_full.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_full, dst_full)
                    files_to_add.append(str(dst_full.relative_to(repo_dir)))
                    logger.info(f"[Sync] CREATE: {dst}")

            elif action == "update" and src:
                dst_full = repo_dir / dst
                src_full = Path(src)
                if src_full.exists():
                    dst_full.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src_full, dst_full)
                    files_to_add.append(str(dst_full.relative_to(repo_dir)))
                    logger.info(f"[Sync] UPDATE: {dst}")

            elif action == "merge" and src:
                # 合并多个源文件到一个目标
                src_files = op.get("source_files", [])
                if isinstance(src_files, str):
                    src_files = [src_files]
                dst_full = repo_dir / dst
                dst_full.parent.mkdir(parents=True, exist_ok=True)
                merged = []
                for sf in src_files:
                    sf_path = Path(sf)
                    if sf_path.exists():
                        merged.append(f"=== 来源: {sf_path.name} ===\n")
                        merged.append(sf_path.read_text(encoding="utf-8"))
                        merged.append("\n\n")
                dst_full.write_text("\n".join(merged), encoding="utf-8")
                files_to_add.append(str(dst_full.relative_to(repo_dir)))
                logger.info(f"[Sync] MERGE: {dst} ({len(src_files)} sources)")

        if not files_to_add:
            return SyncResult(
                success=True, repo=repo, action="noop",
                files=[], commit_hash=None, error=None,
                duration_ms=(time.time() - start) * 1000,
            )

        # Git add
        for f in files_to_add:
            self._run_git(str(repo_dir), "add", f)

        # Git commit（批量合并为一次）
        commit_msg = self._build_commit_message(repo, operations)
        code, stdout, stderr = self._run_git(str(repo_dir), "commit", "-m", commit_msg)
        commit_hash = None
        if code == 0:
            # 提取 commit hash
            for line in stdout.split("\n"):
                if line.strip().startswith("["):
                    parts = line.split()
                    if len(parts) >= 2:
                        commit_hash = parts[1].rstrip("]")
                        break
            logger.info(f"[Sync] COMMIT: {commit_hash} - {commit_msg[:50]}")
        else:
            logger.warning(f"[Sync] COMMIT failed: {stderr[:200]}")

        # Git push（如果配置了远程）
        if commit_hash and self._has_remote(repo_dir):
            push_code, push_out, push_err = self._run_git(str(repo_dir), "push")
            if push_code != 0:
                logger.warning(f"[Sync] PUSH failed: {push_err[:200]}")
                return SyncResult(
                    success=False, repo=repo, action="sync",
                    files=files_to_add, commit_hash=commit_hash,
                    error=f"Push failed: {push_err[:200]}",
                    duration_ms=(time.time() - start) * 1000,
                )

        return SyncResult(
            success=True, repo=repo, action="sync",
            files=files_to_add, commit_hash=commit_hash, error=None,
            duration_ms=(time.time() - start) * 1000,
        )

    def _build_commit_message(self, repo: str, operations: List[Dict]) -> str:
        """构建清晰的提交信息"""
        action_count = {}
        for op in operations:
            a = op.get("action", "?")
            action_count[a] = action_count.get(a, 0) + 1

        parts = []
        for action, count in sorted(action_count.items()):
            label = {"create": "新增", "update": "更新", "merge": "合并"}.get(action, action)
            parts.append(f"{label} {count} 个文件")

        today = datetime.now().strftime("%Y-%m-%d")
        return f"[Curator] {today} - {' / '.join(parts)}"

    def _has_remote(self, repo_dir: Path) -> bool:
        """检查仓库是否有远程配置"""
        code, stdout, _ = self._run_git(str(repo_dir), "remote", "-v")
        return code == 0 and bool(stdout.strip())

    def _log_sync(self, result: SyncResult):
        """记录同步日志"""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "success": result.success,
            "repo": result.repo,
            "action": result.action,
            "files": result.files,
            "commit_hash": result.commit_hash,
            "error": result.error,
            "duration_ms": round(result.duration_ms, 1),
        }
        try:
            with open(self.sync_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_stats(self) -> Dict[str, Any]:
        """获取同步统计"""
        total = 0
        successful = 0
        by_repo = {}
        if self.sync_log_file.exists():
            try:
                with open(self.sync_log_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            entry = json.loads(line)
                            total += 1
                            if entry.get("success"):
                                successful += 1
                            repo = entry.get("repo", "unknown")
                            by_repo[repo] = by_repo.get(repo, 0) + 1
                        except Exception:
                            pass
            except Exception:
                pass
        return {
            "total_syncs": total,
            "successful": successful,
            "failed": total - successful,
            "by_repo": by_repo,
            "last_sync": self._last_sync,
        }
