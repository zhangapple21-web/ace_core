import json

from core.counterexample_executor import StructuralCounterexampleExecutor
from core.free_research_sandbox import FreeResearchSandbox
from core.lazy_cat_audit import LazyCatAudit


def _challenge(root):
    sandbox = FreeResearchSandbox(root)
    sandbox.record_experiment(
        experiment_id="EXP-SOURCE",
        hypothesis="source hypothesis",
        method="bounded local probe",
        outcome="PASS",
        evidence={"source": "evidence://source"},
        metadata={"production_integration": False},
    )
    sandbox.distill("EXP-SOURCE")
    audit = LazyCatAudit(root)
    report = audit.audit_all(
        records=[json.loads((root / "experiments" / "EXP-SOURCE.json").read_text(encoding="utf-8"))],
        distillations=[json.loads((root / "distillations" / "EXP-SOURCE.json").read_text(encoding="utf-8"))],
    )
    assert report["new_challenge_ids"] == ["CHALLENGE-EXP-SOURCE"]
    return json.loads((root / "lazy_cat" / "challenges" / "CHALLENGE-EXP-SOURCE.json").read_text(encoding="utf-8"))


def test_structural_counterexample_executor_resolves_named_dimensions_without_claiming_truth(tmp_path):
    root = tmp_path / "sandbox"
    challenge = _challenge(root)
    result = StructuralCounterexampleExecutor(root).execute(
        challenge=challenge,
        factory_worlds=[{"world_id": "WORLD-COUNTER", "stance": "COUNTEREXAMPLE_SEARCH", "execution_state": "BLUEPRINT_ONLY"}],
    )

    assert result["outcome"] == "PASS"
    assert result["evidence"]["scope"] == "STRUCTURAL_COUNTEREXAMPLE_ONLY"
    assert result["evidence"]["claim_truth_assessed"] is False
    assert result["evidence"]["market_or_production_assessed"] is False
    witness = result["evidence"]["counterexample_witness"]
    assert witness["contract_version"] == "ace.counterexample_witness.v1"
    assert witness["outcome"] == "NOT_FALSIFIED_WITHIN_SCOPE"
    assert witness["production_integration"] is False


def test_structural_counterexample_executor_preserves_a_tampered_source_as_failure(tmp_path):
    root = tmp_path / "sandbox"
    challenge = _challenge(root)
    source_path = root / "experiments" / "EXP-SOURCE.json"
    source = json.loads(source_path.read_text(encoding="utf-8"))
    source["hypothesis"] = "tampered"
    source_path.write_text(json.dumps(source), encoding="utf-8")

    result = StructuralCounterexampleExecutor(root).execute(
        challenge=challenge,
        factory_worlds=[{"world_id": "WORLD-COUNTER", "stance": "COUNTEREXAMPLE_SEARCH", "execution_state": "BLUEPRINT_ONLY"}],
    )
    assert result["outcome"] == "FAIL"
    assert result["evidence"]["source_record_hash_valid"] is False
