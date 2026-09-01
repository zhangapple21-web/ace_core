import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.file_scanner import FileScanner
from core.fragment_index import FragmentIndex
from core.local_archaeologist import LocalArchaeologist
from core.mine_seed_scanner import MineSeedScanner
from core.task import TaskPool
from core.task_creator import TaskCreator
from core.web_scout import WebScout


def test_archaeology_and_external_producers_use_admission_without_learning_contract():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        fragment = root / "fragment.md"
        fragment.write_text("# R1 structure\n", encoding="utf-8")
        scanner = FileScanner(
            task_pool=pool,
            fragment_index=FragmentIndex(str(root / "fragment_index")),
            scan_roots=[],
        )
        archaeology_task = scanner._create_archaeology_task(fragment)

        assert archaeology_task.outputs["admission"]["source_type"] == "archaeology"
        assert "learning_contract" not in archaeology_task.outputs["admission"]
        assert archaeology_task.outputs["source_file"] == str(fragment)

        scout = WebScout(root, lexicon=None, memory_index=None, task_pool=pool)
        count = scout._maybe_create_task(
            [
                {"full_name": "org/a", "html_url": "https://example.test/a"},
                {"full_name": "org/b", "html_url": "https://example.test/b"},
                {"full_name": "org/c", "html_url": "https://example.test/c"},
            ],
            "github",
        )
        assert count == 1
        external = next(task for task in pool.list_tasks() if task.creator == "web_scout")
        assert external.outputs["admission"]["source_type"] == "external_research"
        assert len(external.outputs["findings"]) == 3


def test_task_creator_maps_internal_candidates_to_governed_sources():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        creator = TaskCreator(task_pool=pool, base_dir=root)
        tasks = creator.create_tasks_from_candidates([
            {
                "type": "lexicon_gap",
                "category": "protocol",
                "task_title": "Fill protocol lexicon gap",
                "priority": "medium",
                "hypothesis": "The category has too few concepts.",
                "tags": ["lexicon"],
            }
        ])

        assert len(tasks) == 1
        task = tasks[0]
        assert task.outputs["admission"]["source_type"] == "system_observation"
        assert task.outputs["candidate_type"] == "lexicon_gap"


def test_local_archaeology_observation_cannot_bypass_independent_evidence_admission():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        mine_seed = MineSeedScanner(str(root / "mine_seed"))
        commit = {"hash": "abc123", "subject": "ordinary finding", "author": "tester"}

        assert mine_seed._create_cross_agent_task(commit, ["finding.md"], pool, {"critical", "high"}) is None
        assert not pool.list_tasks()

        archaeologist = LocalArchaeologist(root, lexicon=None, memory_index=None, task_pool=pool)
        analysis = {
            "missing_structures": ["unabsorbed"],
            "absorption_rate": 0.1,
            "total_structures": 1,
        }
        file_info = {"path": str(root / "record.md"), "category": "考古报告"}
        task = archaeologist._create_absorption_task(
            file_info,
            analysis,
            {"critical", "high"},
        )

        assert task is None
        assert not pool.list_tasks()

        scout = WebScout(root, lexicon=None, memory_index=None, task_pool=pool)
        count = scout._maybe_create_task(
            [
                {"full_name": "org/a", "html_url": "https://example.test/a"},
                {"full_name": "org/b", "html_url": "https://example.test/b"},
                {"full_name": "org/c", "html_url": "https://example.test/c"},
            ],
            "github",
            {"critical", "high"},
        )

        assert count == 0
        assert not pool.list_tasks()


def test_invalid_source_type_is_rejected_before_pool_write():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        admission = {
            "source_type": "invalid_source",
            "source_ref": "bad-1",
            "why_now": "test",
            "evidence": [{"source": "test"}],
            "expected_result": "test",
            "verification_method": "test",
            "risk": "test",
            "estimated_scope": "test",
        }
        try:
            pool.create_task("invalid", creator="producer", admission=admission)
        except ValueError as error:
            assert str(error) == "invalid_task_source_type"
        else:
            raise AssertionError("invalid sources must not enter TaskPool")
        assert not pool.list_tasks()


if __name__ == "__main__":
    test_archaeology_and_external_producers_use_admission_without_learning_contract()
    test_task_creator_maps_internal_candidates_to_governed_sources()
    test_invalid_source_type_is_rejected_before_pool_write()
    print("production admission source checks passed")
