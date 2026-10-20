"""A retired free model must be refused before a subprocess starts.

Measured 2026-10-19. Four of the nine pinned ids no longer resolved on the free
tier: fledge-alpha-free - the writing workhorse - muse-spark-1.3-contributor-free,
ling-3.1-flash-free and ling-3.0-flash-fin-free. Five models the CLI served had
never been registered, including the two named as the replacement writing path,
deepseek-v4.1-flash-free and glm-5.3-flash-free.

The part that mattered more than the rot: `resolve_cli_model` returned those
dead ids happily. It only asked whether a slug appeared in OPENCODE_MODELS,
which is the same stale table, so a retired model passed validation and failed
at the call instead.

These tests pin the two halves that fix that: liveness comes from the CLI, and a
CLI that cannot be asked must not take the free tier offline with it.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.miner_pool.providers import free_model_discovery as fmd
from core.miner_pool.providers.opencode_cli import (
    MODEL_MAP,
    resolve_cli_model,
    available_cli_models,
)

# The four ids that were pinned on 2026-10-18 and gone by 2026-10-19.
RETIRED = (
    "opencode/fledge-alpha-free",
    "opencode/muse-spark-1.3-contributor-free",
    "opencode/ling-3.1-flash-free",
    "opencode/ling-3.0-flash-fin-free",
)


def test_a_retired_model_is_refused_not_routed():
    for cli_id in RETIRED:
        assert resolve_cli_model(cli_id) is None, (
            f"{cli_id} no longer exists and must be refused before any call"
        )
        assert resolve_cli_model(f"opencode_cli:{cli_id.split('/', 1)[1]}") is None


def test_the_replacement_writing_models_are_routable():
    """The owner named these as the path forward; they must actually work."""
    for miner_id in ("opencode_cli:deepseek-v4.1-flash-free",
                     "opencode_cli:glm-5.3-flash-free"):
        resolved = resolve_cli_model(miner_id)
        assert resolved == miner_id.split(":", 1)[1].join(("opencode/", "")), resolved


def test_discovery_reads_the_cli_not_this_repository():
    live = fmd.discover_free_models(force=True)
    assert live, "no free models discovered"
    assert all("-free" in m.lower() for m in live), live
    assert "opencode/glm-5.3-flash-free" in live
    # A retired id must not reappear from this repo's own memory.
    for dead in RETIRED:
        assert dead not in live


def test_a_failed_probe_keeps_the_last_good_roster():
    """A flapping CLI must not take the free tier offline.

    Emptying the roster on a failed probe would read as "the free tier is gone"
    and stop every free route at once - a transient CLI problem turning into a
    total outage of the cheapest capacity.
    """
    fmd.reset_cache()
    good = fmd.discover_free_models(force=True)
    assert good

    def broken(*args, **kwargs):
        raise OSError("simulated CLI failure")

    original = fmd._run_cli
    fmd._run_cli = broken
    try:
        after_failure = fmd.discover_free_models(force=True)
        assert after_failure == good, (
            "a failed probe must return the previous roster, not an empty one"
        )
        state = fmd.cache_state()
        # Either failure mode is acceptable here; what matters is that one was
        # recorded and the roster survived it.
        assert state["error"] in {"cli_probe_failed", "cli_probe_raised"}
        assert state["model_count"] == len(good)
    finally:
        fmd._run_cli = original
        fmd.reset_cache()


def test_a_probe_that_returns_none_also_keeps_the_roster():
    """The expected failure path: the probe declines rather than raising."""
    fmd.reset_cache()
    good = fmd.discover_free_models(force=True)
    assert good

    original = fmd._run_cli
    fmd._run_cli = lambda *a, **k: None
    try:
        assert fmd.discover_free_models(force=True) == good
        assert fmd.cache_state()["error"] == "cli_probe_failed"
    finally:
        fmd._run_cli = original
        fmd.reset_cache()


def test_an_empty_free_tier_is_recorded_as_a_fact_not_hidden():
    """A genuinely empty roster must be visible, not passed off as stale.

    This is the distinction that matters: "the CLI failed" keeps the old answer,
    while "the CLI answered and offers nothing free" is new information and must
    replace the cache even though it is empty.
    """
    fmd.reset_cache()
    fmd.discover_free_models(force=True)

    original = fmd._run_cli
    fmd._run_cli = lambda *a, **k: ["opencode/some-paid-model", "agnes/agnes-2.5-flash"]
    try:
        assert fmd.discover_free_models(force=True) == []
        state = fmd.cache_state()
        assert state["error"] == "no_free_models_offered"
        assert state["model_count"] == 0
    finally:
        fmd._run_cli = original
        fmd.reset_cache()


def test_cache_state_reports_its_own_age():
    fmd.reset_cache()
    fmd.discover_free_models(force=True)
    state = fmd.cache_state()
    assert state["source"] == "cli"
    assert state["model_count"] > 0
    assert state["age_seconds"] is not None
    assert state["age_seconds"] < fmd.DEFAULT_TTL_SECONDS


def test_available_models_expose_liveness():
    rows = available_cli_models()
    assert rows
    for row in rows:
        assert set(row) >= {"id", "cli_model", "live"}
        assert row["cli_model"] in MODEL_MAP.values()


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))