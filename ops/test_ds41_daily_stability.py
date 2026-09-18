#!/usr/bin/env python3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.runtime_continue_gate import evaluate_daemon_boundary


class FakeLaborPool:
    def __init__(self, providers):
        self.available_providers = list(providers)

    def chat(self, **kwargs):
        return {"success": False, "error": "probe failed", "provider": "shenwen", "model": "gpt-5.6-terra"}


def _daemon_with_pool(providers):
    from ace_daemon import AceDaemon
    temp_dir = tempfile.TemporaryDirectory()
    daemon = AceDaemon(Path(temp_dir.name), {})
    daemon.miner_pool = FakeLaborPool(providers)
    return daemon, temp_dir


def test_daily_health_execution_expects_ds41():
    from ace_daemon import AceDaemon
    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        daemon.miner_pool = FakeLaborPool(["shenwen_ds41"])
        calls = []
        def chat(task_type, messages, system_prompt="", **kwargs):
            calls.append(task_type)
            model = "deepseek-v4.1-flash" if task_type == "execution" else "gpt-5.6-terra"
            return {
                "success": True,
                "provider": "shenwen_ds41" if task_type == "execution" else "shenwen",
                "model": model,
                "usage": {},
                "cost": {},
                "latency_ms": 1,
                "attempts": [],
                "error": "",
            }
        daemon.miner_pool.chat = chat
        result = daemon._run_shenwen_daily_health("2026-09-17")
        assert result["executed"] is True
        expected = [call["expected_model"] for call in result["record"]["calls"]]
        assert expected == ["gpt-5.6-terra", "deepseek-v4.1-flash"]
        assert calls == ["strategic", "execution"]


def test_health_failure_keeps_gate_open_when_ds41_in_pool():
    daemon, temp_dir = _daemon_with_pool(["shenwen_ds41"])
    try:
        summary = daemon._sync_continue_gate_from_daily_health({
            "executed": True,
            "record": {"calls": [
                {"success": False, "task_type": "strategic", "provider": "shenwen"},
                {"success": False, "task_type": "execution", "provider": "shenwen_ds41"},
            ]},
        })
        assert summary["health_failed"] is True
        assert summary["fallbacks_configured"] is True
        assert daemon.state["continue_gate_provider_degraded"] is True
        assert daemon.state["continue_gate_fallbacks_configured"] is True
        boundary = evaluate_daemon_boundary(daemon.base_dir, daemon.state, daemon.config, "run-ds41")
        assert boundary["status"] == "CONTINUE"
        assert "NO_FALLBACK_ON_DEGRADED_PROVIDER" not in boundary["reason_codes"]
    finally:
        temp_dir.cleanup()


def test_health_failure_closes_when_no_labor_channel():
    daemon, temp_dir = _daemon_with_pool([])
    try:
        summary = daemon._sync_continue_gate_from_daily_health({
            "executed": True,
            "record": {"calls": [
                {"success": False, "task_type": "strategic", "provider": "shenwen"},
                {"success": False, "task_type": "execution", "provider": ""},
            ]},
        })
        assert summary["health_failed"] is True
        assert summary["fallbacks_configured"] is False
        boundary = evaluate_daemon_boundary(daemon.base_dir, daemon.state, daemon.config, "run-empty")
        assert boundary["status"] == "CLOSE_AND_HANDOFF"
        assert "NO_FALLBACK_ON_DEGRADED_PROVIDER" in boundary["reason_codes"]
    finally:
        temp_dir.cleanup()

def test_execution_falls_over_from_ds41_502_to_oneapi(monkeypatch):
    import core.miner_pool.miner_pool as miner_pool_module
    from core.miner_pool.miner_pool import MinerPool

    monkeypatch.setattr(miner_pool_module.time, "sleep", lambda _seconds: None)

    class FailProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, **kwargs):
            self.calls += 1
            return {
                "success": False,
                "error": "Upstream service temporarily unavailable. https://shenwenai.com",
                "latency_ms": 1,
            }

    class OkProvider:
        def __init__(self):
            self.calls = 0

        def chat(self, **kwargs):
            self.calls += 1
            return {
                "success": True,
                "content": "ok",
                "model": kwargs.get("model"),
                "usage": {"total_tokens": 1},
                "latency_ms": 1,
            }

    ds41 = FailProvider()
    oneapi = OkProvider()
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    pool._initialized = True
    pool._providers = {"shenwen_ds41": ds41, "oneapi": oneapi}
    pool._router.set_available_providers(["shenwen_ds41", "oneapi"])
    pool._watchdog = None

    result = pool.chat(
        task_type="execution",
        messages=[{"role": "user", "content": "keep working"}],
        max_retries=3,
    )

    assert result["success"] is True
    assert result["provider"] == "oneapi"
    assert result["model"] == "deepseek-v4.1-flash"
    assert ds41.calls == 2
    assert oneapi.calls == 1
    assert result["tried_models"] == [
        "shenwen_ds41:deepseek-v4.1-flash",
        "oneapi:deepseek-v4.1-flash",
    ]
