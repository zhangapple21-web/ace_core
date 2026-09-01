import base64
import json

from core.free_zone_autonomy import FreeZoneAutonomy
from core.sandbox_society import SandboxSociety
from ops.run_museum_archaeology_turn import run_turn as run_museum_turn


def _constitution(root):
    directory = root / "constitution"
    directory.mkdir(parents=True)
    (directory / "R1_ECOLOGY_CONSTITUTION_v1.json").write_text(
        json.dumps({
            "invariants": [
                {"id": "ECO-01", "rule": "continuity is preserved"},
                {"id": "ECO-03", "rule": "failure is material"},
            ]
        }),
        encoding="utf-8",
    )


def test_autonomy_discovers_claims_and_executes_without_teacher_or_court_preapproval(tmp_path):
    root = tmp_path / "sandbox"
    _constitution(root)
    report = FreeZoneAutonomy(root, selection_seed_factory=lambda: 17).run_turn()

    assert report["event"] == "FREE_ZONE_EXPERIMENT_EXECUTED"
    assert report["judgment"]["approval_required"] is False
    assert report["claim"]["status"] == "CLAIMED"
    assert report["execution"]["outcome"] in {"PASS", "FAIL"}
    assert report["production_integration"] is False
    assert report["resource_selection"]["selection_seed"] == 17
    assert report["resource_selection"]["quality_decision_performed"] is False
    assert report["resource_selection"]["outcome_used"] is False
    assert (root / "experiments" / f"{report['execution']['experiment_id']}.json").exists()
    assert report["execution_evidence"]["status"] == "UNATTRIBUTED_LOCAL_CALL"
    assert report["execution_evidence"]["natural_daemon_cycle"] == "UNKNOWN"
    record = json.loads((root / "experiments" / f"{report['execution']['experiment_id']}.json").read_text(encoding="utf-8"))
    assert record["metadata"]["execution_evidence"] == report["execution_evidence"]


def test_autonomy_binds_a_contextual_packet_and_persists_its_missing_learning_needs(tmp_path):
    root = tmp_path / "sandbox"
    _constitution(root)
    report = FreeZoneAutonomy(root, selection_seed_factory=lambda: 17).run_turn()
    experiment_id = report["execution"]["experiment_id"]
    record = json.loads((root / "experiments" / f"{experiment_id}.json").read_text(encoding="utf-8"))
    packet = record["metadata"]["contextual_state_packet"]

    assert packet["scope"] == "FREE_ZONE_RESEARCH_ONLY"
    assert packet["packet_hash"]
    assert packet["learning_needs"]
    assert packet["side_effects"] == {
        "task_created": False,
        "model_called": False,
        "production_runtime_mutation": False,
    }

    distillation = FreeZoneAutonomy(root).sandbox.distill(experiment_id)
    assert distillation["contextual_state"]["packet_hash"] == packet["packet_hash"]
    assert distillation["contextual_state"]["learning_needs"] == packet["learning_needs"]


def test_later_free_zone_turn_compares_its_identity_against_prior_context_with_source_lineage(tmp_path):
    root = tmp_path / "sandbox"
    _constitution(root)
    autonomy = FreeZoneAutonomy(root, selection_seed_factory=iter([101, 202]).__next__)
    autonomy.run_turn()
    SandboxSociety(root).run_turn()
    second = autonomy.run_turn()
    record = json.loads((root / "experiments" / f"{second['execution']['experiment_id']}.json").read_text(encoding="utf-8"))

    drift = record["metadata"]["identity_drift"]
    assert drift["status"] == "ALLOWED_VARIANT"
    assert drift["identity_id"] == "ACE_FREE_ZONE_CONTEXTUAL_RESEARCH"
    assert drift["evidence_refs"]


def test_autonomy_records_explicit_cli_trigger_without_granting_reality_authority(tmp_path):
    root = tmp_path / "sandbox"
    _constitution(root)
    report = FreeZoneAutonomy(root).run_turn(
        execution_context={"trigger_kind": "MANUAL_CLI", "runner": "ops/run_free_zone_autonomy_turn.py", "pid": 42},
    )
    assert report["execution_evidence"]["status"] == "EXPLICIT_TRIGGER_RECORDED"
    assert report["execution_evidence"]["natural_daemon_cycle"] == "NO"
    assert report["execution_evidence"]["shift"] == {"kind": "UNSPECIFIED", "check_in_at": None}
    assert report["production_integration"] is False


def test_off_duty_shift_records_actual_check_in_and_completion_without_claiming_two_hours(tmp_path):
    root = tmp_path / "sandbox"
    _constitution(root)
    report = FreeZoneAutonomy(root).run_turn(
        execution_context={
            "trigger_kind": "MANUAL_CLI",
            "runner": "ops/run_free_zone_autonomy_turn.py",
            "pid": 42,
            "shift_kind": "OFF_DUTY",
            "check_in_at": "2026-08-31T18:30:00+08:00",
        },
    )
    evidence = report["execution_evidence"]
    assert evidence["shift"] == {"kind": "OFF_DUTY", "check_in_at": "2026-08-31T18:30:00+08:00"}
    assert evidence["check_out_at"] == report["at"]
    assert "two_hour" not in evidence
    assert evidence["runtime_proof"] is False


def test_second_autonomy_turn_retains_failure_as_a_normal_counterexample(tmp_path):
    root = tmp_path / "sandbox"
    _constitution(root)
    autonomy = FreeZoneAutonomy(root, selection_seed_factory=iter([101, 202]).__next__)
    first = autonomy.run_turn()
    SandboxSociety(root).run_turn()
    second = autonomy.run_turn()

    assert {first["execution"]["outcome"], second["execution"]["outcome"]} == {"PASS", "FAIL"}
    society = SandboxSociety(root).run_turn()
    assert any(
        item["status"] == "COUNTEREXAMPLE_ONLY"
        for item in society["roles"]["teacher"]["counterexample_queue"]
    )


def test_inbox_food_is_claimed_automatically_and_remains_free_zone_only(tmp_path):
    root = tmp_path / "sandbox"
    _constitution(root)
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "challenge.json").write_text(
        json.dumps({"question": "Can this adversarial claim survive a specialized probe?"}),
        encoding="utf-8",
    )

    report = FreeZoneAutonomy(root).run_turn(max_experiments=2)
    assert {claim["source_kind"] for claim in report["claims"]} == {"constitution", "inbox"}
    assert "INCONCLUSIVE" in {execution["outcome"] for execution in report["executions"]}
    assert report["judgment"]["approval_required"] is False
    assert report["judgment"]["quality_decision_performed"] is False


def test_bounded_batch_executes_multiple_free_zone_items_without_preapproval(tmp_path):
    root = tmp_path / "sandbox"
    _constitution(root)
    report = FreeZoneAutonomy(root).run_turn(max_experiments=2)

    assert len(report["claims"]) == 2
    assert len(report["executions"]) == 2
    assert {item["outcome"] for item in report["executions"]} == {"PASS", "FAIL"}
    assert report["judgment"]["approval_required"] is False


def test_counterexample_becomes_food_for_a_separate_re_observation(tmp_path):
    root = tmp_path / "sandbox"
    _constitution(root)
    FreeZoneAutonomy(root).run_turn(max_experiments=2)
    SandboxSociety(root).run_turn()

    report = FreeZoneAutonomy(root).run_turn()
    assert report["claim"]["source_kind"] == "distillation"
    assert report["execution"]["outcome"] == "PASS"
    record = json.loads((root / "experiments" / f"{report['execution']['experiment_id']}.json").read_text(encoding="utf-8"))
    assert record["metadata"]["source_kind"] == "distillation"
    assert record["evidence"]["parent_preserved"] is True


def test_external_catalog_becomes_free_zone_food_only_after_local_sources_are_empty(tmp_path):
    root = tmp_path / "sandbox"
    autonomy = FreeZoneAutonomy(
        root,
        external_fetcher=lambda url: {"full_name": "stefan-jansen/alphalens-reloaded", "updated_at": "2026-08-27T00:00:00Z"},
    )
    report = autonomy.run_turn(allow_external=True)

    assert report["claim"]["source_kind"] == "external_catalog"
    assert report["execution"]["outcome"] == "INCONCLUSIVE"
    assert report["automatic_external_fetch"] is True
    assert report["production_integration"] is False


def test_public_readme_is_a_bounded_digest_only_after_metadata_food(tmp_path):
    root = tmp_path / "sandbox"
    readme = b"# research design\nNo executable authority.\n"

    def fetch(url):
        if url.endswith("/readme"):
            return {
                "name": "README.md",
                "path": "README.md",
                "sha": "upstream-sha",
                "encoding": "base64",
                "content": base64.b64encode(readme).decode("ascii"),
            }
        return {"full_name": "stefan-jansen/alphalens-reloaded", "updated_at": "2026-08-27T00:00:00Z"}

    autonomy = FreeZoneAutonomy(root, external_fetcher=fetch)
    metadata = autonomy.run_turn(allow_external=True)
    readme_turn = autonomy.run_turn(allow_external=True)

    assert metadata["claim"]["source_kind"] == "external_catalog"
    assert readme_turn["claim"]["source_kind"] == "external_repository_file"
    assert readme_turn["execution"]["outcome"] == "INCONCLUSIVE"
    record = json.loads((root / "experiments" / f"{readme_turn['execution']['experiment_id']}.json").read_text(encoding="utf-8"))
    assert record["evidence"]["content_retained"] is False
    assert record["evidence"]["content_sha256"]
    assert "content" not in record["evidence"]
    assert record["metadata"]["production_integration"] is False


def test_museum_food_is_claimed_and_rechecked_by_free_zone_not_by_museum(tmp_path):
    history = tmp_path / "history"
    reports = history / "private_claw-soul" / "07_OPERATIONS" / "knowledge_reports"
    reports.mkdir(parents=True)
    for day in range(1, 8):
        (reports / f"daily_report_202606{day:02d}.json").write_text(
            json.dumps({"report_date": f"2026-06-{day:02d}", "generated_at": "2026-06-01T00:00:00Z"}),
            encoding="utf-8",
        )
    archaeology = history / "r1-archaeology" / "analysis"
    archaeology.mkdir(parents=True)
    (archaeology / "archaeology_report_20260627.md").write_text("# evidence\n", encoding="utf-8")
    root = tmp_path / "sandbox"

    museum = run_museum_turn(sandbox_root=root, history_root=history)
    assert museum["event"] == "MUSEUM_FOOD_RECORDED"
    assert not list((root / "experiments").glob("*.json"))

    report = FreeZoneAutonomy(root).run_turn()
    assert report["claim"]["source_kind"] == "museum_history"
    assert report["execution"]["outcome"] == "PASS"
    society = SandboxSociety(root).run_turn()
    assert society["roles"]["court"]["status"] == "VALID"
    assert len(society["roles"]["teacher"]["review_queue"]) == 1


def test_local_git_delta_becomes_path_redacted_free_zone_food(tmp_path):
    root = tmp_path / "sandbox"
    observation = {
        "status": "OBSERVED",
        "repository": "C:/local/repository",
        "head": "abc123",
        "safe_paths": ["core/free_zone.py"],
        "safe_path_count": 1,
        "redacted_path_count": 2,
        "paths_sha256": "digest",
        "fingerprint": "git-fingerprint",
        "content_retained": False,
    }
    report = FreeZoneAutonomy(root, git_observer=lambda: observation).run_turn()

    assert report["claim"]["source_kind"] == "local_git"
    assert report["execution"]["outcome"] == "INCONCLUSIVE"
    record = json.loads((root / "experiments" / f"{report['execution']['experiment_id']}.json").read_text(encoding="utf-8"))
    assert record["evidence"]["content_retained"] is False
    assert record["evidence"]["redacted_path_count"] == 2
    assert "safe_paths" not in record["evidence"]
