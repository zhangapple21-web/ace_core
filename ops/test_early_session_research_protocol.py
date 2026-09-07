import pytest

from core.early_session_research_protocol import build_early_session_research_record
from core.indicator_archive import build_indicator_bridge_record


def strict_admission():
    operation = {
        "independent_cross_validation": True, "lineage_observable": True,
        "fresh": True, "coverage_complete": True, "fields_complete": True,
        "cross_source_consistent": True,
    }
    return {"phase_two_status": "ADMITTED", "operations": {name: dict(operation) for name in ("quote", "minute_kline_1m", "index")}}


def observation(fields):
    return {"observed_at": "2026-08-26T09:31:00+08:00", "source_refs": ["evidence://retained-snapshot"], "fields": fields}


def complete_phases():
    return {
        "premarket": observation({"announcement_scan": 1, "overnight_context": 1, "sector_hypotheses": 1}),
        "auction": observation({"auction_quote": 1, "auction_volume": 1, "index_auction": 1}),
        "first_minute": observation({"quote": 1, "minute_kline_1m": 1, "index": 1}),
        "open_validation": observation({"quote": 1, "minute_kline_1m": 1, "index": 1, "sector_breadth": 1, "volume_price": 1}),
    }


def test_open_validation_is_an_explicit_time_box_with_required_fields():
    record = build_early_session_research_record(
        observed_at="2026-08-26T09:36:00+08:00",
        data_admission=strict_admission(),
        rule_profile={"profile_id": "replay-v0", "historical_validation_ref": "casebook://frozen-001"},
        phase_observations=complete_phases(),
        context_questions=[{"source_ref": "snapshot://forum/1", "question": "Does a retail concern match traceable news or volume-price evidence?"}],
    )
    assert record["active_phase"] == "open_validation"
    assert record["phase_results"]["open_validation"]["status"] == "COMPLETE"
    assert record["data_admission"]["strict_live_admission"] is True
    assert record["research_status"] == "RESEARCH_ONLY"
    assert record["recommendation_authority"] is False


def test_missing_1m_data_or_unadmitted_source_fails_closed():
    admission = strict_admission()
    admission["operations"]["minute_kline_1m"]["cross_source_consistent"] = False
    record = build_early_session_research_record(
        observed_at="2026-08-26T09:31:00+08:00", data_admission=admission,
        phase_observations={**complete_phases(), "first_minute": observation({"quote": 1, "minute_kline_1m": None, "index": 1})},
    )
    assert "first_minute_missing_required_fields" in record["blockers"]
    assert "live_quote_1m_index_not_strictly_admitted" in record["blockers"]
    assert "no_frozen_rule_profile" in record["blockers"]


def test_time_zone_and_context_contract_are_enforced():
    with pytest.raises(ValueError, match="explicit timezone"):
        build_early_session_research_record(observed_at="2026-08-26T09:31:00", data_admission={}, phase_observations={})
    with pytest.raises(ValueError, match="context questions"):
        build_early_session_research_record(observed_at="2026-08-26T09:31:00+08:00", data_admission={}, phase_observations={}, context_questions=[{}])


def test_tn6_bridge_is_preserved_as_research_reference_only(tmp_path):
    (tmp_path / "清北竞价排序.tn6").write_bytes(b"fixture")
    bridge = build_indicator_bridge_record(root=tmp_path, observed_at="2026-08-26T09:30:00+08:00")
    record = build_early_session_research_record(
        observed_at="2026-08-26T09:31:00+08:00",
        data_admission=strict_admission(),
        phase_observations=complete_phases(),
        indicator_bridge=bridge,
    )
    assert record["indicator_bridge"]["can_consume_as_market_signal"] is False
    assert record["indicator_bridge"]["entry_count"] == 1


