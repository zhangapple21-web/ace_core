import json

import pytest

from core.daily_research_brief import (
    BriefStatus,
    TeacherDecision,
    build_daily_research_brief,
    record_teacher_decision,
    write_brief,
)


def strict_matrix():
    operations = {
        name: {
            "production_sources": ["source-a", "source-b"],
            "independence_groups": ["group-a", "group-b"],
            "has_independent_cross_validation": True,
        }
        for name in ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index")
    }
    return {"phase_two_admission": {"status": "ADMITTED", "core_operations": operations}}


def ready_quality():
    return {"data_quality_status": "READY", "recommendation_eligibility": "eligible"}


def candidate():
    return {
        "candidate_id": "candidate-001",
        "symbol": "600000",
        "observed_at": "2026-08-26T09:31:00+08:00",
        "rule_card_id": "board_ladder_auction_strength.v0.1",
        "trigger_reasons": ["point-in-time event passed", "independent sources agree"],
        "invalidating_conditions": ["data becomes stale", "price limit lock has no fill evidence"],
        "source_refs": ["evidence://primary", "evidence://independent"],
        "data_snapshot_hash": "a" * 64,
        "research_summary": "Descriptive research state; requires teacher review.",
        "backtest_summary": {"status": "research_validated", "sample_policy": "frozen_oos_required"},
    }


def test_review_ready_brief_is_a_human_review_packet_not_a_recommendation():
    brief = build_daily_research_brief(
        brief_id="brief-001", market_date="2026-08-26", generated_at="2026-08-26T09:31:01+08:00",
        data_quality=ready_quality(), capability_matrix=strict_matrix(), candidates=[candidate()],
    )

    assert brief["brief_status"] == BriefStatus.REVIEW_READY.value
    assert brief["candidate_cards"][0]["symbol"] == "600000"
    assert brief["delivery"] == {
        "mode": "MANUAL_ONLY", "telegram_send_requested": False,
        "telegram_send_performed": False, "outbound_message": None,
    }
    assert "guarantee" in brief["disclaimer"]
    assert "recommendation" not in brief["candidate_cards"][0]


def test_any_data_gate_failure_fails_closed_and_removes_candidate_cards():
    brief = build_daily_research_brief(
        brief_id="brief-002", market_date="2026-08-26", generated_at="2026-08-26T09:31:01+08:00",
        data_quality={"data_quality_status": "STALE", "recommendation_eligibility": "do_not_recommend"},
        capability_matrix=strict_matrix(), candidates=[candidate()],
    )

    assert brief["brief_status"] == BriefStatus.RESEARCH_ONLY.value
    assert brief["candidate_cards"] == []
    assert "data_quality_not_recommendation_eligible" in brief["admission"]["blockers"]


def test_partial_phase_two_admission_is_not_enough_for_teacher_review_cards():
    matrix = strict_matrix()
    matrix["phase_two_admission"]["core_operations"]["index"]["independence_groups"] = ["group-a"]
    brief = build_daily_research_brief(
        brief_id="brief-003", market_date="2026-08-26", generated_at="2026-08-26T09:31:01+08:00",
        data_quality=ready_quality(), capability_matrix=matrix, candidates=[candidate()],
    )

    assert brief["brief_status"] == BriefStatus.RESEARCH_ONLY.value
    assert brief["candidate_cards"] == []
    assert "a_share_phase_two_not_strictly_admitted" in brief["admission"]["blockers"]


def test_teacher_approval_is_audit_only_and_never_sends_telegram():
    brief = build_daily_research_brief(
        brief_id="brief-004", market_date="2026-08-26", generated_at="2026-08-26T09:31:01+08:00",
        data_quality=ready_quality(), capability_matrix=strict_matrix(), candidates=[candidate()],
    )
    decided = record_teacher_decision(
        brief, candidate_id="candidate-001", decision=TeacherDecision.APPROVED,
        decided_at="2026-08-26T09:35:00+08:00", rationale="Teacher independently confirmed the research evidence.",
    )

    assert decided["teacher_decisions"]["candidate-001"]["forward_eligible"] is True
    assert decided["teacher_decisions"]["candidate-001"]["manual_transfer_required"] is True
    assert decided["delivery"]["telegram_send_performed"] is False
    assert decided["delivery"]["outbound_message"] is None


def test_research_only_brief_cannot_be_approved_or_forwarded():
    brief = build_daily_research_brief(
        brief_id="brief-005", market_date="2026-08-26", generated_at="2026-08-26T09:31:01+08:00",
        data_quality={"data_quality_status": "CONFLICT", "recommendation_eligibility": "do_not_recommend"},
        capability_matrix={}, candidates=[candidate()],
    )
    with pytest.raises(ValueError, match="candidate_id"):
        record_teacher_decision(
            brief, candidate_id="candidate-001", decision="APPROVED",
            decided_at="2026-08-26T09:35:00+08:00", rationale="Not permitted.",
        )


def test_brief_persistence_is_json_and_atomic_target(tmp_path):
    brief = build_daily_research_brief(
        brief_id="brief-006", market_date="2026-08-26", generated_at="2026-08-26T09:31:01+08:00",
        data_quality=ready_quality(), capability_matrix=strict_matrix(), candidates=[candidate()],
    )
    path = write_brief(tmp_path / "brief.json", brief)
    assert json.loads(path.read_text(encoding="utf-8"))["brief_id"] == "brief-006"
    assert not path.with_suffix(".json.tmp").exists()


def test_persistence_rejects_forged_outbound_delivery_or_unknown_fields(tmp_path):
    brief = build_daily_research_brief(
        brief_id="brief-007", market_date="2026-08-26", generated_at="2026-08-26T09:31:01+08:00",
        data_quality=ready_quality(), capability_matrix=strict_matrix(), candidates=[candidate()],
    )
    brief["delivery"]["telegram_send_requested"] = True
    with pytest.raises(ValueError, match="MANUAL_ONLY"):
        write_brief(tmp_path / "forged-delivery.json", brief)

    clean = build_daily_research_brief(
        brief_id="brief-008", market_date="2026-08-26", generated_at="2026-08-26T09:31:01+08:00",
        data_quality=ready_quality(), capability_matrix=strict_matrix(), candidates=[candidate()],
    )
    clean["candidate_cards"][0]["broker"] = {"order": "forbidden"}
    with pytest.raises(ValueError, match="unknown fields"):
        write_brief(tmp_path / "forged-card.json", clean)


def test_persistence_rejects_research_only_spoofed_as_review_ready(tmp_path):
    brief = build_daily_research_brief(
        brief_id="brief-009", market_date="2026-08-26", generated_at="2026-08-26T09:31:01+08:00",
        data_quality={"data_quality_status": "STALE", "recommendation_eligibility": "do_not_recommend"},
        capability_matrix={}, candidates=[],
    )
    brief["brief_status"] = BriefStatus.REVIEW_READY.value
    with pytest.raises(ValueError, match="review-ready"):
        write_brief(tmp_path / "forged-ready.json", brief)


