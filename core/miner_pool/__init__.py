"""
矿工池 — 算力军团调度系统

⚠️  DEPRECATED（已废弃，保留血缘）

本模块已被 core.survival_loop.SurvivalLoopEngine 收敛替代。
保留此目录仅作为结构血缘记录，不删除。

演化路径：
  MinerPool (v1) → SurvivalLoopEngine (v2)
  收敛了：MinerPool + ProviderFactory + Router + Watchdog + OPS诊断

结构 → 协议 → 记忆 → 路由 → 模型
模型只是临时执行节点。

MinerPool 不负责思考。
只负责：给我一个任务类型，我派最合适的模型上。

模块组成：
  credential_manager.py  — 凭证管理（从 coze-assets 读取）
  providers/             — 各模型提供商适配器
  miner_pool.py          — 矿工池主入口
  model_router.py        — 智能路由调度器
  task_profiles.py       — 任务画像（什么任务派什么模型）
  integration.py         — 与 Researcher / Validator / Archivist 集成
"""

from .credential_manager import CredentialManager
from .miner_pool import MinerPool
from .model_router import ModelRouter
from .task_profiles import TASK_PROFILES, get_task_profile, list_task_types
from .integration import (
    ResearcherWithMinerPool,
    ValidatorWithMinerPool,
    ArchivistWithMinerPool,
    create_miner_pool,
    enhance_roles,
)

__all__ = [
    "CredentialManager",
    "MinerPool",
    "ModelRouter",
    "TASK_PROFILES",
    "get_task_profile",
    "list_task_types",
    "ResearcherWithMinerPool",
    "ValidatorWithMinerPool",
    "ArchivistWithMinerPool",
    "create_miner_pool",
    "enhance_roles",
]
