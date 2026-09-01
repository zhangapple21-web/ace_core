import json

from core.task import TaskPool
from core.task_creator import TaskCreator


def test_discovery_mode_experience_cannot_create_a_second_self_referential_task(tmp_path):
    pool = TaskPool(str(tmp_path / "task_pool"))
    source = pool.create_task(
        "Observed data gap",
        creator="discovery_mode",
        admission={
            "source_type": "system_observation",
            "source_ref": "test://observation",
            "why_now": "test the self-reference guard",
            "evidence": ["test://evidence"],
            "expected_result": "no recursive task",
            "verification_method": "inspect TaskPool",
            "risk": "none",
            "estimated_scope": "one fixture",
        },
    )
    pool.update_task(source)
    pattern_dir = tmp_path / "09_KNOWLEDGE" / "pattern"
    pattern_dir.mkdir(parents=True)
    (pattern_dir / "EXP-discovery-loop.json").write_text(
        json.dumps(
            {
                "experience_id": "EXP-discovery-loop",
                "source_task_id": source.task_id,
                "conclusion": "A task must not be regenerated from its own deposition.",
            }
        ),
        encoding="utf-8",
    )

    result = TaskCreator(pool, tmp_path).scan_and_create()

    assert result["new_experiences"] == []
    assert result["tasks_created"] == []
