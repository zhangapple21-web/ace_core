import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.discovery import DiscoveryCandidate, DiscoveryMode
from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.task import TaskPool


def maintenance_candidate(task_type="reasoning", metadata=None):
    contract = {
        "why_now": "A reproducible runtime audit gap is ready for dispatch.",
        "evidence": [
            {
                "source": "runtime_audit",
                "source_ref": "runtime:health-1",
                "detail": "bounded runtime gap",
            },
            {
                "source": "incident_archive",
                "source_ref": "archive:incident-9",
                "detail": "independent unresolved incident",
            },
        ],
        "priority": "high",
        "expected_result": "A governed maintenance task is persisted.",
        "verification_method": "Inspect the persisted task metadata.",
        "risk": "Metadata-only task creation.",
        "source": "runtime_audit",
        "estimated_scope": "one converter path",
    }
    return DiscoveryCandidate(
        fingerprint=f"admission-maintenance-{task_type}-{bool(metadata)}",
        title="Persist discovery admission",
        description="A runtime audit identified a bounded maintenance gap.",
        reason="The runtime audit has reproducible evidence and no viable work exists.",
        objective="What explains the bounded runtime gap?",
        completion_criteria="The task contains the complete admission record.",
        verification_method="Inspect the persisted task metadata.",
        task_type=task_type,
        metadata={"autonomous_maintenance": contract, **(metadata or {})},
    )


def convert_candidate(candidate):
    temp_dir = tempfile.TemporaryDirectory()
    root = Path(temp_dir.name)
    task_pool = TaskPool(str(root / "pool"))
    observer = RuntimeObserver(str(root / "observations"))
    discovery = DiscoveryMode(
        task_pool=task_pool,
        observer=observer,
        base_dir=str(root),
        candidate_sources=[lambda: [candidate]],
    )
    converter = ObservationToTaskConverter(observer, task_pool)
    assert discovery.discover()["status"] == "observed"
    return temp_dir, task_pool, converter.convert()


def test_qualified_discovery_task_is_admitted_as_reasoning_and_persisted():
    temp_dir, task_pool, result = convert_candidate(maintenance_candidate())
    try:
        assert result["tasks_created"] == 1
        assert result["candidate_count"] == 1
        assert result["eligible_count"] == 1
        assert result["reasoning_tasks_created"] == 1

        task = task_pool.list_tasks(status="pending", limit=1)[0]
        admission = task.outputs["admission"]
        decision = task.outputs["model_task_admission"]
        assert admission["source_type"] == "maintenance"
        assert admission["source_ref"] == "admission-maintenance-reasoning-False"
        assert len(admission["evidence"]) == 2
        assert "task_type:reasoning" in task.tags
        assert decision["eligible"] is True
        assert decision["classification"] == "reasoning"
        assert decision["evidence_refs"] == ["runtime:health-1", "archive:incident-9"]
        assert task.outputs["discovery"]["fingerprint"] == "admission-maintenance-reasoning-False"
        assert task.outputs["source_obs_id"]
    finally:
        temp_dir.cleanup()


def test_discovery_route_metadata_does_not_reject_qualified_reasoning_candidate():
    temp_dir, task_pool, result = convert_candidate(maintenance_candidate(metadata={
        "route": {"mode": "local_evidence_only"},
    }))
    try:
        assert result["tasks_created"] == 1
        assert task_pool.list_tasks(status="pending", limit=1)[0].outputs["model_task_admission"]["eligible"] is True
    finally:
        temp_dir.cleanup()


def test_single_source_discovery_candidate_creates_no_model_task():
    candidate = maintenance_candidate()
    candidate.metadata["autonomous_maintenance"]["evidence"] = candidate.metadata["autonomous_maintenance"]["evidence"][:1]

    temp_dir, task_pool, result = convert_candidate(candidate)
    try:
        assert result["tasks_created"] == 0
        assert result["candidate_count"] == 1
        assert result["rejected_count"] == 1
        assert result["outcome"] == "NO_VALID_MODEL_TASK_TARGET"
        assert result["rejection_reasons"] == {"independent_evidence_required": 1}
        assert task_pool.list_tasks(status="pending", limit=10) == []
    finally:
        temp_dir.cleanup()


def test_explicit_local_only_discovery_candidate_creates_no_model_task():
    temp_dir, task_pool, result = convert_candidate(maintenance_candidate(metadata={
        "local_evidence_only": True,
    }))
    try:
        assert result["tasks_created"] == 0
        assert result["rejection_reasons"] == {"local_evidence_only": 1}
        assert task_pool.list_tasks(status="pending", limit=10) == []
    finally:
        temp_dir.cleanup()


def test_non_reasoning_discovery_candidate_is_rejected_without_relabeling():
    for task_type in ("strategic", "execution"):
        temp_dir, task_pool, result = convert_candidate(maintenance_candidate(task_type=task_type))
        try:
            assert result["tasks_created"] == 0
            assert result["rejection_reasons"] == {"model_role_contract_required": 1}
            assert task_pool.list_tasks(status="pending", limit=10) == []
        finally:
            temp_dir.cleanup()
