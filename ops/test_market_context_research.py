import json

import pytest

from core.market_context_research import build_market_context_research, write_market_context_research


def fact():
    return {"source_ref": "market://quote/600000#sha256=abc", "observed_at": "2026-08-26T09:31:00+08:00", "summary": "Observed price and turnover snapshot.", "upstream_identity": "registered_quote_source", "lineage_observable": True}


def community():
    return {"source_role": "community_discussion", "source_ref": "snapshot://xueqiu/abc#sha256=abc", "observed_at": "2026-08-26T09:32:00+08:00", "summary": "Public discussion expresses a concern requiring independent verification.", "upstream_identity": "xueqiu", "lineage_observable": True}


def test_context_records_questions_without_recommendation_authority(tmp_path):
    record = build_market_context_research(market_date="2026-08-26", observed_at="2026-08-26T09:33:00+08:00", market_facts=[fact()], context_evidence=[community()])
    assert record["research_status"] == "RESEARCH_ONLY"
    assert record["recommendation_authority"] is False
    assert record["market_data_admission_changed"] is False
    assert record["cross_validation_questions"][0]["status"] == "UNVERIFIED_CONTEXT"
    path = write_market_context_research(tmp_path / "market_context_latest.json", record)
    assert json.loads(path.read_text(encoding="utf-8"))["research_status"] == "RESEARCH_ONLY"


def test_context_rejects_missing_market_fact_or_unknown_role():
    with pytest.raises(ValueError, match="market fact"):
        build_market_context_research(market_date="2026-08-26", observed_at="now", market_facts=[], context_evidence=[community()])
    bad = dict(community())
    bad["source_role"] = "advisor"
    with pytest.raises(ValueError, match="not allowed"):
        build_market_context_research(market_date="2026-08-26", observed_at="now", market_facts=[fact()], context_evidence=[bad])


