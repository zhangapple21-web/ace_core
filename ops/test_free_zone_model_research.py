from core.free_zone_model_research import FreeZoneModelResearch


class Pool:
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        assert kwargs["task_type"] == "free_exploration"
        # The adapter must declare the sandbox prompt egressable; without a
        # declaration the standing boundary fails every turn closed.
        assert kwargs.get("data_boundary") == {"data_class": "PUBLIC"}
        # The unpinned profile gets one fallback rotation; a pinned seat is
        # exactly one attempt and may not fall through to a paid provider.
        assert kwargs.get("max_retries") == (1 if "selected_spec" in kwargs else 2)
        return {"success": True, "content": '{"hypotheses":["h"],"counterexamples":["c"],"evidence_gaps":["g"],"next_verification":["v"]}', "provider": "nim", "model": "fixture-model", "usage": {"total_tokens": 3}, "latency_ms": 2, "attempts": [{"model": "fixture:model", "provider": "nim", "success": True, "retryable": False, "latency_ms": 2, "error": ""}]}


class UnavailablePool:
    def __init__(self):
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": False, "content": "", "provider": "nim", "model": "", "usage": {}, "latency_ms": 1, "attempts": []}


def test_model_turn_uses_existing_free_profile_and_keeps_raw_text_out_of_receipt():
    seed = {"seed_hash": "a" * 64, "transfer_hypothesis": "h", "counterexample_question": "q", "next_verification": "v"}
    pool = Pool()
    receipt = FreeZoneModelResearch(pool).run(seed)
    assert pool.calls[0]["max_retries"] == 2
    assert "selected_spec" not in pool.calls[0]
    assert receipt["outcome"] == "MODEL_TURN_RECORDED"
    assert receipt["raw_content_retained"] is False
    assert "content" not in receipt
    assert receipt["production_integration"] is False
    assert receipt["model_execution_realm"] == "CLOUD"
    assert receipt["dual_source_status"] == "LOCAL_BASELINE_PLUS_CLOUD"
    assert receipt["invitation"]["cloud_invitation_status"] == "CLOUD_RESPONSE_RECORDED"
    assert receipt["invitation"]["miner_pool_invitation_status"] == "DISPATCHED"
    assert receipt["research_material"]["status"] == "STRUCTURED_DISTILLATION"
    assert receipt["research_material"]["contract"] == "hypotheses"
    assert all("text" in item for item in receipt["research_material"]["items"])


class ScriptedProvider:
    """Fail once like a pre-subprocess flap, then serve."""

    def __init__(self, fail_error):
        self.fail_error = fail_error
        self.calls = 0

    def chat(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {"success": False, "content": "", "model": "", "usage": {},
                    "latency_ms": 0, "error": self.fail_error}
        return {"success": True, "content": "second twin serves", "model": "m2",
                "usage": {}, "latency_ms": 5, "error": ""}


def test_non_retryable_flap_rotates_to_the_next_twin():
    """The 23:26 shape: worker aggregate, attempts 0ms, second twin must serve."""
    from core.miner_pool.miner_pool import MinerPool
    from core.miner_pool.model_router import ModelSpec

    pool = MinerPool.__new__(MinerPool)
    pool._providers = {"prov_a": ScriptedProvider("opencode_all_models_failed"),
                       "prov_b": ScriptedProvider("never fails twice")}
    pool._providers["prov_b"].calls = 1  # only prov_a fails its first call
    pool._watchdog = None
    pool._initialized = True
    pool._routing_ledger = None

    specs = [ModelSpec.from_id("prov_a:m1"), ModelSpec.from_id("prov_b:m2")]

    class Router:
        def resolve_route(self, *a, **k):
            return {}

        def select_model(self, **kwargs):
            tried = kwargs.get("exclude_models") or []
            for spec in specs:
                if spec.full_id not in tried:
                    return spec
            return None

        def mark_model_health(self, *a, **k):
            return None

        def record_call(self, *a, **k):
            return None

    pool._router = Router()
    result = pool.chat(
        task_type="free_exploration",
        messages=[{"role": "user", "content": "probe"}],
        system_prompt="Free Zone only.",
        max_retries=2,
        max_tokens=16,
        data_boundary={"data_class": "PUBLIC"},
    )
    assert result["success"] is True
    assert result["provider"] == "prov_b"
    assert [a["model"] for a in result["attempts"]] == ["prov_a:m1", "prov_b:m2"]


def test_pinned_model_is_passed_as_selected_spec_with_single_attempt():
    from core.miner_pool.model_router import ModelSpec

    seed = {"seed_hash": "c" * 64, "transfer_hypothesis": "h", "counterexample_question": "q", "next_verification": "v"}
    pool = Pool()
    FreeZoneModelResearch(pool).run(seed, selected_model="opencode_cli:muse-spark-1.3-contributor-free")
    request = pool.calls[0]
    assert request["selected_spec"] == ModelSpec.from_id("opencode_cli:muse-spark-1.3-contributor-free")
    assert "selected_model" not in request
    assert request["max_retries"] == 1
    assert "provider" not in request


def test_response_contract_and_system_prompt_are_bounded():
    import pytest

    seed = {"seed_hash": "e" * 64, "transfer_hypothesis": "h", "counterexample_question": "q", "next_verification": "v"}
    pool = Pool()
    with pytest.raises(ValueError):
        FreeZoneModelResearch(pool).run(seed, response_contract="arbitrary")
    with pytest.raises(ValueError):
        FreeZoneModelResearch(pool).run(seed, system_prompt="x" * 2001)
    with pytest.raises(ValueError):
        FreeZoneModelResearch(pool).run(seed, max_tokens=4096)
    with pytest.raises(ValueError):
        FreeZoneModelResearch(pool).run(seed, role="not a role")
    assert pool.calls == []


def test_invalid_pinned_model_is_rejected_before_pool_call():
    seed = {"seed_hash": "d" * 64, "transfer_hypothesis": "h", "counterexample_question": "q", "next_verification": "v"}
    pool = Pool()
    try:
        FreeZoneModelResearch(pool).run(seed, selected_model="opencode_cli")
    except ValueError as exc:
        assert "provider:model" in str(exc)
    else:
        raise AssertionError("unqualified model id must fail closed")
    assert pool.calls == []


def test_local_baseline_is_deterministic_and_survives_cloud_unavailability():
    seed = {"seed_hash": "b" * 64, "transfer_hypothesis": "h", "counterexample_question": "q", "next_verification": "v"}
    cloud = FreeZoneModelResearch(Pool()).run(seed)
    unavailable = FreeZoneModelResearch(UnavailablePool()).run(seed)
    assert cloud["local_baseline"] == unavailable["local_baseline"]
    assert unavailable["dual_source_status"] == "LOCAL_BASELINE_ONLY"
    assert unavailable["research_material"] == {"status": "UNAVAILABLE", "contract": "hypotheses"}
    assert unavailable["taskpool_mutated"] is False
    assert unavailable["invitation"]["cloud_invitation_status"] == "CLOUD_ROUTE_NOT_ATTEMPTED"


