import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ops.taskpool_historical_reconciliation import build_dry_run


def _write(root, state, task_id, rule, *, categories=None, errors=None, lease=False):
    path = root / "task_pool" / state / f"{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "task_id": task_id,
        "status": state,
        "created_at": "2026-08-26T10:00:00+08:00",
        "review_count": 1,
        "lease_owner": "researcher" if lease else None,
        "claim_id": "claim" if lease else None,
        "depends_on": [],
        "outputs": {
            "conversion_rule": rule,
            "admission": {
                "source_type": "system_observation",
                "source_ref": f"OBS-{task_id}",
                "evidence": [{"content": "evidence"}],
            },
            "last_validator_result": {"outcome": "rework_pending"},
        },
    }
    if categories is not None:
        record["outputs"]["admission"]["evidence"][0]["system_state"] = {"gap_categories": categories}
    if errors is not None:
        record["outputs"]["admission"]["evidence"][0]["system_state"] = {"error_samples": errors}
    path.write_text(json.dumps(record), encoding="utf-8")


def test_dry_run_only_groups_pending_equivalent_semantics(tmp_path):
    _write(tmp_path, "pending", "RQ-1", "lexicon_category_gap", categories=["stock", "concept"])
    _write(tmp_path, "pending", "RQ-2", "lexicon_category_gap", categories=["concept", "stock"])
    _write(tmp_path, "pending", "RQ-3", "lexicon_category_gap", categories=["risk"])
    _write(tmp_path, "blocked", "RQ-4", "lexicon_category_gap", categories=["stock", "concept"])
    _write(tmp_path, "pending", "RQ-5", "lexicon_category_gap", categories=["stock", "concept"], lease=True)

    report = build_dry_run(tmp_path, cutoff_at="2026-08-26T12:00:00+08:00")

    assert report["mode"] == "dry_run"
    assert report["snapshot"]["stable"] is True
    assert report["summary"]["merge_candidate_groups"] == 1
    group = report["groups"][0]
    assert group["canonical_task_id"] == "RQ-1"
    assert group["donor_task_ids"] == ["RQ-2"]
    assert report["summary"]["excluded_count"] == 3
    assert (tmp_path / "task_pool" / "pending" / "RQ-2.json").exists()


def test_dry_run_marks_recent_error_without_continuity_as_ambiguous(tmp_path):
    _write(tmp_path, "pending", "RQ-1", "recent_errors", errors=["research_lease_renewal_failed"])
    _write(tmp_path, "pending", "RQ-2", "recent_errors", errors=["research_lease_renewal_failed"])

    report = build_dry_run(tmp_path, cutoff_at="2026-08-26T12:00:00+08:00")

    assert report["summary"]["merge_candidate_groups"] == 0
    assert report["summary"]["needs_review_groups"] == 1
    assert report["groups"][0]["decision"] == "needs_review"
    assert report["groups"][0]["reason_codes"] == ["RECENT_ERROR_CONTINUITY_NOT_PROVEN"]


def test_dry_run_interprets_legacy_naive_task_time_in_cutoff_timezone(tmp_path):
    _write(tmp_path, "pending", "RQ-1", "lexicon_category_gap", categories=["stock"])
    _write(tmp_path, "pending", "RQ-2", "lexicon_category_gap", categories=["stock"])
    for task in (tmp_path / "task_pool" / "pending").glob("*.json"):
        record = json.loads(task.read_text(encoding="utf-8"))
        record["created_at"] = "2026-08-26T10:00:00"
        task.write_text(json.dumps(record), encoding="utf-8")

    report = build_dry_run(tmp_path, cutoff_at="2026-08-26T12:00:00+08:00")

    assert report["summary"]["merge_candidate_groups"] == 1


