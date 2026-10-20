import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_watchdog_state_round_trip_is_atomic_and_valid(tmp_path):
    from core.miner_pool.provider_watchdog import HEALTHY, ProviderWatchdog

    watchdog = ProviderWatchdog(state_dir=str(tmp_path))
    watchdog.register_provider("shenwen", "http://127.0.0.1:3000/v1")
    watchdog._providers["shenwen"].status = HEALTHY
    watchdog.record_success("shenwen", 12)

    state_path = tmp_path / "watchdog_state.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["providers"]["shenwen"]["status"] == HEALTHY
    assert not list(tmp_path.glob("watchdog_state.*.tmp"))


def test_corrupt_watchdog_snapshot_fails_closed_and_records_recovery_reason(tmp_path):
    state_path = tmp_path / "watchdog_state.json"
    state_path.write_text('{"providers":', encoding="utf-8")

    from core.miner_pool.provider_watchdog import ProviderWatchdog

    watchdog = ProviderWatchdog(state_dir=str(tmp_path))
    assert watchdog.is_healthy("shenwen") is False
    watchdog.register_provider("shenwen", "http://127.0.0.1:3000/v1")

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["providers"]["shenwen"]["status"] == "UNHEALTHY"
    assert payload["state_load_error"]


def _watchdog_with_aged(tmp_path, name, status, age_hours=None):
    """A provider whose stored rating is age_hours old (None = never)."""
    import time

    from core.miner_pool.provider_watchdog import ProviderWatchdog

    watchdog = ProviderWatchdog(state_dir=str(tmp_path))
    watchdog.register_provider(name, "http://127.0.0.1:3000/v1")
    provider = watchdog._providers[name]
    provider.status = status
    provider.total_calls = 5
    if age_hours is not None:
        stamp = time.time() - age_hours * 3600
        provider.last_check = stamp
        provider.last_success = stamp
    return watchdog


def test_fresh_healthy_rating_reports_current(tmp_path):
    import time

    from core.miner_pool.provider_watchdog import HEALTHY, STALE_TTL_SECONDS

    watchdog = _watchdog_with_aged(tmp_path, "glm", HEALTHY, age_hours=1)
    now = time.time()
    assert watchdog.effective_status("glm", now=now) == HEALTHY
    assert watchdog.is_healthy("glm") is True


def test_aged_healthy_rating_reports_stale_not_current(tmp_path):
    import time

    from core.miner_pool.provider_watchdog import HEALTHY, STALE, STALE_TTL_SECONDS

    watchdog = _watchdog_with_aged(tmp_path, "glm", HEALTHY, age_hours=30)
    now = time.time()
    assert watchdog.effective_status("glm", now=now, ttl_seconds=STALE_TTL_SECONDS) == STALE
    # Idle is not a fault: still routable, only deprioritized.
    assert watchdog.is_healthy("glm") is True
    assert watchdog.get_best_provider() == "glm"


def test_live_traffic_clears_staleness(tmp_path):
    import time

    from core.miner_pool.provider_watchdog import HEALTHY, STALE_TTL_SECONDS

    watchdog = _watchdog_with_aged(tmp_path, "glm", HEALTHY, age_hours=30)
    assert watchdog.effective_status("glm", ttl_seconds=STALE_TTL_SECONDS) != HEALTHY
    watchdog.record_success("glm", 120)
    assert watchdog.effective_status("glm", ttl_seconds=STALE_TTL_SECONDS) == HEALTHY


def test_fresh_unhealthy_is_not_masked_as_stale(tmp_path):
    import time

    from core.miner_pool.provider_watchdog import UNHEALTHY

    watchdog = _watchdog_with_aged(tmp_path, "oneapi", UNHEALTHY, age_hours=1)
    assert watchdog.effective_status("oneapi", now=time.time()) == UNHEALTHY
    assert watchdog.is_healthy("oneapi") is False
    assert watchdog.get_best_provider() is None


def test_aged_unhealthy_stays_out_of_routing(tmp_path):
    import time

    from core.miner_pool.provider_watchdog import STALE, UNHEALTHY

    watchdog = _watchdog_with_aged(tmp_path, "oneapi", UNHEALTHY, age_hours=400)
    assert watchdog.effective_status("oneapi", now=time.time()) == STALE
    assert watchdog.is_healthy("oneapi") is False
    assert watchdog.get_best_provider() is None


def test_never_observed_provider_reports_stale(tmp_path):
    from core.miner_pool.provider_watchdog import STALE

    watchdog = _watchdog_with_aged(tmp_path, "fresh", "UNHEALTHY", age_hours=None)
    assert watchdog.effective_status("fresh") == STALE
    assert watchdog.effective_status("no_such_provider") == STALE


def test_routing_prefers_fresh_over_stale_equal_rating(tmp_path):
    import time

    from core.miner_pool.provider_watchdog import HEALTHY

    watchdog = _watchdog_with_aged(tmp_path, "old", HEALTHY, age_hours=72)
    watchdog.register_provider("new", "http://127.0.0.1:3001/v1")
    provider = watchdog._providers["new"]
    provider.status = HEALTHY
    provider.total_calls = 5
    provider.last_check = time.time()
    provider.last_success = time.time()
    assert watchdog.get_best_provider() == "new"


def test_idle_all_stale_pool_still_routes(tmp_path):
    from core.miner_pool.provider_watchdog import HEALTHY

    watchdog = _watchdog_with_aged(tmp_path, "only", HEALTHY, age_hours=72)
    # An empty, quiet pool must not read as "no route exists".
    assert watchdog.get_best_provider() == "only"


def test_stats_and_listing_carry_honest_age(tmp_path):
    from core.miner_pool.provider_watchdog import HEALTHY

    watchdog = _watchdog_with_aged(tmp_path, "glm", HEALTHY, age_hours=30)
    stats = watchdog.get_stats()
    assert stats["stale"] == 1
    listed = {item["name"]: item for item in watchdog.list_providers()}
    assert listed["glm"]["effective_status"] != HEALTHY
    assert listed["glm"]["stale"] is True
    assert listed["glm"]["age_hours"] is not None and listed["glm"]["age_hours"] > 24
