import json

import pytest

from core.archaeology_exporter import ArchaeologyExporter
from core.memory_index import MemoryIndex
from core.miner_pool.miner_pool import MinerPool
from core.miner_pool.providers.openai_compatible import OpenAICompatibleProvider, ShenwenImagesProvider
from core.mirror_constitution import validate_data_boundary
from core.task import Task


def test_miner_pool_blocks_unclassified_or_private_data_before_initializing(monkeypatch, tmp_path):
    pool = MinerPool(coze_assets_path=str(tmp_path / "missing-assets"))
    monkeypatch.setattr(pool, "initialize", lambda: pytest.fail("must reject before provider initialization"))

    result = pool.chat("reasoning", [{"role": "user", "content": "private prompt"}])

    assert result["success"] is False
    assert result["routing"]["selected_route_state"] == "DATA_BOUNDARY_BLOCKED"
    assert "data_boundary_record_missing" in result["error"]
    assert result["tried_models"] == []


def test_miner_pool_blocks_credential_like_public_payload_before_initializing(monkeypatch, tmp_path):
    pool = MinerPool(coze_assets_path=str(tmp_path / "missing-assets"))
    monkeypatch.setattr(pool, "initialize", lambda: pytest.fail("credential-like payload must block first"))
    fake_token = "sk-" + ("a" * 32)

    result = pool.chat(
        "reasoning",
        [{"role": "user", "content": f"use this token: {fake_token}"}],
        data_boundary={"data_class": "PUBLIC"},
    )

    assert result["success"] is False
    assert "credential_like_content_detected" in result["error"]


def test_miner_pool_allows_an_explicit_public_task_through_a_fake_provider(tmp_path):
    pool = MinerPool(coze_assets_path=str(tmp_path / "missing-assets"))

    class Router:
        def resolve_route(self, *_args, **_kwargs):
            return {"state": "selected"}

        def select_model(self, **_kwargs):
            return type("Spec", (), {
                "provider": "fake",
                "model": "test-model",
                "full_id": "fake:test-model",
                "route_state": "NORMAL",
            })()

        def mark_model_health(self, *_args):
            return None

        def record_call(self, **_kwargs):
            return None

    class FakeProvider:
        def chat(self, **_kwargs):
            return {"success": True, "content": "ok", "model": "test-model", "provider": "fake", "usage": {}, "latency_ms": 1}

    pool._initialized = True
    pool._router = Router()
    pool._providers = {"fake": FakeProvider()}
    result = pool.chat("reasoning", [{"role": "user", "content": "public prompt"}], data_boundary={"data_class": "PUBLIC"})

    assert result["success"] is True
    assert result["data_boundary"]["allowed"] is True
    assert result["data_boundary"]["data_class"] == "PUBLIC"


def test_openai_compatible_provider_blocks_missing_and_forged_sanitization_before_network(monkeypatch):
    calls = []
    monkeypatch.setattr("core.miner_pool.providers.openai_compatible.urllib.request.urlopen", lambda *a, **k: calls.append((a, k)))
    provider = OpenAICompatibleProvider(api_key="fake", base_url="https://example.invalid/v1")

    missing = provider.chat(messages=[{"role": "user", "content": "x"}], model="test")
    forged = provider.chat(
        messages=[{"role": "user", "content": "x"}],
        model="test",
        data_boundary={"data_class": "STRUCTURE", "sanitized": True},
    )
    token = "sk-" + ("a" * 32)
    public_but_sensitive = provider.chat(
        messages=[{"role": "user", "content": f"token={token}"}],
        model="test",
        data_boundary={"data_class": "PUBLIC"},
    )

    assert "DATA_BOUNDARY_BLOCKED" in missing["error"]
    assert "trusted_sanitization_receipt_required" in forged["error"]
    assert "credential_like_content_detected" in public_but_sensitive["error"]
    assert calls == []


def test_openai_compatible_provider_allows_explicit_public_payload(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "ok"}}], "model": "test"}).encode()

    calls = []
    monkeypatch.setattr("core.miner_pool.providers.openai_compatible.govern_model_messages", lambda messages, **_kwargs: messages)
    monkeypatch.setattr("core.miner_pool.providers.openai_compatible.urllib.request.urlopen", lambda *a, **k: (calls.append((a, k)) or FakeResponse()))
    provider = OpenAICompatibleProvider(api_key="fake", base_url="https://example.invalid/v1")

    result = provider.chat(
        messages=[{"role": "user", "content": "public prompt"}],
        model="test",
        data_boundary={"data_class": "PUBLIC"},
    )

    assert result["success"] is True
    assert len(calls) == 1


def test_legacy_llm_router_blocks_private_or_unclassified_before_request(monkeypatch, tmp_path):
    from core.llm.client import LLMConfig, LLMRouter, ModelInfo

    calls = []
    monkeypatch.setattr("core.llm.client.requests.post", lambda *a, **k: calls.append((a, k)))
    router = LLMRouter.__new__(LLMRouter)
    router.models = [
        ModelInfo(
            name="test-model",
            provider="test",
            config=LLMConfig("https://example.invalid/v1/chat/completions", "fake-key"),
            priority=1,
        )
    ]

    with pytest.raises(RuntimeError, match="DATA_BOUNDARY_BLOCKED"):
        router.call([{"role": "user", "content": "private test"}])

    assert calls == []


def test_legacy_llm_router_does_not_register_hardcoded_oneapi_fallback(monkeypatch, tmp_path):
    from core.llm.client import LLMRouter

    monkeypatch.delenv("ACE_ONEAPI_API_KEY", raising=False)
    monkeypatch.delenv("ONEAPI_API_KEY", raising=False)
    router = LLMRouter(str(tmp_path / "empty-assets"))

    assert all(model.name != "oneapi-cloud" for model in router.models)


def test_survival_loop_and_telegram_notifier_block_private_defaults_before_network(monkeypatch):
    from core.notifier.tg_notifier import TgNotifier
    from core.survival_loop.engine import SurvivalLoopEngine

    calls = []
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: calls.append((a, k)))
    engine = SurvivalLoopEngine.__new__(SurvivalLoopEngine)
    result = engine.chat(messages=[{"role": "user", "content": "private"}])
    assert result["success"] is False
    assert "DATA_BOUNDARY_BLOCKED" in result["error"]

    notifier = TgNotifier.__new__(TgNotifier)
    notifier.enabled = True
    notifier._api_base = "https://example.invalid/bot-placeholder"
    notifier.chat_id = "placeholder"
    assert notifier._send_message("private notification") is False
    assert calls == []


def test_autonomous_kernel_experiment_blocks_private_input_before_model_or_persistence():
    from core.autonomous.kernel import AutonomousKernel

    class ExplodingEngine:
        available_providers = ["fake"]

        def chat(self, **_kwargs):
            pytest.fail("private data must not reach an LLM engine")

    kernel = AutonomousKernel.__new__(AutonomousKernel)
    kernel.llm_engine = ExplodingEngine()

    result = kernel.run_experiment("private experiment input")

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "DATA_BOUNDARY_BLOCKED"
    assert result["provider_calls"] == 0


def test_key_health_records_and_reports_never_include_visible_credential_prefix(tmp_path):
    from core.governance.key_health import KeyHealthManager

    fake_key = "test-only-credential-prefix-value"
    manager = KeyHealthManager(str(tmp_path))
    record = manager.record_success("test-provider", fake_key, 12)

    saved = manager.records_file.read_text(encoding="utf-8")
    report = manager.generate_markdown_report()
    assert fake_key not in saved
    assert "key_prefix" not in saved
    assert fake_key not in report
    assert fake_key[:10] not in report
    assert record.key_prefix == ""

    manager.record_failure("test-provider", fake_key, 20, reason=f"Authorization: Bearer {fake_key}")
    updated = manager.records_file.read_text(encoding="utf-8")
    assert fake_key not in updated
    assert "Authorization: Bearer" not in updated


def test_key_health_hides_legacy_prefix_loaded_from_existing_log(tmp_path):
    from core.governance.key_health import KeyHealthManager

    health_dir = tmp_path / "key_health"
    health_dir.mkdir()
    old_prefix = "legacy-prefix-must-not-render"
    old_record = {
        "key_id": "legacy-hash-id",
        "provider": "test-provider",
        "key_prefix": old_prefix,
        "success_count": 1,
        "failure_count": 0,
        "total_requests": 1,
        "success_rate": 1.0,
        "health_score": 100.0,
        "status": "healthy",
    }
    (health_dir / "key_health.jsonl").write_text(json.dumps(old_record) + "\n", encoding="utf-8")

    manager = KeyHealthManager(str(tmp_path))

    assert manager.get_provider_keys("test-provider")[0].key_prefix == ""
    assert old_prefix not in manager.generate_markdown_report()


def test_key_health_sanitizes_nested_legacy_metadata_before_resaving(tmp_path):
    from core.governance.key_health import KeyHealthManager

    health_dir = tmp_path / "key_health"
    health_dir.mkdir()
    legacy_prefix = "legacy-nested-prefix-must-not-survive"
    fake_token = "sk-" + ("b" * 32)
    old_record = {
        "key_id": "legacy-meta-record",
        "provider": "test-provider",
        "meta": {
            "api_key_prefix": legacy_prefix,
            "nested": {
                "Authorization": f"Bearer {fake_token}",
                "note": f"provider diagnostic mentions {fake_token}",
            },
            "safe_label": "kept",
        },
    }
    records_file = health_dir / "key_health.jsonl"
    records_file.write_text(json.dumps(old_record) + "\n", encoding="utf-8")

    manager = KeyHealthManager(str(tmp_path))
    record = manager.get_provider_keys("test-provider")[0]
    manager._save(record)
    saved = records_file.read_text(encoding="utf-8").splitlines()[-1]
    decoded = json.loads(saved)

    assert legacy_prefix not in saved
    assert fake_token not in saved
    assert "api_key_prefix" not in decoded["meta"]
    assert "Authorization" not in decoded["meta"]["nested"]
    assert decoded["meta"]["nested"]["note"].find("[REDACTED]") >= 0
    assert decoded["meta"]["safe_label"] == "kept"


def test_model_verification_evidence_never_contains_api_key_prefix(monkeypatch, tmp_path):
    from core.governance.model_verifier import ModelVerifier

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode("utf-8")

    monkeypatch.setattr("core.governance.model_verifier.urllib.request.urlopen", lambda *_args, **_kwargs: FakeResponse())
    fake_key = "test-only-model-key-value"
    verifier = ModelVerifier(str(tmp_path))
    result = verifier.verify_model(
        "test-provider", "test-model", api_key=fake_key, base_url="https://example.invalid/v1"
    )

    assert result.passed is True
    assert fake_key not in str(result.evidence)
    assert "api_key_prefix" not in result.evidence


def test_image_provider_blocks_unclassified_prompt_before_network(monkeypatch):
    calls = []
    monkeypatch.setattr("core.miner_pool.providers.openai_compatible.urllib.request.urlopen", lambda *a, **k: calls.append((a, k)))
    provider = ShenwenImagesProvider(api_key="fake", base_url="https://example.invalid/v1")

    result = provider.generate_image("private scene", model="test-image")

    assert result["success"] is False
    assert "DATA_BOUNDARY_BLOCKED" in result["error"]
    assert calls == []


def test_image_provider_blocks_credential_like_public_prompt_before_network(monkeypatch):
    calls = []
    monkeypatch.setattr("core.miner_pool.providers.openai_compatible.urllib.request.urlopen", lambda *a, **k: calls.append((a, k)))
    provider = ShenwenImagesProvider(api_key="fake", base_url="https://example.invalid/v1")

    result = provider.generate_image(
        "scene " + "ghp_" + ("a" * 30),
        model="test-image",
        data_boundary={"data_class": "PUBLIC"},
    )

    assert result["success"] is False
    assert "credential_like_content_detected" in result["error"]
    assert calls == []


def test_memory_write_defaults_to_private_and_export_rejects_private_or_legacy_entries(tmp_path):
    class FakeIdentity:
        name = "ACE"

        def continuity_mark(self):
            return "continuity"

    class FakeLexicon:
        def classify(self, _text):
            return []

    index = MemoryIndex(tmp_path / "memory", FakeIdentity(), FakeLexicon())
    index.add(title="private", content="private memory")
    entry = index._index[-1]
    assert entry["data_class"] == "PRIVATE"
    assert validate_data_boundary(entry, target="INTERNAL")["valid"] is True

    exporter = ArchaeologyExporter(tmp_path / "ace", str(tmp_path / "mine-seed"))
    with pytest.raises(ValueError, match="memory_export_data_boundary_blocked"):
        exporter.export_memory_index({"entries": [entry]})
    with pytest.raises(ValueError, match="memory_export_data_boundary_blocked"):
        exporter.export_memory_index({"entries": [{"summary": "legacy has no classification"}]})


def test_memory_export_allows_only_explicit_public_entries(tmp_path):
    exporter = ArchaeologyExporter(tmp_path / "ace", str(tmp_path / "mine-seed"))
    files = exporter.export_memory_index({"entries": [{"data_class": "PUBLIC", "summary": "public"}]})

    assert len(files) == 2
    with open(files[0], encoding="utf-8") as exported:
        assert json.load(exported)["entries"][0]["data_class"] == "PUBLIC"


def test_task_defaults_to_private_but_can_explicitly_classify_public_content():
    assert Task("RQ-private", "private").data_class == "PRIVATE"
    public = Task("RQ-public", "public", data_class="PUBLIC")
    assert Task.from_dict(public.to_dict()).data_class == "PUBLIC"
