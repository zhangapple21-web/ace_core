import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ops.model_routing_evaluation import evaluate_routing_readiness


def _write_task(
    root,
    task_id,
    model,
    *,
    case_id=None,
    verified=None,
    cost=0.0,
    evidence_hash="evidence-a",
    input_hash="input-a",
    harness_version="routing-shadow/v1",
    role="researcher",
    reconciled_bill=False,
):
    path = root / "task_pool" / "archived" / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    trace = {
        "task_type": "strategic",
        "provider": "shenwen",
        "selected_model": model,
        "role": role,
        "api_called": True,
        "api_result": "success",
        "latency_ms": 100,
        "cost": {"total_usd": cost},
    }
    if case_id:
        trace["eval_case_id"] = case_id
        trace.update({
            "evaluation_harness_id": "isolated-shadow-run-a",
            "evaluation_contract_sha256": "contract-a",
            "evidence_or_context_hash": evidence_hash,
            "evidence_cutoff_at": "2026-08-27T00:00:00+00:00",
            "input_sha256": input_hash,
            "harness_version": harness_version,
            "case_manifest_sha256": "manifest-a",
            "provider_and_model": f"shenwen:{model}",
            "api_result_and_retry_count": {"api_result": "success", "retry_count": 0},
            "verification_independent_group_id": "independent-review-a",
            "verifier_id": "verifier-a",
            "verification_input_sha256": "verification-input-a",
        })
    if verified is not None:
        trace["verification_outcome"] = verified
    if reconciled_bill:
        trace["actual_provider_bill_cost"] = {
            "amount_usd": cost,
            "reconciliation_status": "reconciled",
            "bill_record_hash": f"bill-{task_id}",
        }
    task = {
        "task_id": task_id,
        "outputs": {
            "model_task_admission": {"eligible": True, "classification": "strategic"},
            "model_execution": [trace],
        },
    }
    path.write_text(json.dumps(task), encoding="utf-8")


def test_readiness_blocks_upgrade_when_traces_are_not_paired(tmp_path):
    _write_task(tmp_path, "RQ-1", "gpt-5.6-terra", verified="pass", cost=0.02)
    _write_task(tmp_path, "RQ-2", "candidate-model", verified="pass", cost=0.01)

    report = evaluate_routing_readiness(
        tmp_path, baseline_model="gpt-5.6-terra", candidate_model="candidate-model"
    )

    assert report["decision"] == "UPGRADE_BLOCKED"
    assert report["reason_codes"] == ["NO_MATCHED_EVALUATION_CASES"]
    assert report["coverage"]["admitted_trace_count"] == 2
    assert report["coverage"]["paired_case_count"] == 0


def test_readiness_requires_verification_for_a_matched_case(tmp_path):
    _write_task(tmp_path, "RQ-1", "gpt-5.6-terra", case_id="case-a", verified="pass")
    _write_task(tmp_path, "RQ-2", "candidate-model", case_id="case-a", verified=None)

    report = evaluate_routing_readiness(
        tmp_path, baseline_model="gpt-5.6-terra", candidate_model="candidate-model"
    )

    assert report["decision"] == "UPGRADE_BLOCKED"
    assert report["reason_codes"] == ["INCOMPLETE_EVALUATION_CONTRACT"]
    assert report["coverage"]["paired_case_count"] == 0
    assert report["coverage"]["verified_paired_case_count"] == 0


def test_readiness_marks_a_small_verified_pair_shadow_only(tmp_path):
    _write_task(tmp_path, "RQ-1", "gpt-5.6-terra", case_id="case-a", verified="pass", cost=0.02)
    _write_task(tmp_path, "RQ-2", "candidate-model", case_id="case-a", verified="pass", cost=0.01)

    report = evaluate_routing_readiness(
        tmp_path, baseline_model="gpt-5.6-terra", candidate_model="candidate-model"
    )

    assert report["decision"] == "SHADOW_ONLY"
    assert report["reason_codes"] == ["INSUFFICIENT_VERIFIED_PAIRED_CASES"]
    assert report["comparisons"][0]["candidate_success_rate"] == 1.0


def test_readiness_blocks_matching_case_when_frozen_input_differs(tmp_path):
    _write_task(tmp_path, "RQ-1", "gpt-5.6-terra", case_id="case-a", verified="pass")
    _write_task(
        tmp_path,
        "RQ-2",
        "candidate-model",
        case_id="case-a",
        verified="pass",
        input_hash="input-after-new-evidence",
    )

    report = evaluate_routing_readiness(
        tmp_path, baseline_model="gpt-5.6-terra", candidate_model="candidate-model"
    )

    assert report["decision"] == "UPGRADE_BLOCKED"
    assert report["reason_codes"] == ["NO_MATCHED_EVALUATION_CASES"]
    assert report["coverage"]["paired_case_count"] == 0


def test_readiness_blocks_incomplete_explicit_evaluation_contract(tmp_path):
    _write_task(tmp_path, "RQ-1", "gpt-5.6-terra", case_id="case-a", verified="pass")
    _write_task(tmp_path, "RQ-2", "candidate-model", case_id="case-a", verified="pass")
    path = tmp_path / "task_pool" / "archived" / "RQ-2.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["outputs"]["model_execution"][0]["harness_version"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    report = evaluate_routing_readiness(
        tmp_path, baseline_model="gpt-5.6-terra", candidate_model="candidate-model"
    )

    assert report["decision"] == "UPGRADE_BLOCKED"
    assert report["reason_codes"] == ["INCOMPLETE_EVALUATION_CONTRACT"]
    assert report["coverage"]["selected_trace_incomplete_evaluation_contract"] == 1


def test_readiness_blocks_ambiguous_duplicate_trace_for_same_frozen_case(tmp_path):
    _write_task(tmp_path, "RQ-1", "gpt-5.6-terra", case_id="case-a", verified="pass")
    _write_task(tmp_path, "RQ-1-repeat", "gpt-5.6-terra", case_id="case-a", verified="pass")
    _write_task(tmp_path, "RQ-2", "candidate-model", case_id="case-a", verified="pass")

    report = evaluate_routing_readiness(
        tmp_path, baseline_model="gpt-5.6-terra", candidate_model="candidate-model"
    )

    assert report["decision"] == "UPGRADE_BLOCKED"
    assert report["reason_codes"] == ["AMBIGUOUS_CASE_CARDINALITY"]
    assert report["coverage"]["ambiguous_case_count"] == 1


def test_readiness_requires_reconciled_bill_cost_before_evaluation_ready(tmp_path):
    for index in range(2):
        _write_task(
            tmp_path, f"RQ-b-{index}", "gpt-5.6-terra", case_id=f"case-{index}", verified="pass"
        )
        _write_task(
            tmp_path, f"RQ-c-{index}", "candidate-model", case_id=f"case-{index}", verified="pass"
        )

    report = evaluate_routing_readiness(
        tmp_path,
        baseline_model="gpt-5.6-terra",
        candidate_model="candidate-model",
        minimum_verified_pairs=2,
    )

    assert report["decision"] == "UPGRADE_BLOCKED"
    assert report["reason_codes"] == ["MATCHED_CASES_MISSING_RECONCILED_BILL_COST"]


def test_complete_isolated_pairs_are_evaluation_ready_but_do_not_change_route(tmp_path):
    for index in range(2):
        _write_task(
            tmp_path,
            f"RQ-b-{index}",
            "gpt-5.6-terra",
            case_id=f"case-{index}",
            verified="pass",
            cost=0.02,
            reconciled_bill=True,
        )
        _write_task(
            tmp_path,
            f"RQ-c-{index}",
            "candidate-model",
            case_id=f"case-{index}",
            verified="pass",
            cost=0.01,
            reconciled_bill=True,
        )

    report = evaluate_routing_readiness(
        tmp_path,
        baseline_model="gpt-5.6-terra",
        candidate_model="candidate-model",
        minimum_verified_pairs=2,
    )

    assert report["decision"] == "EVALUATION_READY"
    assert report["routing_effect"] is False
    assert report["comparisons"][0]["reconciled_bill_cost"] is True
