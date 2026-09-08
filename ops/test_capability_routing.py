import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class _RoutingProvider:
    def __init__(self, failures_before_success=0):
        self.failures_before_success = failures_before_success
        self.calls = []

    def chat(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) <= self.failures_before_success:
            return {
                "success": False,
                "error": "The read operation timed out",
                "latency_ms": 1,
            }
        return {
            "success": True,
            "content": "ok",
            "model": kwargs["model"],
            "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
            "latency_ms": 2,
        }


def test_terra_is_default_and_astra_is_complex_escalation():
    from core.miner_pool.model_router import ModelRouter

    router = ModelRouter(available_providers=["shenwen"])

    normal = router.resolve_route("reasoning")
    complex_route = router.resolve_route(
        "reasoning",
        task_context={"complexity": "complex", "risk_level": "high"},
    )

    assert normal["selected_labor"] == "shenwen:gpt-5.6-terra"
    assert normal["selected_route_state"] == "DEFAULT"
    assert normal["default_labor"] == "shenwen:gpt-5.6-terra"
    assert complex_route["escalation"] is True
    assert complex_route["candidate_labor"][0] == "shenwen:gpt-6-astra"
    assert complex_route["selected_labor"] == "shenwen:gpt-6-astra"
    assert complex_route["selected_route_state"] == "POC_COMPLEX_ESCALATION"


def test_strategy_profile_allows_astra_only_when_complex():
    from core.miner_pool.model_router import ModelRouter

    router = ModelRouter(available_providers=["shenwen"])
    normal = router.select_model("strategic")
    complex_model = router.select_model(
        "strategic", task_context={"execution_discipline": {"complexity": "complex"}}
    )

    assert normal.full_id == "shenwen:gpt-5.6-terra"
    assert complex_model.full_id == "shenwen:gpt-6-astra"


def test_route_receipt_uses_existing_watchdog_snapshot():
    from core.miner_pool.model_router import ModelRouter
    from core.miner_pool.provider_watchdog import HEALTHY, ProviderWatchdog

    watchdog = ProviderWatchdog()
    watchdog.register_provider("shenwen", "http://provider.test/v1")
    watchdog._providers["shenwen"].status = HEALTHY
    watchdog._providers["shenwen"].total_calls = 1
    router = ModelRouter(available_providers=["shenwen"], watchdog=watchdog)

    decision = router.resolve_route("strategic")

    assert decision["watchdog"]["status"] == "OBSERVED"
    assert decision["watchdog"]["providers"]["shenwen"]["status"] == HEALTHY


def test_route_receipt_exposes_capability_labor_details_and_poc_boundary():
    from core.miner_pool.model_router import ModelRouter

    router = ModelRouter(available_providers=["shenwen"])
    decision = router.resolve_route(
        "strategic",
        task_context={"execution_discipline": {"complexity": "complex"}},
    )

    assert decision["capability"] == "deep_reasoning"
    assert decision["candidate_labor_details"][0]["provider_and_model"] == "shenwen:gpt-6-astra"
    assert decision["candidate_labor_details"][0]["production_eligible"] is False
    assert decision["evidence_boundary"] == "candidate_complex_route_only"


def test_evidence_ledger_records_call_recovery_cost_and_verification(tmp_path):
    from core.miner_pool.capability_routing import CapabilityEvidenceLedger

    ledger = CapabilityEvidenceLedger(str(tmp_path))
    evidence = ledger.record_call(
        task_type="reasoning",
        capability="general_reasoning",
        provider="shenwen",
        model="gpt-6-astra",
        success=True,
        latency_ms=120,
        usage={"prompt_tokens": 3, "completion_tokens": 2},
        cost={"total_usd": 0.01, "usage_source": "provider_response"},
        attempts=[
            {"model": "shenwen:gpt-6-astra", "success": False, "error": "timeout"},
            {"model": "shenwen:gpt-5.6-terra", "success": True},
        ],
        route_state="POC_COMPLEX_ESCALATION",
    )
    receipt = ledger.record_verification(
        capability="general_reasoning",
        provider_and_model="shenwen:gpt-6-astra",
        outcome="pass",
        verifier_id="isolated-test",
        evidence_hash="abc123",
        independent_group_id="group-a",
    )
    snapshot = ledger.snapshot()
    bucket = snapshot["capabilities"]["general_reasoning"]

    assert evidence["route_id"]
    assert receipt["receipt_id"]
    assert bucket["independent_call_evidence"][0]["usage_known"] is True
    assert bucket["failure_recovery_evidence"][0]["recovered"] is True
    assert bucket["cost_records"][0]["status"] == "known"
    assert bucket["capability_verification_receipts"][0]["outcome"] == "pass"
    assert (tmp_path / "capability_routing_evidence.json").is_file()
    json.loads((tmp_path / "capability_routing_evidence.json").read_text(encoding="utf-8"))


def test_evidence_readiness_keeps_promotion_fail_closed(tmp_path):
    from core.miner_pool.capability_routing import CapabilityEvidenceLedger

    ledger = CapabilityEvidenceLedger(str(tmp_path))
    ledger.ensure_capabilities(["deep_reasoning"])
    readiness = ledger.readiness_snapshot()

    assert readiness["system_status"] == "AUTONOMOUS_CAPABILITY_ROUTING_POC_READY"
    assert readiness["promotion_status"] == "PRODUCTION_MODEL_ROUTING_NOT_YET_PROMOTED"
    assert readiness["capabilities"]["deep_reasoning"]["state"] == "UNOBSERVED"
    assert "capability_verification_receipts" in readiness["capabilities"]["deep_reasoning"]["missing_evidence"]


def test_governed_promotion_requires_all_evidence_and_changes_only_receipt(tmp_path):
    from core.miner_pool.capability_routing import CapabilityEvidenceLedger
    from core.miner_pool.model_router import ModelRouter

    ledger = CapabilityEvidenceLedger(str(tmp_path))
    for _ in range(3):
        ledger.record_call(
            task_type="strategic",
            capability="deep_reasoning",
            provider="shenwen",
            model="gpt-6-astra",
            success=True,
            usage={"total_tokens": 4},
            cost={"total_usd": 0.01, "usage_source": "reconciled"},
        )
    # One actual recovered fallback is enough for the recovery gate; the
    # independent quality receipts remain a separate three-review requirement.
    ledger.record_call(
        task_type="strategic",
        capability="deep_reasoning",
        provider="shenwen",
        model="gpt-6-astra",
        success=True,
        attempts=[
            {"model": "shenwen:gpt-6-astra", "success": False, "error": "timeout"},
            {"model": "shenwen:gpt-5.6-terra", "success": True},
        ],
    )
    for index in range(3):
        ledger.record_verification(
            capability="deep_reasoning",
            provider_and_model="shenwen:gpt-6-astra",
            outcome="pass",
            verifier_id=f"verifier-{index}",
            evidence_hash=f"hash-{index}",
            independent_group_id=f"group-{index}",
        )
    ledger.record_fallback_test(
        capability="deep_reasoning",
        primary="shenwen:gpt-6-astra",
        fallback="shenwen:gpt-5.6-terra",
        compatible=True,
        evidence_hash="fallback-hash",
    )

    router = ModelRouter(available_providers=["shenwen"], evidence_ledger=ledger)
    decision = router.resolve_route(
        "strategic", task_context={"complexity": "complex"}
    )
    assert decision["selected_route_state"] == "PROMOTED_COMPLEX_ESCALATION"
    assert decision["evidence_boundary"] == "promoted_complex_route"
    assert decision["candidate_labor_details"][0]["production_eligible"] is True


def test_miner_pool_routes_complex_work_and_recovers_to_terra(tmp_path, monkeypatch):
    from core.miner_pool.miner_pool import MinerPool
    import core.miner_pool.miner_pool as miner_pool_module

    monkeypatch.setattr(miner_pool_module.time, "sleep", lambda _seconds: None)
    pool = MinerPool(state_dir=str(tmp_path), coze_assets_path="C:/nonexistent-assets")
    provider = _RoutingProvider(failures_before_success=2)
    pool._providers = {"shenwen": provider}
    pool._router.set_available_providers(["shenwen"])
    pool._initialized = True

    result = pool.chat(
        "reasoning",
        [{"role": "user", "content": "bounded complex task"}],
        max_retries=3,
        complexity="complex",
    )

    assert result["success"] is True
    assert [call["model"] for call in provider.calls] == [
        "gpt-6-astra",
        "gpt-6-astra",
        "gpt-5.6-terra",
    ]
    assert result["routing"]["selected_labor"] == "shenwen:gpt-5.6-terra"
    assert result["routing"]["fallback_chain"] == [
        "shenwen:gpt-6-astra",
        "shenwen:gpt-5.6-terra",
    ]
    evidence = pool.get_capability_routing_snapshot()["evidence"]
    bucket = evidence["capabilities"]["general_reasoning"]
    assert bucket["failure_recovery_evidence"]
    assert bucket["fallback_compatibility_tests"][-1]["compatible"] is True
