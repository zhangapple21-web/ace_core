from core.teacher_review_packet import build_teacher_review_packet
from ops.test_teacher_review_research import session


def test_packet_allows_two_cards_on_fresh_traceable_evidence():
    packet = build_teacher_review_packet(
        packet_id="p-1",
        as_of="2026-08-27T09:40:00+08:00",
        evidence_sessions=[session("2026-08-27T09:32:00+08:00")],
        candidates=[
            {"symbol": "000001", "thesis": "板块强度与量价共振", "trigger_conditions": ["开盘承接不弱"], "invalidation_conditions": ["跌破早盘低点"], "source_refs": ["evidence://a"], "observed_at": "2026-08-27T09:32:00+08:00"},
            {"symbol": "000002", "thesis": "热点延续观察", "trigger_conditions": ["成交量保持"], "invalidation_conditions": ["板块退潮"], "source_refs": ["evidence://b"], "observed_at": "2026-08-27T09:32:00+08:00"},
        ],
    )
    assert packet["mode"] == "LIVE_RESEARCH"
    assert len(packet["candidate_cards"]) == 2
    assert packet["delivery"]["telegram_send_performed"] is False
    assert packet["opportunity_call"]["daily_signal"] == "GRADE_CALL_UNAVAILABLE"


def test_packet_preserves_three_axes_and_reports_no_a_without_forcing_two_bs():
    packet = build_teacher_review_packet(
        packet_id="p-graded",
        as_of="2026-08-27T09:40:00+08:00",
        evidence_sessions=[session("2026-08-27T09:32:00+08:00")],
        candidates=[
            {"symbol": "000001", "thesis": "进攻观察", "trigger_conditions": ["承接"], "invalidation_conditions": ["失效"], "source_refs": ["evidence://a"], "observed_at": "2026-08-27T09:32:00+08:00", "attack_grade": "B", "conviction": "HIGH", "risk_level": "HIGH"},
            {"symbol": "000002", "thesis": "平衡观察", "trigger_conditions": ["放量"], "invalidation_conditions": ["破位"], "source_refs": ["evidence://b"], "observed_at": "2026-08-27T09:32:00+08:00", "attack_grade": "B", "conviction": "MEDIUM", "risk_level": "MEDIUM"},
        ],
    )
    assert packet["candidate_cards"][0]["risk_level"] == "HIGH"
    assert packet["opportunity_call"]["daily_signal"] == "NO_A_TODAY"
    assert packet["opportunity_call"]["a_grade_present"] is False


def test_packet_has_no_cards_when_hard_evidence_is_missing():
    broken = session("2026-08-27T09:39:00+08:00")
    broken["operations"]["index"]["fields_complete"] = False
    packet = build_teacher_review_packet(
        packet_id="p-2", as_of="2026-08-27T09:40:00+08:00",
        evidence_sessions=[broken], candidates=[],
    )
    assert packet["mode"] == "NONE"
    assert packet["candidate_cards"] == []


