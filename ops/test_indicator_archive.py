import hashlib

import pytest

from core.indicator_archive import (
    CONTRACT_VERSION,
    build_indicator_bridge_record,
    classify_indicator_name,
    inventory_tn6,
)


def test_filename_mapping_is_metadata_only():
    result = classify_indicator_name("清北竞价绝杀排序.tn6")
    assert "auction" in result["semantic_tags"]
    assert result["mapped_factors"] == ["auction_opening_support"]


def test_inventory_hashes_files_without_parsing_formula(tmp_path):
    nested = tmp_path / "指标-通信达"
    nested.mkdir()
    sample = nested / "分时主买主图.tn6"
    sample.write_bytes(b"binary-fixture")
    entries = inventory_tn6(tmp_path)
    assert len(entries) == 1
    assert entries[0].parse_status == "BINARY_FORMULA_UNPARSED"
    assert entries[0].sha256 == hashlib.sha256(b"binary-fixture").hexdigest()
    assert entries[0].mapped_factors == ("intraday_volume_price_turnover",)


def test_bridge_remains_research_only_and_reports_uncovered_next_day_path(tmp_path):
    (tmp_path / "板块排名.tn6").write_bytes(b"fixture")
    record = build_indicator_bridge_record(root=tmp_path, observed_at="2026-09-05T21:00:00+08:00")
    assert record["contract_version"] == CONTRACT_VERSION
    assert record["entry_count"] == 1
    assert record["can_consume_as_market_signal"] is False
    assert record["production_integration"] is False
    assert "next_day_path_exit" in record["missing_factor_coverage"]
    assert record["experience_prior"]["epistemic_status"] == "HYPOTHESIS_ONLY"
    assert record["experience_prior"]["score_contribution"] == 0.0


def test_bridge_requires_timezone_and_directory(tmp_path):
    with pytest.raises(ValueError, match="timezone"):
        build_indicator_bridge_record(root=tmp_path, observed_at="2026-09-05T21:00:00")
    with pytest.raises(ValueError, match="existing_directory"):
        inventory_tn6(tmp_path / "missing")


