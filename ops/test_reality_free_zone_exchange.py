import hashlib
import json
from pathlib import Path

import pytest

from core.reality_free_zone_exchange import RealityFreeZoneExchange
from core.free_zone_reality_bridge import FreeZoneRealityBridge


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _write(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gap(root: Path, *, same_group=False):
    first = root / "evidence" / "runtime.json"
    second = root / "evidence" / "audit.md"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text('{"state":"degraded"}\n', encoding="utf-8")
    second.write_text("independent boundary audit\n", encoding="utf-8")
    return {
        "gap_id": "ACE-GAP-REALITY-LOOP-ONE",
        "epistemic_status": "FACT",
        "observation": "A runtime-reported gap has no current ACE-side minimal repair candidate.",
        "reality_scope": "ACE runtime continuity",
        "research_question": "Which bounded counterexample or design probe can falsify the assumed repair path?",
        "expected_result": "A Free Zone experiment records a result without changing ACE production state.",
        "verification_method": "Recheck evidence hashes, the inbound receipt, and zero TaskPool/runtime mutations.",
        "constraints": [
            "no TaskPool creation",
            "no model call",
            "no production mutation",
            "existing ACE gates remain authoritative",
        ],
        "evidence_refs": [
            {"ref": "evidence/runtime.json", "independence_group": "runtime", "kind": "runtime_snapshot"},
            {"ref": "evidence/audit.md", "independence_group": "runtime" if same_group else "audit", "kind": "audit"},
        ],
        "ace_review": {
            "decision": "RELEASE_TO_FREE_ZONE",
            "reviewer": "main_steward",
            "review_basis": ["real gap", "bounded research question", "preserved boundaries"],
        },
    }


def test_reality_gap_is_idempotently_released_as_free_zone_food_without_taskpool_authority(tmp_path):
    exchange = RealityFreeZoneExchange(tmp_path)
    task_pool = tmp_path / "task_pool"
    task_pool.mkdir()
    before = list(task_pool.rglob("*"))

    first = exchange.release(_gap(tmp_path))
    second = exchange.release(_gap(tmp_path))

    assert first == second
    assert first["disposition"]["status"] == "RELEASED_TO_FREE_ZONE"
    assert first["disposition"]["task_created"] is False
    assert first["disposition"]["production_runtime_mutation"] is False
    assert first["evidence"]["independent_count"] == 2
    assert list(task_pool.rglob("*")) == before

    inbox = tmp_path / "07_SANDBOX" / "free_research" / "inbox" / f"{first['exchange_id']}.json"
    food = json.loads(inbox.read_text(encoding="utf-8"))
    assert food["food_kind"] == "ace_reality_gap"
    assert food["origin"]["exchange_id"] == first["exchange_id"]
    assert food["production_integration"] is False


def test_reality_gap_requires_main_steward_and_independent_evidence(tmp_path):
    exchange = RealityFreeZoneExchange(tmp_path)
    with pytest.raises(ValueError, match="independent evidence groups required"):
        exchange.release(_gap(tmp_path, same_group=True))

    gap = _gap(tmp_path)
    gap["ace_review"]["reviewer"] = "worker"
    with pytest.raises(ValueError, match="authorized ACE Reality review required"):
        exchange.release(gap)


def test_free_zone_experiment_carries_origin_for_later_reflection(tmp_path):
    from core.free_research_sandbox import FreeResearchSandbox

    sandbox = FreeResearchSandbox(tmp_path / "07_SANDBOX" / "free_research")
    record = sandbox.record_experiment(
        experiment_id="EXP-REFLECTION-ONE",
        hypothesis="A linked experiment retains the ACE-origin receipt.",
        method="Preserve origin identity in the experiment and distillation.",
        outcome="PASS",
        evidence={"observed": True},
        metadata={
            "source_kind": "ace_reality_gap",
            "ace_reality_gap_origin": {"exchange_id": "EXCHANGE-ABC", "receipt_sha256": "abc"},
        },
    )
    sandbox.distill(record["experiment_id"])
    distillation = json.loads((sandbox.distillations / "EXP-REFLECTION-ONE.json").read_text(encoding="utf-8"))
    assert distillation["origin"]["exchange_id"] == "EXCHANGE-ABC"


def test_outbound_bridge_verifies_and_preserves_a_real_reality_gap_origin(tmp_path):
    receipt = RealityFreeZoneExchange(tmp_path).release(_gap(tmp_path))
    sandbox = tmp_path / "07_SANDBOX" / "free_research"
    experiment_id = "EXP-REFLECTION-BRIDGE"
    experiment = {
        "contract_version": "ace.free_research_sandbox.v1",
        "experiment_id": experiment_id,
        "mode": "FREE_RESEARCH_ONLY",
        "hypothesis": "The reflected result remains linked to ACE's actual gap.",
        "method": "Verify the inbound receipt before a separate outbound review.",
        "outcome": "PASS",
        "evidence": {"observed": True},
        "metadata": {"free_zone_only": True},
        "pollution_flags": [],
        "production_integration": False,
    }
    experiment["record_hash"] = _digest(experiment)
    _write(sandbox / "experiments" / f"{experiment_id}.json", experiment)
    distillation = {
        "automatic_delivery": False,
        "automatic_promotion": False,
        "automatic_task_creation": False,
        "contract_version": "ace.free_research_sandbox.v1",
        "experiment_id": experiment_id,
        "mode": "DISTILLATION_ONLY",
        "outcome": "PASS",
        "pattern": "Retain the linked gap identity during a separate ACE review.",
        "production_integration": False,
        "reason": "retained_learning",
        "source_record_hash": experiment["record_hash"],
        "status": "PROPOSAL_ONLY",
        "origin": {"exchange_id": receipt["exchange_id"], "receipt_sha256": receipt["receipt_hash"]},
    }
    distillation["distillation_hash"] = _digest(distillation)
    source = sandbox / "distillations" / f"{experiment_id}.json"
    _write(source, distillation)

    bridge = FreeZoneRealityBridge(tmp_path, sandbox_root=sandbox)
    reflected = bridge.build(source, _bridge_mapping(tmp_path))
    assert reflected["source"]["origin_reality_gap"]["exchange_id"] == receipt["exchange_id"]
    assert reflected["disposition"]["status"] == "ACCEPTED_REALITY_RESEARCH"


def _bridge_mapping(root: Path):
    first = root / "evidence" / "bridge-a.md"
    second = root / "evidence" / "bridge-b.md"
    first.write_text("a\n", encoding="utf-8")
    second.write_text("b\n", encoding="utf-8")
    return {
        "mapping_id": "REFLECT-ONE",
        "epistemic_status": "INFERENCE",
        "observation": "A linked Free Zone result is ready for ACE-side research review.",
        "learning": "Preserve the reality-gap lineage before evaluating the result.",
        "reality_scope": "ACE runtime continuity",
        "research_question": "Does the reflection preserve the original ACE gap?",
        "expected_result": "A research receipt records both directions without production mutation.",
        "verification_method": "Check receipt hashes and zero authority changes.",
        "constraints": ["no task creation", "no production mutation"],
        "evidence_refs": [
            {"ref": "evidence/bridge-a.md", "independence_group": "a", "kind": "audit"},
            {"ref": "evidence/bridge-b.md", "independence_group": "b", "kind": "runtime"},
        ],
        "ace_review": {"decision": "ACCEPT_FOR_RESEARCH", "reviewer": "main_steward", "review_basis": ["lineage", "evidence"]},
    }


