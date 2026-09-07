import json

from core.data_admission_recovery import DataAdmissionRecovery


def _matrix(*, quote_sources=None, quote_cross=False):
    rows = {}
    for name in ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index"):
        sources = quote_sources if name == "quote" else ["a", "b"]
        cross = quote_cross if name == "quote" else True
        rows[name] = {
            "production_sources": sources or [],
            "independence_groups": sources or [],
            "has_independent_cross_validation": cross,
        }
    return {"phase_two_admission": {"status": "NOT_ADMITTED", "core_operations": rows}}


def test_recovery_ledger_turns_a_repeated_blocker_into_a_verification_due_signal(tmp_path):
    ledger = DataAdmissionRecovery(tmp_path)
    first = ledger.build(_matrix(), observed_at="2026-09-01T09:35:00+08:00")
    second = ledger.build(_matrix(), observed_at="2026-09-01T12:35:00+08:00")
    third = ledger.build(_matrix(), observed_at="2026-09-01T15:20:00+08:00")

    assert first["recovery_status"] == "RECOVERY_IN_PROGRESS"
    assert third["recovery_status"] == "RECOVERY_VERIFICATION_DUE"
    assert third["operations"]["quote"]["research_candidate_sources"] == ["sina_direct", "tencent_direct"]
    assert third["side_effects"]["admission_changed"] is False
    assert third["next_action"] == "research_candidate_source_evidence_without_changing_the_existing_refresh_or_admission"
    assert json.loads(ledger.path.read_text(encoding="utf-8"))["consecutive_unchanged_observations"] == 3


def test_recovery_never_confuses_a_plan_with_admission(tmp_path):
    report = DataAdmissionRecovery(tmp_path).build(
        _matrix(quote_sources=["sina_direct", "tencent_direct"], quote_cross=True)
    )
    assert report["phase_two_status"] == "NOT_ADMITTED"
    assert report["side_effects"]["recommendation_created"] is False


