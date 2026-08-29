import hashlib
import json
from pathlib import Path

import pytest

from core.free_zone_reality_bridge import FreeZoneRealityBridge


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value):
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _source_fixture(root: Path, *, status="PROPOSAL_ONLY", outcome="PASS", polluted=False):
    sandbox = root / "07_SANDBOX" / "free_research"
    experiment_id = "EXP-BRIDGE-ONE"
    experiment = {
        "contract_version": "ace.free_research_sandbox.v1",
        "experiment_id": experiment_id,
        "mode": "FREE_RESEARCH_ONLY",
        "hypothesis": "A free-zone learning may be mapped without mutating either realm.",
        "method": "Retain the source and create a separate hash-bound mapping.",
        "outcome": outcome,
        "evidence": {"observed": True},
        "metadata": {"free_zone_only": True},
        "pollution_flags": ["untrusted_source"] if polluted else [],
        "production_integration": False,
    }
    experiment["record_hash"] = _digest(experiment)
    experiment_path = sandbox / ("quarantine" if polluted else "experiments") / f"{experiment_id}.json"
    _write_json(experiment_path, experiment)

    distillation = {
        "automatic_delivery": False,
        "automatic_promotion": False,
        "automatic_task_creation": False,
        "contract_version": "ace.free_research_sandbox.v1",
        "experiment_id": experiment_id,
        "mode": "DISTILLATION_ONLY",
        "outcome": outcome,
        "pattern": "Preserve the original artifact and map only an explicitly named learning.",
        "production_integration": False,
        "reason": "retained_learning",
        "source_record_hash": experiment["record_hash"],
        "status": status,
    }
    distillation["distillation_hash"] = _digest(distillation)
    distillation_path = sandbox / "distillations" / f"{experiment_id}.json"
    _write_json(distillation_path, distillation)
    return sandbox, distillation_path


def _mapping(root: Path, *, decision="ACCEPT_FOR_RESEARCH", same_group=False):
    first = root / "evidence" / "independent_audit.md"
    second = root / "evidence" / "runtime_snapshot.json"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("independent boundary audit\n", encoding="utf-8")
    second.write_text('{"cycle_status":"completed"}\n', encoding="utf-8")
    return {
        "mapping_id": "ECO-02-EXPLICIT-REALM-BRIDGE",
        "epistemic_status": "INFERENCE",
        "observation": "A named Free Zone learning and independent ACE evidence agree on a realm boundary.",
        "learning": "Copy by reference and hash; never let a Free Zone outcome mutate ACE automatically.",
        "reality_scope": "ACE realm boundary",
        "research_question": "Can the learning survive translation without becoming a production claim?",
        "expected_result": "One immutable ACE-side research receipt exists and both realms remain unchanged.",
        "verification_method": "Verify source hashes, evidence groups, receipt hash, and zero TaskPool or daemon calls.",
        "constraints": [
            "no automatic task creation",
            "no model call",
            "no production runtime mutation",
            "existing ACE Admission remains authoritative",
        ],
        "evidence_refs": [
            {
                "ref": str(first.relative_to(root)).replace("\\", "/"),
                "independence_group": "audit",
                "kind": "independent_audit",
            },
            {
                "ref": str(second.relative_to(root)).replace("\\", "/"),
                "independence_group": "audit" if same_group else "runtime",
                "kind": "runtime_observation",
            },
        ],
        "ace_review": {
            "decision": decision,
            "reviewer": "main_steward",
            "review_basis": ["source integrity", "independent reality evidence", "preserved gates"],
        },
    }


def test_explicit_bridge_is_hash_bound_idempotent_and_has_no_automatic_authority(tmp_path):
    sandbox, source = _source_fixture(tmp_path)
    receipt_dir = tmp_path / "08_GOVERNANCE" / "free_zone_bridge" / "receipts"
    task_pool = tmp_path / "task_pool"
    task_pool.mkdir()
    source_before = source.read_bytes()
    task_pool_before = list(task_pool.rglob("*"))

    bridge = FreeZoneRealityBridge(tmp_path, sandbox_root=sandbox, receipt_dir=receipt_dir)
    first = bridge.build(source, _mapping(tmp_path))
    second = bridge.build(source, _mapping(tmp_path))

    assert first == second
    assert first["disposition"]["status"] == "ACCEPTED_REALITY_RESEARCH"
    assert first["source"]["learning_status"] == "PROPOSAL_ONLY"
    assert first["source"]["source_outcome"] == "PASS"
    assert first["evidence"]["independent_count"] == 2
    assert first["disposition"] == {
        "status": "ACCEPTED_REALITY_RESEARCH",
        "task_created": False,
        "model_call": False,
        "production_runtime_mutation": False,
        "admission_bypassed": False,
        "recommendation_authority": False,
        "next_gate": "EXISTING_ACE_ADMISSION_OR_EXPERIENCE_REVIEW",
    }
    assert source.read_bytes() == source_before
    assert list(task_pool.rglob("*")) == task_pool_before
    assert len(list(receipt_dir.glob("BRIDGE-*.json"))) == 1


def test_bridge_requires_one_explicit_named_distillation_inside_the_free_zone(tmp_path):
    sandbox, source = _source_fixture(tmp_path)
    bridge = FreeZoneRealityBridge(tmp_path, sandbox_root=sandbox)
    mapping = _mapping(tmp_path)

    with pytest.raises(ValueError, match="named distillation file required"):
        bridge.build(source.parent, mapping)

    outside = tmp_path / "outside.json"
    outside.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ValueError, match="source must be inside the Free Zone distillations directory"):
        bridge.build(outside, mapping)


def test_bridge_rejects_tampering_and_polluted_acceptance(tmp_path):
    sandbox, source = _source_fixture(tmp_path)
    value = json.loads(source.read_text(encoding="utf-8"))
    value["pattern"] = "tampered"
    _write_json(source, value)
    bridge = FreeZoneRealityBridge(tmp_path, sandbox_root=sandbox)

    with pytest.raises(ValueError, match="source distillation hash mismatch"):
        bridge.build(source, _mapping(tmp_path))

    sandbox, polluted_source = _source_fixture(
        tmp_path / "polluted", status="QUARANTINED", outcome="FAIL", polluted=True
    )
    polluted_bridge = FreeZoneRealityBridge(tmp_path / "polluted", sandbox_root=sandbox)
    with pytest.raises(ValueError, match="polluted source cannot be accepted into ACE research"):
        polluted_bridge.build(polluted_source, _mapping(tmp_path / "polluted"))


def test_acceptance_requires_fresh_review_and_two_independent_reality_groups(tmp_path):
    sandbox, source = _source_fixture(tmp_path)
    bridge = FreeZoneRealityBridge(tmp_path, sandbox_root=sandbox)

    with pytest.raises(ValueError, match="independent evidence groups required"):
        bridge.build(source, _mapping(tmp_path, same_group=True))

    mapping = _mapping(tmp_path)
    del mapping["ace_review"]
    with pytest.raises(ValueError, match="mapping has missing or unknown fields"):
        bridge.build(source, mapping)

    mapping = _mapping(tmp_path)
    mapping["ace_review"]["reviewer"] = "delegated_worker"
    with pytest.raises(ValueError, match="fresh main-steward review required"):
        bridge.build(source, mapping)


def test_hold_mapping_and_counterexample_keep_their_epistemic_status(tmp_path):
    sandbox, source = _source_fixture(tmp_path, status="COUNTEREXAMPLE_ONLY", outcome="FAIL")
    bridge = FreeZoneRealityBridge(tmp_path, sandbox_root=sandbox)
    mapping = _mapping(tmp_path, decision="HOLD_FOR_EVIDENCE", same_group=True)

    receipt = bridge.build(source, mapping)

    assert receipt["disposition"]["status"] == "MAPPED_SHADOW"
    assert receipt["source"]["learning_status"] == "COUNTEREXAMPLE_ONLY"
    assert receipt["source"]["source_outcome"] == "FAIL"
    assert "value_score" not in receipt
    assert receipt["ace_review"]["decision"] == "HOLD_FOR_EVIDENCE"
