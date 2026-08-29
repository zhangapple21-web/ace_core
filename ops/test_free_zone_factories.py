import json

from core.free_zone_autonomy import FreeZoneAutonomy
from core.sandbox_society import SandboxSociety


def _git_food():
    return {
        "status": "OBSERVED",
        "repository": "C:/local/repository",
        "head": "abc123",
        "safe_paths": ["core/free_zone.py"],
        "safe_path_count": 1,
        "redacted_path_count": 1,
        "paths_sha256": "paths-digest",
        "fingerprint": "git-food-fingerprint",
        "content_retained": False,
    }


def test_five_factories_materialize_a_thread_mark_worlds_processing_and_smelting(tmp_path):
    root = tmp_path / "sandbox"
    report = FreeZoneAutonomy(root, git_observer=_git_food).run_turn()
    experiment_id = report["execution"]["experiment_id"]
    factories = report["factories"]

    assert report["claim"]["source_kind"] == "local_git"
    assert factories["recovery_thread_count"] == 1
    assert factories["mark_count"] == 1
    assert factories["world_count"] == 2
    assert factories["processing_receipt_count"] == 1
    assert factories["courier_receipt_count"] == 0
    assert factories["production_integration"] is False

    thread = next((root / "factories" / "threads").glob("*.json"))
    mark = next((root / "factories" / "marks").glob("*.json"))
    worlds = [json.loads(path.read_text(encoding="utf-8")) for path in (root / "factories" / "worlds").glob("*.json")]
    process = json.loads((root / "factories" / "processing" / f"{experiment_id}.json").read_text(encoding="utf-8"))
    assert json.loads(thread.read_text(encoding="utf-8"))["content_retained"] is False
    assert "LOCAL_PATH_REDACTED" in json.loads(mark.read_text(encoding="utf-8"))["labels"]
    assert {world["stance"] for world in worlds} == {"DIRECT_OBSERVATION", "COUNTEREXAMPLE_SEARCH"}
    assert all(world["execution_state"] == "BLUEPRINT_ONLY" for world in worlds)
    assert process["production_integration"] is False
    assert process["selected_stance"] == "DIRECT_OBSERVATION"

    society = SandboxSociety(root).run_turn()
    assert society["factories"]["smelter_receipt_count"] == 1
    receipt = json.loads((root / "factories" / "smelter" / f"{experiment_id}.json").read_text(encoding="utf-8"))
    assert receipt["thread_id"] == process["thread_id"]
    assert receipt["production_integration"] is False


def test_external_public_food_gets_a_courier_receipt_without_payload_retention(tmp_path):
    root = tmp_path / "sandbox"
    autonomy = FreeZoneAutonomy(
        root,
        git_observer=lambda: {"status": "NO_SAFE_GIT_FOOD"},
        external_fetcher=lambda url: {"full_name": "stefan-jansen/alphalens-reloaded", "updated_at": "2026-08-27T00:00:00Z"},
    )
    report = autonomy.run_turn(allow_external=True)
    experiment_id = report["execution"]["experiment_id"]

    assert report["claim"]["source_kind"] == "external_catalog"
    assert report["factories"]["courier_receipt_count"] == 1
    receipt = json.loads((root / "factories" / "courier" / f"COURIER-{experiment_id}.json").read_text(encoding="utf-8"))
    assert receipt["direction"] == "PUBLIC_BATTLEFIELD_TO_FREE_ZONE"
    assert receipt["payload_retained"] is False
    assert receipt["credentials_read"] is False
    assert receipt["production_integration"] is False
