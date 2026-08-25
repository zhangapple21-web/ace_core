import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.task import TaskPool


def admission(source_type, source_ref):
    return {
        "source_type": source_type,
        "source_ref": source_ref,
        "why_now": "Current evidence shows this work is actionable.",
        "evidence": [{"source": source_ref, "detail": "Observed internal signal."}],
        "expected_result": "The recorded gap is resolved or explicitly bounded.",
        "verification_method": "Verify the source signal after task completion.",
        "risk": "Internal maintenance only.",
        "estimated_scope": "single bounded task",
    }


def test_production_task_requires_valid_admission_metadata():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)

        try:
            pool.create_task("Unadmitted production task", creator="file_scanner")
        except ValueError as error:
            assert str(error) == "task_admission_required"
        else:
            raise AssertionError("production task creation must require admission")


def test_admission_persists_required_metadata_for_archaeology_task():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task(
            "Archaeology task",
            creator="file_scanner",
            admission=admission("archaeology", "C:/archive/fragment.md"),
        )

        stored = pool.load_task(task.task_id)
        assert stored.outputs["admission"]["source_type"] == "archaeology"
        assert stored.outputs["admission"]["source_ref"] == "C:/archive/fragment.md"
        assert stored.outputs["admission"]["evidence"]


def test_learning_requires_learning_contract_in_addition_to_admission():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)

        try:
            pool.create_task(
                "Learning task",
                creator="discovery_mode",
                admission=admission("learning", "obs-learning-1"),
            )
        except ValueError as error:
            assert str(error) == "learning_contract_required"
        else:
            raise AssertionError("learning admission must require a learning contract")


def test_same_source_reference_does_not_create_duplicate_task():
    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        first = pool.create_task(
            "Observed runtime gap",
            creator="observation_to_task",
            admission=admission("evidence", "obs-123"),
        )
        second = pool.create_task(
            "Observed runtime gap retry",
            creator="observation_to_task",
            admission=admission("evidence", "obs-123"),
        )

        assert second.task_id == first.task_id
        assert len(pool.list_tasks()) == 1


if __name__ == "__main__":
    test_production_task_requires_valid_admission_metadata()
    test_admission_persists_required_metadata_for_archaeology_task()
    test_learning_requires_learning_contract_in_addition_to_admission()
    test_same_source_reference_does_not_create_duplicate_task()
    print("task admission checks passed")
