import json
from datetime import datetime
from pathlib import Path

import pytest

import ace_daemon
from core.free_research_sandbox import FreeResearchSandbox
from core.free_zone_roundtable import (
    CONTRACT_VERSION,
    MAX_CALLS_PER_SESSION,
    SEATS,
    FreeZoneRoundtable,
)

#: Providers a roundtable seat may sit on. Every one of them is free, and
#: none of them is a paid route. Two of them on purpose: the room should not
#: be one vendor agreeing with itself.
FREE_PROVIDERS = {"opencode_cli", "amd_radeon"}


class StubPool:
    """Records every call so a test can prove what was (not) dispatched."""

    def __init__(self, answers=None, fail_models=()):
        self.calls = []
        self.answers = answers or {}
        self.fail_models = set(fail_models)

    def chat(self, task_type, messages, system_prompt="", max_retries=3,
             selected_spec=None, **kwargs):
        model = getattr(selected_spec, "model", "?")
        self.calls.append({
            "task_type": task_type,
            "model": model,
            "provider": getattr(selected_spec, "provider", "?"),
            "system_prompt": system_prompt,
            "user": messages[0]["content"],
            "max_retries": max_retries,
            "selected_spec": selected_spec is not None,
            "boundary": kwargs.get("data_boundary"),
        })
        if model in self.fail_models:
            return {"success": False, "content": "", "error": "seat down",
                    "model": model, "provider": "opencode_cli", "latency_ms": 5}
        return {"success": True, "content": self.answers.get(model, f"{model} says hello"),
                "model": model, "provider": "opencode_cli", "latency_ms": 7}


def _seed_open_question(root: Path, pattern: str = "When a stage skips silently, investigate via telemetry."):
    sandbox = FreeResearchSandbox(root)
    sandbox.initialize()
    record = sandbox.record_experiment(
        experiment_id="EXP-SRC-1",
        hypothesis="silent skip",
        method="telemetry",
        outcome="INCONCLUSIVE",
        evidence={"k": "v"},
        metadata={"source_kind": "unit_test"},
    )
    sandbox.distill("EXP-SRC-1")
    return record


def test_seats_are_free_cli_only_and_pinned(tmp_path):
    _seed_open_question(tmp_path)
    pool = StubPool()
    rt = FreeZoneRoundtable(tmp_path, pool)
    result = rt.run_once(force=True)
    assert result["status"] == "ROUNDTABLE_RECORDED"
    assert pool.calls, "expected at least one seat to speak"
    for call in pool.calls:
        assert call["selected_spec"], "seat must pin its model, not fall to the router"
        assert call["provider"] in FREE_PROVIDERS, (
            f"seat escaped to a paid provider: {call['provider']}"
        )
        assert "paid" not in call["model"]
        assert call["max_retries"] == 1, "a pinned seat must not spend budget retrying"
        assert call["boundary"] == {"data_class": "PUBLIC"}


def test_a_failing_seat_does_not_stop_the_session_or_fall_back_to_paid(tmp_path):
    _seed_open_question(tmp_path)
    # The seat under test is the first CLI twin in the roster, so this does not
    # depend on a specific model id surviving a roster change. StubPool matches
    # on the short model id, so strip the provider prefix.
    dead = SEATS[0][1].split(":", 1)[-1]
    pool = StubPool(fail_models={dead})
    rt = FreeZoneRoundtable(tmp_path, pool)
    result = rt.run_once(force=True)
    assert result["status"] == "ROUNDTABLE_RECORDED"
    assert result["seats_spoken"] >= 2, "other seats still spoke"
    assert all(call["provider"] in FREE_PROVIDERS for call in pool.calls), \
        "a dead seat must not be replaced by a paid provider"
    # dead seat recorded honestly as UNAVAILABLE
    session = json.loads((tmp_path / "reports" / "roundtable" / f"{result['session_id']}.json").read_text(encoding="utf-8"))
    statuses = {s["seat"]: s["status"] for s in session["seats"] if s["round"] == 1}
    assert statuses[SEATS[0][0]] == "UNAVAILABLE", "the dead seat must say so"
    assert statuses[SEATS[1][0]] == "SPOKEN", "a neighbour must still speak"


def test_calls_stay_within_budget_and_run_two_bounded_rounds(tmp_path):
    _seed_open_question(tmp_path)
    pool = StubPool()
    rt = FreeZoneRoundtable(tmp_path, pool)
    result = rt.run_once(force=True)
    assert result["model_calls"] <= MAX_CALLS_PER_SESSION
    assert result["model_calls"] == len(SEATS) * 2, "every seat, two bounded rounds"
    assert len(SEATS) >= 2, "roster must hold at least one seat per vendor"
    assert {m.split(":", 1)[0] for _, m in SEATS} == FREE_PROVIDERS, (
        "both free vendors must hold seats"
    )
    session = json.loads((tmp_path / "reports" / "roundtable" / f"{result['session_id']}.json").read_text(encoding="utf-8"))
    rounds = {s["round"] for s in session["seats"]}
    assert rounds == {1, 2}, "second round cross-examines the first"
    # second round must actually see the other seats' first-round text
    round2_prompt = next(c["user"] for c in pool.calls if "cross-examination" in c["user"])
    assert "What the other seats said" in round2_prompt
    assert "muse-spark-1.3-contributor-free says hello" in round2_prompt


def test_transcript_and_experiment_stay_inside_the_sandbox(tmp_path):
    _seed_open_question(tmp_path)
    pool = StubPool()
    rt = FreeZoneRoundtable(tmp_path, pool)
    before = {p for p in tmp_path.rglob("*") if p.is_file()}
    result = rt.run_once(force=True)
    after = {p for p in tmp_path.rglob("*") if p.is_file()}
    new_files = after - before
    assert new_files, "expected sandbox artifacts"
    for path in new_files:
        assert tmp_path in path.parents or path.parent == tmp_path, "writes stayed in sandbox root"
    session = json.loads((tmp_path / "reports" / "roundtable" / f"{result['session_id']}.json").read_text(encoding="utf-8"))
    assert session["production_integration"] is False
    assert session["taskpool_mutated"] is False
    assert session["automatic_promotion"] is False


def test_distillation_files_roundtable_as_open_question_not_a_pass(tmp_path):
    _seed_open_question(tmp_path)
    pool = StubPool()
    rt = FreeZoneRoundtable(tmp_path, pool)
    result = rt.run_once(force=True)
    # free talk is never a production PASS by itself
    assert result["distillation_status"] == "OPEN_QUESTION"


def test_cooldown_blocks_a_second_session_and_the_gate_says_why(tmp_path):
    _seed_open_question(tmp_path)
    pool = StubPool()
    rt = FreeZoneRoundtable(tmp_path, pool)
    rt.run_once(force=True)
    blocked = rt.run_once()
    assert blocked["status"] == "NOT_DUE"
    assert blocked["reason"].startswith("BLOCKED_BY_")
    gates = blocked["gate_evaluation"]["gates"]
    assert gates["cooldown_elapsed"]["passed"] is False


def test_topic_is_not_reused_so_the_sandbox_cannot_feed_itself_forever(tmp_path):
    _seed_open_question(tmp_path)
    pool = StubPool()
    rt = FreeZoneRoundtable(tmp_path, pool)
    first = rt.run_once(force=True)
    # Second forced session: the only open question is now used, so no new topic.
    second = rt.run_once(force=True)
    assert second["status"] == "NO_TOPIC"
    assert second["model_calls"] == 0
    assert first["topic_hash"] != ""


def test_explicit_seed_topic_wins_over_open_questions(tmp_path):
    _seed_open_question(tmp_path)
    channel = tmp_path / "inbox" / "roundtable"
    channel.mkdir(parents=True, exist_ok=True)
    (channel / "retry-policy.json").write_text(json.dumps({
        "question": "Should a blocked task that hit the terminal branch deposit an experience?",
        "source_ref": "unit_test",
    }), encoding="utf-8")
    pool = StubPool()
    rt = FreeZoneRoundtable(tmp_path, pool)
    result = rt.run_once(force=True)
    assert result["topic_source"].startswith("seed:")


def test_roundtable_seed_channel_is_invisible_to_the_flat_inbox_scan(tmp_path):
    """The model shift scans inbox/*.json; roundtable seeds must not pollute it."""
    channel = tmp_path / "inbox" / "roundtable"
    channel.mkdir(parents=True, exist_ok=True)
    (channel / "retry-policy.json").write_text(json.dumps({"question": "q" * 30}), encoding="utf-8")
    flat = sorted(p.name for p in (tmp_path / "inbox").glob("*.json"))
    assert flat == [], "roundtable seed must not appear in the flat inbox scan"


def test_absent_miner_pool_is_an_explicit_gate_not_a_crash(tmp_path):
    _seed_open_question(tmp_path)
    rt = FreeZoneRoundtable(tmp_path, None)
    result = rt.run_once(force=True)
    assert result["status"] == "NOT_DUE"
    assert result["reason"] == "MINER_POOL_ABSENT"


def test_agreement_is_labeled_as_unverified(tmp_path):
    _seed_open_question(tmp_path)
    pool = StubPool(answers={
        "muse-spark-1.3-contributor-free": "I agree the evidence is thin; dispute the priority.",
        "mimo-v2.6-flash-free": "I agree, and I do not know yet.",
        "ling-3.1-flash-free": "Uncertain; one measurement would settle it.",
    })
    rt = FreeZoneRoundtable(tmp_path, pool)
    result = rt.run_once(force=True)
    session = json.loads((tmp_path / "reports" / "roundtable" / f"{result['session_id']}.json").read_text(encoding="utf-8"))
    assert session["agreement"]["status"] == "READ_FROM_TRANSCRIPT"
    assert session["agreement"]["verified"] is False


def test_contract_version_is_declared(tmp_path):
    _seed_open_question(tmp_path)
    rt = FreeZoneRoundtable(tmp_path, StubPool())
    result = rt.run_once(force=True)
    assert result["contract_version"] == CONTRACT_VERSION
    session = json.loads((tmp_path / "reports" / "roundtable" / f"{result['session_id']}.json").read_text(encoding="utf-8"))
    assert session["contract_version"] == CONTRACT_VERSION


# ---------------------------------------------------------------- daemon stage

class _FixedClock:
    """Freeze the daemon stage inside the evening window for a deterministic run."""

    value = datetime(2026, 10, 11, 19, 0, 0)

    @classmethod
    def now(cls):
        return cls.value

    @classmethod
    def strftime(cls, *_):
        return cls.value.strftime(*_)


class _StubDaemon:
    def __init__(self, base_dir, config, pool):
        self.base_dir = base_dir
        self.config = config
        self.miner_pool = pool
        self.state = {}
        self.saved = False

    def _save_state(self):
        self.saved = True

    def _log_error(self, *_args, **_kwargs):
        pass


def _daemon_stage(monkeypatch, tmp_path, *, enabled, clock, pool):
    monkeypatch.setattr(ace_daemon, "datetime", clock)
    root = tmp_path / "07_SANDBOX" / "free_research"
    _seed_open_question(root)
    daemon = _StubDaemon(tmp_path, {"runtime": {"free_zone_roundtable": {"enabled": enabled}}}, pool)
    return ace_daemon.AceDaemon._run_free_zone_roundtable_if_due(daemon), daemon


def test_daemon_stage_disabled_is_an_explicit_gate(tmp_path, monkeypatch):
    result, daemon = _daemon_stage(
        monkeypatch, tmp_path, enabled=False, clock=_FixedClock, pool=StubPool()
    )
    assert result["status"] == "DISABLED"
    assert daemon.state["stage_gate_decisions"]["free_zone_roundtable"]["decision"] == "DISABLED"


def test_daemon_stage_outside_the_window_waits(tmp_path, monkeypatch):
    class _MorningClock(_FixedClock):
        value = datetime(2026, 10, 11, 9, 0, 0)

    result, daemon = _daemon_stage(
        monkeypatch, tmp_path, enabled=True, clock=_MorningClock, pool=StubPool()
    )
    assert result["status"] == "WAITING_FOR_DEDICATED_SHIFT"


def test_daemon_stage_absent_pool_is_named_not_crashed(tmp_path, monkeypatch):
    result, _ = _daemon_stage(
        monkeypatch, tmp_path, enabled=True, clock=_FixedClock, pool=None
    )
    assert result["status"] == "NO_EXISTING_MINER_POOL"


def test_daemon_stage_runs_a_session_and_records_the_decision(tmp_path, monkeypatch):
    result, daemon = _daemon_stage(
        monkeypatch, tmp_path, enabled=True, clock=_FixedClock, pool=StubPool()
    )
    assert result["status"] == "ROUNDTABLE_RECORDED"
    record = daemon.state["stage_gate_decisions"]["free_zone_roundtable"]
    assert record["decision"] == "ROUNDTABLE_RECORDED"
    assert record["session_id"] == result["session_id"]
    assert daemon.state["free_zone_roundtable_last"]["production_integration"] is False
    assert daemon.saved is True

