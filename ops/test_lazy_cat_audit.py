import json

from core.free_research_sandbox import FreeResearchSandbox
from core.free_zone_autonomy import FreeZoneAutonomy
from core.lazy_cat_audit import LazyCatAudit
from core.sandbox_society import SandboxSociety


def test_lazy_cat_returns_incomplete_old_proposal_as_a_post_execution_challenge(tmp_path):
    root = tmp_path / "sandbox"
    sandbox = FreeResearchSandbox(root)
    sandbox.record_experiment(
        experiment_id="EXP-OLD",
        hypothesis="old shape",
        method="isolated probe",
        outcome="PASS",
        evidence={"source": "evidence://old"},
    )

    report = SandboxSociety(root).run_turn()
    lazy = report["roles"]["lazy_cat"]
    assert lazy["return_to_free_zone_count"] == 1
    assert lazy["new_challenge_ids"] == ["CHALLENGE-EXP-OLD"]
    assert report["roles"]["teacher"]["review_queue"] == []
    assert report["roles"]["teacher"]["lazy_cat_queue"][0]["experiment_id"] == "EXP-OLD"
    assert report["roles"]["lazy_cat"]["may_block_free_zone"] is False


def test_lazy_cat_challenge_executes_a_structural_counterexample_without_an_entry_gate(tmp_path):
    root = tmp_path / "sandbox"
    sandbox = FreeResearchSandbox(root)
    sandbox.record_experiment(
        experiment_id="EXP-OLD",
        hypothesis="old shape",
        method="isolated probe",
        outcome="PASS",
        evidence={"source": "evidence://old"},
    )
    SandboxSociety(root).run_turn()

    report = FreeZoneAutonomy(
        root,
        git_observer=lambda: {"status": "NO_SAFE_GIT_FOOD"},
    ).run_turn()
    assert report["claim"]["source_kind"] == "lazy_cat_challenge"
    assert report["execution"]["outcome"] == "PASS"
    record = (root / "experiments" / f"{report['execution']['experiment_id']}.json").read_text(encoding="utf-8")
    assert "STRUCTURAL_COUNTEREXAMPLE_ONLY" in record
    process = json.loads(
        (root / "factories" / "processing" / f"{report['execution']['experiment_id']}.json").read_text(encoding="utf-8")
    )
    assert process["selected_stance"] == "COUNTEREXAMPLE_SEARCH"
    assert process["world_id"] not in process["unexecuted_rival_world_ids"]
    probe = next((root / "lazy_cat" / "challenge_probes").glob("*.json"))
    probe_data = json.loads(probe.read_text(encoding="utf-8"))
    assert probe_data["state"] == "PROBE_COMPLETED_WITHIN_SCOPE"
    assert LazyCatAudit(root).pending_challenges() == []
    society = SandboxSociety(root).run_turn()
    assert society["roles"]["lazy_cat"]["pending_challenge_count"] == 0
    verdict = next(
        item
        for item in (root / "lazy_cat" / "verdicts").glob("*.json")
        if json.loads(item.read_text(encoding="utf-8")).get("experiment_id") == report["execution"]["experiment_id"]
    )
    assert json.loads(verdict.read_text(encoding="utf-8"))["checks"]["counterexample_witness"] is True
    assert society["production_integration"] is False
    assert report["judgment"]["quality_decision_performed"] is False
    assert report["production_integration"] is False


def test_factory_backed_experiment_is_fit_for_teacher_review_but_never_auto_approved(tmp_path):
    root = tmp_path / "sandbox"
    constitution = root / "constitution"
    constitution.mkdir(parents=True)
    (constitution / "R1_ECOLOGY_CONSTITUTION_v1.json").write_text(
        json.dumps({"invariants": [{"id": "ECO-01", "rule": "boundary persists"}]}),
        encoding="utf-8",
    )
    report = FreeZoneAutonomy(
        root,
        git_observer=lambda: {"status": "NO_SAFE_GIT_FOOD"},
    ).run_turn()
    society = SandboxSociety(root).run_turn()

    assert society["roles"]["lazy_cat"]["fit_for_teacher_review_count"] == 1
    assert society["roles"]["teacher"]["review_queue"][0]["experiment_id"] == report["execution"]["experiment_id"]
    assert society["roles"]["teacher"]["may_approve"] is False
    assert society["production_integration"] is False
