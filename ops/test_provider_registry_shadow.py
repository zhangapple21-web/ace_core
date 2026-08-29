from core.governance.provider_registry import ProviderRegistry


def test_register_shadow_catalog_is_unverified_and_non_production(tmp_path):
    registry = ProviderRegistry(str(tmp_path))
    registry.register_shadow_catalog(
        "shenwen_grok",
        "https://api.shenwenai.com/v1",
        {"grok-4.6": {"display_name": "Grok 4.6"}},
    )
    model = registry.get_model("shenwen_grok", "grok-4.6")
    assert model.status == "beta"
    assert model.verified is False
    assert model.meta["shadow_only"] is True
    assert model.meta["production_eligible"] is False
