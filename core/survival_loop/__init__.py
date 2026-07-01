"""
Survival Loop Engine — 单循环执行内核

收敛自：MinerPool + ProviderFactory + Router + Watchdog + OPS诊断

核心原则：
  一个任务入口 → 一个循环执行 → 一个结果出口

Provider 固定顺序：
  glm → openrouter → nim → apiyi → sambanova → oneapi → github_models → modelscope → huggingface

失败处理：
  所有错误统一视为 FAIL → 切换下一个 provider
"""

from .engine import SurvivalLoopEngine

__all__ = ["SurvivalLoopEngine"]
