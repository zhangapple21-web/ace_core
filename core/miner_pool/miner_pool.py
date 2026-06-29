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
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

from .credential_manager import CredentialManager, ProviderCredential
from .model_router import ModelRouter, ModelSpec
from .task_profiles import get_task_profile
from .providers.openai_compatible import (
    NIMProvider,
    GitHubModelsProvider,
    GLMProvider,
    OpenRouterProvider,
    APIYiProvider,
    SambaNovaProvider,
    OneAPIProvider,
    OpenAICompatibleProvider,
)


PROVIDER_FACTORY = {
    "nim": NIMProvider,
    "github_models": GitHubModelsProvider,
    "glm": GLMProvider,
    "openrouter": OpenRouterProvider,
    "apiyi": APIYiProvider,
    "sambanova": SambaNovaProvider,
    "oneapi": OneAPIProvider,
    "modelscope": OpenAICompatibleProvider,
    "huggingface": OpenAICompatibleProvider,
    "ace_proxy": OpenAICompatibleProvider,  # ACE 自己的 OpenAI 兼容代理
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
        self._router = ModelRouter()
        self._state_dir = Path(state_dir) if state_dir else None
        self._initialized = False

        if self._state_dir:
            self._state_dir.mkdir(parents=True, exist_ok=True)

    def initialize(self) -> bool:
        """初始化矿工池：加载凭证 + 创建提供商实例"""
        if self._initialized:
            return True

        try:
            if not self._credential_mgr.load():
                return False

            available = self._credential_mgr.list_providers()
            self._router.set_available_providers(available)

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

    def chat(
        self,
        task_type: str,
        messages: List[Dict[str, str]],
        system_prompt: str = "",
        max_retries: int = 3,
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
            "task_type": task_type,
        }

        if not self._providers:
            result["error"] = "no available providers"
            return result

        # 准备 messages
        full_messages = []
        if system_prompt:
            full_messages.append({"role": "system", "content": system_prompt})
        full_messages.extend(messages)

        profile = get_task_profile(task_type)
        temperature = kwargs.pop("temperature", profile.get("temperature", 0.7))
        max_tokens = kwargs.pop("max_tokens", profile.get("max_tokens", 1024))
        timeout = kwargs.pop("timeout", profile.get("timeout", 60))

        tried = []
        last_error = ""

        for attempt in range(max_retries):
            # 选模型
            spec = self._router.select_model(
                task_type=task_type,
                exclude_models=tried,
            )
            if not spec:
                last_error = last_error or "no available models for this task type"
                break

            tried.append(spec.full_id)
            provider = self._providers.get(spec.provider)
            if not provider:
                self._router.mark_model_health(spec.full_id, False)
                continue

            # 调用
            try:
                call_result = provider.chat(
                    messages=full_messages,
                    model=spec.model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    **kwargs,
                )
            except Exception as e:
                call_result = {"success": False, "error": str(e), "latency_ms": 0}

            # 记录
            self._router.record_call(
                model_id=spec.full_id,
                task_type=task_type,
                success=call_result.get("success", False),
                latency_ms=call_result.get("latency_ms", 0),
            )

            if call_result.get("success"):
                result["success"] = True
                result["content"] = call_result.get("content", "")
                result["model"] = call_result.get("model", spec.model)
                result["provider"] = spec.provider
                result["usage"] = call_result.get("usage", {})
                result["latency_ms"] = call_result.get("latency_ms", 0)
                result["tried_models"] = tried
                self._router.mark_model_health(spec.full_id, True)
                return result
            else:
                last_error = call_result.get("error", "unknown error")
                self._router.mark_model_health(spec.full_id, False)

        result["error"] = last_error
        result["tried_models"] = tried
        return result

    def multi_chat(
        self,
        task_type: str,
        messages: List[Dict[str, str]],
        system_prompt: str = "",
        model_count: int = 3,
        diverse: bool = True,
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
            )
            result["requested_model"] = spec.full_id
            results.append(result)

        return results

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
