import pytest

from core.indicator_archive import build_indicator_bridge_record
from core.tn6_experience_fusion import (
    CONTRACT_VERSION,
    DEFAULT_VETERAN_PRINCIPLES,
    annotate_candidate_with_prior,
    build_tn6_experience_prior,
)


def _bridge(tmp_path):
    for name in ("竞价排序.tn6", "突破起爆.tn6", "回踩承接.tn6", "板块热点.tn6"):
        (tmp_path / name).write_bytes(name.encode("utf-8"))
    return build_indicator_bridge_record(root=tmp_path, observed_at="2026-09-06T09:30:00+08:00")


def test_prior_extracts_structures_and_keeps_hypothesis_boundary(tmp_path):
    prior = build_tn6_experience_prior(
        _bridge(tmp_path),
        veteran_principles=[{
            "rule_id": "old-hand-001",
            "statement": "先看预期差，再等承接确认，失效就退出",
            "motifs": ["first_breakout", "first_pullback_position"],
        }],
    )
    assert prior["source_entry_count"] == 4
    assert {item["motif_id"] for item in prior["motifs"]} == {
        "opening_agency", "first_breakout", "first_pullback_position", "sector_breadth_expansion",
    }
    assert prior["veteran_alignment"][0]["alignment_status"] == "UNVALIDATED_ALIGNMENT"
    assert prior["score_contribution"] == 0.0
    assert prior["changes_candidate_grade"] is False
    assert prior["can_consume_as_market_signal"] is False


def test_prior_rejects_promoted_or_malformed_bridge(tmp_path):
    bridge = _bridge(tmp_path)
    bridge["research_status"] = "ADMITTED"
    with pytest.raises(ValueError, match="research_only"):
        build_tn6_experience_prior(bridge)

    bridge = _bridge(tmp_path)
    bridge["entry_count"] = 99
    with pytest.raises(ValueError, match="entry_count_mismatch"):
        build_tn6_experience_prior(bridge)


def test_annotation_preserves_grade_conviction_risk_and_score(tmp_path):
    prior = build_tn6_experience_prior(_bridge(tmp_path))
    candidate = {
        "candidate_id": "000001",
        "score": 4.2,
        "attack_grade": "A+",
        "conviction": "HIGH",
        "risk_level": "HIGH",
    }
    annotated = annotate_candidate_with_prior(
        candidate, prior, matched_motifs=["first_breakout"]
    )
    for field in ("score", "attack_grade", "conviction", "risk_level"):
        assert annotated[field] == candidate[field]
    assert annotated["tn6_prior_annotation"]["effect"] == "context_only"
    assert annotated["tn6_prior_annotation"]["score_delta"] == 0.0


def test_annotation_requires_this_contract():
    with pytest.raises(ValueError, match="unsupported_tn6_experience_prior"):
        annotate_candidate_with_prior({}, {"contract_version": CONTRACT_VERSION + ".x"})


def test_default_veteran_principles_are_context_only(tmp_path):
    bridge = _bridge(tmp_path)
    assert len(DEFAULT_VETERAN_PRINCIPLES) >= 4
    prior = bridge["experience_prior"]
    assert len(prior["veteran_alignment"]) == len(DEFAULT_VETERAN_PRINCIPLES)
    assert prior["score_contribution"] == 0.0
    assert prior["changes_candidate_grade"] is False
    assert prior["changes_conviction"] is False
    assert prior["changes_risk_level"] is False
