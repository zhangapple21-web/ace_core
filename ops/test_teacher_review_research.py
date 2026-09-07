from core.teacher_review_research import assess_teacher_review_lane


def session(at):
    item = {
        "source_refs": ["evidence://a", "evidence://b"],
        "independence_groups": ["group-a", "group-b"],
        "lineage_observable": True,
        "coverage_complete": True,
        "fields_complete": True,
        "cross_source_consistent": True,
    }
    return {"observed_at": at, "operations": {name: dict(item) for name in ("quote", "minute_kline_1m", "index")}}


def test_live_lane_allows_two_teacher_review_cards_without_production_admission():
    record = assess_teacher_review_lane(
        as_of="2026-08-27T09:40:00+08:00",
        evidence_sessions=[session("2026-08-27T09:32:00+08:00")],
    )
    assert record["mode"] == "LIVE_RESEARCH"
    assert record["candidate_cards_authorized"] == 2
    assert record["strict_production_admission_unchanged"] is True
    assert record["automatic_delivery"] is False


def test_recent_multi_day_lane_uses_three_complete_sessions_when_live_is_stale():
    record = assess_teacher_review_lane(
        as_of="2026-08-27T09:40:00+08:00",
        evidence_sessions=[
            session("2026-08-26T09:35:00+08:00"),
            session("2026-08-25T09:35:00+08:00"),
            session("2026-08-22T09:35:00+08:00"),
        ],
    )
    assert record["mode"] == "RECENT_MULTI_DAY_RESEARCH"


def test_missing_hard_field_does_not_get_filled_by_context_or_old_data():
    broken = session("2026-08-27T09:39:00+08:00")
    broken["operations"]["index"]["fields_complete"] = False
    record = assess_teacher_review_lane(
        as_of="2026-08-27T09:40:00+08:00", evidence_sessions=[broken],
    )
    assert record["mode"] == "NONE"
    assert record["candidate_cards_authorized"] == 0


