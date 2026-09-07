import importlib


def test_oneapi_default_matches_verified_route(monkeypatch):
    monkeypatch.delenv("ONEAPI_MODEL", raising=False)
    integration = importlib.import_module("core.miner_pool.integration")
    engine = importlib.import_module("core.survival_loop.engine")
    assert integration._provider_default_model("oneapi") == "gpt-5.4-mini"
    assert engine.DEFAULT_MODEL["oneapi"] == "gpt-5.4-mini"


def test_oneapi_model_can_be_selected_without_changing_other_routes(monkeypatch):
    monkeypatch.setenv("ONEAPI_MODEL", "some-mapped-model")
    integration = importlib.reload(importlib.import_module("core.miner_pool.integration"))
    engine = importlib.reload(importlib.import_module("core.survival_loop.engine"))
    assert integration._provider_default_model("oneapi") == "some-mapped-model"
    assert engine.DEFAULT_MODEL["oneapi"] == "some-mapped-model"
    assert integration._provider_default_model("github_models") == "gpt-4o"
    monkeypatch.delenv("ONEAPI_MODEL", raising=False)
    importlib.reload(integration)
    importlib.reload(engine)


