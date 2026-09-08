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

import hashlib
import random
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

from .task_profiles import get_task_profile, TASK_PROFILES
from .capability_routing import (
    CapabilityEvidenceLedger,
    capability_for_task,
    infer_complexity,
    is_complex_escalation,
    model_capability,
)


@dataclass
class ModelSpec:
    """模型规格"""
    provider: str       # nim / github_models / glm / ...
    model: str          # 模型名
    full_id: str        # provider:model 格式
    tier: str = "unknown"  # ultra / heavy / reason / fast / unknown
    capabilities: Tuple[str, ...] = ()
    production_eligible: bool = False
    route_state: str = "UNVERIFIED"

    @classmethod
    def from_id(cls, model_id: str) -> "ModelSpec":
        """从 provider:model 格式解析"""
        if ":" in model_id:
            provider, model = model_id.split(":", 1)
        else:
            provider, model = "unknown", model_id
        metadata = model_capability(model_id)
        return cls(
            provider=provider,
            model=model,
            full_id=model_id,
            tier=str(metadata.get("tier", "unknown")),
            capabilities=tuple(metadata.get("capabilities", [])),
            production_eligible=bool(metadata.get("production_eligible", False)),
            route_state=str(metadata.get("route_state", "UNVERIFIED")),
        )


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

    def __init__(
        self,
        available_providers: List[str] = None,
        watchdog=None,
        evidence_ledger: Optional[CapabilityEvidenceLedger] = None,
    ):
        self._available_providers = set(available_providers or [])
        self._model_health: Dict[str, bool] = {}  # model_id -> is_healthy
        self._call_history: List[Dict] = []
        self._watchdog = watchdog
        self._evidence_ledger = evidence_ledger

    def set_available_providers(self, providers: List[str]):
        """更新可用提供商列表"""
        self._available_providers = set(providers)

    def set_watchdog(self, watchdog) -> None:
        """Attach the existing ProviderWatchdog as a read-only route input."""

        self._watchdog = watchdog

    def set_evidence_ledger(self, evidence_ledger: Optional[CapabilityEvidenceLedger]) -> None:
        self._evidence_ledger = evidence_ledger

    def mark_model_health(self, model_id: str, healthy: bool):
        """标记模型健康状态"""
        self._model_health[model_id] = healthy

    def select_model(
        self,
        task_type: str,
        strategy: str = "",
        exclude_models: List[str] = None,
        exclude_providers: List[str] = None,
        include_shadow: bool = False,
        task_context: Optional[Dict[str, Any]] = None,
        complexity: Optional[str] = None,
    ) -> Optional[ModelSpec]:
        """
        为任务选择最合适的模型

        Args:
            task_type: 任务类型
            strategy: 覆盖默认策略
            exclude_models: 排除的模型列表（重试时用）
            exclude_providers: 运行时健康状态禁止使用的提供商

        Returns:
            ModelSpec 或 None
        """
        profile = get_task_profile(task_type)
        if profile.get("shadow_only") and not include_shadow:
            return None
        if not strategy:
            strategy = profile.get("strategy", "quality_first")

        exclude = set(exclude_models or [])
        excluded_providers = set(exclude_providers or [])

        # 按任务画像、复杂度和能力升级规则排序候选模型。 复杂度只能由
        # execution-discipline/task context 提供，不能由模型自己提升。
        resolved_complexity, complexity_basis = infer_complexity(
            task_type, task_context, complexity
        )
        candidates = self._get_route_candidates(
            task_type=task_type,
            profile=profile,
            strategy=strategy,
            complexity=resolved_complexity,
            task_context=task_context,
        )

        allowed_providers = set(profile.get("allowed_providers", set()))
        allowed_models = set(profile.get("allowed_models", set()))

        # 过滤：提供商可用 + 没被排除 + 健康（如果已知）
        for model_id in candidates:
            spec = ModelSpec.from_id(model_id)
            if spec.provider not in self._available_providers:
                continue
            if allowed_providers and spec.provider not in allowed_providers:
                continue
            if allowed_models and model_id not in allowed_models:
                continue
            if spec.provider in excluded_providers:
                continue
            if self._watchdog is not None:
                try:
                    has_history = getattr(self._watchdog, "has_health_history", None)
                    if has_history and has_history(spec.provider) and not self._watchdog.is_healthy(spec.provider):
                        continue
                except Exception:
                    # A watchdog read failure is an unknown, not a reason to
                    # fabricate health; the caller may still apply its own
                    # fail-closed policy.
                    pass
            if model_id in exclude:
                continue
            if model_id in self._model_health and not self._model_health[model_id]:
                continue
            return spec

        return None

    def resolve_route(
        self,
        task_type: str,
        *,
        task_context: Optional[Dict[str, Any]] = None,
        complexity: Optional[str] = None,
        strategy: str = "",
        exclude_models: Optional[List[str]] = None,
        exclude_providers: Optional[List[str]] = None,
        include_shadow: bool = False,
    ) -> Dict[str, Any]:
        """Return an auditable decision without invoking a provider."""

        profile = get_task_profile(task_type)
        resolved_complexity, basis = infer_complexity(task_type, task_context, complexity)
        capability = capability_for_task(task_type)
        candidates = self._get_route_candidates(
            task_type=task_type,
            profile=profile,
            strategy=strategy or profile.get("strategy", "quality_first"),
            complexity=resolved_complexity,
            task_context=task_context,
        )
        selected = self.select_model(
            task_type=task_type,
            strategy=strategy,
            exclude_models=exclude_models,
            exclude_providers=exclude_providers,
            include_shadow=include_shadow,
            task_context=task_context,
            complexity=complexity,
        )
        return {
            "schema_version": "ace.route-decision.v1",
            "task_type": task_type,
            "capability": capability,
            "complexity": resolved_complexity,
            "complexity_basis": basis,
            "escalation": is_complex_escalation(resolved_complexity, task_context),
            "default_labor": "shenwen:gpt-5.6-terra",
            "candidate_labor": candidates,
            "candidate_labor_details": [
                {
                    "provider_and_model": spec.full_id,
                    "provider": spec.provider,
                    "model": spec.model,
                    "tier": spec.tier,
                    "capabilities": list(spec.capabilities),
                    "production_eligible": spec.production_eligible,
                    "route_state": spec.route_state,
                }
                for spec in (ModelSpec.from_id(model_id) for model_id in candidates)
            ],
            "selected_labor": selected.full_id if selected else None,
            "selected_route_state": selected.route_state if selected else "NO_ELIGIBLE_LABOR",
            "watchdog": self._watchdog_snapshot(),
            "evidence_boundary": (
                "candidate_complex_route_only"
                if selected and selected.route_state == "POC_COMPLEX_ESCALATION"
                else "existing_profile"
            ),
        }

    def _get_route_candidates(
        self,
        *,
        task_type: str,
        profile: Dict[str, Any],
        strategy: str,
        complexity: str,
        task_context: Optional[Dict[str, Any]],
    ) -> List[str]:
        candidates = self._get_sorted_candidates(profile, strategy)
        if is_complex_escalation(complexity, task_context):
            # Escalation list is explicit per task profile.  It is placed in
            # front, but normal Terra remains the first fallback.
            candidates = list(profile.get("escalation_models", [])) + candidates
        # Preserve declaration order while removing duplicates.
        result = []
        for model_id in candidates:
            if model_id not in result:
                result.append(model_id)
        return result

    def _watchdog_snapshot(self) -> Dict[str, Any]:
        watchdog = self._watchdog
        if watchdog is None:
            return {"status": "NOT_ATTACHED", "providers": {}}
        try:
            if hasattr(watchdog, "health_snapshot"):
                return watchdog.health_snapshot()
            providers = {}
            for item in watchdog.list_providers():
                providers[item.get("name", "")] = item
            return {"status": "OBSERVED", "providers": providers}
        except Exception as error:
            return {"status": "UNAVAILABLE", "error": type(error).__name__, "providers": {}}

    def select_models(
        self,
        task_type: str,
        count: int = 3,
        diverse: bool = True,
        include_shadow: bool = False,
        task_context: Optional[Dict[str, Any]] = None,
        complexity: Optional[str] = None,
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
        if profile.get("shadow_only") and not include_shadow:
            return []
        resolved_complexity, _ = infer_complexity(task_type, task_context, complexity)
        candidates = self._get_route_candidates(
            task_type=task_type,
            profile=profile,
            strategy="quality_first",
            complexity=resolved_complexity,
            task_context=task_context,
        )
        allowed_providers = set(profile.get("allowed_providers", set()))
        allowed_models = set(profile.get("allowed_models", set()))

        selected = []
        seen_providers = set()

        for model_id in candidates:
            spec = ModelSpec.from_id(model_id)

            if spec.provider not in self._available_providers:
                continue
            if allowed_providers and spec.provider not in allowed_providers:
                continue
            if allowed_models and model_id not in allowed_models:
                continue
            if diverse and spec.provider in seen_providers:
                continue
            if self._watchdog is not None:
                try:
                    has_history = getattr(self._watchdog, "has_health_history", None)
                    if has_history and has_history(spec.provider) and not self._watchdog.is_healthy(spec.provider):
                        continue
                except Exception:
                    # Preserve the existing unknown-health behavior used by
                    # single-model selection; only known unhealthy providers
                    # are filtered here.
                    pass
            if model_id in self._model_health and not self._model_health[model_id]:
                continue

            selected.append(spec)
            seen_providers.add(spec.provider)

            if len(selected) >= count:
                break

        return selected

    def select_shadow_model(self, task_type: str) -> Optional[ModelSpec]:
        """Explicit opt-in entry point for shadow workers.

        Keeping this separate from normal selection makes it easy for ACE to
        dispatch exploratory sub-workers without weakening production routing.
        """
        profile = get_task_profile(task_type)
        if not profile.get("shadow_only"):
            return None
        return self.select_model(task_type, include_shadow=True)

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

    def record_call(
        self,
        model_id: str,
        task_type: str,
        success: bool,
        latency_ms: int,
        *,
        provider: str = "",
        usage: Optional[Dict[str, Any]] = None,
        cost: Optional[Dict[str, Any]] = None,
        attempts: Optional[List[Dict[str, Any]]] = None,
        route_state: str = "UNVERIFIED",
    ):
        """记录调用历史（用于后续优化路由）"""
        self._call_history.append({
            "model_id": model_id,
            "task_type": task_type,
            "success": success,
            "latency_ms": latency_ms,
            "provider": provider,
        })
        # 只保留最近 1000 条
        if len(self._call_history) > 1000:
            self._call_history = self._call_history[-1000:]
        if self._evidence_ledger:
            capability = capability_for_task(task_type)
            model = model_id.split(":", 1)[1] if ":" in model_id else model_id
            self._evidence_ledger.record_call(
                task_type=task_type,
                capability=capability,
                provider=provider or (model_id.split(":", 1)[0] if ":" in model_id else ""),
                model=model,
                success=success,
                latency_ms=latency_ms,
                usage=usage,
                cost=cost,
                attempts=attempts,
                route_state=route_state,
            )
            # A successful response after trying more than one labour is also
            # a compatibility observation: the fallback accepted the same
            # task envelope and returned a usable result. Keep it separate
            # from failure-recovery evidence for promotion checks.
            route_rows = [
                str(item.get("model", ""))
                for item in (attempts or [])
                if isinstance(item, dict) and item.get("model")
            ]
            unique_routes = list(dict.fromkeys(route_rows))
            if success and len(unique_routes) > 1:
                evidence_hash = hashlib.sha256(
                    "|".join(unique_routes).encode("utf-8")
                ).hexdigest()
                self._evidence_ledger.record_fallback_test(
                    capability=capability,
                    primary=unique_routes[0],
                    fallback=unique_routes[-1],
                    compatible=True,
                    evidence_hash=evidence_hash,
                )

    def get_stats(self) -> Dict[str, Any]:
        """获取路由统计"""
        total = len(self._call_history)
        if total == 0:
            return {
                "total_calls": 0,
                "available_providers": list(self._available_providers),
                "task_types_supported": list(TASK_PROFILES.keys()),
                "capability_evidence": self._evidence_ledger.snapshot() if self._evidence_ledger else None,
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
            "capability_evidence": self._evidence_ledger.snapshot() if self._evidence_ledger else None,
        }
