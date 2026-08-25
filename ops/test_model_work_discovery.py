import tempfile
from pathlib import Path

from core.discovery import DiscoveryCandidate, DiscoveryMode
from core.model_work_discovery import ModelWorkDiscovery
from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.stock_discovery_sources import StockDiscoverySources
from core.task import TaskPool
from core.task_roles import Researcher


def _candidate(fingerprint="real-model-work", evidence=None):
    evidence = evidence if evidence is not None else [
        {"source_ref": "benchmark.json#source-a", "content": "measured failure A"},
        {"source_ref": "provider.json#source-b", "content": "independent failure B"},
    ]
    return DiscoveryCandidate(
        fingerprint=fingerprint,
        title="Investigate measured cross-source disagreement",
        description="Two independent production artifacts disagree.",
        reason="The disagreement is unresolved and affects a production boundary.",
        objective="Explain the disagreement and identify its invalidating conditions.",
        completion_criteria="Produce a bounded explanation with counter-evidence.",
        verification_method="Re-run both measurements and compare their hashes.",
        metadata={"autonomous_maintenance": {
            "why_now": "Two current independent artifacts disagree.",
            "evidence": evidence,
            "priority": "high",
            "expected_result": "A falsifiable explanation of the disagreement.",
            "verification_method": "Re-run both independent measurements.",
            "risk": "Research only; no production mutation or external send.",
            "source": "system_review",
            "estimated_scope": "The two cited artifacts only.",
        }},
    )


def _runtime(root, source, evidence_revision_provider=None):
    pool = TaskPool(str(root / "task_pool"))
    observer = RuntimeObserver(str(root / "observations"))
    discovery = DiscoveryMode(
        pool,
        observer,
        str(root),
        candidate_sources=[source],
        include_repository_gap=False,
    )
    coordinator = ModelWorkDiscovery(
        discovery,
        str(root / "model_work_discovery_latest.json"),
        evidence_revision_provider=evidence_revision_provider,
    )
    return pool, observer, coordinator


def test_local_pending_does_not_suppress_daily_model_work():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pool, observer, coordinator = _runtime(root, lambda: [_candidate()])
        pool.create_task(
            title="Existing local archaeology",
            priority="high",
            creator="test",
            tags=["archaeology", "local_evidence_only"],
        )

        report = coordinator.discover_daily(day="2026-08-25")
        assert report["outcome"] == "MODEL_WORK_CANDIDATE_OBSERVED"
        converted = ObservationToTaskConverter(observer, pool).convert()
        assert converted["reasoning_tasks_created"] == 1


def test_daily_discovery_is_bounded_and_fingerprint_is_not_recreated():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        calls = []

        def source():
            calls.append(True)
            return [_candidate()]

        pool, observer, coordinator = _runtime(root, source)
        first = coordinator.discover_daily(day="2026-08-25")
        second = coordinator.discover_daily(day="2026-08-25")
        assert first["outcome"] == "MODEL_WORK_CANDIDATE_OBSERVED"
        assert first["candidate_observation_cap"] == 1
        assert "candidate_creation_quota" not in first
        assert second["outcome"] == "ALREADY_DISCOVERED_TODAY"
        assert len(calls) == 1

        ObservationToTaskConverter(observer, pool).convert()
        next_day = coordinator.discover_daily(day="2026-08-26")
        assert next_day["outcome"] == "NO_VALID_MODEL_WORK"
        assert len(pool.list_tasks(status="pending")) == 1


def test_same_day_same_evidence_revision_is_bounded():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        calls = []

        def source():
            calls.append(True)
            return [_candidate()]

        pool, observer, coordinator = _runtime(
            root,
            source,
            evidence_revision_provider=lambda: {
                "revision": "revision-a",
                "observed_at": "2026-08-25T01:00:00+00:00",
            },
        )
        first = coordinator.discover_daily(day="2026-08-25")
        second = coordinator.discover_daily(day="2026-08-25")

        assert first["evidence_revision"] == "revision-a"
        assert second["status"] == "not_run"
        assert second["outcome"] == "ALREADY_DISCOVERED_FOR_EVIDENCE_REVISION"
        assert len(calls) == 1


def test_same_day_changed_evidence_revision_allows_rediscovery():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        calls = []
        revision = {"value": "revision-a"}

        def source():
            calls.append(True)
            return [_candidate(fingerprint=f"candidate-{len(calls)}")]

        _, _, coordinator = _runtime(
            root,
            source,
            evidence_revision_provider=lambda: {
                "revision": revision["value"],
                "observed_at": "2026-08-25T02:00:00+00:00",
            },
        )
        first = coordinator.discover_daily(day="2026-08-25")
        revision["value"] = "revision-b"
        second = coordinator.discover_daily(day="2026-08-25")

        assert first["evidence_revision"] == "revision-a"
        assert second["evidence_revision"] == "revision-b"
        assert second["previous_evidence_revision"] == "revision-a"
        assert second["rediscovery_reason"] == "evidence_revision_changed"
        assert len(calls) == 2


def test_legacy_same_day_report_rechecks_once_for_newer_evidence():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        calls = []

        def source():
            calls.append(True)
            return []

        _, _, coordinator = _runtime(
            root,
            source,
            evidence_revision_provider=lambda: {
                "revision": "revision-new",
                "observed_at": "2026-08-25T12:57:05+00:00",
            },
        )
        coordinator._write_report({
            "discovery_date": "2026-08-25",
            "recorded_at": "2026-08-25T02:49:10+00:00",
            "outcome": "NO_VALID_MODEL_WORK",
        })

        migrated = coordinator.discover_daily(day="2026-08-25")
        bounded = coordinator.discover_daily(day="2026-08-25")

        assert migrated["evidence_revision"] == "revision-new"
        assert migrated["rediscovery_reason"] == "new_evidence_after_legacy_report"
        assert bounded["outcome"] == "ALREADY_DISCOVERED_FOR_EVIDENCE_REVISION"
        assert len(calls) == 1


def test_changed_revision_does_not_recreate_same_candidate_fingerprint():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        revision = {"value": "revision-a"}
        pool, observer, coordinator = _runtime(
            root,
            lambda: [_candidate()],
            evidence_revision_provider=lambda: {
                "revision": revision["value"],
                "observed_at": "2026-08-25T12:57:05+00:00",
            },
        )
        assert coordinator.discover_daily(day="2026-08-25")["outcome"] == "MODEL_WORK_CANDIDATE_OBSERVED"
        ObservationToTaskConverter(observer, pool).convert()
        revision["value"] = "revision-b"

        rediscovered = coordinator.discover_daily(day="2026-08-25")

        assert rediscovered["outcome"] == "NO_VALID_MODEL_WORK"
        assert len(pool.list_tasks(status="pending")) == 1


def test_evidence_revision_failure_fails_closed_to_daily_boundary():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        calls = []

        def source():
            calls.append(True)
            return []

        def broken_revision():
            raise OSError("revision source unavailable")

        _, _, coordinator = _runtime(
            root,
            source,
            evidence_revision_provider=broken_revision,
        )
        first = coordinator.discover_daily(day="2026-08-25")
        second = coordinator.discover_daily(day="2026-08-25")

        assert first["evidence_revision"] is None
        assert second["outcome"] == "ALREADY_DISCOVERED_TODAY"
        assert len(calls) == 1


def test_stock_evidence_revision_is_content_stable_and_changes_with_benchmark():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        evidence_dir = root / "evidence"
        evidence_dir.mkdir()
        benchmark = evidence_dir / "stock_data_benchmark_latest.json"
        benchmark.write_text(
            '{"completed_at":"2026-08-25T12:57:05+00:00","summary":{"sources":{"sina":{"availability":0.8}}}}',
            encoding="utf-8",
        )
        observer = RuntimeObserver(str(root / "observations"))
        sources = StockDiscoverySources(
            observer,
            str(root),
            evidence_dir=str(evidence_dir),
        )

        first = sources.evidence_revision()
        second = sources.evidence_revision()
        benchmark.write_text(
            '{"completed_at":"2026-08-25T13:10:00+00:00","summary":{"sources":{"sina":{"availability":0.9}}}}',
            encoding="utf-8",
        )
        changed = sources.evidence_revision()

        assert first == second
        assert first["observed_at"] == "2026-08-25T12:57:05+00:00"
        assert changed["revision"] != first["revision"]
        assert changed["observed_at"] == "2026-08-25T13:10:00+00:00"


def test_no_candidate_records_no_valid_model_work_without_task_side_effects():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pool, observer, coordinator = _runtime(root, lambda: [])
        report = coordinator.discover_daily(day="2026-08-25")
        assert report["outcome"] == "NO_VALID_MODEL_WORK"
        assert not observer.get_recent(limit=10)
        assert not pool.list_tasks(limit=10)


def test_admission_funnel_is_persisted_without_changing_decisions():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pool, observer, coordinator = _runtime(root, lambda: [_candidate()])
        coordinator.discover_daily(day="2026-08-25")
        conversion = ObservationToTaskConverter(observer, pool).convert()

        funnel = coordinator.record_admission(conversion)
        assert funnel == {
            "candidate_count": 1,
            "eligible_count": 1,
            "rejected_count": 0,
            "reasoning_tasks_created": 1,
            "model_tasks_created": 1,
            "task_types_created": {"reasoning": 1},
            "rejection_reasons": {},
        }
        persisted = coordinator._read_report()
        assert persisted["admission_funnel"] == funnel
        assert coordinator.record_admission({"candidate_count": 0}) == funnel
        persisted["admission_funnel"] = {"candidate_count": 0}
        coordinator._write_report(persisted)
        recovered = coordinator.record_admission({"candidate_count": 0})
        assert recovered["eligible_count"] == 1
        assert recovered["recovered_from_task_id"]


def test_one_evidence_reference_is_observed_but_not_admitted():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pool, observer, coordinator = _runtime(
            root,
            lambda: [_candidate(evidence=[{"source_ref": "same.json#only"}])],
        )
        assert coordinator.discover_daily(day="2026-08-25")["outcome"] == "MODEL_WORK_CANDIDATE_OBSERVED"
        converted = ObservationToTaskConverter(observer, pool).convert()
        assert converted["tasks_created"] == 0
        assert converted["rejection_reasons"] == {"independent_evidence_required": 1}


def test_candidate_without_evidence_is_observed_then_rejected_by_admission():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        pool, observer, coordinator = _runtime(
            root,
            lambda: [_candidate(evidence=[])],
        )

        report = coordinator.discover_daily(day="2026-08-25")
        assert report["outcome"] == "MODEL_WORK_CANDIDATE_OBSERVED"

        converted = ObservationToTaskConverter(observer, pool).convert()
        assert converted["candidate_count"] == 1
        assert converted["eligible_count"] == 0
        assert converted["tasks_created"] == 0
        assert converted["rejection_reasons"] == {
            "independent_evidence_required": 1,
        }
        assert not pool.list_tasks(limit=10)


def test_duplicate_evidence_references_count_as_one():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        duplicate = [
            {"source_ref": "same.json#same", "content": "first rendering"},
            {"source_ref": "same.json#same", "content": "duplicate rendering"},
        ]
        pool, observer, coordinator = _runtime(
            root,
            lambda: [_candidate(evidence=duplicate)],
        )
        coordinator.discover_daily(day="2026-08-25")
        converted = ObservationToTaskConverter(observer, pool).convert()
        assert converted["tasks_created"] == 0
        assert converted["rejection_reasons"] == {"independent_evidence_required": 1}


def test_admitted_model_work_is_visible_beyond_one_hundred_rework_tasks():
    with tempfile.TemporaryDirectory() as directory:
        pool = TaskPool(str(Path(directory) / "task_pool"))
        for index in range(101):
            task = pool.create_task(
                title=f"Old local rework {index}",
                priority="high",
                creator="test",
                tags=["archaeology"],
            )
            task.last_claimed_at = "2026-08-24T00:00:00"
            task.rework_count = 1
            task.consecutive_rework_claims = 2
            task.outputs["last_validator_result"] = {"outcome": "rework_pending"}
            pool.update_task(task)

        model_task = pool.create_task(
            title="Admitted model work",
            priority="high",
            creator="discovery_mode",
            tags=["task_type:reasoning"],
            admission={
                "source_type": "maintenance",
                "source_ref": "discovery:model-work",
                "why_now": "Independent evidence identifies unresolved model work.",
                "evidence": [
                    {"source_ref": "runtime:a", "content": "measured A"},
                    {"source_ref": "benchmark:b", "content": "measured B"},
                ],
                "expected_result": "A falsifiable explanation.",
                "verification_method": "Re-run both measurements.",
                "risk": "Research only.",
                "estimated_scope": "The cited evidence only.",
            },
            outputs={
                "discovery": {"task_type": "reasoning"},
                "model_task_admission": {
                    "eligible": True,
                    "classification": "reasoning",
                },
            },
        )

        claimed = Researcher(task_pool=pool).pick_up_task(priority="any")
        assert claimed is not None
        assert claimed.task_id == model_task.task_id


def test_researcher_preserves_admission_evidence_and_grounds_model_prompt():
    class RecordingRouter:
        def __init__(self):
            self.messages = []

        def chat(self, *, messages, **kwargs):
            self.messages = messages
            return {
                "success": True,
                "content": "Evidence A and B disagree; re-run both before changing roles.",
                "provider": "nim",
                "model": "nvidia/nemotron-3-ultra-550b-a55b",
                "tried_models": ["nim:nvidia/nemotron-3-ultra-550b-a55b"],
                "latency_ms": 1,
            }

    with tempfile.TemporaryDirectory() as directory:
        pool = TaskPool(str(Path(directory) / "task_pool"))
        candidate = _candidate().metadata["autonomous_maintenance"]
        task = pool.create_task(
            title="Grounded model research",
            hypothesis="Explain the measured disagreement.",
            priority="high",
            creator="discovery_mode",
            tags=["task_type:reasoning"],
            admission={
                "source_type": "maintenance",
                "source_ref": "discovery:grounded",
                "why_now": candidate["why_now"],
                "evidence": candidate["evidence"],
                "expected_result": candidate["expected_result"],
                "verification_method": candidate["verification_method"],
                "risk": candidate["risk"],
                "estimated_scope": candidate["estimated_scope"],
            },
            outputs={
                "discovery": {"task_type": "reasoning"},
                "model_task_admission": {
                    "eligible": True,
                    "classification": "reasoning",
                },
            },
        )
        claimed = pool.claim_task(task.task_id, "researcher")
        router = RecordingRouter()
        Researcher(task_pool=pool, llm_router=router).research_task(claimed)

        reviewed = pool.load_task(task.task_id)
        assert reviewed.status == "review"
        assert {item["source"] for item in reviewed.evidence} == {
            "benchmark.json#source-a",
            "provider.json#source-b",
        }
        prompt = router.messages[0]["content"]
        assert "benchmark.json#source-a" in prompt
        assert "provider.json#source-b" in prompt
        assert reviewed.outputs["model_research_result"]["content"].startswith(
            "Evidence A and B disagree"
        )


def test_claimed_model_rework_is_visible_beyond_old_rework_page():
    with tempfile.TemporaryDirectory() as directory:
        pool = TaskPool(str(Path(directory) / "task_pool"))
        for index in range(101):
            task = pool.create_task(
                title=f"Old rework {index}",
                priority="high",
                creator="test",
                tags=["archaeology"],
            )
            task.last_claimed_at = "2026-08-24T00:00:00"
            task.rework_count = 2
            task.consecutive_rework_claims = 2
            task.outputs["last_validator_result"] = {"outcome": "rework_pending"}
            pool.update_task(task)

        model_task = pool.create_task(
            title="Claimed model rework",
            priority="high",
            creator="discovery_mode",
            tags=["task_type:reasoning"],
            admission={
                "source_type": "maintenance",
                "source_ref": "discovery:claimed-model",
                "why_now": "Independent evidence identifies unresolved model work.",
                "evidence": [
                    {"source_ref": "runtime:a", "content": "measured A"},
                    {"source_ref": "benchmark:b", "content": "measured B"},
                ],
                "expected_result": "A falsifiable explanation.",
                "verification_method": "Re-run both measurements.",
                "risk": "Research only.",
                "estimated_scope": "The cited evidence only.",
            },
            outputs={
                "discovery": {"task_type": "reasoning"},
                "model_task_admission": {
                    "eligible": True,
                    "classification": "reasoning",
                },
            },
        )
        claimed = pool.claim_task(model_task.task_id, "researcher")
        pool.move_task(claimed.task_id, "review", actor="researcher", task=claimed)
        reviewed = pool.load_task(claimed.task_id)
        reviewed.outputs["last_validator_result"] = {"outcome": "rework_pending"}
        reviewed.consecutive_rework_claims = 2
        pool.update_task(reviewed)
        pool.move_task(
            claimed.task_id,
            "pending",
            actor="validator",
            reason="validator_rework_pending",
            task=pool.load_task(claimed.task_id),
        )
        selected = Researcher(task_pool=pool).pick_up_task(priority="any")
        assert selected is not None
        assert selected.task_id == model_task.task_id
