import json
import logging

from core.assets.asset_curator import Asset, AssetCurator


def test_asset_metadata_and_serialization_never_contain_credential_values(tmp_path, caplog):
    secret_md = tmp_path / "01_credentials" / "SECRET.md"
    secret_md.parent.mkdir(parents=True)
    secret_md.write_text(
        "GitHub Models\n- Token: github-secret\n- Base: https://github.example/v1\n"
        "Bot1: telegram-secret\n",
        encoding="utf-8",
    )

    asset = Asset(
        name="direct_secret",
        url="https://example.test",
        type="secret",
        auth_type="bearer",
        metadata={"token": "direct-secret", "nested": [{"bot_token": "nested-secret"}], "label": "public"},
    )
    curator = AssetCurator()
    with caplog.at_level(logging.INFO):
        assert curator.discover_from_repo(str(tmp_path)) == 4

    serialized = [asset.to_dict()] + [item.to_dict() for item in curator.assets]
    output = json.dumps(serialized)

    for credential in ("direct-secret", "nested-secret", "github-secret", "telegram-secret"):
        assert credential not in output
        assert credential not in caplog.text

    assert asset.metadata["label"] == "public"
    assert "credential_ref" in asset.metadata
    assert curator.get_by_name("github_models_endpoint") is not None
    assert curator.get_by_name("github_models_key") is not None
    assert curator.get_by_name("telegram_bot_1") is not None


