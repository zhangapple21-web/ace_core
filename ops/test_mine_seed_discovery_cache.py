from pathlib import Path

import ace_daemon
from core.miner_pool import credential_manager


def test_mine_seed_discovery_caches_by_checkout_parent(monkeypatch, tmp_path):
    ace_daemon._MINE_SEED_DISCOVERY_CACHE.clear()
    checkout_parent = tmp_path / "workspace"
    checkout = checkout_parent / "ace_core"
    checkout.mkdir(parents=True)
    mine_seed_git = checkout_parent / "mine-seed" / ".git"
    mine_seed_git.mkdir(parents=True)
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    calls = []
    original_rglob = Path.rglob

    def tracked_rglob(self, pattern):
        calls.append((self, pattern))
        return original_rglob(self, pattern)

    monkeypatch.setattr(Path, "rglob", tracked_rglob)
    daemon = ace_daemon.AceDaemon.__new__(ace_daemon.AceDaemon)
    daemon.base_dir = checkout

    first = daemon._find_mine_seed()
    second = daemon._find_mine_seed()

    assert first == str(mine_seed_git.parent)
    assert second == first
    assert calls == [(checkout_parent, "mine-seed/.git")]


def test_mine_seed_discovery_cache_does_not_cross_checkout_parents(monkeypatch, tmp_path):
    ace_daemon._MINE_SEED_DISCOVERY_CACHE.clear()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    first_parent = tmp_path / "first"
    second_parent = tmp_path / "second"
    first_checkout = first_parent / "ace_core"
    second_checkout = second_parent / "ace_core"
    first_checkout.mkdir(parents=True)
    second_checkout.mkdir(parents=True)
    (first_parent / "mine-seed" / ".git").mkdir(parents=True)

    first = ace_daemon.AceDaemon.__new__(ace_daemon.AceDaemon)
    first.base_dir = first_checkout
    second = ace_daemon.AceDaemon.__new__(ace_daemon.AceDaemon)
    second.base_dir = second_checkout

    assert first._find_mine_seed() == str(first_parent / "mine-seed")
    assert second._find_mine_seed() is None


def test_legacy_artifact_fallback_discovery_is_cached_per_shared_scope(monkeypatch, tmp_path):
    ace_daemon._ECO_FALLBACK_DISCOVERY_CACHE.clear()
    ace_daemon._OMEGA_FALLBACK_DISCOVERY_CACHE.clear()
    home = tmp_path / "home"
    (home / "Downloads").mkdir(parents=True)
    (home / "Desktop").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    parent = tmp_path / "workspace"
    first_base = parent / "first"
    second_base = parent / "second"
    first_base.mkdir(parents=True)
    second_base.mkdir()
    artifact_dir = parent / "legacy"
    artifact_dir.mkdir()
    eco = artifact_dir / "eco_layer_fixture.json"
    omega = artifact_dir / "omega_final_fixture.json"
    eco.write_text("{}", encoding="utf-8")
    omega.write_text("{}", encoding="utf-8")
    first = ace_daemon.AceDaemon.__new__(ace_daemon.AceDaemon)
    first.base_dir = first_base
    second = ace_daemon.AceDaemon.__new__(ace_daemon.AceDaemon)
    second.base_dir = second_base

    assert first._find_eco_layer() == [str(eco)]
    assert second._find_eco_layer() == [str(eco)]
    assert first._find_omega_final() == [str(omega)]
    assert second._find_omega_final() == [str(omega)]


def test_credential_discovery_caches_by_effective_search_roots(monkeypatch, tmp_path):
    credential_manager._COZE_ASSET_DISCOVERY_CACHE.clear()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    secret = workspace / "coze-assets" / "01_credentials" / "SECRET.md"
    secret.parent.mkdir(parents=True)
    secret.write_text("fixture", encoding="utf-8")
    monkeypatch.setattr(Path, "cwd", classmethod(lambda cls: workspace))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))

    first = credential_manager.CredentialManager()._coze_assets_path
    second = credential_manager.CredentialManager()._coze_assets_path

    assert first == secret.parent.parent
    assert second == first


