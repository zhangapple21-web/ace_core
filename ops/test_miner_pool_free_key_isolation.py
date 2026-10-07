# Regression: free routes and paid routes must not share one health fate.
#
# Field evidence: the 3001 relay died, free-model calls through it failed,
# and the provider-granular watchdog marked the whole "oneapi" entry
# UNHEALTHY after consecutive failures. The miner's exclusion logic then
# fenced off every oneapi model, including paid ones the 3000 gateway still
# served fine. Splitting the free routes onto their own provider key gives
# each side an independent health ledger.
import os

os.environ.setdefault("ONEAPI_KEY", "test-key-for-routing-only")
os.environ.setdefault("ONEAPI_BASE_URL", "http://localhost:3000/v1")

from core.miner_pool import task_profiles as profiles
from core.miner_pool.miner_pool import PROVIDER_FACTORY
from core.miner_pool.credential_manager import CredentialManager


def test_free_entries_use_their_own_provider_key():
    text = open("core/miner_pool/task_profiles.py", encoding="utf-8").read()
    for name in [
        "fledge-alpha-free",
        "mimo-v2.6-flash-free",
        "muse-spark-1.3-contributor-free",
        "longcat-2.5-preview-free",
        "nemotron-3.5-lightning-free",
        "nemotron-3-ultra-free",
    ]:
        assert f'"oneapi_free:{name}"' in text, f"{name} must route via oneapi_free"
        assert f'"oneapi:{name}"' not in text, f"{name} must not share the paid key"


def test_factory_and_credentials_cover_the_free_key():
    assert "oneapi_free" in PROVIDER_FACTORY

    manager = CredentialManager()
    manager.load()
    assert "oneapi_free" in manager.list_providers()
    assert "oneapi" in manager.list_providers()
    assert manager.get("oneapi_free").base_url == manager.get("oneapi").base_url


def test_free_key_shares_the_localhost_fallback(monkeypatch):
    """Without ONEAPI_KEY, the free key must still resolve via OPENAI_API_KEY,
    exactly like oneapi does. Otherwise the split strands the free tier."""
    monkeypatch.delenv("ONEAPI_KEY", raising=False)
    monkeypatch.delenv("ONEAPI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "fallback-key-for-test")

    manager = CredentialManager()
    manager.load()
    assert "oneapi_free" in manager.list_providers()
    assert "oneapi" in manager.list_providers()


def test_paid_pool_survives_a_dead_free_key():
    """The exclusion that fenced the paid pool must not fire for oneapi."""
    from core.miner_pool.provider_watchdog import ProviderWatchdog

    watchdog = ProviderWatchdog()
    watchdog.register_provider(
        name="oneapi_free",
        base_url="http://localhost:3000/v1",
        api_key="test-key-for-routing-only",
    )
    for _ in range(5):
        watchdog.record_failure("oneapi_free", error="3001 relay down")
    assert watchdog.has_health_history("oneapi_free")
    assert not watchdog.is_healthy("oneapi_free")

    # oneapi itself never failed here, so a router consulting the watchdog
    # must still consider it eligible.
    assert not watchdog.has_health_history("oneapi") or watchdog.is_healthy("oneapi")
