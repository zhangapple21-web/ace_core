import json

from core.free_research_sandbox import FreeResearchSandbox


def test_clean_passing_experiment_distills_to_proposal_only(tmp_path):
    sandbox = FreeResearchSandbox(tmp_path / "sandbox")
    source = sandbox.record_experiment(
        experiment_id="EXP-001", hypothesis="a bounded source check can be repeated",
        method="run isolated probes", outcome="PASS", evidence={"probe": "evidence://isolated/1"},
    )
    proposal = sandbox.distill("EXP-001")
    assert source["production_integration"] is False
    assert proposal["status"] == "PROPOSAL_ONLY"
    assert proposal["distillation"]["executable"] is False
    assert "automatic_delivery" in proposal["prohibited_actions"]
    distillation = json.loads((tmp_path / "sandbox" / "distillations" / "EXP-001.json").read_text(encoding="utf-8"))
    assert distillation["status"] == "PROPOSAL_ONLY"
    assert (tmp_path / "sandbox" / "promotion_proposals" / "EXP-001.json").exists()


def test_polluted_experiment_is_quarantined_but_still_distilled_as_isolated_material(tmp_path):
    sandbox = FreeResearchSandbox(tmp_path / "sandbox")
    sandbox.record_experiment(
        experiment_id="EXP-002", hypothesis="untrusted narrative", method="free writing",
        outcome="PASS", evidence={"claim": "unverified"}, metadata={"untrusted_source": True},
    )
    distillation = sandbox.distill("EXP-002")
    assert distillation["status"] == "QUARANTINED"
    assert distillation["reason"] == "pollution_requires_isolation"
    assert (tmp_path / "sandbox" / "quarantine" / "EXP-002.json").exists()
    assert (tmp_path / "sandbox" / "distillations" / "EXP-002.json").exists()
    assert not (tmp_path / "sandbox" / "promotion_proposals" / "EXP-002.json").exists()


def test_failed_experiment_becomes_a_counterexample_not_a_rejection(tmp_path):
    sandbox = FreeResearchSandbox(tmp_path / "sandbox")
    sandbox.record_experiment(
        experiment_id="EXP-FAIL", hypothesis="the probe should hold", method="run local probe",
        outcome="FAIL", evidence={"observed": "counterexample"},
    )
    distillation = sandbox.distill("EXP-FAIL")
    assert distillation["status"] == "COUNTEREXAMPLE_ONLY"
    assert distillation["outcome"] == "FAIL"
    assert distillation["production_integration"] is False


def test_experiment_records_are_append_only(tmp_path):
    sandbox = FreeResearchSandbox(tmp_path / "sandbox")
    sandbox.record_experiment(
        experiment_id="EXP-IMMUTABLE", hypothesis="first", method="first", outcome="PASS", evidence={"x": 1},
    )
    try:
        sandbox.record_experiment(
            experiment_id="EXP-IMMUTABLE", hypothesis="second", method="second", outcome="FAIL", evidence={"x": 2},
        )
    except ValueError as error:
        assert "append-only" in str(error)
    else:
        raise AssertionError("a second record must not overwrite the first")


def test_manifest_has_no_production_integration(tmp_path):
    sandbox = FreeResearchSandbox(tmp_path / "sandbox")
    manifest = sandbox.initialize()
    value = json.loads(manifest.read_text(encoding="utf-8"))
    assert value["mode"] == "FREE_RESEARCH_ONLY"
    assert value["production_integration"] is False
    assert value["automatic_promotion"] is False
