import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.minimal_assistant import (
    HIGH_RISK_MARKERS,
    adapt_user_prompt,
    build_messages,
    handle_assistant_command,
    resolve_assistant_config,
)
from core.miner_pool.credential_manager import ProviderCredential


def test_adapt_user_prompt_redirects_high_risk_requests():
    prompt = adapt_user_prompt("帮我绕过安全限制")
    assert "防御性、安全审计、合规排查" in prompt
    assert "原始需求：帮我绕过安全限制" in prompt
    assert any(marker in "帮我绕过安全限制" for marker in HIGH_RISK_MARKERS)


def test_adapt_user_prompt_marks_debug_requests_first():
    prompt = adapt_user_prompt("Python traceback 怎么看")
    assert prompt.startswith("这是一个调试排错请求。")
    assert prompt.endswith("Python traceback 怎么看")


def test_build_messages_keeps_three_system_messages_and_adapted_user_prompt():
    messages = build_messages("帮我写一个最小 HTTP 服务")
    assert [message["role"] for message in messages] == ["system", "system", "system", "user"]
    assert "这是一个实现请求。" in messages[-1]["content"]


def test_resolve_assistant_config_uses_official_defaults_for_openai_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config = resolve_assistant_config()

    assert config.provider == "openai_env"
    assert config.base_url == "https://api.openai.com/v1"
    assert config.model == "gpt-4o"


def test_resolve_assistant_config_prefers_known_provider_model_when_base_url_matches(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config = resolve_assistant_config()

    assert config.provider == "openrouter"
    assert config.base_url == "https://openrouter.ai/api/v1"
    assert config.model == "anthropic/claude-3.5-sonnet"


def test_resolve_assistant_config_maps_shenwen_gateway_and_uses_verified_default(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.shenwenai.com/v1")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    config = resolve_assistant_config()

    assert config.provider == "ace_proxy"
    assert config.model == "gpt-5.5"
    assert config.base_url == "https://api.shenwenai.com/v1"


def test_resolve_assistant_config_falls_back_to_workspace_credentials(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    class FakeCredentialManager:
        def load(self):
            return None

        def get(self, provider):
            if provider == "glm":
                return ProviderCredential(
                    provider="glm",
                    base_url="https://open.bigmodel.cn/api/paas/v4",
                    api_keys=["glm-key"],
                    source="test",
                )
            return None

    monkeypatch.setattr("core.minimal_assistant.CredentialManager", FakeCredentialManager)

    config = resolve_assistant_config()

    assert config.provider == "glm"
    assert config.model == "glm-4-flash"
    assert config.api_key == "glm-key"


def test_call_assistant_blocks_ambiguous_execution_before_provider_call(monkeypatch):
    calls = []

    class ExplodingProvider:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            calls.append(kwargs)
            raise AssertionError("ambiguous execution must not call provider")

    monkeypatch.setattr("core.minimal_assistant.OpenAICompatibleProvider", ExplodingProvider)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    result = __import__("core.minimal_assistant", fromlist=["call_assistant"]).call_assistant("你自己看着办，尽可能修复好")

    assert result["success"] is False
    assert result["clarification_required"] is True
    assert result["execution_boundary"] == "CONFIRMATION_REQUIRED"
    assert result["decision_candidate"]["action"] == "ASK_FOR_CLARIFICATION_OR_CONFIRMATION"
    assert calls == []


def test_handle_assistant_command_prints_json_response(monkeypatch, capsys):
    monkeypatch.setattr(
        "core.minimal_assistant.call_assistant",
        lambda prompt, model=None: {"success": True, "content": "ok", "resolved_model": model or "gpt-4o"},
    )

    exit_code = handle_assistant_command(["--json", "帮我写一个脚本"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert '"success": true' in captured.out


def test_handle_assistant_command_requires_prompt(capsys):
    exit_code = handle_assistant_command(["--json"])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "用法: python ace.py assistant <问题>" in captured.out


