from core.miner_pool.model_router import ModelRouter
from core.miner_pool.task_profiles import (
    SHENWEN_GROK_45,
    SHENWEN_GROK_46,
    get_task_profile,
)


def test_grok_profiles_are_explicitly_shadow_only():
    research = get_task_profile("grok_research_shadow")
    coding = get_task_profile("grok_coding_shadow")

    assert research["shadow_only"] is True
    assert coding["shadow_only"] is True
    assert research["provider_registry_required"] is True
    assert coding["provider_registry_required"] is True
    assert research["preferred_models"] == [SHENWEN_GROK_46]
    assert coding["preferred_models"] == [SHENWEN_GROK_45]


def test_shadow_profiles_never_enter_normal_route():
    router = ModelRouter(available_providers=["shenwen_grok"])

    assert router.select_model("grok_research_shadow") is None
    assert router.select_models("grok_coding_shadow") == []


def test_shadow_profiles_can_be_selected_only_explicitly():
    router = ModelRouter(available_providers=["shenwen_grok"])

    research = router.select_model("grok_research_shadow", include_shadow=True)
    coding = router.select_model("grok_coding_shadow", include_shadow=True)

    assert research is not None
    assert research.full_id == SHENWEN_GROK_46
    assert coding is not None
    assert coding.full_id == SHENWEN_GROK_45
    assert router.select_shadow_model("grok_research_shadow").full_id == SHENWEN_GROK_46
