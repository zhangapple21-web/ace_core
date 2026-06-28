"""
权限契约 — Authority Contract

定义系统中角色、权限和授权验证的标准接口：
  - Role: 系统角色定义
  - Permission: 权限项定义
  - PermissionMatrix: 角色-权限矩阵
  - AuthorityContract: 权限验证抽象接口

设计原则：
  - 最小权限原则：默认无权限，显式授权
  - 角色分层：高层角色继承低层角色权限
  - 可审计：所有权限检查可追溯
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any


class Role(str, Enum):
    """系统角色"""

    OBSERVER = "observer"
    RESEARCH_AGENT = "research_agent"
    ENGINEERING_AGENT = "engineering_agent"
    VALIDATOR = "validator"
    ARCHIVIST = "archivist"
    REPOSITORY_CURATOR = "repository_curator"
    SCHEDULER = "scheduler"
    GUARDIAN = "guardian"
    ADMIN = "admin"


class Permission(str, Enum):
    """权限项"""

    # 观察相关
    OBSERVE = "observe"
    RECORD = "record"

    # 研究相关
    CREATE = "create"
    MODIFY = "modify"
    RESEARCH = "research"
    ANALYZE = "analyze"

    # 工程相关
    CODE = "code"
    TEST = "test"
    REFACTOR = "refactor"

    # 验证相关
    VALIDATE = "validate"
    APPROVE = "approve"
    REJECT = "reject"

    # 归档相关
    ARCHIVE = "archive"
    CURATE = "curate"

    # 同步相关
    SYNC = "sync"
    GIT_PUSH = "git_push"
    GIT_COMMIT = "git_commit"

    # 管理相关
    COMPARE = "compare"
    MERGE = "merge"
    SPLIT = "split"
    BACKUP = "backup"
    REPO_REVIEW = "repo_review"

    # 调度相关
    SCHEDULE = "schedule"
    ASSIGN = "assign"

    # 守护相关
    GUARD = "guard"
    SHUTDOWN = "shutdown"

    # 管理员
    ADMIN_ALL = "admin_all"


@dataclass
class PermissionMatrix:
    """
    角色-权限矩阵

    定义每个角色拥有哪些权限。
    支持角色继承：高级角色自动拥有低级角色的所有权限。
    """

    matrix: Dict[str, Set[str]] = field(default_factory=dict)

    def __post_init__(self):
        if not self.matrix:
            self._init_default_matrix()

    def _init_default_matrix(self):
        """初始化默认权限矩阵"""
        self.matrix = {
            Role.OBSERVER.value: {
                Permission.OBSERVE.value,
                Permission.RECORD.value,
            },
            Role.RESEARCH_AGENT.value: {
                Permission.OBSERVE.value,
                Permission.RECORD.value,
                Permission.CREATE.value,
                Permission.MODIFY.value,
                Permission.RESEARCH.value,
                Permission.ANALYZE.value,
            },
            Role.ENGINEERING_AGENT.value: {
                Permission.CREATE.value,
                Permission.MODIFY.value,
                Permission.CODE.value,
                Permission.TEST.value,
                Permission.REFACTOR.value,
            },
            Role.VALIDATOR.value: {
                Permission.OBSERVE.value,
                Permission.VALIDATE.value,
                Permission.APPROVE.value,
                Permission.REJECT.value,
                Permission.ANALYZE.value,
            },
            Role.ARCHIVIST.value: {
                Permission.ARCHIVE.value,
                Permission.CURATE.value,
                Permission.COMPARE.value,
            },
            Role.REPOSITORY_CURATOR.value: {
                Permission.CURATE.value,
                Permission.COMPARE.value,
                Permission.MERGE.value,
                Permission.SPLIT.value,
                Permission.ARCHIVE.value,
                Permission.GIT_PUSH.value,
                Permission.GIT_COMMIT.value,
                Permission.BACKUP.value,
                Permission.REPO_REVIEW.value,
                Permission.SYNC.value,
            },
            Role.SCHEDULER.value: {
                Permission.SCHEDULE.value,
                Permission.ASSIGN.value,
                Permission.OBSERVE.value,
            },
            Role.GUARDIAN.value: {
                Permission.GUARD.value,
                Permission.SHUTDOWN.value,
                Permission.VALIDATE.value,
                Permission.OBSERVE.value,
            },
            Role.ADMIN.value: {perm.value for perm in Permission},
        }

    def has_permission(self, role: Role, permission: Permission) -> bool:
        """
        检查角色是否拥有指定权限

        Args:
            role: 角色
            permission: 权限项

        Returns:
            bool: 是否拥有该权限
        """
        role_perms = self.matrix.get(role.value, set())
        return permission.value in role_perms

    def get_role_permissions(self, role: Role) -> Set[str]:
        """
        获取角色的所有权限

        Args:
            role: 角色

        Returns:
            Set[str]: 权限集合
        """
        return self.matrix.get(role.value, set()).copy()

    def grant_permission(self, role: Role, permission: Permission) -> None:
        """
        授予角色权限

        Args:
            role: 角色
            permission: 权限项
        """
        if role.value not in self.matrix:
            self.matrix[role.value] = set()
        self.matrix[role.value].add(permission.value)

    def revoke_permission(self, role: Role, permission: Permission) -> None:
        """
        撤销角色权限

        Args:
            role: 角色
            permission: 权限项
        """
        if role.value in self.matrix:
            self.matrix[role.value].discard(permission.value)

    def can_act(self, actor_role: Role, target_action: str) -> bool:
        """
        检查角色是否可以执行某个动作

        兼容字符串形式的动作名，便于从配置或外部调用。

        Args:
            actor_role: 执行者角色
            target_action: 动作名（字符串）

        Returns:
            bool: 是否有权执行
        """
        try:
            perm = Permission(target_action)
            return self.has_permission(actor_role, perm)
        except ValueError:
            return False

    def to_dict(self) -> Dict[str, List[str]]:
        """序列化为字典"""
        return {
            role: sorted(list(perms))
            for role, perms in self.matrix.items()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, List[str]]) -> "PermissionMatrix":
        """从字典反序列化"""
        matrix = {
            role: set(perms)
            for role, perms in data.items()
        }
        return cls(matrix=matrix)


@dataclass
class AuthorizationResult:
    """
    授权验证结果

    记录一次权限检查的详细信息，便于审计。
    """

    authorized: bool
    role: str
    permission: str
    reason: str = ""
    checked_at: str = ""
    context: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.checked_at:
            self.checked_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "authorized": self.authorized,
            "role": self.role,
            "permission": self.permission,
            "reason": self.reason,
            "checked_at": self.checked_at,
            "context": self.context,
        }


class AuthorityContract(ABC):
    """
    权限验证抽象契约

    所有权限验证器必须实现此接口。
    保证不同实现（本地权限、远程权限服务、分布式授权）
    都遵循统一的调用约定。
    """

    @abstractmethod
    def check_permission(
        self,
        role: Role,
        permission: Permission,
        context: Optional[Dict[str, Any]] = None,
    ) -> AuthorizationResult:
        """
        检查角色是否拥有指定权限

        Args:
            role: 待检查的角色
            permission: 待检查的权限
            context: 上下文信息（资源、操作对象等）

        Returns:
            AuthorizationResult: 授权结果
        """
        pass

    @abstractmethod
    def get_permissions(self, role: Role) -> Set[str]:
        """
        获取角色的所有权限

        Args:
            role: 角色

        Returns:
            Set[str]: 权限标识集合
        """
        pass

    @abstractmethod
    def list_roles(self) -> List[str]:
        """
        列出所有可用角色

        Returns:
            List[str]: 角色名称列表
        """
        pass

    def require_permission(
        self,
        role: Role,
        permission: Permission,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        要求必须拥有指定权限，否则抛出异常

        Args:
            role: 角色
            permission: 权限
            context: 上下文

        Raises:
            PermissionError: 如果没有权限
        """
        result = self.check_permission(role, permission, context)
        if not result.authorized:
            raise PermissionError(
                f"角色 {role.value} 无权限 {permission.value}: {result.reason}"
            )
