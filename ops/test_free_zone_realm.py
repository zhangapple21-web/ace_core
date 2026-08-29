import json

import pytest

from core.free_research_sandbox import FreeResearchSandbox
from core.free_zone_autonomy import FreeZoneAutonomy
from core.free_zone_realm import state_for
from core.sandbox_society import SandboxSociety


def _git_food():
    return {
        "status": "OBSERVED",
        "repository": "C:/local/repository",
        "head": "abc123",
        "safe_paths": ["core/example.py"],
        "safe_path_count": 1,
        "redacted_path_count": 0,
        "paths_sha256": "digest",
        "fingerprint": "realm-test-git-food",
        "content_retained": False,
    }


def test_realm_contract_preserves_open_free_zone_and_guarded_outbound_edge():
    raw = state_for("inbound", source_kind="semantic_seed_unstructured")
    proposal = state_for("distillation", source_kind="semantic_seed", distillation_status="PROPOSAL_ONLY")
    quarantine = state_for("experiment", source_kind="inbox", polluted=True)

    assert raw == {
        "contract_version": "ace.free_zone_realm.v1",
        "realm": "FREE",
        "authority": "SANDBOX_ONLY",
        "retention": "LINE",
        "outbound_rule": "REOBSERVE",
        "production_integration": False,
    }
    assert proposal["realm"] == "SHADOW"
    assert proposal["authority"] == "GOVERNED"
    assert proposal["outbound_rule"] == "EXISTING_ADMISSION"
    assert quarantine["realm"] == "UNDERWORLD"
    assert quarantine["retention"] == "ARCHIVED"
    assert quarantine["outbound_rule"] == "NONE"
    with pytest.raises(ValueError, match="unsupported"):
        state_for("reality")


def test_free_zone_records_carry_realm_state_through_factories_and_distillation(tmp_path):
    root = tmp_path / "sandbox"
    report = FreeZoneAutonomy(root, git_observer=_git_food, selection_seed_factory=lambda: 4).run_turn()
    experiment_id = report["execution"]["experiment_id"]

    assert report["claim"]["realm_state"]["realm"] == "FREE"
    experiment = json.loads((root / "experiments" / f"{experiment_id}.json").read_text(encoding="utf-8"))
    assert experiment["realm_state"]["realm"] == "SHADOW"
    thread = json.loads(next((root / "factories" / "threads").glob("*.json")).read_text(encoding="utf-8"))
    world = json.loads(next((root / "factories" / "worlds").glob("*.json")).read_text(encoding="utf-8"))
    assert thread["realm_state"]["realm"] == "FREE"
    assert world["realm_state"]["realm"] == "INTERNAL"

    SandboxSociety(root).run_turn()
    distillation = json.loads((root / "distillations" / f"{experiment_id}.json").read_text(encoding="utf-8"))
    assert distillation["realm_state"]["realm"] == "SHADOW"
    assert distillation["realm_state"]["outbound_rule"] == "REOBSERVE"


def test_polluted_record_goes_to_underworld_without_erasing_the_record(tmp_path):
    root = tmp_path / "sandbox"
    sandbox = FreeResearchSandbox(root)
    record = sandbox.record_experiment(
        experiment_id="EXP-POLLUTED", hypothesis="keep a trace", method="isolate it",
        outcome="INCONCLUSIVE", evidence={"source": "untrusted"},
        metadata={"untrusted_source": True},
    )

    assert record["realm_state"]["realm"] == "UNDERWORLD"
    assert record["realm_state"]["retention"] == "ARCHIVED"
    assert (root / "quarantine" / "EXP-POLLUTED.json").exists()
