#!/usr/bin/env python3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.governance.provider_registry import ProviderRegistry
from core.miner_pool.miner_pool import MinerPool
from core.miner_pool.model_router import ModelRouter
from core.miner_pool.task_profiles import SHENWEN_DS41_FLASH, get_task_profile


DS41_ID = "deepseek-v4.1-flash"
GOVERNANCE_DIR = Path(__file__).resolve().parent.parent / "08_GOVERNANCE"


def test_miner_pool_initializes_separate_shenwen_ds41_channel(monkeypatch):
    monkeypatch.setenv("SHENWEN_DS41_API_KEY", "test-ds41-key")
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")

    assert pool.initialize() is True
    assert "shenwen_ds41" in pool.available_providers
    assert pool._providers["shenwen_ds41"].provider_name == "shenwen_ds41"


def test_long_labor_selects_ds41_without_include_shadow():
    router = ModelRouter(available_providers=["shenwen_ds41"])

    for task_type in ("execution", "fast_response", "classification"):
        spec = router.select_model(task_type)
        assert spec is not None, task_type
        assert spec.full_id == SHENWEN_DS41_FLASH
        assert spec.provider == "shenwen_ds41"
        assert spec.model == DS41_ID


def test_ds41_profiles_are_not_shadow_only():
    execution = get_task_profile("execution")
    assert execution.get("shadow_only") is not True
    assert SHENWEN_DS41_FLASH in execution["preferred_models"]
    assert SHENWEN_DS41_FLASH in execution["allowed_models"]
    assert "shenwen_ds41" in execution["allowed_providers"]

    router = ModelRouter(available_providers=["shenwen_ds41"])
    assert router.select_model("execution", include_shadow=False).full_id == SHENWEN_DS41_FLASH


def test_ds41_does_not_replace_strategic_terra():
    router = ModelRouter(available_providers=["shenwen_ds41", "shenwen", "oneapi"])
    spec = router.select_model("strategic")
    assert spec is not None
    assert spec.model == "gpt-5.6-terra"
    assert spec.full_id != SHENWEN_DS41_FLASH


def test_provider_registry_marks_ds41_production_eligible():
    registry = ProviderRegistry(str(GOVERNANCE_DIR))
    model = registry.get_model("shenwen_ds41", DS41_ID)
    assert model is not None
    assert model.verified is True
    assert model.meta.get("shadow_only") is False
    assert model.meta.get("production_eligible") is True


def test_ds41_provider_does_not_force_thinking_disabled(monkeypatch):
    import json

    from core.miner_pool.providers.openai_compatible import ShenwenDs41Provider

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({
                "model": "deepseek-v4.1-flash",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"total_tokens": 2},
            }).encode("utf-8")

    def fake_urlopen(req, timeout=60):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    provider = ShenwenDs41Provider(api_key="test-ds41-key")
    result = provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="deepseek-v4.1-flash",
        max_tokens=16,
    )

    assert result["success"] is True
    assert result["content"] == "ok"
    assert "thinking" not in captured["payload"]


def test_ds41_provider_uses_reasoning_content_if_message_empty(monkeypatch):
    import json

    from core.miner_pool.providers.openai_compatible import ShenwenDs41Provider

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({
                "model": "deepseek-v4.1-flash",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning_content": "ok",
                    }
                }],
                "usage": {"total_tokens": 8},
            }).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: Response())

    provider = ShenwenDs41Provider(api_key="test-ds41-key")
    result = provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        model="deepseek-v4.1-flash",
    )

    assert result["success"] is True
    assert result["content"] == "ok"


def test_ds41_env_alias_swa_key(monkeypatch):
    monkeypatch.delenv("SHENWEN_DS41_API_KEY", raising=False)
    monkeypatch.setenv("SWA_KEY_DS41", "alias-ds41-key")
    from core.miner_pool.miner_pool import MinerPool
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    assert pool.initialize() is True
    assert "shenwen_ds41" in pool.available_providers

def test_ds41_reads_windows_user_env_when_process_env_missing(monkeypatch):
    monkeypatch.delenv("SHENWEN_DS41_API_KEY", raising=False)
    monkeypatch.delenv("SWA_KEY_DS41", raising=False)

    def fake_user_env(*args):
        name = args[-1]
        return "user-ds41-key" if name == "SHENWEN_DS41_API_KEY" else ""

    monkeypatch.setattr(
        "core.miner_pool.credential_manager.CredentialManager._windows_user_env",
        staticmethod(fake_user_env),
    )
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    assert pool.initialize() is True
    assert "shenwen_ds41" in pool.available_providers
