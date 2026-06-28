"""
执行契约 — SyncManager 执行层接口规范

定义同步执行过程中的核心数据结构和接口契约：
- 执行操作类型
- 执行结果追踪
- 防抖机制
- Git 操作封装
- 执行日志审计

设计原则：
  1. 只执行不决策 — 严格按照 Sync Plan 执行，不做任何即兴操作
  2. 签名验证 — 每个 plan 必须有有效馆长签名
  3. 防抖保护 — 同仓库 60 分钟内最多同步一次
  4. 批量提交 — 同类操作合并为单次 git commit
  5. 全链路可追溯 — 每个操作都有日志记录
"""

import json
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import List, Dict, Any, Optional, Protocol, runtime_checkable


logger = logging.getLogger(__name__)


class SyncAction(str, Enum):
    """同步动作枚举"""
    CREATE = "create"
    UPDATE = "update"
    MERGE = "merge"
    DISCARD = "discard"
    SPLIT = "split"
    ARCHIVE = "archive"
    DELETE = "delete"
    NOOP = "noop"


class SyncStatus(str, Enum):
    """同步状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DEBOUNCED = "debounced"
    VERIFY_FAILED = "verify_failed"


class RepoType(str, Enum):
    """仓库类型枚举"""
    MINE_SEED = "mine-seed"
    ACE_CORE = "ace-core"
    CUSTOM = "custom"


@dataclass
class SyncOperation:
    """
    单个同步操作

    对应 SyncPlan 中的一个决策，是执行的最小单元。
    """
    operation_id: str
    action: SyncAction
    source_path: str = ""
    target_path: str = ""
    target_repo: str = ""
    artifact_id: str = ""
    artifact_title: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> bool:
        """
        验证操作的完整性

        Returns:
            是否通过验证
        """
        if not self.operation_id:
            return False
        if not isinstance(self.action, SyncAction):
            return False
        if self.action in (SyncAction.CREATE, SyncAction.UPDATE, SyncAction.MERGE):
            if not self.source_path or not self.target_path:
                return False
            if not self.target_repo:
                return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "operation_id": self.operation_id,
            "action": self.action.value if isinstance(self.action, SyncAction) else self.action,
            "source_path": self.source_path,
            "target_path": self.target_path,
            "target_repo": self.target_repo,
            "artifact_id": self.artifact_id,
            "artifact_title": self.artifact_title,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncOperation":
        """从字典反序列化"""
        action = data.get("action", "create")
        if isinstance(action, str):
            try:
                action = SyncAction(action)
            except ValueError:
                action = SyncAction.NOOP

        return cls(
            operation_id=data.get("operation_id", ""),
            action=action,
            source_path=data.get("source_path", ""),
            target_path=data.get("target_path", ""),
            target_repo=data.get("target_repo", ""),
            artifact_id=data.get("artifact_id", ""),
            artifact_title=data.get("artifact_title", ""),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SyncResult:
    """
    单仓库同步执行结果

    记录一个仓库的同步执行结果，包括成功/失败状态、
    涉及文件、commit hash、错误信息等。
    """
    success: bool
    repo: str
    action: SyncAction
    files: List[str] = field(default_factory=list)
    commit_hash: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    started_at: str = ""
    finished_at: str = ""
    operations_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "success": self.success,
            "repo": self.repo,
            "action": self.action.value if isinstance(self.action, SyncAction) else self.action,
            "files": self.files,
            "commit_hash": self.commit_hash,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "operations_count": self.operations_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncResult":
        """从字典反序列化"""
        action = data.get("action", "noop")
        if isinstance(action, str):
            try:
                action = SyncAction(action)
            except ValueError:
                action = SyncAction.NOOP

        return cls(
            success=data.get("success", False),
            repo=data.get("repo", ""),
            action=action,
            files=data.get("files", []),
            commit_hash=data.get("commit_hash"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0.0),
            started_at=data.get("started_at", ""),
            finished_at=data.get("finished_at", ""),
            operations_count=data.get("operations_count", 0),
        )


@dataclass
class LastSyncRecord:
    """
    最近一次同步记录

    用于防抖机制，记录每个仓库最近一次同步的时间和结果。
    """
    repo: str
    timestamp: str
    commit: Optional[str] = None
    files_count: int = 0
    success: bool = True

    def is_within_debounce(self, debounce_minutes: int) -> bool:
        """
        检查是否在防抖期内

        Args:
            debounce_minutes: 防抖分钟数

        Returns:
            是否在防抖期内
        """
        try:
            last_time = datetime.fromisoformat(self.timestamp)
            elapsed = (datetime.now() - last_time).total_seconds() / 60
            return elapsed < debounce_minutes
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "repo": self.repo,
            "timestamp": self.timestamp,
            "commit": self.commit,
            "files_count": self.files_count,
            "success": self.success,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LastSyncRecord":
        """从字典反序列化"""
        return cls(
            repo=data.get("repo", ""),
            timestamp=data.get("timestamp", ""),
            commit=data.get("commit"),
            files_count=data.get("files_count", 0),
            success=data.get("success", True),
        )


@dataclass
class SyncLogEntry:
    """
    同步日志条目

    记录每一次同步执行的完整信息，用于审计和追溯。
    """
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = False
    repo: str = ""
    action: str = ""
    files: List[str] = field(default_factory=list)
    commit_hash: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    plan_id: str = ""
    operations_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "timestamp": self.timestamp,
            "success": self.success,
            "repo": self.repo,
            "action": self.action,
            "files": self.files,
            "commit_hash": self.commit_hash,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 1),
            "plan_id": self.plan_id,
            "operations_count": self.operations_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncLogEntry":
        """从字典反序列化"""
        return cls(
            timestamp=data.get("timestamp", ""),
            success=data.get("success", False),
            repo=data.get("repo", ""),
            action=data.get("action", ""),
            files=data.get("files", []),
            commit_hash=data.get("commit_hash"),
            error=data.get("error"),
            duration_ms=data.get("duration_ms", 0.0),
            plan_id=data.get("plan_id", ""),
            operations_count=data.get("operations_count", 0),
        )


@dataclass
class SyncPlanVerification:
    """
    Sync Plan 验证结果

    记录对 Sync Plan 的签名验证结果。
    """
    valid: bool
    reason: str = ""
    plan_hash: str = ""
    expected_signature: str = ""
    actual_signature: str = ""
    timestamp_valid: bool = True
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "valid": self.valid,
            "reason": self.reason,
            "plan_hash": self.plan_hash,
            "expected_signature": self.expected_signature,
            "actual_signature": self.actual_signature,
            "timestamp_valid": self.timestamp_valid,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SyncPlanVerification":
        """从字典反序列化"""
        return cls(
            valid=data.get("valid", False),
            reason=data.get("reason", ""),
            plan_hash=data.get("plan_hash", ""),
            expected_signature=data.get("expected_signature", ""),
            actual_signature=data.get("actual_signature", ""),
            timestamp_valid=data.get("timestamp_valid", True),
            timestamp=data.get("timestamp", ""),
        )


@runtime_checkable
class ISyncExecutor(Protocol):
    """
    同步执行器接口协议

    定义 SyncManager 必须实现的核心接口。
    任何实现此协议的类都可以作为同步执行器使用。
    """

    def verify_plan(self, sync_plan: Dict[str, Any]) -> SyncPlanVerification:
        """
        验证同步计划的签名和完整性

        Args:
            sync_plan: 待验证的同步计划字典

        Returns:
            SyncPlanVerification 验证结果
        """
        ...

    def execute_plan(self, sync_plan: Dict[str, Any]) -> List[SyncResult]:
        """
        执行同步计划

        Args:
            sync_plan: 经过验证的同步计划字典

        Returns:
            每个仓库的执行结果列表
        """
        ...

    def is_debounced(self, repo: str) -> bool:
        """
        检查仓库是否在防抖期内

        Args:
            repo: 仓库名称

        Returns:
            是否在防抖期内
        """
        ...

    def get_stats(self) -> Dict[str, Any]:
        """
        获取同步统计信息

        Returns:
            统计数据字典
        """
        ...


@runtime_checkable
class IGitOperator(Protocol):
    """
    Git 操作器接口协议

    定义底层 Git 操作的接口，便于替换实现或进行 mock 测试。
    """

    def run_git(self, repo_dir: str, *args: str) -> tuple[int, str, str]:
        """
        执行 Git 命令

        Args:
            repo_dir: 仓库目录
            *args: Git 命令参数

        Returns:
            (return_code, stdout, stderr)
        """
        ...

    def add_files(self, repo_dir: str, files: List[str]) -> bool:
        """
        Git add 文件

        Args:
            repo_dir: 仓库目录
            files: 相对路径文件列表

        Returns:
            是否成功
        """
        ...

    def commit(self, repo_dir: str, message: str) -> tuple[bool, Optional[str]]:
        """
        Git commit

        Args:
            repo_dir: 仓库目录
            message: 提交信息

        Returns:
            (是否成功, commit_hash)
        """
        ...

    def push(self, repo_dir: str) -> bool:
        """
        Git push

        Args:
            repo_dir: 仓库目录

        Returns:
            是否成功
        """
        ...

    def has_remote(self, repo_dir: str) -> bool:
        """
        检查仓库是否配置了远程

        Args:
            repo_dir: 仓库目录

        Returns:
            是否有远程配置
        """
        ...


class GitOperator:
    """
    默认 Git 操作器实现

    使用 subprocess 调用系统 git 命令。
    """

    def __init__(self, timeout: int = 120):
        """
        初始化 Git 操作器

        Args:
            timeout: Git 命令超时时间（秒）
        """
        self.timeout = timeout

    def run_git(self, repo_dir: str, *args: str) -> tuple[int, str, str]:
        """
        执行 Git 命令

        Args:
            repo_dir: 仓库目录
            *args: Git 命令参数

        Returns:
            (return_code, stdout, stderr)
        """
        import subprocess

        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            return result.returncode, result.stdout, result.stderr
        except Exception as e:
            return -1, "", str(e)

    def add_files(self, repo_dir: str, files: List[str]) -> bool:
        """
        Git add 文件

        Args:
            repo_dir: 仓库目录
            files: 相对路径文件列表

        Returns:
            是否全部成功
        """
        all_success = True
        for f in files:
            code, _, _ = self.run_git(repo_dir, "add", f)
            if code != 0:
                all_success = False
        return all_success

    def commit(self, repo_dir: str, message: str) -> tuple[bool, Optional[str]]:
        """
        Git commit

        Args:
            repo_dir: 仓库目录
            message: 提交信息

        Returns:
            (是否成功, commit_hash)
        """
        code, stdout, stderr = self.run_git(repo_dir, "commit", "-m", message)
        if code != 0:
            logger.warning(f"Git commit failed: {stderr[:200]}")
            return False, None

        commit_hash = None
        for line in stdout.split("\n"):
            if line.strip().startswith("["):
                parts = line.split()
                if len(parts) >= 2:
                    commit_hash = parts[1].rstrip("]")
                    break
        return True, commit_hash

    def push(self, repo_dir: str) -> bool:
        """
        Git push

        Args:
            repo_dir: 仓库目录

        Returns:
            是否成功
        """
        code, _, stderr = self.run_git(repo_dir, "push")
        if code != 0:
            logger.warning(f"Git push failed: {stderr[:200]}")
            return False
        return True

    def has_remote(self, repo_dir: str) -> bool:
        """
        检查仓库是否配置了远程

        Args:
            repo_dir: 仓库目录

        Returns:
            是否有远程配置
        """
        code, stdout, _ = self.run_git(repo_dir, "remote", "-v")
        return code == 0 and bool(stdout.strip())


class SyncExecutionContract:
    """
    同步执行契约 — 执行层规范实现

    封装 SyncManager 执行过程的所有数据结构和验证逻辑，
    确保执行过程的安全性和可追溯性。

    核心约束：
      - 只执行来自 Curator 的签名计划
      - 同仓库 60 分钟内最多同步一次
      - 批量合并同类操作为单次提交
      - 完整记录所有执行日志

    使用示例:
        contract = SyncExecutionContract(
            curator_id="ace_runtime_curator",
            curator_secret="secret_key",
            debounce_minutes=60,
        )
        verification = contract.verify_plan(sync_plan_dict)
        if verification.valid:
            results = contract.execute_plan(sync_plan_dict, repo_map, git_operator)
    """

    def __init__(
        self,
        curator_id: str = "ace_runtime_curator",
        curator_secret: str = "curator_secret_key",
        debounce_minutes: int = 60,
        data_dir: Optional[str] = None,
    ):
        """
        初始化执行契约

        Args:
            curator_id: 馆长标识符
            curator_secret: 馆长密钥（用于签名验证）
            debounce_minutes: 防抖分钟数
            data_dir: 数据存储目录
        """
        self.curator_id = curator_id
        self.curator_secret = curator_secret
        self.debounce_minutes = debounce_minutes

        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(__file__).resolve().parent.parent.parent / "06_RUNTIME" / "ace" / "data" / "sync_manager"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.last_sync_file = self.data_dir / "last_sync.json"
        self.sync_log_file = self.data_dir / "sync_log.jsonl"
        self._last_sync: Dict[str, LastSyncRecord] = self._load_last_sync()

    def _load_last_sync(self) -> Dict[str, LastSyncRecord]:
        """加载最近同步记录"""
        if self.last_sync_file.exists():
            try:
                with open(self.last_sync_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return {
                    repo: LastSyncRecord.from_dict(record)
                    for repo, record in data.items()
                }
            except Exception:
                logger.warning("加载最近同步记录失败，使用空记录")
        return {}

    def _save_last_sync(self):
        """保存最近同步记录"""
        data = {
            repo: record.to_dict()
            for repo, record in self._last_sync.items()
        }
        try:
            with open(self.last_sync_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存最近同步记录失败: {e}")

    def _generate_signature(self, plan_hash: str, timestamp: str) -> str:
        """
        生成签名

        Args:
            plan_hash: 计划哈希
            timestamp: 时间戳

        Returns:
            签名字符串
        """
        raw = f"{self.curator_id}:{timestamp}:{plan_hash}:{self.curator_secret}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def verify_plan(self, sync_plan: Dict[str, Any]) -> SyncPlanVerification:
        """
        验证同步计划的签名和完整性

        Args:
            sync_plan: 待验证的同步计划字典

        Returns:
            SyncPlanVerification 验证结果
        """
        plan_hash = sync_plan.get("plan_hash", "")
        timestamp = sync_plan.get("timestamp", "")
        signature = sync_plan.get("curator_signature", "")
        plan_curator_id = sync_plan.get("curator_id", "")

        if not plan_hash or not timestamp or not signature:
            return SyncPlanVerification(
                valid=False,
                reason="缺少必要签名字段（plan_hash / timestamp / curator_signature）",
                plan_hash=plan_hash,
                actual_signature=signature,
                timestamp=timestamp,
            )

        if plan_curator_id and plan_curator_id != self.curator_id:
            return SyncPlanVerification(
                valid=False,
                reason=f"馆长ID不匹配: expected={self.curator_id}, got={plan_curator_id}",
                plan_hash=plan_hash,
                actual_signature=signature,
                timestamp=timestamp,
            )

        expected = self._generate_signature(plan_hash, timestamp)
        if expected != signature:
            return SyncPlanVerification(
                valid=False,
                reason="签名不匹配",
                plan_hash=plan_hash,
                expected_signature=expected,
                actual_signature=signature,
                timestamp=timestamp,
            )

        return SyncPlanVerification(
            valid=True,
            reason="验证通过",
            plan_hash=plan_hash,
            expected_signature=expected,
            actual_signature=signature,
            timestamp_valid=True,
            timestamp=timestamp,
        )

    def is_debounced(self, repo: str) -> bool:
        """
        检查仓库是否在防抖期内

        Args:
            repo: 仓库名称

        Returns:
            是否在防抖期内
        """
        if repo not in self._last_sync:
            return False
        record = self._last_sync[repo]
        if record.is_within_debounce(self.debounce_minutes):
            logger.info(f"仓库 {repo} 在防抖期内，跳过同步")
            return True
        return False

    def update_last_sync(self, result: SyncResult):
        """
        更新最近同步记录

        Args:
            result: 同步结果
        """
        if result.success and result.action != SyncAction.DEBOUNCED:
            self._last_sync[result.repo] = LastSyncRecord(
                repo=result.repo,
                timestamp=datetime.now().isoformat(),
                commit=result.commit_hash,
                files_count=len(result.files),
                success=result.success,
            )
            self._save_last_sync()

    def group_operations_by_repo(self, operations: List[SyncOperation]) -> Dict[str, List[SyncOperation]]:
        """
        按仓库分组操作

        Args:
            operations: 操作列表

        Returns:
            以仓库名为 key 的操作列表字典
        """
        grouped: Dict[str, List[SyncOperation]] = {}
        for op in operations:
            if op.action in (SyncAction.CREATE, SyncAction.UPDATE, SyncAction.MERGE):
                repo = op.target_repo or "unknown"
                if repo not in grouped:
                    grouped[repo] = []
                grouped[repo].append(op)
        return grouped

    def build_commit_message(self, repo: str, operations: List[SyncOperation]) -> str:
        """
        构建提交信息

        Args:
            repo: 仓库名称
            operations: 操作列表

        Returns:
            提交信息字符串
        """
        action_count: Dict[str, int] = {}
        for op in operations:
            action_key = op.action.value if isinstance(op.action, SyncAction) else op.action
            action_count[action_key] = action_count.get(action_key, 0) + 1

        parts = []
        action_labels = {
            "create": "新增",
            "update": "更新",
            "merge": "合并",
            "delete": "删除",
        }
        for action, count in sorted(action_count.items()):
            label = action_labels.get(action, action)
            parts.append(f"{label} {count} 个文件")

        today = datetime.now().strftime("%Y-%m-%d")
        return f"[Curator] {today} - {' / '.join(parts)}"

    def log_sync(self, result: SyncResult, plan_id: str = ""):
        """
        记录同步日志

        Args:
            result: 同步结果
            plan_id: 计划ID
        """
        entry = SyncLogEntry(
            timestamp=datetime.now().isoformat(),
            success=result.success,
            repo=result.repo,
            action=result.action.value if isinstance(result.action, SyncAction) else result.action,
            files=result.files,
            commit_hash=result.commit_hash,
            error=result.error,
            duration_ms=result.duration_ms,
            plan_id=plan_id,
            operations_count=result.operations_count,
        )
        try:
            with open(self.sync_log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"记录同步日志失败: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        获取同步统计信息

        Returns:
            统计数据字典
        """
        total = 0
        successful = 0
        by_repo: Dict[str, int] = {}

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
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                logger.error(f"读取同步日志失败: {e}")

        return {
            "total_syncs": total,
            "successful": successful,
            "failed": total - successful,
            "by_repo": by_repo,
            "last_sync": {
                repo: record.to_dict()
                for repo, record in self._last_sync.items()
            },
        }
