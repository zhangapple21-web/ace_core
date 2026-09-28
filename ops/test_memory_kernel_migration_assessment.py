import json

from ops.assess_memory_index_migration import assess


def test_large_low_provenance_index_is_staged(tmp_path):
    source = tmp_path / "memory_index.json"
    source.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": str(index),
                        "type": "daily_summary",
                        "data_class": "PRIVATE",
                        "created_at": "2026-09-28T00:00:00Z",
                    }
                    for index in range(501)
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report = assess(source)
    assert report["status"] == "STAGED_MIGRATION_REQUIRED"
    assert "legacy_index_large" in report["reasons"]
    assert report["production_integration"] is False


def test_small_provenanced_index_can_be_bounded(tmp_path):
    source = tmp_path / "memory_index.json"
    source.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "id": "one",
                        "type": "experience",
                        "data_class": "STRUCTURE",
                        "source_path": "receipt://one",
                        "created_at": "2026-09-28T00:00:00Z",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = assess(source)
    assert report["status"] == "READY_FOR_BOUNDED_MIGRATION"
    assert report["source_coverage"] == 1.0
