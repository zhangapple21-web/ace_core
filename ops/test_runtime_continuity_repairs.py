import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_legacy_heartbeat_module_fails_closed_before_side_effects():
    module_path = Path(__file__).resolve().parent.parent / "04_PROTOCOLS" / "heartbeat.py"
    spec = importlib.util.spec_from_file_location("legacy_heartbeat", module_path)
    module = importlib.util.module_from_spec(spec)
    with pytest.raises(RuntimeError, match="heartbeat_deprecated"):
        spec.loader.exec_module(module)


def test_daemon_heartbeat_records_its_owner():
    from core.heartbeat import Heartbeat

    with tempfile.TemporaryDirectory() as temp_dir:
        heartbeat = Heartbeat(Path(temp_dir))
        heartbeat.mark_starting(pid=123, run_id="run-1")
        status = heartbeat.beat(reason="startup")
        assert status["owner"] == "ace_daemon"
        assert status["run_id"] == "run-1"


def test_observation_converter_formats_gap_and_error_state_into_tasks():
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from ops.test_support import FixtureTaskPool as TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        observer.record(
            description="lexicon category gap",
            system_state={
                "gap_categories": ["category_one", "category_two", "category_three"],
                "total_concepts": 12,
                "uncategorized": 2,
            },
            severity="medium",
            source="runtime_audit",
            category="gap",
        )
        observer.record(
            description="recent runtime errors",
            system_state={
                "recent_error_count": 4,
                "error_samples": ["module: failure"],
            },
            severity="medium",
            source="runtime_audit",
            category="anomaly",
        )

        result = ObservationToTaskConverter(observer, pool).convert()
        tasks = pool.list_tasks(status="pending", limit=10)

        assert result["tasks_created"] == 2
        assert len(tasks) == 2
        assert any("category_one, category_two, category_three" in task.hypothesis for task in tasks)
        assert any("4" in task.hypothesis for task in tasks)


def test_recurring_identical_lexicon_gap_does_not_expand_taskpool():
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from ops.test_support import FixtureTaskPool as TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        state = {
            "gap_categories": ["stock", "industry", "concept"],
            "total_concepts": 12,
            "uncategorized": 0,
        }
        observer.record("first persistent lexicon gap", state, severity="medium", source="runtime", category="gap")
        first = ObservationToTaskConverter(observer, pool).convert()
        observer.record("same persistent lexicon gap", {**state, "total_concepts": 13}, severity="medium", source="runtime", category="gap")
        second = ObservationToTaskConverter(observer, pool).convert()

        assert first["tasks_created"] == 1
        assert second["tasks_created"] == 0
        assert second["details"][0]["status"] == "semantic_duplicate"
        assert len(pool.list_tasks(status="pending", limit=10)) == 1


def test_recurring_recent_error_does_not_recreate_after_non_convergent_block():
    """A blocked incident remains the canonical task until its error set changes."""
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from ops.test_support import FixtureTaskPool as TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        state = {
            "recent_error_count": 7,
            "error_samples": ["researcher_task: research_lease_renewal_failed"],
        }
        observer.record("first recurring error", state, severity="medium", source="runtime", category="anomaly")
        first = ObservationToTaskConverter(observer, pool).convert()
        task = pool.list_tasks(status="pending", limit=1)[0]
        pool.block_task(task.task_id, "same evidence reached the review limit", actor="test", block_type="manual_gate_blocked")

        observer.record(
            "same recurring error with a new rolling count",
            {**state, "recent_error_count": 9},
            severity="medium",
            source="runtime",
            category="anomaly",
        )
        second = ObservationToTaskConverter(observer, pool).convert()

        assert first["tasks_created"] == 1
        assert second["tasks_created"] == 0
        assert second["semantic_duplicates"] == 1
        assert second["details"][0]["status"] == "semantic_duplicate"
        assert len(pool.list_tasks(status="blocked", limit=10)) == 1


def test_recurring_error_with_new_error_identity_creates_new_task():
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from ops.test_support import FixtureTaskPool as TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        observer.record(
            "first error",
            {"recent_error_count": 4, "error_samples": ["module_a: failure"]},
            severity="medium",
            source="runtime",
            category="anomaly",
        )
        first = ObservationToTaskConverter(observer, pool).convert()
        observer.record(
            "different error",
            {"recent_error_count": 4, "error_samples": ["module_b: failure"]},
            severity="medium",
            source="runtime",
            category="anomaly",
        )
        second = ObservationToTaskConverter(observer, pool).convert()

        assert first["tasks_created"] == 1
        assert second["tasks_created"] == 1
        assert len(pool.list_tasks(status="pending", limit=10)) == 2


def test_taskpool_stats_separate_executable_and_historical_counts():
    from ops.test_support import FixtureTaskPool as TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(str(Path(temp_dir) / "task_pool"))
        first = pool.create_task(
            "pending task",
            hypothesis="h",
            creator="test",
            admission=None,
        )
        archived = pool.create_task(
            "archived task",
            hypothesis="h2",
            creator="test",
            admission=None,
        )
        pool.move_task(archived.task_id, "graveyard", actor="test")
        blocked = pool.create_task(
            "blocked task",
            hypothesis="h3",
            creator="test",
            admission=None,
        )
        pool.block_task(blocked.task_id, "waiting", actor="test")

        stats = pool.get_stats()
        assert stats["total"] == 3
        assert stats["executable"] == 1
        assert stats["blocked"] == 1
        assert stats["historical"] == 1


def test_same_day_lexicon_gap_is_not_repeated_as_daemon_work():
    """A five-minute daemon must not repeatedly run empty lexicon extraction."""
    from datetime import datetime
    from ace_daemon import AceDaemon

    class Lexicon:
        def get_stats(self):
            return {
                "total_concepts": 12,
                "categories": {"stock": 1, "industry": 2, "healthy": 5},
            }

    class MemoryIndex:
        def get_stats(self):
            return {"total": 9}

    daemon = AceDaemon.__new__(AceDaemon)
    daemon.lexicon = Lexicon()
    daemon.memory_index = MemoryIndex()
    daemon.eco_parser = None
    daemon.slice_clusterer = None
    daemon.discover_scan_targets = lambda: []
    today = datetime.now().strftime("%Y-%m-%d")
    daemon.state = {
        "lexicon_gap_attempt": {
            "date": today,
            "signature": ["industry", "stock"],
            "concepts_added": 0,
        }
    }

    decision = daemon.decide_today_task()

    assert [action["type"] for action in decision["actions"]] == ["no_new_discovery"]

    # A materially new category is a new problem identity and remains eligible.
    daemon.lexicon.get_stats = lambda: {
        "total_concepts": 12,
        "categories": {"stock": 1, "industry": 2, "risk": 0, "healthy": 5},
    }
    changed = daemon.decide_today_task()
    assert [action["type"] for action in changed["actions"]] == ["lexicon_gap"]


def test_concept_extraction_excludes_the_daemons_own_cycle_summaries():
    """Telemetry must not become recursive evidence for concept mining."""
    from ace_daemon import AceDaemon

    class MemoryIndex:
        def search(self, limit):
            assert limit == 200
            return [
                {"type": "cycle_summary", "content": "x" * 100},
                {"type": "note", "content": "independent bounded research material " + "y" * 60},
            ]

    class ConceptMiner:
        def __init__(self):
            self.chunks = None

        def batch_mine(self, chunks, **kwargs):
            self.chunks = chunks
            return {"added": 1}

    daemon = AceDaemon.__new__(AceDaemon)
    daemon.memory_index = MemoryIndex()
    daemon.concept_miner = ConceptMiner()

    assert daemon.extract_new_concepts() == 1
    assert daemon.concept_miner.chunks == [
        {"content": "independent bounded research material " + "y" * 60}
    ]


def test_concept_extraction_does_not_run_when_only_cycle_summaries_exist():
    from ace_daemon import AceDaemon

    class MemoryIndex:
        def search(self, limit):
            return [{"type": "cycle_summary", "content": "x" * 100}]

    class ConceptMiner:
        def batch_mine(self, *args, **kwargs):
            raise AssertionError("cycle-summary telemetry must not be mined")

    daemon = AceDaemon.__new__(AceDaemon)
    daemon.memory_index = MemoryIndex()
    daemon.concept_miner = ConceptMiner()

    assert daemon.extract_new_concepts() == 0


def _checkup_state(failed_names, timestamp="2026-10-09T14:47:01", stdout_ok=True):
    """Mirror the production checkup snapshot shape (health probe nests JSON)."""
    inner = {
        "timestamp": timestamp,
        "overall": "error",
        "total_checks": 18,
        "passed": 17,
        "errors": 1,
        "checks": [
            {"name": "dir_core", "passed": True, "severity": "error", "detail": "C:/tmp/ace_core/core"},
            *[
                {"name": name, "passed": False, "severity": "error", "detail": "active=0, blocked=61"}
                for name in failed_names
            ],
        ],
    }
    stdout = json.dumps(inner, ensure_ascii=False) if stdout_ok else "{truncated"
    return {
        "checkup_path": "ops/logs/checkup_history.jsonl",
        "checkup_snapshot": {
            "timestamp": timestamp,
            "checks": {"health": {"returncode": 2, "stdout": stdout}},
            "overall": "error",
        },
    }


def _record_checkup(observer, state, description="patrol failed"):
    observer.record(
        description,
        state,
        severity="high",
        source="checkup_history",
        category="health",
    )


def test_recurring_checkup_error_does_not_recreate_after_non_convergent_block():
    """The hourly patrol failure is one incident, not one task per hour."""
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from ops.test_support import FixtureTaskPool as TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        _record_checkup(observer, _checkup_state(["failing probe"]))
        first = ObservationToTaskConverter(observer, pool).convert()
        task = pool.list_tasks(status="pending", limit=1)[0]
        pool.block_task(task.task_id, "same evidence reached the review limit", actor="test", block_type="manual_gate_blocked")

        # Next hour: new observation id and timestamp, same red probe.
        _record_checkup(
            observer,
            _checkup_state(["failing probe"], timestamp="2026-10-09T15:47:01"),
            description="patrol failed again",
        )
        second = ObservationToTaskConverter(observer, pool).convert()

        assert first["tasks_created"] == 1
        assert second["tasks_created"] == 0
        assert second["semantic_duplicates"] == 1
        assert second["details"][0]["status"] == "semantic_duplicate"
        assert second["details"][0]["existing_task_id"] == task.task_id
        assert len(pool.list_tasks(status="blocked", limit=10)) == 1


def test_checkup_error_with_new_failed_probe_creates_new_task():
    """A different red probe is a different incident and stays visible."""
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from ops.test_support import FixtureTaskPool as TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        _record_checkup(observer, _checkup_state(["probe one"]))
        first = ObservationToTaskConverter(observer, pool).convert()
        _record_checkup(observer, _checkup_state(["probe two"], timestamp="2026-10-09T15:47:01"))
        second = ObservationToTaskConverter(observer, pool).convert()

        assert first["tasks_created"] == 1
        assert second["tasks_created"] == 1
        assert len(pool.list_tasks(status="pending", limit=10)) == 2


def test_checkup_error_with_unreadable_detail_dedups_at_group_level():
    """Truncated probe output still carries its group: one task, not a flood."""
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from ops.test_support import FixtureTaskPool as TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        _record_checkup(observer, _checkup_state(["probe one"], stdout_ok=False))
        first = ObservationToTaskConverter(observer, pool).convert()
        _record_checkup(
            observer,
            _checkup_state(["probe one"], timestamp="2026-10-09T15:47:01", stdout_ok=False),
        )
        second = ObservationToTaskConverter(observer, pool).convert()

        assert first["tasks_created"] == 1
        assert second["tasks_created"] == 0
        assert second["details"][0]["status"] == "semantic_duplicate"


def test_checkup_error_without_determinable_identity_stays_visible():
    """No probe structure at all means no identity: fail open, stay visible."""
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from ops.test_support import FixtureTaskPool as TaskPool

    def _structureless_state(timestamp):
        return {
            "checkup_path": "ops/logs/checkup_history.jsonl",
            "checkup_snapshot": {"timestamp": timestamp, "overall": "error"},
        }

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        _record_checkup(observer, _structureless_state("2026-10-09T14:47:01"))
        first = ObservationToTaskConverter(observer, pool).convert()
        _record_checkup(observer, _structureless_state("2026-10-09T15:47:01"))
        second = ObservationToTaskConverter(observer, pool).convert()

        assert first["tasks_created"] == 1
        assert second["tasks_created"] == 1


def test_compact_and_dump_snapshots_share_one_identity():
    """The 026-class transition: same incident, two snapshot shapes, one task."""
    import json as _json

    from core.observation_to_task import BUILTIN_RULES, ObservationToTaskConverter
    from core.observation import RuntimeObserver
    from ops.test_support import FixtureTaskPool as TaskPool

    rule = next(r for r in BUILTIN_RULES if r.name == "checkup_error")
    failed = ["known_backlog", "stale_ratings"]

    # Legacy shape: raw stdout dump nested in the snapshot.
    inner = {"overall": "warning", "checks": [
        {"name": "ok_probe", "passed": True, "severity": "error", "detail": "x"},
        *[{"name": name, "passed": False, "severity": "warning", "detail": "d"} for name in failed],
    ]}
    dump_state = {
        "checkup_path": "ops/logs/checkup_history.jsonl",
        "checkup_snapshot": {
            "timestamp": "2026-10-09T16:47:01",
            "checks": {"health": {"returncode": 1, "stdout": _json.dumps(inner)}},
            "overall": "error",
        },
    }
    # Compact shape: run_checkup names the failing probes explicitly.
    compact_state = {
        "checkup_path": "ops/logs/checkup_history.jsonl",
        "checkup_snapshot": {
            "timestamp": "2026-10-09T17:47:01",
            "checks": {"health": {
                "overall": "warning", "passed": 18, "warnings": 2, "errors": 0,
                "failed_checks": [{"name": n, "severity": "warning"} for n in failed],
                "returncode": 1,
            }},
            "overall": "error",
        },
    }
    assert (
        ObservationToTaskConverter._semantic_signature(rule, dump_state)
        == ObservationToTaskConverter._semantic_signature(rule, compact_state)
    ) != ""

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        observer.record("dump shape patrol", dump_state, severity="high",
                        source="checkup_history", category="health")
        first = ObservationToTaskConverter(observer, pool).convert()
        observer.record("compact shape patrol", compact_state, severity="high",
                        source="checkup_history", category="health")
        second = ObservationToTaskConverter(observer, pool).convert()

        assert first["tasks_created"] == 1
        assert second["tasks_created"] == 0
        assert second["details"][0]["status"] == "semantic_duplicate"


def test_legacy_checkup_task_without_signature_still_dedups():
    """Tasks filed before signatures existed rejoin dedup via admission evidence."""
    from types import SimpleNamespace

    from core.observation_to_task import BUILTIN_RULES, ObservationToTaskConverter

    rule = next(r for r in BUILTIN_RULES if r.name == "checkup_error")
    state = _checkup_state(["failing probe"])
    legacy_task = SimpleNamespace(outputs={
        "conversion_rule": "checkup_error",
        "admission": {"evidence": [{"system_state": state}]},
    })
    assert (
        ObservationToTaskConverter._task_semantic_signature(legacy_task, rule)
        == ObservationToTaskConverter._semantic_signature(rule, state)
    )
    assert ObservationToTaskConverter._semantic_signature(rule, state) != ""


def test_concept_miner_has_builtin_regex_tokenizer():
    from core.concept_miner import ConceptMiner

    class Lexicon:
        def get_concept(self, name):
            return None

        def list_concepts(self, limit=300):
            return []

    result = ConceptMiner(Lexicon()).mine_concepts(
        "ACE Runtime Continuity " * 10,
        source="runtime_test",
        min_occurrence=2,
        auto_add=False,
    )

    assert result["tokenizer"] == "regex"
    assert result["candidates_considered"] >= 1




