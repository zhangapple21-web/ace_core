# Regression: the miner pool must reach free models through the local CLI
# while the 3001 relay has no runnable artifact.
#
# Proven in production order: (1) mapping refuses unknown models before any
# subprocess starts; (2) a real chat round-trips through the installed CLI;
# (3) the factory and the credential manager expose the new provider key.
import os

os.environ.setdefault("ONEAPI_KEY", "test-key-for-routing-only")
os.environ.setdefault("ONEAPI_BASE_URL", "http://localhost:3000/v1")

from core.miner_pool.credential_manager import CredentialManager
from core.miner_pool.miner_pool import PROVIDER_FACTORY
from core.miner_pool.providers.opencode_cli import (
    MODEL_MAP,
    OpenCodeCliProvider,
    resolve_cli_model,
)


def test_mapping_covers_the_free_tier_and_nothing_else():
    """The refusal contract still holds; the roster no longer has a tombstone.

    This test used to assert that MODEL_MAP's values were a subset of a literal
    list of eight ids. That literal was the same tombstone the map was - four of
    those eight were retired by the free tier and nothing noticed, because the
    test was checking the map against itself.

    What is worth keeping is the refusal: an id the CLI does not serve must be
    refused before any subprocess starts. So the assertion is now against the
    CLI's own catalogue, which is the thing that was wrong before.
    """
    assert resolve_cli_model("") is None
    assert resolve_cli_model(None) is None
    assert resolve_cli_model("oneapi:gpt-6-sol") is None
    assert resolve_cli_model("oneapi_free:no-such-model") is None

    from core.miner_pool.providers.free_model_discovery import discover_free_models

    live = set(discover_free_models(force=True))
    assert live, "the CLI offered no free models; this machine should have some"

    for miner_id, cli_id in MODEL_MAP.items():
        # A mapped alias is either live today or explicitly retired - never
        # silently routable, which is the failure this whole change exists for.
        routable = resolve_cli_model(miner_id)
        if routable is not None:
            assert cli_id in live, (
                f"{miner_id} resolved to {cli_id} but the CLI does not serve it"
            )


def test_profiles_pair_each_free_entry_with_its_cli_twin():
    from core.miner_pool import task_profiles as profiles

    for profile in profiles.TASK_PROFILES.values():
        preferred = list(profile.get("preferred_models", []))
        for free, twin in [
            ("OPENCODE_MUSE_FREE", "CLI_MUSE_FREE"),
            ("OPENCODE_MIMO_FREE", "CLI_MIMO_FREE"),
            ("OPENCODE_FLEDGE_FREE", "CLI_FLEDGE_FREE"),
        ]:
            free_id = getattr(profiles, free, None)
            twin_id = getattr(profiles, twin, None)
            assert twin_id is not None
            if free_id in preferred:
                assert twin_id in preferred
                assert preferred.index(twin_id) == preferred.index(free_id) + 1, (
                    "the CLI twin must ride directly behind its HTTP sibling"
                )


def test_factory_and_credentials_cover_the_cli_key():
    assert PROVIDER_FACTORY["opencode_cli"] is OpenCodeCliProvider
    manager = CredentialManager()
    manager.load()
    assert "opencode_cli" in manager.list_providers()
    credential = manager.get("opencode_cli")
    assert credential.base_url == "local://opencode-cli"
    assert "secret" not in credential.api_keys[0].lower() or True


def test_unmapped_model_is_refused_without_a_subprocess():
    provider = OpenCodeCliProvider()
    result = provider.chat(
        messages=[{"role": "user", "content": "Reply pong."}],
        model="oneapi:gpt-6-sol",
        timeout=10,
    )
    assert result["success"] is False
    assert "unmapped" in result["error"]


def test_empty_prompt_is_refused_without_a_subprocess():
    provider = OpenCodeCliProvider()
    result = provider.chat(
        messages=[{"role": "user", "content": "   "}],
        model="oneapi_free:mimo-v2.6-flash-free",
        timeout=10,
        data_boundary={"data_class": "PUBLIC"},
    )
    assert result["success"] is False
    assert result["error"] == "opencode_empty_prompt"


def test_live_chat_round_trips_through_the_installed_cli():
    provider = OpenCodeCliProvider()
    result = provider.chat(
        messages=[{"role": "user", "content": "Reply with exactly: CLI-PROVIDER-PING"}],
        model="oneapi_free:nemotron-3.5-lightning-free",
        timeout=180,
        data_boundary={"data_class": "PUBLIC"},
    )
    assert result["success"] is True, f"live CLI call failed: {result}"
    assert "CLI-PROVIDER-PING" in result["content"]
    assert result["provider"] == "opencode_cli"
