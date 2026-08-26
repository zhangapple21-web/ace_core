import sys
import tempfile
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_observation_converter_formats_gap_and_error_state_into_tasks():
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

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
    from core.task import TaskPool

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
