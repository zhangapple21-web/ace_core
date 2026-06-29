"""
模型路由器 — ModelRouter

不是找最好的模型。
是找最适合这个任务的模型。

路由逻辑：
  1. 根据任务类型取任务画像
  2. 从 preferred_models 里挑第一个可用的
  3. 不可用则往下试 fallback_models
  4. 都不行则返回 None（调用方降级）

支持策略：
  - quality_first:   质量优先，从最好的开始试
  - cost_effective:  性价比优先，先试便宜的
  - latency_first:   延迟优先，先试最快的
  - diverse:         多样性优先，返回多个不同厂商的（用于多模型辩论）
"""

import random
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from .task_profiles import get_task_profile, TASK_PROFILES


@dataclass
class ModelSpec:
    """模型规格"""
    provider: str       # nim / github_models / glm / ...
    model: str          # 模型名
    full_id: str        # provider:model 格式
    tier: str = "unknown"  # ultra / heavy / reason / fast / unknown

    @classmethod
    def from_id(cls, model_id: str) -> "ModelSpec":
        """从 provider:model 格式解析"""
        if ":" in model_id:
            provider, model = model_id.split(":", 1)
        else:
            provider, model = "unknown", model_id
        return cls(provider=provider, model=model, full_id=model_id)


class ModelRouter:
    """
    模型路由器

    职责：
      - 根据任务类型和可用提供商，选择最合适的模型
      - 支持重试时自动降级到下一个模型
      - 支持多模型采样（用于交叉验证）

    不负责：
      - 实际调用模型（那是 MinerPool 的事）
      - 维护模型健康状态（那是 Provider 的事）
    """

    def __init__(self, available_providers: List[str] = None):
        self._available_providers = set(available_providers or [])
        self._model_health: Dict[str, bool] = {}  # model_id -> is_healthy
        self._call_history: List[Dict] = []

    def set_available_providers(self, providers: List[str]):
        """更新可用提供商列表"""
        self._available_providers = set(providers)

    def mark_model_health(self, model_id: str, healthy: bool):
        """标记模型健康状态"""
        self._model_health[model_id] = healthy

    def select_model(
        self,
        task_type: str,
        strategy: str = "",
        exclude_models: List[str] = None,
    ) -> Optional[ModelSpec]:
        """
        为任务选择最合适的模型

        Args:
            task_type: 任务类型
            strategy: 覆盖默认策略
            exclude_models: 排除的模型列表（重试时用）

        Returns:
            ModelSpec 或 None
        """
        profile = get_task_profile(task_type)
        if not strategy:
            strategy = profile.get("strategy", "quality_first")

        exclude = set(exclude_models or [])

        # 按策略排序候选模型
        candidates = self._get_sorted_candidates(profile, strategy)

        # 过滤：提供商可用 + 没被排除 + 健康（如果已知）
        for model_id in candidates:
            spec = ModelSpec.from_id(model_id)
            if spec.provider not in self._available_providers:
                continue
            if model_id in exclude:
                continue
            if model_id in self._model_health and not self._model_health[model_id]:
                continue
            return spec

        return None

    def select_models(
        self,
        task_type: str,
        count: int = 3,
        diverse: bool = True,
    ) -> List[ModelSpec]:
        """
        选择多个模型（用于交叉验证、多视角）

        Args:
            task_type: 任务类型
            count: 需要几个模型
            diverse: 是否要求不同厂商

        Returns:
            ModelSpec 列表
        """
        profile = get_task_profile(task_type)
        candidates = self._get_sorted_candidates(profile, "quality_first")

        selected = []
        seen_providers = set()

        for model_id in candidates:
            spec = ModelSpec.from_id(model_id)

            if spec.provider not in self._available_providers:
                continue
            if diverse and spec.provider in seen_providers:
                continue
            if model_id in self._model_health and not self._model_health[model_id]:
                continue

            selected.append(spec)
            seen_providers.add(spec.provider)

            if len(selected) >= count:
                break

        return selected

    def _get_sorted_candidates(self, profile: Dict, strategy: str) -> List[str]:
        """根据策略获取排序后的候选模型列表"""
        preferred = profile.get("preferred_models", [])
        fallback = profile.get("fallback_models", [])

        if strategy == "cost_effective":
            # 先试 fallback（通常更便宜），不行再上 preferred
            return fallback + preferred
        elif strategy == "latency_first":
            # 快速的放前面（fallback 通常更快更便宜）
            return fallback + preferred
        elif strategy == "diverse":
            # 交替取 preferred 和 fallback，保证多样性
            return self._interleave(preferred, fallback)
        else:
            # quality_first 和默认：preferred 在前
            return preferred + fallback

    @staticmethod
    def _interleave(list_a: List, list_b: List) -> List:
        """交替合并两个列表"""
        result = []
        max_len = max(len(list_a), len(list_b))
        for i in range(max_len):
            if i < len(list_a):
                result.append(list_a[i])
            if i < len(list_b):
                result.append(list_b[i])
        return result

    def record_call(self, model_id: str, task_type: str, success: bool, latency_ms: int):
        """记录调用历史（用于后续优化路由）"""
        self._call_history.append({
            "model_id": model_id,
            "task_type": task_type,
            "success": success,
            "latency_ms": latency_ms,
        })
        # 只保留最近 1000 条
        if len(self._call_history) > 1000:
            self._call_history = self._call_history[-1000:]

    def get_stats(self) -> Dict[str, Any]:
        """获取路由统计"""
        total = len(self._call_history)
        if total == 0:
            return {
                "total_calls": 0,
                "available_providers": list(self._available_providers),
                "task_types_supported": list(TASK_PROFILES.keys()),
            }

        by_model: Dict[str, Dict] = {}
        for call in self._call_history:
            mid = call["model_id"]
            if mid not in by_model:
                by_model[mid] = {"calls": 0, "success": 0, "total_latency": 0}
            by_model[mid]["calls"] += 1
            if call["success"]:
                by_model[mid]["success"] += 1
            by_model[mid]["total_latency"] += call["latency_ms"]

        model_stats = {}
        for mid, s in by_model.items():
            model_stats[mid] = {
                "calls": s["calls"],
                "success_rate": s["success"] / s["calls"] if s["calls"] > 0 else 0,
                "avg_latency_ms": s["total_latency"] / s["calls"] if s["calls"] > 0 else 0,
            }

        return {
            "total_calls": total,
            "available_providers": list(self._available_providers),
            "task_types_supported": list(TASK_PROFILES.keys()),
            "model_stats": model_stats,
        }
