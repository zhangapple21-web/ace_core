"""单一便携路径解析层。

所有 ACE 恢复/引导脚本只通过本模块取得仓库内路径。ROOTS 是唯一的
布局表：仓库可以位于任意盘符，外部能力资产通过环境变量注入，绝不把
当前机器的绝对目录写入执行路径。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Mapping


# 只需修改这一张表即可调整仓库内布局；值均相对于 workspace。
ROOTS: dict[str, str] = {
    "recovery": "recovery",
    "config_example": "ace_config.example.json",
    "config_local": "ace_config.local.json",
    "task_pool": "task_pool",
    "runtime": "runtime",
    "events": "06_RUNTIME/ace/data/events",
    "tasks": "06_RUNTIME/ace/data/tasks",
    "memory_cache": "06_RUNTIME/ace/data/memory",
    "knowledge_axiom": "09_KNOWLEDGE/axiom",
    "knowledge_constraint": "09_KNOWLEDGE/constraint",
    "knowledge_pattern": "09_KNOWLEDGE/pattern",
    "ace_cli": "ace.py",
    "health_check": "ops/health_check.py",
    "restore_core": "ace_core",
    "restore_video": "ace-video-kingdom",
    "restore_optional": "optional",
}


def _clean_workspace(workspace: Path | str) -> Path:
    return Path(workspace).expanduser().resolve()


def resolve(workspace: Path | str, key: str, *parts: str) -> Path:
    """Resolve a symbolic path from ROOTS and reject traversal outside workspace."""
    if key not in ROOTS:
        raise KeyError(f"未知 ACE 路径键: {key}")
    root = _clean_workspace(workspace)
    candidate = (root / ROOTS[key]).joinpath(*parts).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError(f"路径越界: {key} -> {candidate}")
    return candidate


def layout(workspace: Path | str) -> dict[str, Path]:
    """返回当前 workspace 的完整解析表，便于报告和测试。"""
    return {key: resolve(workspace, key) for key in ROOTS}


def external_path(env_name: str) -> Path | None:
    """读取可选外部资产路径；未设置/空值表示禁用，不猜测本机目录。"""
    value = os.environ.get(env_name, "").strip()
    return Path(value).expanduser().resolve() if value else None


def portable_environment(workspace: Path | str, extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """为子进程提供可审计的路径环境，不写入机器专属绝对路径。"""
    env = dict(os.environ)
    env["ACE_WORKSPACE_ROOT"] = str(_clean_workspace(workspace))
    if extra:
        env.update(extra)
    return env
