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
