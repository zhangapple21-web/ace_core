import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class Response:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_probe_provider_ports_is_independent_and_read_only(monkeypatch):
    from core.provider_health_boundary import probe_provider_ports

    calls = []

    def get(url, timeout):
        calls.append(("GET", url, timeout))
        if "3000" in url:
            raise ConnectionError("connection refused")
        return Response(404 if url.endswith("/health") else 502, "gateway failure")

    monkeypatch.setattr("core.provider_health_boundary.requests.get", get)
    result = probe_provider_ports([3000, 3002], timeout_seconds=1)

    assert result["side_effects"] == "none"
    assert result["ports"]["3000"]["status"] == "unavailable"
    assert result["ports"]["3000"]["error_class"] == "connection_refused"
    assert result["ports"]["3002"]["status"] == "degraded"
    assert result["ports"]["3002"]["endpoints"]["/v1/models"]["status_code"] == 502
    assert all(method == "GET" for method, _, _ in calls)


def test_probe_provider_ports_does_not_touch_task_pool(monkeypatch, tmp_path):
    from core.provider_health_boundary import probe_provider_ports

    monkeypatch.setattr(
        "core.provider_health_boundary.requests.get",
        lambda url, timeout: Response(200, "ok"),
    )
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    result = probe_provider_ports([3000], timeout_seconds=1, evidence_dir=tmp_path)
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))

    assert result["side_effects"] == "none"
    assert before == after

