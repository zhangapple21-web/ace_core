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
