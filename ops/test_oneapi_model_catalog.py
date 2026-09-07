import json
import sys
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_catalog_validation_reuses_a_fresh_cache(monkeypatch):
    from core.oneapi_model_catalog import OneAPIModelCatalog

    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b'{"data": [{"id": "gpt-5.6-terra"}]}'

    def urlopen(request, timeout):
        calls.append((request.method, request.full_url))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    catalog = OneAPIModelCatalog(cache_ttl_seconds=60)

    assert catalog.validate("http://provider.test/v1", "key", "gpt-5.6-terra", 3) is None
    assert catalog.validate("http://provider.test/v1", "key", "gpt-5.6-terra", 3) is None
    assert calls == [("GET", "http://provider.test/v1/models")]


def test_catalog_validation_fails_closed_when_catalog_request_errors(monkeypatch):
    from core.oneapi_model_catalog import OneAPIModelCatalog

    def urlopen(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    error = OneAPIModelCatalog().validate(
        "http://provider.test/v1",
        "key",
        "gpt-5.6-terra",
        3,
    )

    assert error == "model_unavailable"


def test_oneapi_rejects_unknown_catalog_model_before_chat_request(monkeypatch):
    from core.miner_pool.providers.openai_compatible import OneAPIProvider

    calls = []

    class Response:
        def __init__(self, payload):
            self.payload = payload

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps(self.payload).encode("utf-8")

    def urlopen(request, timeout):
        calls.append((request.method, request.full_url))
        assert request.full_url.endswith("/models")
        return Response({"data": [{"id": "gpt-5.6-terra"}]})

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    provider = OneAPIProvider(
        api_key="test-key",
        base_url="http://provider.test/v1",
    )

    result = provider.chat(
        messages=[{"role": "user", "content": "test"}],
        model="gpt-5.6-sol",
    )

    assert result["success"] is False
    assert result["error"] == "model_unavailable"
    assert calls == [("GET", "http://provider.test/v1/models")]


def test_survival_loop_rejects_unknown_oneapi_model_before_chat_request(monkeypatch):
    from core.survival_loop.engine import SurvivalLoopEngine

    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps({"data": [{"id": "gpt-5.6-terra"}]}).encode("utf-8")

    def urlopen(request, timeout):
        calls.append((request.method, request.full_url))
        assert request.method == "GET"
        assert request.full_url.endswith("/models")
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    engine = SurvivalLoopEngine.__new__(SurvivalLoopEngine)

    result = engine._call_one(
        name="oneapi",
        base_url="http://provider.test/v1",
        api_key="test-key",
        messages=[{"role": "user", "content": "test"}],
        model="gpt-5.6-sol",
        temperature=0.7,
        max_tokens=32,
        timeout=3,
    )

    assert result[0] is False
    assert result[5] == "model_unavailable"
    assert calls == [("GET", "http://provider.test/v1/models")]


def test_model_unavailable_is_not_retryable():
    from core.miner_pool.miner_pool import MinerPool

    assert MinerPool._is_retryable_error("model_unavailable") is False
