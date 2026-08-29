from core.miner_pool.miner_pool import MinerPool
from core.miner_pool.providers.openai_compatible import ShenwenGrokProvider


def test_shadow_task_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("SHENWEN_GROK_API_KEY", "test-grok-heavy-key")
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    assert pool.initialize()

    assert pool.chat("grok_research_shadow", [{"role": "user", "content": "x"}])["success"] is False


def test_shadow_task_records_provider_authoritative_cost(monkeypatch):
    monkeypatch.setenv("SHENWEN_GROK_API_KEY", "test-grok-heavy-key")
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    assert pool.initialize()

    def fake_chat(self, **kwargs):
        return {
            "success": True,
            "content": "OK",
            "model": kwargs["model"],
            "provider": "shenwen_grok",
            "usage": {"cost_in_usd_ticks": 1_234_567},
            "latency_ms": 12,
            "error": "",
        }

    monkeypatch.setattr(ShenwenGrokProvider, "chat", fake_chat)
    result = pool.chat(
        "grok_research_shadow",
        [{"role": "user", "content": "x"}],
        include_shadow=True,
    )

    assert result["success"] is True
    assert result["provider"] == "shenwen_grok"
    assert result["cost"]["total_usd"] == 1.234567
    assert result["cost"]["usage_source"] == "provider_response"


def test_new_provider_can_receive_its_first_probe():
    from core.miner_pool.provider_watchdog import ProviderWatchdog

    watchdog = ProviderWatchdog()
    watchdog.register_provider("new_provider", "https://example.invalid", "test-key")

    assert watchdog.is_healthy("new_provider") is False
    assert watchdog.has_health_history("new_provider") is False
