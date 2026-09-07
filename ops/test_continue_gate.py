from core.continue_gate import CLOSE_AND_HANDOFF, CONTINUE, evaluate_continue_gate


def _good():
    return (
        {
            "fresh": True,
            "context_id": "ctx-1",
            "estimated_tokens": 10,
            "context_limit": 100,
            "same_failure_count": 0,
            "prior_attempt_without_receipt": False,
        },
        {
            "available": True,
            "provider": "local",
            "interface": "chat_completions",
            "continuation_supported": True,
            "provider_degraded": False,
            "fallbacks_configured": True,
        },
        {"required_receipts": [], "receipts": []},
    )


def test_continue_requires_all_three_proof_classes():
    assert evaluate_continue_gate(*_good())["status"] == CONTINUE


def test_near_context_limit_closes_before_more_work():
    context, protocol, evidence = _good()
    context["estimated_tokens"] = 80
    result = evaluate_continue_gate(context, protocol, evidence)
    assert result["status"] == CLOSE_AND_HANDOFF
    assert "CONTEXT_BUDGET_NEAR_LIMIT" in result["reason_codes"]


def test_repeated_degraded_failure_without_fallback_closes():
    context, protocol, evidence = _good()
    context["same_failure_count"] = 2
    protocol.update({"provider_degraded": True, "fallbacks_configured": False})
    result = evaluate_continue_gate(context, protocol, evidence)
    assert result["status"] == CLOSE_AND_HANDOFF
    assert "REPEATED_FAILURE_LIMIT" in result["reason_codes"]
    assert "NO_FALLBACK_ON_DEGRADED_PROVIDER" in result["reason_codes"]


def test_missing_receipt_closes_and_new_experiment_can_be_explicitly_empty():
    context, protocol, evidence = _good()
    evidence["required_receipts"] = ["attempt-1"]
    assert evaluate_continue_gate(context, protocol, evidence)["status"] == CLOSE_AND_HANDOFF
    evidence["allow_empty_for_new_experiment"] = True
    assert evaluate_continue_gate(context, protocol, evidence)["status"] == CONTINUE


