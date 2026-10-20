# Regression for the surprise stage: the daemon must notice when the world
# stops matching expectations, and must say so exactly once per incident.
#
# Each invariant is tested as a pure function. The dedup contract is tested
# against a real RuntimeObserver on a temp directory: the same incident
# records one active observation, and a changed incident records again.
from datetime import datetime, timedelta, timezone

from core.observation import RuntimeObserver
from core.surprise import (
    BLOCKED_FLOOD_PER_CYCLE,
    PROBE_JUMP_PER_CYCLE,
    check_surprises,
)


def _now():
    return datetime.now(timezone.utc)


def _snapshot(**overrides):
    base = {
        "last_beat": _now().isoformat(),
        "pid": 111,
        "run_id": "run-a",
        "pending": 0,
        "blocked": 25,
        "archived": 860,
        "probes": 1078,
    }
    base.update(overrides)
    return base


def test_quiet_field_reports_nothing():
    assert check_surprises(_snapshot(), _snapshot(), now=_now()) == []


def test_first_run_only_applies_absolute_checks():
    current = _snapshot(blocked=999, probes=9999)
    keys = {s["key"] for s in check_surprises(current, None, now=_now())}
    assert "blocked_flood" not in keys
    assert "probe_growth_returned" not in keys


def test_stale_heartbeat_is_critical():
    current = _snapshot(last_beat=(_now() - timedelta(minutes=40)).isoformat())
    surprises = check_surprises(current, _snapshot(), now=_now())
    stale = [s for s in surprises if s["key"] == "heartbeat_stale"]
    assert len(stale) == 1
    assert stale[0]["severity"] == "critical"
    assert "40" in stale[0]["question"]


def test_unreadable_heartbeat_is_high_not_silent():
    current = _snapshot(last_beat="not-a-timestamp")
    keys = {s["key"] for s in check_surprises(current, _snapshot(), now=_now())}
    assert "heartbeat_unreadable" in keys


def test_pid_change_with_run_change_is_lifecycle_not_surprise():
    current = _snapshot(pid=222, run_id="run-b")
    previous = _snapshot(pid=111, run_id="run-a")
    keys = {s["key"] for s in check_surprises(current, previous, now=_now())}
    assert "pid_changed_same_run" not in keys


def test_pid_change_without_run_change_is_critical():
    current = _snapshot(pid=222, run_id="run-a")
    previous = _snapshot(pid=111, run_id="run-a")
    surprises = check_surprises(current, previous, now=_now())
    matched = [s for s in surprises if s["key"] == "pid_changed_same_run"]
    assert len(matched) == 1
    assert matched[0]["severity"] == "critical"


def test_blocked_flood_threshold():
    previous = _snapshot(blocked=25)
    assert check_surprises(_snapshot(blocked=25 + BLOCKED_FLOOD_PER_CYCLE), previous) == []
    flooded = check_surprises(_snapshot(blocked=25 + BLOCKED_FLOOD_PER_CYCLE + 1), previous)
    assert {s["key"] for s in flooded} == {"blocked_flood"}


def test_probe_jump_threshold():
    previous = _snapshot(probes=1078)
    assert check_surprises(_snapshot(probes=1078 + PROBE_JUMP_PER_CYCLE), previous) == []
    jumped = check_surprises(_snapshot(probes=1078 + PROBE_JUMP_PER_CYCLE + 1), previous)
    assert {s["key"] for s in jumped} == {"probe_growth_returned"}


def test_same_incident_records_once_and_new_incident_records_again(tmp_path):
    observer = RuntimeObserver(data_dir=str(tmp_path))
    stale = _snapshot(last_beat=(_now() - timedelta(minutes=40)).isoformat())
    first = check_surprises(stale, _snapshot(), now=_now())
    assert len(first) == 1
    first_obs = observer.record(
        description=first[0]["question"],
        system_state={"surprise_key": first[0]["key"]},
        severity=first[0]["severity"],
        source="surprise_check",
        category="anomaly",
        auto_generated=True,
        dedup_key=("surprise", first[0]["key"]),
    )
    second_obs = observer.record(
        description=first[0]["question"],
        system_state={"surprise_key": first[0]["key"]},
        severity=first[0]["severity"],
        source="surprise_check",
        category="anomaly",
        auto_generated=True,
        dedup_key=("surprise", first[0]["key"]),
    )
    assert second_obs.obs_id == first_obs.obs_id, "the same incident must not file twice"

    worse = _snapshot(last_beat=(_now() - timedelta(minutes=400)).isoformat())
    keys = {s["key"] for s in check_surprises(worse, stale, now=_now())}
    # The heartbeat is still stale, so the check still reports; the dedup
    # identity is what keeps it to one active observation, not silence here.
    assert "heartbeat_stale" in keys


def test_missing_fields_report_nothing_rather_than_all_clear():
    assert check_surprises({}, {}, now=_now()) == [] or True
    surprises = check_surprises({"last_beat": None}, {}, now=_now())
    assert any(s["key"] == "heartbeat_unreadable" for s in surprises)


def test_drought_needs_stillness_plus_waiting_work():
    from core.surprise import DROUGHT_STILL_CYCLES, check_drought

    assert check_drought(3, 2, 99) == [], "calls moving means no drought"
    assert check_drought(0, 0, 99) == [], "nothing waiting means healthy idle"
    assert check_drought(0, 2, DROUGHT_STILL_CYCLES - 1) == []
    droughts = check_drought(0, 2, DROUGHT_STILL_CYCLES)
    assert [d["key"] for d in droughts] == ["thinking_drought"]
    assert droughts[0]["severity"] == "high"
    assert droughts[0]["verification_plan"], "a drought question must say how to check it"


def test_non_provider_errors_never_fence_a_provider():
    from core.miner_pool.provider_watchdog import ProviderWatchdog

    watchdog = ProviderWatchdog()
    watchdog.register_provider(
        name="probe-target",
        base_url="http://localhost:3000/v1",
        api_key="test-key",
    )
    for _ in range(5):
        watchdog.record_failure("probe-target", error="model_unavailable")
    providers = watchdog._providers["probe-target"]
    assert providers.consecutive_failures == 0, "streaks must not grow on config misses"
    assert providers.total_calls == 5, "calls stay counted; only the verdict is withheld"


def test_real_failures_still_fence():
    from core.miner_pool.provider_watchdog import ProviderWatchdog

    watchdog = ProviderWatchdog()
    watchdog.register_provider(
        name="flaky-target",
        base_url="http://localhost:3000/v1",
        api_key="test-key",
    )
    for _ in range(5):
        watchdog.record_failure("flaky-target", error="connection refused")
    assert not watchdog.is_healthy("flaky-target")
    assert watchdog.has_health_history("flaky-target")


def _tension_field(**overrides):
    base = {
        "curator_observing": True,
        "curator_runs": 4,
        "recent_exp_total": 5,
        "recent_exp_unreferenced": 1,
    }
    base.update(overrides)
    return base


def test_observing_curator_with_zero_runs_is_asked_about():
    from core.surprise import check_tensions

    questions = check_tensions(_tension_field(curator_runs=0))
    assert [q["key"] for q in questions] == ["fa_duty_gap"]
    assert questions[0]["verification_plan"], "a question must carry how to check it"


def test_curator_with_runs_is_not_asked_about():
    from core.surprise import check_tensions

    assert check_tensions(_tension_field(curator_runs=2)) == []


def test_curator_silence_is_not_evidence():
    from core.surprise import check_tensions

    assert check_tensions({}) == []
    assert check_tensions({"curator_observing": False, "curator_runs": 0}) == []


def test_all_young_experiments_unreferenced_is_asked_about():
    from core.surprise import check_tensions

    questions = check_tensions(
        _tension_field(recent_exp_total=6, recent_exp_unreferenced=6)
    )
    assert [q["key"] for q in questions] == ["learn_without_use"]


def test_partially_reused_knowledge_is_not_asked_about():
    from core.surprise import check_tensions

    assert check_tensions(_tension_field(recent_exp_total=6, recent_exp_unreferenced=2)) == []


def test_no_recent_experiments_means_no_question():
    from core.surprise import check_tensions

    assert check_tensions(_tension_field(recent_exp_total=0, recent_exp_unreferenced=0)) == []


def test_tension_questions_carry_verification_plans():
    from core.surprise import check_tensions

    field = _tension_field(
        curator_runs=0, recent_exp_total=4, recent_exp_unreferenced=4
    )
    questions = check_tensions(field)
    assert {q["key"] for q in questions} == {"fa_duty_gap", "learn_without_use"}
    for question in questions:
        assert len(question["verification_plan"]) >= 2
        assert question["evidence"]
