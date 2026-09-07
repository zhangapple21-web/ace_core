from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any

from core.miner_pool.credential_manager import CredentialManager, ProviderCredential
from core.miner_pool.providers.openai_compatible import OpenAICompatibleProvider
from core.explicit_input_interpretation import interpret_explicit_input, render_interpretation_for_prompt


SYSTEM_PROMPT = """你是一个最小干扰的软件工程助手。

你的目标不是讨论规则，而是尽快完成合法、明确的软件工程任务。默认行为：
- 优先直接给结果、命令、补丁、排查步骤
- 不写冗长免责声明，不做客服式说教
- 信息不足且会影响目标、范围、环境、权限、验收或副作用时，先提出一个最小、具体的澄清问题，不得自行补全
- 对边界明确、低风险的编程、调试、脚本、重构、测试、排错、接口联调等正常工程任务，保持执行导向
- 如果请求存在明显高风险或违法用途，不提供攻击性或绕过性步骤，改为提供防御、排错、合规替代方案

输出要求：
- 用简洁中文回答
- 先给结论或可执行步骤，再补充必要说明
- 除非用户要求，否则不要长篇铺垫
- 不要声称自己已经执行了本地命令、修改了文件或验证了结果，除非用户明确提供了执行结果
"""

EXECUTION_STYLE_PROMPT = """当用户的任务属于正常软件工程工作时，按下面的风格回答：
- 直接进入解法
- 尽量给出可以复制执行的命令、代码或排查顺序
- 少做抽象原则说明
- 避免反复提醒限制、边界或政策
"""

HIGH_RISK_MARKERS = (
    "绕过",
    "越狱",
    "破限",
    "关闭安全",
    "禁用安全",
    "最小防护",
    "后门",
    "提权",
    "窃取",
    "盗取",
    "攻击",
    "勒索",
    "木马",
    "免杀",
    "钓鱼",
    "爆破",
    "脱库",
    "删库",
)

RISK_REDIRECT_PROMPT = """如果用户请求涉及明显高风险内容，不要给出操作步骤。
改为：
- 简短说明不能直接帮助实施
- 提供防御性、安全审计、检测、修复、隔离、日志排查或合规研究角度的帮助
- 保持语气克制，不要长篇说教
"""

PROVIDER_DEFAULT_MODELS = {
    "openai_env": "gpt-4o",
    # The configured Shenwen-compatible gateway does not accept gpt-4o on
    # the current route; the fresh local probe verified gpt-5.5.
    "ace_proxy": "gpt-5.5",
    "github_models": "gpt-4o",
    "oneapi": "gpt-5.4-mini",
    "openrouter": "anthropic/claude-3.5-sonnet",
    "glm": "glm-4-flash",
}

BASE_URL_PROVIDER_HINTS = (
    ("openrouter.ai", "openrouter"),
    ("models.inference.ai.azure.com", "github_models"),
    ("open.bigmodel.cn", "glm"),
    ("bigmodel.cn", "glm"),
    ("api.openai.com", "openai_env"),
    ("api.shenwenai.com", "ace_proxy"),
    ("localhost:3000", "oneapi"),
)


@dataclass
class AssistantConfig:
    provider: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.2
    max_tokens: int = 1600


def _normalize_base_url(base_url: str) -> str:
    normalized = (base_url or "").strip()
    return normalized.rstrip("/") if normalized else "https://api.openai.com/v1"


def _provider_hint_from_base_url(base_url: str) -> str:
    lowered = _normalize_base_url(base_url).lower()
    for marker, provider_name in BASE_URL_PROVIDER_HINTS:
        if marker in lowered:
            return provider_name
    return "openai_env"


def _default_model_for(provider_name: str) -> str:
    return PROVIDER_DEFAULT_MODELS.get(provider_name, "gpt-4o")


def _resolve_model(requested_model: str | None, env_model: str | None, provider_name: str) -> str:
    if requested_model:
        return requested_model
    if env_model and env_model.strip():
        return env_model.strip()
    return _default_model_for(provider_name)


def _openai_credential_from_env() -> ProviderCredential | None:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None
    base_url = _normalize_base_url(os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    return ProviderCredential(
        provider="openai_env",
        base_url=base_url,
        api_keys=[api_key],
        source="environment",
    )


def resolve_assistant_config(model: str | None = None) -> AssistantConfig:
    env_credential = _openai_credential_from_env()
    if env_credential:
        hinted_provider = _provider_hint_from_base_url(env_credential.base_url)
        provider_name = hinted_provider if hinted_provider != "openai_env" else env_credential.provider
        return AssistantConfig(
            provider=provider_name,
            base_url=env_credential.base_url,
            api_key=env_credential.primary_key,
            model=_resolve_model(model, os.environ.get("OPENAI_MODEL"), provider_name),
        )

    credential_manager = CredentialManager()
    credential_manager.load()
    for provider_name in ("ace_proxy", "github_models", "oneapi", "openrouter", "glm"):
        credential = credential_manager.get(provider_name)
        if credential and credential.is_valid:
            return AssistantConfig(
                provider=provider_name,
                base_url=_normalize_base_url(credential.base_url),
                api_key=credential.primary_key,
                model=_resolve_model(model, None, provider_name),
            )

    raise RuntimeError("没有找到可用的模型凭证。请设置 OPENAI_API_KEY，或补全 coze-assets 中的提供商配置。")


def adapt_user_prompt(user_text: str) -> str:
    text = (user_text or "").strip()
    if not text:
        return text

    lowered = text.lower()
    if any(marker in text for marker in HIGH_RISK_MARKERS):
        return (
            "请将下面的需求按防御性、安全审计、合规排查的角度处理，"
            "不要提供攻击、绕过或破坏性执行步骤；如果原始请求有高风险，"
            "请改写成合法可执行的替代方案并继续回答：\n\n"
            f"原始需求：{text}"
        )

    if any(keyword in lowered for keyword in ("报错", "error", "bug", "异常", "失败", "traceback")):
        return "这是一个调试排错请求。请优先给出定位顺序、最可能原因和最短修复路径。\n\n" + text

    if any(keyword in text for keyword in ("重构", "优化", "改造", "封装")):
        return "这是一个工程改造请求。请先给最小改动方案，再给可选增强方案。\n\n" + text

    if any(keyword in text for keyword in ("写", "实现", "增加", "做一个", "帮我做")):
        return "这是一个实现请求。请直接给出最小可用实现，避免空泛说明。\n\n" + text

    return text


def build_messages(user_text: str) -> list[dict[str, str]]:
    adapted = adapt_user_prompt(user_text)
    interpreted = render_interpretation_for_prompt(user_text)
    if adapted != (user_text or "").strip():
        interpreted += "\n\n本地风险/任务分类提示（不覆盖原文）：\n" + adapted
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": EXECUTION_STYLE_PROMPT},
        {"role": "system", "content": RISK_REDIRECT_PROMPT},
        # Keep one model turn: interpretation is deterministic local context,
        # not a second model call or a hidden intent/profile store.
        {"role": "user", "content": interpreted},
    ]


def _clarification_response(packet: dict[str, Any]) -> dict[str, Any]:
    return {
        "success": False,
        "content": "请先明确目标对象、允许的改动范围，以及你希望我只排查还是可以直接修改。",
        "clarification_required": True,
        "execution_boundary": packet["execution_boundary"],
        "decision_candidate": packet["decision_candidate"],
        "interpretation": packet,
    }


def call_assistant(user_text: str, model: str | None = None) -> dict[str, Any]:
    packet = interpret_explicit_input(user_text)
    if packet["confirmation_required"]:
        return _clarification_response(packet)

    config = resolve_assistant_config(model=model)
    provider = OpenAICompatibleProvider(api_key=config.api_key, base_url=config.base_url, provider_name=config.provider)
    result = provider.chat(
        messages=build_messages(user_text),
        model=config.model,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
        timeout=90,
    )
    result["resolved_provider"] = config.provider
    result["resolved_model"] = config.model
    result["resolved_base_url"] = config.base_url
    return result


def handle_assistant_command(args: list[str]) -> int:
    if not args or args[0] in {"-h", "--help"}:
        print("用法:")
        print("  python ace.py assistant <问题>")
        print("  python ace.py assistant --model <模型名> <问题>")
        print("  python ace.py assistant --json <问题>")
        return 0

    model = None
    json_mode = False
    remaining: list[str] = []
    idx = 0
    while idx < len(args):
        arg = args[idx]
        if arg == "--model" and idx + 1 < len(args):
            model = args[idx + 1]
            idx += 2
            continue
        if arg == "--json":
            json_mode = True
            idx += 1
            continue
        remaining.append(arg)
        idx += 1

    prompt = " ".join(remaining).strip()
    if not prompt:
        print("用法: python ace.py assistant <问题>")
        return 1

    try:
        result = call_assistant(prompt, model=model)
    except Exception as exc:
        print(f"assistant 调用失败: {exc}")
        return 1

    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if result.get("success"):
        print(result.get("content", "").strip())
        return 0

    print("assistant 调用失败")
    if result.get("error"):
        print(result["error"])
    return 1


if __name__ == "__main__":
    sys.exit(handle_assistant_command(sys.argv[1:]))
