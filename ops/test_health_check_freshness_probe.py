# Regression: patrol reports model-health ratings with their age.
#
# Idle must never read as fault (no error for STALE), old ratings must
# never pose as current (named with ages), and a fresh failure must stay
# a failure (STALE never masks UNHEALTHY). Read-only: nothing here probes
# the network, manufactures a call, or writes a task.
import json
import time
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _watchdog_dir(workdir, providers):
    from ops import health_check  # noqa: F401  (import shape only)

    state_dir = (
        Path(workdir) / "06_RUNTIME" / "ace" / "data" / "miner_pool" / "provider_watchdog"
    )
    state_dir.mkdir(parents=True)
    (state_dir / "watchdog_state.json").write_text(
        json.dumps({"providers": providers, "switch_events": []}), encoding="utf-8"
    )


def _record(name, status, age_hours):
    stamp = time.time() - age_hours * 3600 if age_hours is not None else 0.0
    return {
        "provider": name,
        "status": status,
        "last_check": stamp,
        "last_success": stamp,
        "total_calls": 5,
        "failed_calls": 0,
    }


def _probe(workdir, monkeypatch):
    from ops import health_check

    monkeypatch.setattr(health_check, "BASE_DIR", Path(workdir))
    checker = health_check.HealthChecker()
    checker._check_provider_freshness()
    return checker


def test_stale_ratings_warn_with_names_and_ages(tmp_path, monkeypatch):
    _watchdog_dir(tmp_path, {
        "glm": _record("glm", "HEALTHY", 1),
        "oneapi": _record("oneapi", "UNHEALTHY", 400),
        "nim": _record("nim", "HEALTHY", 800),
        "fresh_bad": _record("fresh_bad", "UNHEALTHY", 1),
    })
    checker = _probe(tmp_path, monkeypatch)

    assert not checker.errors
    warnings = [e for e in checker.results if e["name"] == "模型健康评级新鲜"]
    assert len(warnings) == 1
    entry = warnings[0]
    assert entry["passed"] is False
    assert entry["severity"] == "warning"
    assert "STALE=2" in entry["detail"]
    assert "oneapi(" in entry["detail"] and "nim(" in entry["detail"]
    # The fresh failure is still reported as a failure, not hidden by STALE.
    assert "UNHEALTHY=1" in entry["detail"]


def test_all_fresh_pool_passes(tmp_path, monkeypatch):
    _watchdog_dir(tmp_path, {
        "glm": _record("glm", "HEALTHY", 1),
        "opencode_cli": _record("opencode_cli", "RECOVERING", 2),
    })
    checker = _probe(tmp_path, monkeypatch)

    assert not checker.errors
    assert not checker.warnings
    entry = [e for e in checker.results if e["name"] == "模型健康评级新鲜"][0]
    assert entry["passed"] is True


def test_missing_watchdog_state_is_not_a_fault(tmp_path, monkeypatch):
    from ops import health_check

    monkeypatch.setattr(health_check, "BASE_DIR", Path(tmp_path))
    checker = health_check.HealthChecker()
    checker._check_provider_freshness()

    assert not checker.errors
