#!/usr/bin/env python3
import sys
import tempfile
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeMinerPool:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or {
            "success": True,
            "content": "受控模型结论",
            "provider": "glm",
            "model": "glm-4-flash",
            "usage": {"total_tokens": 12},
            "latency_ms": 7,
            "error": "",
            "tried_models": ["glm:glm-4-flash"],
            "attempts": [],
        }

    def chat(self, task_type, messages, system_prompt="", **kwargs):
        self.calls.append({
            "task_type": task_type,
            "messages": messages,
            "system_prompt": system_prompt,
        })
        return self.response


class RetryingProvider:
    def __init__(self, failures_before_success=1, error="The read operation timed out"):
        self.calls = 0
        self.failures_before_success = failures_before_success
        self.error = error

    def chat(self, **kwargs):
        self.calls += 1
        if self.calls <= self.failures_before_success:
            return {"success": False, "error": self.error, "latency_ms": 1}
        return {
            "success": True,
            "content": "同角色重试成功",
            "model": "gpt-5.4-mini",
            "usage": {"total_tokens": 9},
            "latency_ms": 2,
        }


class RecordingProvider:
    def __init__(self, model):
        self.model = model
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        return {
            "success": True,
            "content": "provider result",
            "model": self.model,
            "usage": {"total_tokens": 1},
            "latency_ms": 1,
        }


class ProviderStatusWatchdog:
    def __init__(self, healthy):
        self.healthy = set(healthy)

    def is_healthy(self, provider_name):
        return provider_name in self.healthy

    def record_success(self, provider_name, latency_ms):
        pass

    def record_failure(self, provider_name, error):
        pass


def _wire_fake_miner_pool(daemon, miner_pool):
    daemon.miner_pool = miner_pool
    daemon.researcher.llm_router = miner_pool
    daemon.validator.llm_router = miner_pool


def _run_role_task(task_type, response=None):
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        miner_pool = FakeMinerPool(response)
        _wire_fake_miner_pool(daemon, miner_pool)
        task = daemon.task_pool.create_task(
            f"验证 {task_type} 角色路由",
            hypothesis="角色任务必须保持原始任务语义",
            priority="high",
            creator="test",
            tags=[f"task_type:{task_type}"],
        )
        daemon._run_task_lifecycle()
        stored = daemon.task_pool.load_task(task.task_id)
        return miner_pool, stored.outputs["model_execution"]


def test_daemon_passes_configured_miner_pool_asset_path(monkeypatch):
    from ace_daemon import AceDaemon

    captured = {}

    class CapturingMinerPool:
        def __init__(self, coze_assets_path=None, state_dir=None):
            captured["coze_assets_path"] = coze_assets_path
            captured["state_dir"] = state_dir

        def chat(self, **kwargs):
            return {"success": False, "error": "not used", "tried_models": []}

    monkeypatch.setattr("ace_daemon.MinerPool", CapturingMinerPool)

    with tempfile.TemporaryDirectory() as temp_dir:
        asset_path = Path(temp_dir) / "private-assets"
        AceDaemon(
            Path(temp_dir),
            {"runtime": {"miner_pool_assets_path": str(asset_path)}},
        )

    assert captured["coze_assets_path"] == str(asset_path)


def test_reasoning_task_records_research_and_validation_model_trace():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        miner_pool = FakeMinerPool()
        _wire_fake_miner_pool(daemon, miner_pool)
        task = daemon.task_pool.create_task(
            "验证主链模型执行",
            hypothesis="明确的 reasoning 任务应到达矿池",
            priority="high",
            creator="test",
            tags=["task_type:reasoning"],
        )

        daemon._run_task_lifecycle()

        stored = daemon.task_pool.load_task(task.task_id)
        trace = stored.outputs["model_execution"]
        assert [entry["role"] for entry in trace] == ["researcher", "validator"]
        assert all(entry["api_called"] for entry in trace)
        assert all(entry["api_result"] == "success" for entry in trace)
        assert all(entry["provider"] == "glm" for entry in trace)
        assert all(entry["model"] == "glm-4-flash" for entry in trace)
        assert len(miner_pool.calls) == 2


def test_discovery_route_metadata_does_not_block_reasoning_task():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        miner_pool = FakeMinerPool()
        _wire_fake_miner_pool(daemon, miner_pool)
        task = daemon.task_pool.create_task(
            "路由观察任务",
            hypothesis="route metadata is observational",
            priority="high",
            creator="test",
            tags=["task_type:reasoning"],
            outputs={"discovery": {"route": {"mode": "local_evidence_only"}}},
        )

        daemon._run_task_lifecycle()

        stored = daemon.task_pool.load_task(task.task_id)
        assert len(miner_pool.calls) == 2
        assert len(stored.outputs["model_execution"]) == 2


def test_explicit_local_only_task_does_not_call_miner_pool():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        miner_pool = FakeMinerPool()
        _wire_fake_miner_pool(daemon, miner_pool)
        task = daemon.task_pool.create_task(
            "本地证据任务",
            hypothesis="explicit local only",
            priority="high",
            creator="test",
            tags=["task_type:reasoning"],
            outputs={
                "model_task_admission": {
                    "eligible": False,
                    "classification": "local_evidence_only",
                },
            },
        )

        daemon._run_task_lifecycle()

        stored = daemon.task_pool.load_task(task.task_id)
        assert miner_pool.calls == []
        assert stored.outputs.get("model_execution", []) == []


def test_failed_model_call_persists_failure_trace_and_keeps_local_lifecycle():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        miner_pool = FakeMinerPool({
            "success": False,
            "content": "",
            "provider": "",
            "model": "",
            "usage": {},
            "latency_ms": 0,
            "error": "no available providers",
            "tried_models": ["glm:glm-4-flash", "nim:qwen"],
        })
        _wire_fake_miner_pool(daemon, miner_pool)
        task = daemon.task_pool.create_task(
            "验证失败调用留痕",
            hypothesis="模型不可用不能中断本地研究流程",
            priority="high",
            creator="test",
            tags=["task_type:strategic"],
        )

        daemon._run_task_lifecycle()

        stored = daemon.task_pool.load_task(task.task_id)
        trace = stored.outputs["model_execution"]
        assert [entry["api_result"] for entry in trace] == ["failed", "failed"]
        assert all(entry["api_called"] for entry in trace)
        assert all(entry["error"] == "no available providers" for entry in trace)
        assert all(entry["fallback"] for entry in trace)
        assert len(miner_pool.calls) == 2
        assert stored.status == "pending"
        assert stored.retry_after
        assert stored.outputs["last_validator_result"]["outcome"] == "rework_pending"


def test_miner_pool_initializes_shenwen_from_runtime_environment(monkeypatch):
    from core.miner_pool.miner_pool import MinerPool

    monkeypatch.setenv("SHENWEN_API_KEY", "test-runtime-key")
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")

    assert pool.initialize() is True
    assert "shenwen" in pool.available_providers


def test_role_profiles_register_native_strategic_execution_and_free_boundaries():
    from core.miner_pool.task_profiles import get_task_profile

    strategic = get_task_profile("strategic")
    execution = get_task_profile("execution")
    free = get_task_profile("free_exploration")

    assert strategic["expected_model"] == "gpt-5.6-terra"
    assert strategic["preferred_models"] == ["shenwen:gpt-5.6-terra"]
    assert strategic["allowed_providers"] == {"shenwen"}
    assert execution["expected_model"] == "gpt-5.4-mini"
    assert execution["preferred_models"] == ["shenwen:gpt-5.4-mini"]
    assert execution["allowed_providers"] == {"shenwen"}
    assert free["allowed_providers"] == {"glm", "nim", "ollama"}
    assert "shenwen:gpt-5.6-terra" not in free["preferred_models"]
    assert "shenwen:gpt-5.4-mini" not in free["preferred_models"]


def test_strategic_uses_native_profile_and_records_terra_result():
    response = {
        "success": True,
        "content": "战略结论",
        "provider": "shenwen",
        "model": "gpt-5.6-terra",
        "error": "",
        "tried_models": ["shenwen:gpt-5.6-terra"],
    }

    miner_pool, trace = _run_role_task("strategic", response)

    assert [call["task_type"] for call in miner_pool.calls] == ["strategic", "strategic"]
    assert all(entry["task_type"] == "strategic" for entry in trace)
    assert all(entry["profile"] == "strategic" for entry in trace)
    assert all(entry["expected_model"] == "gpt-5.6-terra" for entry in trace)
    assert all(entry["selected_model"] == "gpt-5.6-terra" for entry in trace)
    assert all(entry["result"] == "success" for entry in trace)


def test_execution_uses_native_profile_and_records_mini_result():
    response = {
        "success": True,
        "content": "执行结论",
        "provider": "shenwen",
        "model": "gpt-5.4-mini",
        "error": "",
        "tried_models": ["shenwen:gpt-5.4-mini"],
    }

    miner_pool, trace = _run_role_task("execution", response)

    assert [call["task_type"] for call in miner_pool.calls] == ["execution", "execution"]
    assert all(entry["task_type"] == "execution" for entry in trace)
    assert all(entry["profile"] == "execution" for entry in trace)
    assert all(entry["expected_model"] == "gpt-5.4-mini" for entry in trace)
    assert all(entry["selected_model"] == "gpt-5.4-mini" for entry in trace)
    assert all(entry["selected_model"] != "gpt-5.6-terra" for entry in trace)


def test_execution_rejects_strategic_model_response():
    response = {
        "success": True,
        "content": "错误角色结论",
        "provider": "shenwen",
        "model": "gpt-5.6-terra",
        "error": "",
        "tried_models": ["shenwen:gpt-5.6-terra"],
    }

    _, trace = _run_role_task("execution", response)

    assert all(entry["result"] == "failed" for entry in trace)
    assert all(entry["quality_gate"]["executed"] is False for entry in trace)
    assert all(entry["error"] == "selected provider/model violates task profile" for entry in trace)


def test_free_exploration_preserves_free_profile_and_provider_boundary():
    response = {
        "success": True,
        "content": "探索结论",
        "provider": "glm",
        "model": "glm-4-flash",
        "error": "",
        "tried_models": ["glm:glm-4-flash"],
    }

    miner_pool, trace = _run_role_task("free_exploration", response)

    assert [call["task_type"] for call in miner_pool.calls] == ["free_exploration", "free_exploration"]
    assert all(entry["profile"] == "free_exploration" for entry in trace)
    assert all(entry["provider"] in {"glm", "nim", "ollama"} for entry in trace)
    assert all(entry["selected_model"] not in {"gpt-5.6-terra", "gpt-5.4-mini"} for entry in trace)


def test_fa_quality_gate_requires_successful_model_result():
    failed_response = {
        "success": False,
        "content": "",
        "provider": "shenwen",
        "model": "",
        "error": "provider unavailable",
        "tried_models": ["shenwen:gpt-5.6-terra"],
    }

    _, trace = _run_role_task("strategic", failed_response)

    assert all(entry["quality_gate"]["executed"] is False for entry in trace)
    assert all(entry["quality_gate"]["status"] == "not_run" for entry in trace)
    assert all(entry["selected_model"] == "gpt-5.6-terra" for entry in trace)


def test_fa_quality_gate_records_pass_after_successful_model_result():
    response = {
        "success": True,
        "content": "探索结论",
        "provider": "glm",
        "model": "glm-4-flash",
        "error": "",
        "tried_models": ["glm:glm-4-flash"],
    }

    _, trace = _run_role_task("free_exploration", response)

    assert all(entry["quality_gate"]["executed"] is True for entry in trace)
    assert all(entry["quality_gate"]["status"] == "pass" for entry in trace)


def test_execution_retries_the_same_allowed_model_after_transient_failure():
    from core.miner_pool.miner_pool import MinerPool

    provider = RetryingProvider()
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    pool._initialized = True
    pool._providers = {"shenwen": provider}
    pool._router.set_available_providers(["shenwen"])

    result = pool.chat(
        task_type="execution",
        messages=[{"role": "user", "content": "retry"}],
        max_retries=3,
    )

    assert result["success"] is True
    assert result["provider"] == "shenwen"
    assert result["model"] == "gpt-5.4-mini"
    assert provider.calls == 2
    assert [attempt["model"] for attempt in result["attempts"]] == [
        "shenwen:gpt-5.4-mini",
        "shenwen:gpt-5.4-mini",
    ]


def test_execution_does_not_retry_non_retryable_provider_error():
    from core.miner_pool.miner_pool import MinerPool

    provider = RetryingProvider(error="HTTP 401: unauthorized")
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    pool._initialized = True
    pool._providers = {"shenwen": provider}
    pool._router.set_available_providers(["shenwen"])

    result = pool.chat(
        task_type="execution",
        messages=[{"role": "user", "content": "retry"}],
        max_retries=3,
    )

    assert result["success"] is False
    assert provider.calls == 1
    assert result["attempts"][0]["retryable"] is False


def test_miner_pool_skips_provider_watchdog_offline_candidate_before_call():
    """Persisted OFFLINE health must constrain a fresh daemon's router."""
    from core.miner_pool.miner_pool import MinerPool

    github = RecordingProvider("gpt-4o")
    nim = RecordingProvider("nvidia/nemotron-3-ultra-550b-a55b")
    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    pool._initialized = True
    pool._providers = {"github_models": github, "nim": nim}
    pool._router.set_available_providers(["github_models", "nim"])
    pool._watchdog = ProviderStatusWatchdog({"nim"})

    result = pool.chat(
        task_type="reasoning",
        messages=[{"role": "user", "content": "route around known offline provider"}],
        max_retries=1,
    )

    assert result["success"] is True
    assert result["provider"] == "nim"
    assert result["tried_models"] == ["nim:nvidia/nemotron-3-ultra-550b-a55b"]
    assert github.calls == 0
    assert nim.calls == 1


class UsageProvider:
    def __init__(self, model, usage):
        self.model = model
        self.usage = usage

    def chat(self, **kwargs):
        return {
            "success": True,
            "content": "health response",
            "model": self.model,
            "usage": self.usage,
            "latency_ms": 4,
        }


def test_shenwen_terra_cost_uses_only_actual_usage_fields():
    from core.miner_pool.miner_pool import MinerPool

    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    pool._initialized = True
    pool._providers = {
        "shenwen": UsageProvider(
            "gpt-5.6-terra",
            {
                "prompt_tokens": 1_000_000,
                "completion_tokens": 1_000_000,
                "cache_read_tokens": 1_000_000,
                "cache_write_tokens": 1_000_000,
            },
        )
    }
    pool._router.set_available_providers(["shenwen"])

    result = pool.chat("strategic", [{"role": "user", "content": "cost"}])

    assert result["cost"] == {
        "currency": "USD",
        "input_usd": 0.44,
        "cache_read_usd": 0.044,
        "cache_write_usd": 0.55,
        "output_usd": 2.64,
        "total_usd": 3.674,
        "usage_source": "provider_response",
    }


def test_shenwen_mini_cost_treats_absent_usage_fields_as_zero():
    from core.miner_pool.miner_pool import MinerPool

    pool = MinerPool(coze_assets_path="C:/nonexistent-assets")
    pool._initialized = True
    pool._providers = {
        "shenwen": UsageProvider(
            "gpt-5.4-mini",
            {
                "prompt_tokens": 1_000_000,
                "completion_tokens": 1_000_000,
                "cache_read_tokens": 1_000_000,
            },
        )
    }
    pool._router.set_available_providers(["shenwen"])

    result = pool.chat("execution", [{"role": "user", "content": "cost"}])

    assert result["cost"] == {
        "currency": "USD",
        "input_usd": 0.165,
        "cache_read_usd": 0.0165,
        "cache_write_usd": 0.0,
        "output_usd": 0.99,
        "total_usd": 1.1715,
        "usage_source": "provider_response",
    }


def test_model_execution_trace_records_actual_usage_and_cost():
    response = {
        "success": True,
        "content": "战略结论",
        "provider": "shenwen",
        "model": "gpt-5.6-terra",
        "usage": {"prompt_tokens": 8, "completion_tokens": 4},
        "cost": {"currency": "USD", "total_usd": 0.00001408},
        "latency_ms": 9,
        "attempts": [{"number": 1, "success": True}],
        "error": "",
        "tried_models": ["shenwen:gpt-5.6-terra"],
    }

    _, trace = _run_role_task("strategic", response)

    assert all(entry["usage"] == response["usage"] for entry in trace)
    assert all(entry["cost"] == response["cost"] for entry in trace)
    assert all(entry["latency_ms"] == 9 for entry in trace)
    assert all(entry["attempts"] == response["attempts"] for entry in trace)


def test_daily_shenwen_health_calls_each_role_once_and_persists_total_cost():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        miner_pool = FakeMinerPool()
        miner_pool.response = {
            "success": True,
            "content": "healthy",
            "provider": "shenwen",
            "model": "",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "cost": {"currency": "USD", "total_usd": 0.25},
            "latency_ms": 5,
            "attempts": [{"number": 1, "success": True}],
            "error": "",
            "tried_models": [],
        }
        _wire_fake_miner_pool(daemon, miner_pool)

        first = daemon._run_shenwen_daily_health("2026-08-23")
        second = daemon._run_shenwen_daily_health("2026-08-23")

        assert first["executed"] is True
        assert second["executed"] is False
        assert [call["task_type"] for call in miner_pool.calls] == ["strategic", "execution"]
        assert daemon.state["shenwen_daily_cost"]["2026-08-23"]["total_usd"] == 0.5
        assert daemon.state["shenwen_daily_cost"]["2026-08-23"]["successful_calls"] == 2


def test_daily_cost_summary_includes_successful_task_trace_costs():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        date = "2026-08-23"
        task = daemon.task_pool.create_task(
            "记录当日神隐业务成本",
            creator="test",
            outputs={
                "model_execution": [{
                    "provider": "shenwen",
                    "api_result": "success",
                    "at": f"{date}T10:00:00",
                    "cost": {"currency": "USD", "total_usd": 0.75},
                }]
            },
        )
        daemon.state["shenwen_daily_health"] = {
            date: {"calls": [{"success": True, "cost": {"total_usd": 0.25}}]}
        }

        summary = daemon._refresh_shenwen_daily_cost(date)

        assert task.task_id
        assert summary["total_usd"] == 1.0
        assert summary["health_call_count"] == 1
        assert summary["task_call_count"] == 1
        assert summary["successful_calls"] == 2


def test_daily_cost_summary_counts_failed_task_calls_without_charging_them():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        date = "2026-08-23"
        daemon.task_pool.create_task(
            "记录失败调用",
            creator="test",
            outputs={
                "model_execution": [{
                    "provider": "shenwen",
                    "api_result": "failed",
                    "at": f"{date}T11:00:00",
                    "cost": {},
                }]
            },
        )
        daemon.state["shenwen_daily_health"] = {
            date: {"calls": [{"success": False, "cost": {}}]}
        }

        summary = daemon._refresh_shenwen_daily_cost(date)

        assert summary["total_usd"] == 0.0
        assert summary["successful_calls"] == 0
        assert summary["total_calls"] == 2


def test_run_once_does_not_create_daily_health_calls():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        miner_pool = FakeMinerPool()
        _wire_fake_miner_pool(daemon, miner_pool)

        daemon.run_once(dry_run=True)

        assert miner_pool.calls == []


def test_daemon_loop_runs_daily_health_call_before_regular_work():
    from ace_daemon import AceDaemon

    with tempfile.TemporaryDirectory() as temp_dir:
        daemon = AceDaemon(Path(temp_dir), {})
        miner_pool = FakeMinerPool({
            "success": True,
            "content": "OK",
            "provider": "shenwen",
            "model": "gpt-5.6-terra",
            "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            "cost": {"currency": "USD", "total_usd": 0.01},
            "latency_ms": 3,
            "attempts": [{"number": 1, "success": True}],
            "error": "",
            "tried_models": ["shenwen:gpt-5.6-terra"],
        })
        _wire_fake_miner_pool(daemon, miner_pool)

        def stop_after_regular_work(**kwargs):
            daemon.request_shutdown("test_complete")
            return {"auto_result": {"tasks_executed": 0}}

        daemon.run_once = stop_after_regular_work
        daemon.run_daemon(interval_seconds=0, max_iterations=1, dry_run=True)

        assert [call["task_type"] for call in miner_pool.calls] == [
            "strategic", "execution"
        ]
        assert daemon.state["shenwen_daily_cost"][
            daemon.state["shenwen_daily_health"].keys().__iter__().__next__()
        ]["total_usd"] == 0.02
