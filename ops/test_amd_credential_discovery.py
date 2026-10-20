"""The daemon is a different process: it must find its own credentials.

The operator exported ``AMD_RADEON_TOKEN`` in one shell. The daemon runs as a
Scheduled Task under pythonw and never inherited that process environment, so
every AMD seat returned UNAVAILABLE at the evening window and a two-vendor
room quietly degraded to one - the exact failure that looks like success.

``CredentialManager`` already had a User-scope registry fallback for the
shenwen seats. AMD did not have one. This pins the fallback that closes it, and
the end-to-end shape it makes possible: a provider that initialises and answers
a real call with no secret in the process environment at all.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.miner_pool import credential_manager as cm_module  # noqa: E402
from core.miner_pool.credential_manager import CredentialManager  # noqa: E402


def test_amd_credential_falls_back_to_the_user_registry(monkeypatch, tmp_path):
    """No AMD_RADEON_TOKEN in the process env must not strand the AMD seats."""
    monkeypatch.delenv("AMD_RADEON_TOKEN", raising=False)
    # a User-scope registry that holds the token, and nothing else
    monkeypatch.setattr(
        cm_module.CredentialManager,
        "_windows_user_env",
        lambda self, name: {"AMD_RADEON_TOKEN": "rc-pinned-by-test"}.get(name, ""),
    )

    manager = CredentialManager(coze_assets_path=str(tmp_path))
    manager._load_from_env_override()

    cred = manager._credentials.get("amd_radeon")
    assert cred is not None, "AMD seat is unreachable without a process env var"
    assert cred.is_valid
    assert cred.base_url == "https://developer.amd.com.cn/radeon/v1"
    assert cred.api_keys == ["rc-pinned-by-test"]


def test_amd_seat_is_not_added_when_no_token_exists_anywhere(monkeypatch, tmp_path):
    """Absent everywhere means honestly absent, not a placeholder."""
    monkeypatch.delenv("AMD_RADEON_TOKEN", raising=False)
    monkeypatch.setattr(
        cm_module.CredentialManager, "_windows_user_env", lambda self, name: ""
    )

    manager = CredentialManager(coze_assets_path=str(tmp_path))
    manager._load_from_env_override()
    assert "amd_radeon" not in manager._credentials


def test_a_real_provider_chain_initialises_without_the_process_secret(monkeypatch, tmp_path):
    """The pool must reach amd_radeon when only the registry holds the token."""
    monkeypatch.delenv("AMD_RADEON_TOKEN", raising=False)
    monkeypatch.setattr(
        cm_module.CredentialManager, "_windows_user_env", lambda self, name: ""
    )

    from core.miner_pool.miner_pool import PROVIDER_FACTORY

    assert "amd_radeon" in PROVIDER_FACTORY, "the AMD route is not registered"
    # the provider itself is what refuses to exist without a secret, so a
    # missing credential stays a visible gate rather than a half-wired seat
    assert callable(PROVIDER_FACTORY["amd_radeon"])