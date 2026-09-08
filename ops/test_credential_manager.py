from pathlib import Path


def test_credential_manager_accepts_current_oneapi_miner_label(tmp_path: Path):
    from core.miner_pool.credential_manager import CredentialManager

    assets = tmp_path / "private-assets"
    secret_dir = assets / "01_credentials"
    secret_dir.mkdir(parents=True)
    (secret_dir / "SECRET.md").write_text(
        "\n".join(
            [
                "## One API 配置",
                "- 地址: http://127.0.0.1:3000",
                "- 有效API token(miner-v2): v2-token-placeholder",
                "- 有效API token(miner-token): miner-token-placeholder",
            ]
        ),
        encoding="utf-8",
    )

    manager = CredentialManager(str(assets))
    assert manager.load() is True
    credential = manager.get("oneapi")
    assert credential is not None
    assert credential.base_url == "http://127.0.0.1:3000/v1"
    assert credential.primary_key == "miner-token-placeholder"
