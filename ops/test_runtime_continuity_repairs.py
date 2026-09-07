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




