from core.free_zone_model_research import FreeZoneModelResearch


class Pool:
    def chat(self, **kwargs):
        assert kwargs["task_type"] == "free_exploration"
        # The adapter must declare the sandbox prompt egressable; without a
        # declaration the standing boundary fails every turn closed.
        assert kwargs.get("data_boundary") == {"data_class": "PUBLIC"}
        # …and must allow one fallback rotation: single-shot turns die on
        # any pre-subprocess flap.
        assert kwargs.get("max_retries") == 2
        return {"success": True, "content": "hypothesis and counterexample", "provider": "nim", "model": "fixture-model", "usage": {"total_tokens": 3}, "latency_ms": 2, "attempts": [{"model": "fixture:model", "provider": "nim", "success": True, "retryable": False, "latency_ms": 2, "error": ""}]}


class UnavailablePool:
    def chat(self, **_):
        return {"success": False, "content": "", "provider": "nim", "model": "", "usage": {}, "latency_ms": 1, "attempts": []}


def test_model_turn_uses_existing_free_profile_and_keeps_raw_text_out_of_receipt():
    seed = {"seed_hash": "a" * 64, "transfer_hypothesis": "h", "counterexample_question": "q", "next_verification": "v"}
    receipt = FreeZoneModelResearch(Pool()).run(seed)
    assert receipt["outcome"] == "MODEL_TURN_RECORDED"
    assert receipt["raw_content_retained"] is False
    assert "content" not in receipt
    assert receipt["production_integration"] is False
    assert receipt["model_execution_realm"] == "CLOUD"
    assert receipt["dual_source_status"] == "LOCAL_BASELINE_PLUS_CLOUD"
    assert receipt["invitation"]["cloud_invitation_status"] == "CLOUD_RESPONSE_RECORDED"
    assert receipt["invitation"]["miner_pool_invitation_status"] == "DISPATCHED"


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


def test_local_baseline_is_deterministic_and_survives_cloud_unavailability():
    seed = {"seed_hash": "b" * 64, "transfer_hypothesis": "h", "counterexample_question": "q", "next_verification": "v"}
    cloud = FreeZoneModelResearch(Pool()).run(seed)
    unavailable = FreeZoneModelResearch(UnavailablePool()).run(seed)
    assert cloud["local_baseline"] == unavailable["local_baseline"]
    assert unavailable["dual_source_status"] == "LOCAL_BASELINE_ONLY"
    assert unavailable["research_material"] == {"status": "UNAVAILABLE"}
    assert unavailable["taskpool_mutated"] is False
    assert unavailable["invitation"]["cloud_invitation_status"] == "CLOUD_ROUTE_NOT_ATTEMPTED"


