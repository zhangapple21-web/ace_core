"""Attached knowledge has to reach the prompt, or attaching it is decoration.

Also guards the negative half: an unknown task, a non-reuse evidence entry, or a
knowledge entry whose artifact is not really on disk must all produce no hint.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ace_daemon import AceDaemon  # noqa: E402
from core.task import TaskPool  # noqa: E402


def _daemon(root: Path, pool: TaskPool, settings=None):
    return AceDaemon(root, {"runtime": {"knowledge_reuse": settings or {}}})


def _task(pool, evidence):
    task = pool.create_task(
        "reuse subject", creator="test",
        admission={
            "source_type": "archaeology", "source_ref": f"ref-{len(evidence)}",
            "why_now": "reuse", "evidence": [{"source": "s", "risk": "low"}],
            "expected_result": "e", "verification_method": "v",
            "risk": "r", "estimated_scope": "one",
        },
        outputs={},
    )
    task.evidence = list(evidence or [])
    pool.update_task(task)
    return task


def test_reuse_entries_reach_the_prompt_with_citation_instruction():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "task_pool"))
        artifact = "docs/OLD_MAP.md"
        (root / "docs").mkdir()
        (root / artifact).write_text("# old map\n", encoding="utf-8")
        task = _task(pool, [{
            "source": "knowledge_join:file:abc123",
            "archived_task": "RQ-005", "artifact": artifact,
            "identity_key": "file=state.json",
        }])
        daemon = _daemon(root, pool)
        hint = daemon._reuse_hint_for(task.task_id, str(root))
        assert "knowledge_join:file:abc123" in hint
        assert "RQ-005" in hint and artifact in hint
        assert "knowledge_join source id" in hint.lower()
        assert "if none of it applies" in hint.lower()


def test_no_hint_without_reuse_evidence():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "task_pool"))
        task = _task(pool, [{"source": "delivery_verification",
                             "content": "verified_artifact:docs/X:sha"}])
        daemon = _daemon(root, pool)
        assert daemon._reuse_hint_for(task.task_id, str(root)) == ""
        assert daemon._reuse_hint_for("RQ-DOES-NOT-EXIST", str(root)) == ""


def test_missing_artifact_is_not_offered_to_the_worker():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "task_pool"))
        task = _task(pool, [{
            "source": "knowledge_join:file:deadbeef",
            "archived_task": "RQ-151", "artifact": "docs/PHANTOM.md",
            "identity_key": "file=state.json",
        }])
        daemon = _daemon(root, pool)
        assert daemon._reuse_hint_for(task.task_id, str(root)) == ""