from __future__ import annotations

import json

import pytest

from core.civilization_map_reference import (
    MapObjectRef,
    MapRelation,
    canonical_object_id,
    json_line,
    validate_projection,
)


def test_identity_is_stable_and_path_independent():
    first = canonical_object_id("video", "shot:EP01:001")
    second = canonical_object_id("video", "shot:EP01:001")
    assert first == second
    assert "C:" not in first
    assert "D:" not in first


def test_map_reference_keeps_external_authority_and_capability():
    object_id = canonical_object_id("taskpool", "RQ-20260928-001")
    ref = MapObjectRef(
        object_id=object_id,
        namespace="taskpool",
        local_identity="RQ-20260928-001",
        world="ace-core-runtime",
        authority="C:/tmp/ace_core/task_pool",
        source="task_pool/RQ-20260928-001.json",
        state="current",
        capability_addresses=("capability:validation",),
    )
    assert ref.to_dict()["authority"].endswith("task_pool")
    assert ref.to_dict()["capability_addresses"] == ["capability:validation"]


def test_projection_must_point_back_to_authority():
    authority_id = canonical_object_id("video", "shot:EP01:001")
    projection_id = canonical_object_id("public", "shot:EP01:001")
    projection = MapObjectRef(
        object_id=projection_id,
        namespace="public",
        local_identity="shot:EP01:001",
        world="tinghe-archive",
        authority="ace-video-kingdom/research/original_desk",
        role="projection",
        state="current",
        lineage=(authority_id,),
    )
    validate_projection(projection, authority_id)

    broken = MapObjectRef(
        object_id=projection_id,
        namespace="public",
        local_identity="shot:EP01:001",
        world="tinghe-archive",
        authority="ace-video-kingdom/research/original_desk",
        role="projection",
        state="current",
    )
    with pytest.raises(ValueError, match="projection_authority_pointer_required"):
        validate_projection(broken, authority_id)


def test_relations_are_explicit_and_stably_serializable():
    relation = MapRelation(
        from_id="ace:video:source",
        relation="projects",
        to_id="ace:public:projection",
        source="build_tinghe_public_snapshot.py",
    )
    encoded = json_line(relation.to_dict())
    assert json.loads(encoded)["relation"] == "projects"
    assert "source" in encoded


def test_unknown_relation_is_rejected():
    with pytest.raises(ValueError, match="map_relation_invalid"):
        MapRelation("a", "guesses", "b", "unknown")

def _admission(source_ref="obs-123", intent="inspect"):
    return {
        "source_type": "evidence",
        "source_ref": source_ref,
        "operation_intent": intent,
        "why_now": "bounded evidence check",
        "evidence": [{"source": source_ref}],
        "expected_result": "a bounded result",
        "verification_method": "read back the result",
        "risk": "internal",
        "estimated_scope": "small",
    }


def test_taskpool_deduplicates_same_intent_but_not_same_source_only():
    from core.task import TaskPool

    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        first = pool.create_task("Inspect source", admission=_admission())
        same = pool.create_task("Inspect source", admission=_admission())
        different = pool.create_task("Repair source", admission=_admission(intent="repair"))
        assert same.task_id == first.task_id
        assert different.task_id != first.task_id
        assert len(pool.list_tasks()) == 2


def test_taskpool_splits_same_intent_when_payload_changes():
    from core.task import TaskPool

    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        first_admission = _admission(intent="inspect")
        first_admission["payload"] = {"scope": "metadata"}
        second_admission = _admission(intent="inspect")
        second_admission["payload"] = {"scope": "content"}
        first = pool.create_task("Inspect source", admission=first_admission)
        second = pool.create_task("Inspect source", admission=second_admission)
        assert second.task_id != first.task_id
        assert len(pool.list_tasks()) == 2


def test_taskpool_rechecks_all_same_source_intents():
    from core.task import TaskPool

    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        inspect = pool.create_task("Inspect source", admission=_admission(intent="inspect"))
        repair = _admission(intent="repair")
        repair["payload"] = {"scope": "same"}
        repair_retry = _admission(intent="repair")
        repair_retry["payload"] = {"scope": "same"}
        repair = pool.create_task("Repair source", admission=repair)
        repair_retry = pool.create_task("Repair source retry", admission=repair_retry)
        assert repair_retry.task_id == repair.task_id
        assert repair_retry.task_id != inspect.task_id
        assert len(pool.list_tasks()) == 2


def test_taskpool_matches_explicit_identity_across_source_locators():
    from core.task import TaskPool

    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        first_admission = _admission(source_ref="C:/world-a/object.json")
        first_admission["canonical_object_id"] = canonical_object_id("shared", "object-1")
        first_admission["payload"] = {"scope": "same"}
        second_admission = _admission(source_ref="D:/world-b/object.json")
        second_admission["canonical_object_id"] = canonical_object_id("shared", "object-1")
        second_admission["payload"] = {"scope": "same"}
        first = pool.create_task("Inspect object", admission=first_admission)
        second = pool.create_task("Inspect object retry", admission=second_admission)
        assert second.task_id == first.task_id
        assert len(pool.list_tasks()) == 1


def test_taskpool_persists_map_identity_and_intent_fields():
    from core.task import TaskPool

    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        task = pool.create_task("Inspect source", admission=_admission())
        stored = pool.load_task(task.task_id)
        envelope = stored.outputs["admission"]
        assert envelope["canonical_object_id"].startswith("ace:source:evidence:")
        assert envelope["payload_hash"]
        assert envelope["operation_intent"] == "inspect"
        assert envelope["idempotency_token"].startswith("derived:")
