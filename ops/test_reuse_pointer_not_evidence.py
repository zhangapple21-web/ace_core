"""Reuse pointers are context, not corroboration.

A knowledge_join entry names where old knowledge came from. If the Validator
counted it, ACE's own archive could stand in for an independent observation —
and it would also move the evidence signature, which can re-open a rework loop
that had already settled.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.task import Task  # noqa: E402
from core.task_roles import Validator, _is_reuse_pointer  # noqa: E402

SOURCE = "knowledge_join:intent:3867ad58d536"


def _task(evidence):
    return Task(task_id="RQ-T", title="t", creator="test", evidence=list(evidence))


def test_reuse_pointers_are_recognised():
    assert _is_reuse_pointer({"source": SOURCE, "artifact": "docs/A.md"})
    assert not _is_reuse_pointer({"source": "inject_target", "content": "x"})
    assert not _is_reuse_pointer("plain string")


def test_reuse_pointer_does_not_raise_the_evidence_count():
    real = [{"source": "admission", "content": "a" * 80}]
    without = Validator._unique_evidence(_task(real))
    with_pointer = Validator._unique_evidence(_task(real + [
        {"source": SOURCE, "kind": "archived_knowledge", "artifact": "docs/A.md"}]))
    assert without == with_pointer


def test_reuse_pointer_does_not_move_the_evidence_signature():
    real = [{"source": "admission", "content": "a" * 80}]
    before = Validator.evidence_signature(_task(real))
    after = Validator.evidence_signature(_task(real + [
        {"source": SOURCE, "kind": "archived_knowledge", "artifact": "docs/A.md"}]))
    assert before == after, "attaching reuse must not re-open a settled rework loop"


def test_reuse_pointer_does_not_inflate_the_quality_score():
    """Two real evidence items plus a reuse pointer must score like the two."""
    import tempfile

    from core.task import TaskPool
    from core.task_roles import Validator as V

    real = [{"source": "admission", "content": "a" * 300},
            {"source": "observation", "content": "b" * 300}]
    with tempfile.TemporaryDirectory() as temp_dir:
        validator = V(task_pool=TaskPool(str(Path(temp_dir) / "pool")))
        base = validator.assess_prospect(_task(real))
        bumped = validator.assess_prospect(_task(real + [{"source": SOURCE}]))
        assert base["prospect_score"] == bumped["prospect_score"]
        assert base["prospect_level"] == bumped["prospect_level"]
        assert V is not None