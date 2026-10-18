"""Regress the cross-agent scan status handshake end to end.

The daemon scanner owns last_commit/processed_commits, while cross_agent_idle
is evaluated against daemon_state.json. A successful zero-result fetch must
still be stamped through the daemon's existing atomic state-save path.
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ace_daemon import AceDaemon  # noqa: E402
from core.observation import Observation, RuntimeObserver  # noqa: E402
from core.observation_to_task import BUILTIN_RULES, ObservationToTaskConverter, _cross_agent_idle  # noqa: E402


class ScannerStub:
    def __init__(self, outcome=None, error=None):
        self.outcome = outcome
        self.error = error

    def scan_and_create_tasks(self, *_args, **_kwargs):
        if self.error:
            raise self.error
        return dict(self.outcome)


class Unused:
    def __getattr__(self, name):
        raise AssertionError(f"unrelated lifecycle dependency accessed: {name}")


def _daemon(tmp_path, monkeypatch, scanner_outcome=None, scanner_error=None):
    daemon = AceDaemon(tmp_path, {})
    daemon.mine_seed_scanner = ScannerStub(scanner_outcome, scanner_error)
    monkeypatch.setattr(daemon, "_task_production_policy", lambda: {
        "low_value_production": True,
        "pending_tasks": 0,
    })
    monkeypatch.setattr(daemon, "recover_task_pool", lambda: [])
    monkeypatch.setattr(daemon, "run_daily_learning", lambda: {})
    daemon.governed_external_miner = None
    daemon.file_scanner = None
    daemon.self_evolution = None
    daemon.event_listener = None
    daemon.observer = Unused()
    daemon.discovery_mode = None
    daemon.obs_to_task_converter = None
    monkeypatch.setattr(daemon.task_pool, "unblock_ready_dependencies", lambda: [])
    daemon.researcher = Unused()
    daemon.validator = Unused()
    daemon.guardian = Unused()
    daemon.archivist = Unused()
    daemon.experience_deposition = Unused()
    daemon.skill_generator = None
    daemon.memory_gateway = Unused()
    daemon.fragment_index = None
    daemon.local_archaeologist = None
    daemon.web_scout = None
    daemon.daily_shift = None
    daemon.hourly_task_service = None
    daemon.closed_loop_background = None
    daemon.miner_pool = None
    daemon.repository_curator = None
    daemon.free_zone_reflection_relay = None
    daemon.shutdown_event.set()
    monkeypatch.setattr(daemon, "_run_free_zone_autonomy_if_due", lambda: {})
    monkeypatch.setattr(daemon, "_run_sandbox_society_if_due", lambda: {})
    monkeypatch.setattr(daemon, "_run_free_zone_model_shift_if_due", lambda: {})
    monkeypatch.setattr(daemon, "_run_free_zone_roundtable_if_due", lambda: {})
    monkeypatch.setattr(daemon, "_run_free_zone_social_room_if_due", lambda: {})
    monkeypatch.setattr(daemon, "_run_free_zone_external_review_if_due", lambda: {})
    monkeypatch.setattr(daemon, "_dispatch_video_kingdom", lambda: {})
    return daemon


def _run_scanner_lifecycle(daemon):
    return daemon._run_task_lifecycle_unlocked()


def _prepare_observation_producer(daemon, tmp_path):
    daemon.runtime_observer = RuntimeObserver(str(tmp_path / "runtime_observations"))
    daemon.fragment_index = None
    daemon.memory_gateway = type("MemoryStats", (), {"get_stats": lambda self: {"total": 0}})()
    daemon.lexicon = type("LexiconStats", (), {"get_stats": lambda self: {"total_concepts": 0, "categories": {}}})()


def _never_incidents(daemon):
    return [
        observation
        for observation in daemon.runtime_observer.get_recent(limit=200)
        if observation.description == "mine-seed 扫描器从未执行，跨智能体学习通道关闭。"
    ]


@pytest.mark.parametrize(
    "scan_result",
    [
        {"fetched": True, "new_commits": 0, "tasks_created": 0, "commits": [], "error": None},
        {"fetched": True, "new_commits": 1, "tasks_created": 1, "commits": [{"hash": "abc"}], "error": None},
    ],
    ids=["successful-empty-fetch", "successful-with-new-commit"],
)
def test_successful_scan_updates_persisted_status_and_prevents_never_incident(
    tmp_path, monkeypatch, scan_result
):
    daemon = _daemon(tmp_path, monkeypatch, scanner_outcome=scan_result)

    result = _run_scanner_lifecycle(daemon)

    stamped = daemon.state.get("last_mine_seed_scan")
    assert isinstance(stamped, str) and stamped != "never"
    assert datetime.fromisoformat(stamped)
    assert result["mine_seed_commits"] == scan_result["new_commits"]
    assert result["mine_seed_tasks"] == scan_result["tasks_created"]

    reloaded = AceDaemon.__new__(AceDaemon)
    reloaded.data_dir = daemon.data_dir
    reloaded.state_file = daemon.state_file
    assert reloaded._load_state()["last_mine_seed_scan"] == stamped

    _prepare_observation_producer(daemon, tmp_path)
    daemon._record_system_observations()
    recent = daemon.runtime_observer.get_recent(limit=200)
    assert not _never_incidents(daemon)
    assert all(
        observation.system_state.get("last_mine_seed_scan") == stamped
        for observation in recent
        if "last_mine_seed_scan" in observation.system_state
    )
    assert not any(
        _cross_agent_idle(observation)
        for observation in recent
        if "last_mine_seed_scan" in observation.system_state
    )
    probe = Observation(
        obs_id="OBS-CROSS-AGENT-PROBE",
        description="cross agent state probe",
        system_state={"last_mine_seed_scan": stamped},
        severity="medium",
        source="test",
        category="gap",
        related_tasks=[],
        task_generated=None,
        auto_generated=True,
        created_at=datetime.now().isoformat(),
    )
    assert _cross_agent_idle(probe) is False

    converter = ObservationToTaskConverter(
        daemon.runtime_observer,
        daemon.task_pool,
        rules=[rule for rule in BUILTIN_RULES if rule.name == "cross_agent_idle"],
    )
    converted = converter.convert()
    assert converted["tasks_created"] == 0
    assert converted["rules_matched"] == 0
    assert daemon.task_pool.list_tasks(limit=10000) == []


@pytest.mark.parametrize(
    ("scan_result", "scanner_error"),
    [
        ({"fetched": False, "new_commits": 0, "tasks_created": 0, "commits": [], "error": "fetch failed"}, None),
        ({"fetched": False, "new_commits": 0, "tasks_created": 0, "commits": [], "error": None}, None),
        (None, RuntimeError("scanner exploded")),
    ],
    ids=["reported-fetch-failure", "fetched-false", "scanner-exception"],
)
def test_failed_scan_preserves_prior_success_and_never_creates_cross_agent_incident(
    tmp_path, monkeypatch, scan_result, scanner_error
):
    daemon = _daemon(tmp_path, monkeypatch, scanner_outcome=scan_result, scanner_error=scanner_error)
    prior = "2026-10-18T12:34:56.123456"
    daemon.state["last_mine_seed_scan"] = prior
    daemon._save_state()

    _run_scanner_lifecycle(daemon)

    assert daemon.state["last_mine_seed_scan"] == prior
    assert daemon._load_state()["last_mine_seed_scan"] == prior
    _prepare_observation_producer(daemon, tmp_path)
    daemon._record_system_observations()
    assert not _never_incidents(daemon)
    probe = Observation(
        obs_id="OBS-CROSS-AGENT-PROBE",
        description="cross agent state probe",
        system_state={"last_mine_seed_scan": "never"},
        severity="medium",
        source="test",
        category="gap",
        related_tasks=[],
        task_generated=None,
        auto_generated=True,
        created_at=datetime.now().isoformat(),
    )
    assert _cross_agent_idle(probe) is True

    fresh = _daemon(
        tmp_path / "fresh",
        monkeypatch,
        scanner_outcome=scan_result,
        scanner_error=scanner_error,
    )
    _prepare_observation_producer(fresh, tmp_path / "fresh")
    fresh._record_system_observations()
    incidents = _never_incidents(fresh)
    assert incidents
    assert _cross_agent_idle(incidents[0]) is True
    assert fresh.task_pool.list_tasks(limit=10000) == []


def test_scanner_exception_does_not_change_existing_never_state(tmp_path, monkeypatch):
    daemon = _daemon(tmp_path, monkeypatch, scanner_error=RuntimeError("fetch exploded"))

    _run_scanner_lifecycle(daemon)

    assert daemon.state.get("last_mine_seed_scan", "never") == "never"
    assert daemon._load_state().get("last_mine_seed_scan", "never") == "never"
    _prepare_observation_producer(daemon, tmp_path)
    daemon._record_system_observations()
    incidents = _never_incidents(daemon)
    assert incidents
    assert _cross_agent_idle(incidents[0]) is True


def test_missing_fetch_flag_is_not_treated_as_success(tmp_path, monkeypatch):
    daemon = _daemon(
        tmp_path,
        monkeypatch,
        scanner_outcome={"new_commits": 0, "tasks_created": 0, "error": None},
    )

    _run_scanner_lifecycle(daemon)

    assert daemon.state.get("last_mine_seed_scan", "never") == "never"
    assert daemon._load_state().get("last_mine_seed_scan", "never") == "never"
