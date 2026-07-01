"""
Autonomous Kernel — 系统神经节

不是再造系统，是把已有系统点火成自驱闭环。

v1：Trigger + Experiment Orchestrator + Critic + Writeback Gate
"""

from .kernel import AutonomousKernel, TriggerSignal

__all__ = ["AutonomousKernel", "TriggerSignal"]
