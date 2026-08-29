import json

from core.free_research_sandbox import FreeResearchSandbox
from core.sandbox_society import SandboxSociety


def test_society_distills_every_outcome_audits_and_exposes_post_execution_queues(tmp_path):
    root = tmp_path / "sandbox"
    sandbox = FreeResearchSandbox(root)
    sandbox.record_experiment(
        experiment_id="EXP-ONE", hypothesis="repeatable signal", method="isolated probe",
        outcome="PASS", evidence={"source": "evidence://one"},
    )
    sandbox.record_experiment(
        experiment_id="EXP-FAIL", hypothesis="broken signal", method="isolated probe",
        outcome="FAIL", evidence={"source": "evidence://counterexample"},
    )
    report = SandboxSociety(root).run_turn()
    assert report["roles"]["curator"]["new_proposal_ids"] == ["EXP-ONE"]
    assert report["roles"]["curator"]["new_distillations"] == [
        {"experiment_id": "EXP-FAIL", "status": "COUNTEREXAMPLE_ONLY"},
        {"experiment_id": "EXP-ONE", "status": "PROPOSAL_ONLY"},
    ]
    assert report["roles"]["court"]["status"] == "VALID"
    assert report["roles"]["teacher"]["may_approve"] is False
    assert report["roles"]["teacher"]["counterexample_queue"][0]["experiment_id"] == "EXP-FAIL"
    second = SandboxSociety(root).run_turn()
    assert second["roles"]["curator"]["action"] == "NO_NEW_SANDBOX_WORK"


def test_court_detects_record_tampering(tmp_path):
    root = tmp_path / "sandbox"
    sandbox = FreeResearchSandbox(root)
    sandbox.record_experiment(
        experiment_id="EXP-TAMPER", hypothesis="repeatable signal", method="isolated probe",
        outcome="PASS", evidence={"source": "evidence://one"},
    )
    path = root / "experiments" / "EXP-TAMPER.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["hypothesis"] = "tampered"
    path.write_text(json.dumps(value), encoding="utf-8")
    report = SandboxSociety(root).run_turn()
    assert report["roles"]["court"]["status"] == "INVALID"
    assert report["roles"]["court"]["invalid_record_ids"] == ["EXP-TAMPER"]


def test_court_detects_proposal_tampering(tmp_path):
    root = tmp_path / "sandbox"
    sandbox = FreeResearchSandbox(root)
    sandbox.record_experiment(
        experiment_id="EXP-PROPOSAL", hypothesis="repeatable signal", method="isolated probe",
        outcome="PASS", evidence={"source": "evidence://proposal"},
    )
    SandboxSociety(root).run_turn()
    path = root / "promotion_proposals" / "EXP-PROPOSAL.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["reason"] = "tampered"
    path.write_text(json.dumps(value), encoding="utf-8")
    report = SandboxSociety(root).run_turn()
    assert report["roles"]["court"]["status"] == "INVALID"
    assert report["roles"]["court"]["proposal_integrity_failures"] == ["EXP-PROPOSAL"]


def test_court_detects_distillation_tampering(tmp_path):
    root = tmp_path / "sandbox"
    sandbox = FreeResearchSandbox(root)
    sandbox.record_experiment(
        experiment_id="EXP-DISTILL", hypothesis="counterexample", method="isolated probe",
        outcome="FAIL", evidence={"source": "evidence://distill"},
    )
    SandboxSociety(root).run_turn()
    path = root / "distillations" / "EXP-DISTILL.json"
    value = json.loads(path.read_text(encoding="utf-8"))
    value["reason"] = "tampered"
    path.write_text(json.dumps(value), encoding="utf-8")
    report = SandboxSociety(root).run_turn()
    assert report["roles"]["court"]["status"] == "INVALID"
    assert report["roles"]["court"]["distillation_integrity_failures"] == ["EXP-DISTILL"]


def test_court_detects_factory_world_receipt_tampering(tmp_path):
    root = tmp_path / "sandbox"
    sandbox = FreeResearchSandbox(root)
    sandbox.record_experiment(
        experiment_id="EXP-FACTORY", hypothesis="fixture", method="isolated probe",
        outcome="PASS", evidence={"source": "evidence://factory"},
    )
    SandboxSociety(root).run_turn()
    worlds = root / "factories" / "worlds"
    worlds.mkdir(parents=True, exist_ok=True)
    (worlds / "WORLD-TAMPER.json").write_text(
        json.dumps({
            "world_id": "WORLD-TAMPER",
            "factory": "imitation",
            "world_hash": "not-a-valid-hash",
        }),
        encoding="utf-8",
    )

    report = SandboxSociety(root).run_turn()

    assert report["roles"]["court"]["status"] == "INVALID"
    assert report["roles"]["court"]["factory_integrity_failures"] == [
        "worlds:WORLD-TAMPER"
    ]


def test_design_seed_is_reported_without_claiming_production_consumption(tmp_path):
    root = tmp_path / "sandbox"
    constitution = root / "constitution"
    constitution.mkdir(parents=True)
    (constitution / "R1_ECOLOGY_CONSTITUTION_v1.json").write_text(
        json.dumps({
            "contract_version": "seed.v1",
            "route": ["observe", "question", "review"],
            "invariants": [{"id": "ECO-01"}],
            "reinstantiation_mapping": {"R1_freezone": "sandbox"},
        }),
        encoding="utf-8",
    )
    report = SandboxSociety(root).run_turn()
    assert report["design_seed"]["status"] == "DESIGN_SEED_OBSERVED"
    assert report["design_seed"]["route"] == ["observe", "question", "review"]
    assert report["design_seed"]["consumption_mode"] == "sandbox_report_only"
    assert report["production_integration"] is False
