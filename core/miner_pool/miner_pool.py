"""
矿工池 — MinerPool

这是算力军团的指挥部。

不是简单的 API 调用封装。
是调度系统：
  - 什么任务派什么模型
  - 失败了自动降级换下一个
  - 需要多视角时派不同厂商的模型互相质疑
  - 记录每个模型的表现，动态调整优先级

调用方式：
  pool = MinerPool(coze_assets_path="/path/to/coze-assets")
  result = pool.chat(task_type="hypothesis_generation", messages=[...])

多模型辩论：
  results = pool.multi_chat(task_type="cross_validation", messages=[...], model_count=3)
"""

import json
import math
import os
import time
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from .credential_manager import CredentialManager, ProviderCredential
from .model_router import ModelRouter, ModelSpec
from .capability_routing import CapabilityEvidenceLedger, capability_for_task, infer_complexity
from .task_profiles import get_task_profile, list_task_types
from .provider_watchdog import ProviderWatchdog
from .providers.openai_compatible import (
    NIMProvider,
    GitHubModelsProvider,
    GLMProvider,
    APIYiProvider,
    SambaNovaProvider,
    OneAPIProvider,
    OpenAICompatibleProvider,
    ShenwenProvider,
    ShenwenGrokProvider,
    ShenwenDs41Provider,
    ShenwenImagesProvider,
)
from ..execution_contract import ensure_execution_contract, normalize_untrusted_messages
from ..mirror_constitution import validate_data_boundary


PROVIDER_FACTORY = {
    "nim": NIMProvider,
    "github_models": GitHubModelsProvider,
    "glm": GLMProvider,
    "apiyi": APIYiProvider,
    "sambanova": SambaNovaProvider,
    "oneapi": OneAPIProvider,
    "modelscope": OpenAICompatibleProvider,
    "huggingface": OpenAICompatibleProvider,
    "ace_proxy": OpenAICompatibleProvider,  # ACE 自己的 OpenAI 兼容代理
    "shenwen": ShenwenProvider,
    "shenwen_grok": ShenwenGrokProvider,
    "shenwen_ds41": ShenwenDs41Provider,
    "shenwen_images": ShenwenImagesProvider,
}


class MinerPool:
    """
    矿工池 — 算力军团调度系统

    设计原则：
      1. 结构 > 模型：调度逻辑是核心，模型可替换
      2. 失败不阻塞：一个模型挂了自动试下一个
      3. 多样性优先：关键任务用不同厂商模型交叉验证
      4. 记录一切：每次调用都留下记录，用于优化路由
    """

    def __init__(
        self,
        coze_assets_path: Optional[str] = None,
        credential_manager: Optional[CredentialManager] = None,
        state_dir: Optional[str] = None,
    ):
        self._credential_mgr = credential_manager or CredentialManager(coze_assets_path)
        self._providers: Dict[str, OpenAICompatibleProvider] = {}
        self._state_dir = Path(state_dir) if state_dir else None
        self._routing_ledger = CapabilityEvidenceLedger(
            str(self._state_dir) if self._state_dir else None
        )
        self._routing_ledger.ensure_capabilities(
            capability_for_task(task_type) for task_type in list_task_types()
        )
        self._router = ModelRouter(evidence_ledger=self._routing_ledger)
        self._watchdog: Optional[ProviderWatchdog] = None
        self._initialized = False

        if self._state_dir:
            self._state_dir.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> bool:
        """初始化矿工池：加载凭证 + 创建提供商实例 + 初始化 Watchdog"""
        if self._initialized:
            return True

        try:
            if not self._credential_mgr.load():
                return False

            available = self._credential_mgr.list_providers()
            self._router.set_available_providers(available)

            # 初始化 Watchdog
            watchdog_dir = self._state_dir / "provider_watchdog" if self._state_dir else None
            self._watchdog = ProviderWatchdog(state_dir=str(watchdog_dir) if watchdog_dir else None)
            self._router.set_watchdog(self._watchdog)

            for provider_name in available:
                cred = self._credential_mgr.get(provider_name)
                if not cred or not cred.is_valid:
                    continue

                factory = PROVIDER_FACTORY.get(provider_name, OpenAICompatibleProvider)
                try:
                    self._providers[provider_name] = factory(
                        api_key=cred.primary_key,
                        base_url=cred.base_url,
                    )
                    # 注册到 Watchdog
                    self._watchdog.register_provider(
                        name=provider_name,
                        base_url=cred.base_url,
                        api_key=cred.primary_key,
                    )
                except Exception:
                    continue

            self._initialized = bool(self._providers)
            return self._initialized
        except Exception:
            return False

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def available_providers(self) -> List[str]:
        if not self._initialized:
            self.initialize()
        return list(self._providers.keys())

    @property
    def watchdog(self) -> Optional[ProviderWatchdog]:
        """获取 Watchdog 实例"""
        return self._watchdog

    @property
    def router(self) -> ModelRouter:
        """Return the single routing authority owned by this pool."""
        return self._router

    def get_health_stats(self) -> Dict[str, Any]:
        """获取 Provider 健康统计"""
        if self._watchdog:
            return self._watchdog.get_stats()
        return {"error": "watchdog not initialized"}

    def get_capability_routing_snapshot(self) -> Dict[str, Any]:
        """Expose the task -> capability -> labour view for audit/UI use."""

        return {
            "schema_version": "ace.capability-routing.v1",
            "system_status": "AUTONOMOUS_CAPABILITY_ROUTING_POC_READY",
            "promotion_status": "PRODUCTION_MODEL_ROUTING_NOT_YET_PROMOTED",
            "default_model": "shenwen:gpt-5.6-terra",
            "complex_escalation_model": "shenwen:gpt-6-astra",
            "providers": self.available_providers,
            "watchdog": self._router._watchdog_snapshot(),
            "router_stats": self._router.get_stats(),
            "evidence": self._routing_ledger.snapshot(),
            "evidence_readiness": self._routing_ledger.readiness_snapshot(),
        }

    def run_health_check(self) -> Dict[str, Any]:
        """执行全量 Provider 健康检查"""
        if not self._watchdog:
            return {"error": "watchdog not initialized"}
        from .task_profiles import TASK_PROFILES
        test_models = {}
        for tname, tdata in TASK_PROFILES.items():
            preferred = tdata.get("preferred_models", [])
            if preferred:
                first = preferred[0]
                if ":" in first:
                    provider, model = first.split(":", 1)
                    test_models[provider] = model
        # OneAPI is a local mapped-model gateway, not a direct OpenAI
        # catalog.  Its historical generic probe (gpt-4o) is not advertised
        # by the current gateway and turns a healthy /models + chat path into
        # a false UNHEALTHY result.  Keep this probe pinned to the verified
        # local mapping used by the OneAPI provider.
        test_models.setdefault("oneapi", os.environ.get("ONEAPI_MODEL", "gpt-5.4-mini"))
        return self._watchdog.run_full_check(test_models=test_models)

    @staticmethod
    def _shenwen_cost(
        model: str, usage: Dict[str, Any], provider: str = "shenwen"
    ) -> Dict[str, Any]:
        if not isinstance(usage, dict):
            return {}

        def valid_number(value: Any) -> bool:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                return False
            try:
                return math.isfinite(value)
            except OverflowError:
                return False

        # 权威 ticks 不限供应商；非法证据不可当成免费。
        if "cost_in_usd_ticks" in usage:
            ticks = usage["cost_in_usd_ticks"]
            if not valid_number(ticks):
                return {}
            return {
                "currency": "USD",
                "input_usd": 0.0,
                "cache_read_usd": 0.0,
                "cache_write_usd": 0.0,
                "output_usd": 0.0,
                "total_usd": round(ticks / 1_000_000, 12),
                "provider_cost_ticks": ticks,
                "usage_source": "provider_response",
            }
        if provider not in {"shenwen", "shenwen_grok", "shenwen_ds41"}:
            return {}
        prices = {
            "gpt-5.6-terra": {
                "input": 0.44,
                "cache_read": 0.044,
                "cache_write": 0.55,
                "output": 2.64,
            },
            "gpt-5.4-mini": {
                "input": 0.165,
                "cache_read": 0.0165,
                "cache_write": 0.206,
                "output": 0.99,
            },
        }
        price = prices.get(model)
        if not price:
            return {}

        token_fields = ("prompt_tokens", "completion_tokens", "cache_read_tokens", "cache_write_tokens")
        present_fields = [name for name in token_fields if name in usage]
        if not present_fields or any(not valid_number(usage[name]) for name in present_fields):
            return {}

        def token_count(name: str) -> float:
            return usage.get(name, 0)

        input_usd = token_count("prompt_tokens") * price["input"] / 1_000_000
        cache_read_usd = token_count("cache_read_tokens") * price["cache_read"] / 1_000_000
        cache_write_usd = token_count("cache_write_tokens") * price["cache_write"] / 1_000_000
        output_usd = token_count("completion_tokens") * price["output"] / 1_000_000
        total_usd = input_usd + cache_read_usd + cache_write_usd + output_usd
        if not math.isfinite(total_usd):
            return {}
        return {
            "currency": "USD",
            "input_usd": input_usd,
            "cache_read_usd": cache_read_usd,
            "cache_write_usd": cache_write_usd,
            "output_usd": output_usd,
            "total_usd": round(total_usd, 12),
            "usage_source": "provider_response",
        }

    @staticmethod
    def _is_retryable_error(error: str) -> bool:
        normalized = error.lower()
        permanent_markers = (
            "http 400",
            "http 401",
            "http 403",
            "unauthorized",
            "forbidden",
            "invalid api key",
            "unsupported model",
            "model_unavailable",
            "bad request",
            "malformed",
        )
        if any(marker in normalized for marker in permanent_markers):
            return False
        transient_markers = (
            "timeout",
            "timed out",
            "connection",
            "stream ended",
            "rate limit",
            "http 429",
            "http 500",
            "http 502",
            "http 503",
            "http 504",
            "temporarily unavailable",
        )
        return any(marker in normalized for marker in transient_markers)

    def chat(
        self,
        task_type: str,
        messages: List[Dict[str, str]],
        system_prompt: str = "",
        max_retries: int = 3,
        include_shadow: bool = False,
        selected_spec: Optional[ModelSpec] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        执行一次模型调用（自动路由 + 自动重试降级）

        Args:
            task_type: 任务类型（决定用什么模型）
            messages: 对话消息
            system_prompt: 系统提示词（会加到 messages 前面）
            max_retries: 最多试几个模型

        Returns:
            {
                "success": bool,
                "content": str,
                "model": str,
                "provider": str,
                "usage": dict,
                "latency_ms": int,
                "error": str,
                "tried_models": [str],
            }
        """
        data_boundary = kwargs.pop("data_boundary", None)
        boundary = validate_data_boundary(
            data_boundary,
            target="MODEL_CONTEXT",
            payload={"system_prompt": system_prompt, "messages": messages},
        )
        if not boundary["valid"]:
            return {
                "success": False,
                "content": "",
                "model": "",
                "provider": "",
                "usage": {},
                "latency_ms": 0,
                "error": "DATA_BOUNDARY_BLOCKED:" + ",".join(boundary["errors"]),
                "tried_models": [],
                "attempts": [],
                "cost": {},
                "task_type": task_type,
                "routing": {"selected_route_state": "DATA_BOUNDARY_BLOCKED"},
                "data_boundary": {
                    "data_class": boundary.get("data_class"),
                    "target": boundary.get("target"),
                    "allowed": False,
                },
            }
        if not self._initialized:
            self.initialize()

        result = {
            "success": False,
            "content": "",
            "model": "",
            "provider": "",
            "usage": {},
            "latency_ms": 0,
            "error": "",
            "tried_models": [],
            "attempts": [],
            "cost": {},
            "task_type": task_type,
            "data_boundary": {
                "data_class": boundary.get("data_class"),
                "target": boundary.get("target"),
                "allowed": True,
            },
        }

        # Routing metadata is a first-class result.  It contains no prompt or
        # secret and is safe to persist in the task execution trace.
        task_context = kwargs.pop("task_context", None)
        context_task_id = task_context.get("task_id", "") if isinstance(task_context, dict) else ""
        try:
            system_prompt = ensure_execution_contract(
                system_prompt,
                task_type=task_type,
                task_id=str(context_task_id),
            )
        except RuntimeError as error:
            if str(error).startswith("ACE_CONSTITUTION_HIERARCHY_INVALID:"):
                result["error"] = "constitution hierarchy invalid; model call blocked"
                result["routing"] = {"selected_route_state": "CONSTITUTION_HIERARCHY_BLOCKED"}
                return result
            raise
        requested_complexity = kwargs.pop("complexity", None)
        route_decision = self._router.resolve_route(
            task_type,
            task_context=task_context,
            complexity=requested_complexity,
        )
        result["routing"] = route_decision
        result["capability"] = capability_for_task(task_type)
        result["complexity"] = infer_complexity(
            task_type, task_context, requested_complexity
        )[0]

        if not self._providers:
            result["error"] = "no available providers"
            result["routing"]["selected_route_state"] = "NO_CONFIGURED_PROVIDER"
            return result

        # 准备 messages
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(normalize_untrusted_messages(messages))

        profile = get_task_profile(task_type)
        temperature = kwargs.pop("temperature", profile.get("temperature", 0.7))
        max_tokens = kwargs.pop("max_tokens", profile.get("max_tokens", 1024))
        timeout = kwargs.pop("timeout", profile.get("timeout", 60))

        tried = []
        last_error = ""
        spec = selected_spec
        if spec:
            tried.append(spec.full_id)

        for attempt in range(max_retries):
            if spec is None:
                # A fresh daemon loads persisted watchdog state, while the
                # router's per-model in-memory health starts empty.  Keep the
                # router independent from the watchdog, but never select a
                # provider which the watchdog already considers unavailable.
                # DEGRADED intentionally remains eligible: its existing
                # watchdog contract permits bounded fallback attempts.
                excluded_providers = []
                if self._watchdog:
                    has_health_history = getattr(self._watchdog, "has_health_history", None)
                    excluded_providers = [
                        provider_name
                        for provider_name in self._providers
                        if (
                            (has_health_history(provider_name) if has_health_history else True)
                            and not self._watchdog.is_healthy(provider_name)
                        )
                    ]
                spec = self._router.select_model(
                    task_type=task_type,
                    exclude_models=tried,
                    exclude_providers=excluded_providers,
                    include_shadow=include_shadow,
                    task_context=task_context,
                    complexity=requested_complexity,
                )
                if not spec:
                    last_error = last_error or "no available models for this task type"
                    break
                tried.append(spec.full_id)

            provider = self._providers.get(spec.provider)
            if not provider:
                last_error = f"provider not configured: {spec.provider}"
                result["attempts"].append({
                    "number": attempt + 1,
                    "model": spec.full_id,
                    "provider": spec.provider,
                    "timeout": timeout,
                    "latency_ms": 0,
                    "success": False,
                    "retryable": False,
                    "error": last_error,
                    "usage": {},
                    "cost": {},
                    "cost_status": "not_called",
                })
                self._router.mark_model_health(spec.full_id, False)
                spec = None
                continue

            try:
                call_result = provider.chat(
                    messages=full_messages,
                    model=spec.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    data_boundary=data_boundary,
                    **kwargs,
                )
            except Exception as error:
                call_result = {"success": False, "error": str(error), "latency_ms": 0}

            success = call_result.get("success", False)
            latency_ms = call_result.get("latency_ms", 0)
            error = call_result.get("error", "")
            retryable = not success and self._is_retryable_error(error)
            call_usage = call_result.get("usage", {})
            call_cost = self._shenwen_cost(
                call_result.get("model", spec.model),
                call_usage,
                provider=spec.provider,
            )
            result["attempts"].append({
                "number": attempt + 1,
                "model": spec.full_id,
                "provider": spec.provider,
                "timeout": timeout,
                "latency_ms": latency_ms,
                "success": success,
                "retryable": retryable,
                "error": error,
                "usage": call_usage,
                "cost": call_cost,
                "cost_status": "known" if call_cost else "unknown",
            })
            self._router.record_call(
                model_id=spec.full_id,
                task_type=task_type,
                success=success,
                latency_ms=latency_ms,
                provider=spec.provider,
                usage=call_result.get("usage", {}),
                cost=call_cost,
                attempts=result["attempts"],
                route_state=spec.route_state,
            )

            if success:
                result["success"] = True
                result["content"] = call_result.get("content", "")
                result["model"] = call_result.get("model", spec.model)
                result["provider"] = spec.provider
                result["usage"] = call_result.get("usage", {})
                # 顶层仅保留成功调用费用，完整链费用留在 attempts。
                result["cost"] = call_cost
                result["latency_ms"] = latency_ms
                result["tried_models"] = tried
                result["routing"] = self._router.resolve_route(
                    task_type,
                    task_context=task_context,
                    complexity=requested_complexity,
                    exclude_models=[],
                )
                result["routing"]["selected_labor"] = spec.full_id
                result["routing"]["selected_route_state"] = spec.route_state
                result["routing"]["fallback_chain"] = list(tried)
                self._router.mark_model_health(spec.full_id, True)
                if self._watchdog:
                    self._watchdog.record_success(spec.provider, latency_ms)
                return result

            last_error = error or "unknown error"
            if self._watchdog:
                self._watchdog.record_failure(spec.provider, last_error)
            if retryable and attempt + 1 < max_retries:
                # Give an escalation labour one bounded retry, then release
                # it so the normal Terra fallback can be selected.  Historical
                # execution profiles keep their existing same-model retry
                # semantics.
                if spec.route_state == "POC_COMPLEX_ESCALATION" and attempt >= 1:
                    self._router.mark_model_health(spec.full_id, False)
                    spec = None
                    continue
                same_model_attempts = sum(
                    1 for item in result["attempts"] if item.get("model") == spec.full_id
                )
                # One same-model retry covers a 502 blip.  Spending the whole
                # budget on DS41 leaves the daily miner idle even when OneAPI
                # or mini remains configured.
                if same_model_attempts < 2:
                    time.sleep(2 ** attempt)
                    continue
                self._router.mark_model_health(spec.full_id, False)
                spec = None
                continue
            if retryable:
                self._router.mark_model_health(spec.full_id, False)
                spec = None
                continue

            self._router.mark_model_health(spec.full_id, False)
            spec = None

        result["error"] = last_error
        result["tried_models"] = tried
        result["routing"]["fallback_chain"] = list(tried)
        result["routing"]["selected_labor"] = tried[-1] if tried else None
        result["routing"]["selected_route_state"] = "FAILED"
        return result

    def multi_chat(
        self,
        task_type: str,
        messages: List[Dict[str, str]],
        system_prompt: str = "",
        model_count: int = 3,
        diverse: bool = True,
        data_boundary: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        多模型并行调用（用于交叉验证、多视角）

        注意：是串行调用（避免并发复杂度），不是真并行。
        但对调用方来说，拿到的是多个模型的结果。

        Args:
            task_type: 任务类型
            messages: 对话消息
            system_prompt: 系统提示词
            model_count: 要几个模型的结果
            diverse: 是否不同厂商

        Returns:
            每个模型的结果列表
        """
        if not self._initialized:
            self.initialize()

        specs = self._router.select_models(
            task_type=task_type,
            count=model_count,
            diverse=diverse,
        )

        results = []
        for spec in specs:
            result = self.chat(
                task_type=task_type,
                messages=messages,
                system_prompt=system_prompt,
                max_retries=1,  # 多模型模式下每个模型只试一次
                selected_spec=spec,
                data_boundary=data_boundary,
            )
            result["requested_model"] = spec.full_id
            results.append(result)

        return results

    def generate_image(
        self,
        prompt: str,
        model: str = "gpt-image-2",
        timeout: int = 900,
        **kwargs,
    ) -> Dict[str, Any]:
        data_boundary = kwargs.pop("data_boundary", None)
        boundary = validate_data_boundary(data_boundary, target="MODEL_CONTEXT", payload=prompt)
        if not boundary["valid"]:
            return {
                "success": False,
                "images": [],
                "model": model,
                "provider": "shenwen_images",
                "usage": {},
                "latency_ms": 0,
                "error": "DATA_BOUNDARY_BLOCKED:" + ",".join(boundary["errors"]),
                "data_boundary": {
                    "data_class": boundary.get("data_class"),
                    "target": boundary.get("target"),
                    "allowed": False,
                },
            }
        if not self._initialized:
            self.initialize()

        result = {
            "success": False,
            "images": [],
            "model": model,
            "provider": "shenwen_images",
            "usage": {},
            "latency_ms": 0,
            "error": "",
        }
        provider = self._providers.get("shenwen_images")
        if not provider:
            result["error"] = "shenwen image provider is not configured"
            return result

        try:
            call_result = provider.generate_image(
                prompt=prompt,
                model=model,
                timeout=timeout,
                data_boundary=data_boundary,
                **kwargs,
            )
        except Exception as e:
            call_result = {"success": False, "error": str(e), "latency_ms": 0}

        result.update(call_result)
        if self._watchdog:
            if result["success"]:
                self._watchdog.record_success("shenwen_images", result["latency_ms"])
            else:
                self._watchdog.record_failure("shenwen_images", result["error"])
        return result

    def cross_validate(
        self,
        hypothesis: str,
        context: str = "",
        model_count: int = 3,
    ) -> Dict[str, Any]:
        """
        交叉验证 — 让多个模型质疑同一个假设

        Validator 用这个。

        Args:
            hypothesis: 待验证的假设
            context: 背景信息
            model_count: 用几个模型验证

        Returns:
            {
                "hypothesis": str,
                "validations": [{model, agree, reason, confidence}],
                "consensus": "agree" | "disagree" | "mixed",
                "agree_count": int,
                "disagree_count": int,
            }
        """
        system_prompt = (
            "你是一个严谨的验证者。你的任务是批判性审视给定的假设，"
            "寻找反例、逻辑漏洞、证据不足的地方。"
            "不要轻易同意，要保持怀疑态度。"
            "用 JSON 输出：{\"agree\": true/false, \"reason\": \"...\", \"confidence\": 0-1}"
        )

        user_msg = f"假设：{hypothesis}\n\n背景信息：{context}\n\n请验证这个假设是否成立。"

        results = self.multi_chat(
            task_type="cross_validation",
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=system_prompt,
            model_count=model_count,
            diverse=True,
        )

        validations = []
        agree_count = 0
        disagree_count = 0

        for r in results:
            validation = {
                "model": r.get("model", ""),
                "provider": r.get("provider", ""),
                "success": r.get("success", False),
                "agree": None,
                "reason": "",
                "confidence": 0,
            }

            if r.get("success") and r.get("content"):
                try:
                    content = r["content"]
                    # 尝试提取 JSON
                    import re
                    json_match = re.search(r'\{[^{}]+\}', content)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        validation["agree"] = parsed.get("agree")
                        validation["reason"] = parsed.get("reason", "")
                        validation["confidence"] = parsed.get("confidence", 0)
                    else:
                        # 粗略判断
                        text_lower = content.lower()
                        validation["agree"] = "同意" in content or "agree" in text_lower
                        validation["reason"] = content[:500]
                except Exception:
                    validation["reason"] = r["content"][:500]

                if validation["agree"] is True:
                    agree_count += 1
                elif validation["agree"] is False:
                    disagree_count += 1

            validations.append(validation)

        consensus = "mixed"
        if agree_count > 0 and disagree_count == 0:
            consensus = "agree"
        elif disagree_count > 0 and agree_count == 0:
            consensus = "disagree"

        return {
            "hypothesis": hypothesis,
            "validations": validations,
            "consensus": consensus,
            "agree_count": agree_count,
            "disagree_count": disagree_count,
            "total_models": len(validations),
        }

    def get_stats(self) -> Dict[str, Any]:
        """获取矿工池统计"""
        if not self._initialized:
            self.initialize()

        router_stats = self._router.get_stats()
        cred_stats = self._credential_mgr.get_stats()

        return {
            "initialized": self._initialized,
            "providers": {
                "available": list(self._providers.keys()),
                "total_configured": len(cred_stats),
                "credentials": cred_stats,
            },
            "router": router_stats,
            "coze_assets_path": self._credential_mgr.coze_assets_path,
        }
