import json

from ops.build_market_context_research import build


def test_build_uses_only_retained_window_and_snapshot_evidence(tmp_path):
    (tmp_path / "finance_work_windows_latest.json").write_text(json.dumps({
        "date": "2026-08-26", "observed_at": "2026-08-26T09:31:00+08:00", "window_status": "RESEARCH_ONLY", "finance_status": "DEGRADED", "recommendation_allowed": False,
    }), encoding="utf-8")
    snapshot = tmp_path / "snapshot.html"
    snapshot.write_text("retained", encoding="utf-8")
    import hashlib
    digest = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    (tmp_path / "public_sentiment_latest.json").write_text(json.dumps({
        "date": "2026-08-26", "observed_at": "2026-08-26T09:32:00+08:00", "sources": [{
            "status": "observed", "source_ref": f"{snapshot}#sha256={digest}", "content_hash": digest,
            "retrieved_at": "2026-08-26T09:32:00+08:00", "title": "Public discussion snapshot", "upstream_identity": "xueqiu", "independence_group": "xueqiu_community", "lineage_observable": True,
        }],
    }), encoding="utf-8")
    record = build(tmp_path)
    assert record["research_status"] == "RESEARCH_ONLY"
    assert record["recommendation_authority"] is False
    assert record["cross_validation_questions"]


def test_build_does_not_fetch_or_invent_context_when_evidence_missing(tmp_path):
    record = build(tmp_path)
    assert record["research_status"] == "NO_CONTEXT_EVIDENCE"
    assert record["recommendation_authority"] is False


