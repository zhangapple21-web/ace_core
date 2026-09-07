from core.free_zone_model_research import FreeZoneModelResearch


class Pool:
    def chat(self, **kwargs):
        assert kwargs["task_type"] == "free_exploration"
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


def test_local_baseline_is_deterministic_and_survives_cloud_unavailability():
    seed = {"seed_hash": "b" * 64, "transfer_hypothesis": "h", "counterexample_question": "q", "next_verification": "v"}
    cloud = FreeZoneModelResearch(Pool()).run(seed)
    unavailable = FreeZoneModelResearch(UnavailablePool()).run(seed)
    assert cloud["local_baseline"] == unavailable["local_baseline"]
    assert unavailable["dual_source_status"] == "LOCAL_BASELINE_ONLY"
    assert unavailable["research_material"] == {"status": "UNAVAILABLE"}
    assert unavailable["taskpool_mutated"] is False
    assert unavailable["invitation"]["cloud_invitation_status"] == "CLOUD_ROUTE_NOT_ATTEMPTED"


