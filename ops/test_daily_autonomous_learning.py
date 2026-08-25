#!/usr/bin/env python3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.daily_learning import DailyLearningLoop
from core.discovery import DiscoveryCandidate, DiscoveryMode
from core.governance.evidence_registry import EvidenceRegistry
from core.governance.knowledge_governor import Governor
from core.governance.knowledge_lifecycle import LifecycleManager
from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.task import TaskPool


CONTRACT = {
    "why_learn": "A verified gap can otherwise recur.",
    "learning_objective": "Establish the boundary from available evidence.",
    "required_evidence": ["two independent primary facts"],
    "mastery_criteria": ["governed conclusion records both evidence identifiers"],
}


def candidate(fingerprint, title, contract=CONTRACT):
    return DiscoveryCandidate(
        fingerprint=fingerprint,
        title=title,
        description=f"Evidence-backed learning observation for {title}.",
        reason="A runtime fact exposes a concrete knowledge gap.",
        objective=contract.get("learning_objective", "missing objective"),
        completion_criteria="The learning result is governed and archived.",
        verification_method="Inspect registry, lifecycle, and daily result.",
        candidate_source="runtime_gap",
        metadata={"learning": contract},
    )


def evidence(content, group, tier="official", directness="primary"):
    return {
        "source": "fixture",
        "content": content,
        "confidence": 0.95,
        "author": group,
        "source_location": f"fixture://{group}",
        "metadata": {
            "source_tier": tier,
            "publisher": group,
            "upstream_identity": group,
            "independence_group": group,
            "directness": directness,
            "retrieval_method": "fixture",
            "cross_validation_source": "local" if group.startswith("internal") else "external",
        },
    }


def learning_evidence(prefix):
    return [
        evidence(f"{prefix}: first independent runtime fact.", f"{prefix}-a"),
        evidence(f"{prefix}: second independent runtime fact.", f"{prefix}-b"),
    ]


def make_loop(root, internal_sources, external_discoverer=None):
    task_pool = TaskPool(str(root / "task_pool"))
    observer = RuntimeObserver(str(root / "observations"))
    converter = ObservationToTaskConverter(observer=observer, task_pool=task_pool)
    discovery = DiscoveryMode(
        task_pool=task_pool,
        observer=observer,
        base_dir=str(root),
        candidate_sources=[],
        include_repository_gap=False,
    )
    return DailyLearningLoop(
        data_dir=str(root / "daily_learning"),
        discovery=discovery,
        converter=converter,
        task_pool=task_pool,
        evidence_registry=EvidenceRegistry(str(root / "governance")),
        knowledge_governor=Governor(str(root / "runtime")),
        lifecycle_manager=LifecycleManager(str(root / "governance" / "lifecycle.jsonl")),
        internal_candidate_sources=internal_sources,
        external_discoverer=external_discoverer,
    )


def main():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        external_calls = []

        internal_day1 = candidate("day-1-runtime-gap", "Learn runtime failure boundary")
        loop = make_loop(
            root,
            internal_sources=[lambda: [(internal_day1, learning_evidence("day-1"))]],
            external_discoverer=lambda objective, tiers: external_calls.append((objective, tiers)) or [],
        )
        day1 = loop.run("2026-08-20")
        assert day1["mode"] == "internal"
        assert day1["outcome"] == "adopt"
        assert day1["task_id"]
        adopted_task = loop.task_pool.load_task(day1["task_id"])
        assert adopted_task.status == "archived"
        assert adopted_task.guardian_decision in {"axiom", "constraint", "experience"}
        assert any(
            event.get("to") == "active"
            and event.get("actor") == "daily_learning"
            and event.get("reason") == "lease_claimed"
            for event in adopted_task.audit_log
        )
        assert day1["no_side_effects"] is False
        assert not external_calls

        external_day2 = candidate("day-2-external-learning", "Learn evidence metadata discipline")
        loop.internal_candidate_sources = [lambda: []]
        loop.external_discoverer = lambda objective, tiers: external_calls.append((objective, tiers)) or [
            (external_day2, [
                evidence("Primary documentation defines evidence metadata.", "official-a"),
                evidence("Independent technical record confirms metadata semantics.", "official-b", "technical_primary"),
            ])
        ]
        day2 = loop.run("2026-08-21")
        assert day2["mode"] == "external"
        assert day2["outcome"] == "adopt"
        assert len(external_calls) == 1

        duplicate = candidate("day-3-duplicate", "Learn evidence metadata discipline")
        loop.internal_candidate_sources = [lambda: [(duplicate, [
            evidence("Primary documentation defines evidence metadata.", "duplicate-a"),
            evidence("Independent technical record confirms metadata semantics.", "duplicate-b", "technical_primary"),
        ])]]
        day3 = loop.run("2026-08-22")
        assert day3["outcome"] in {"observe", "reject"}
        assert day3["outcome"] != "adopt"

        weak_external = candidate("day-4-insufficient", "Learn unverified external claim")
        loop.internal_candidate_sources = [lambda: []]
        loop.external_discoverer = lambda objective, tiers: [
            (weak_external, [
                evidence("Search result snippet only.", "same-upstream", directness="search_result"),
                evidence("Repost of one upstream statement.", "same-upstream", directness="repost"),
                evidence("Wrapper repeats same upstream statement.", "same-upstream"),
            ])
        ]
        day4 = loop.run("2026-08-23")
        assert day4["outcome"] in {"observe", "reject"}
        assert day4["outcome"] != "adopt"
        assert day4["source_independence"]["independent_count"] == 1

        resumed_candidate = candidate("day-5-resumable", "Resume interrupted learning")
        loop.internal_candidate_sources = [lambda: [(resumed_candidate, learning_evidence("resume"))]]
        original_register_evidence = loop._register_evidence
        loop._register_evidence = lambda items: (_ for _ in ()).throw(RuntimeError("simulated_interruption"))
        try:
            loop.run("2026-08-25")
        except RuntimeError as error:
            assert str(error) == "simulated_interruption"
        else:
            raise AssertionError("interrupted learning run must propagate its failure")
        loop._register_evidence = original_register_evidence
        interrupted_task_count = len(loop.task_pool.list_tasks())
        resumed = loop.run("2026-08-25")
        assert resumed["outcome"] == "adopt"
        assert len(loop.task_pool.list_tasks()) == interrupted_task_count

        loop.internal_candidate_sources = [lambda: []]
        loop.external_discoverer = lambda objective, tiers: []
        no_target = loop.run("2026-08-24")
        assert no_target["outcome"] == "NO_VALID_LEARNING_TARGET"
        assert loop.run("2026-08-24") == no_target

        medium_root = root / "medium_backlog"
        medium_candidate = candidate("medium-backlog-learning", "Learn despite maintenance backlog")
        medium_loop = make_loop(
            medium_root,
            internal_sources=[lambda: [(medium_candidate, learning_evidence("medium-backlog"))]],
        )
        medium_loop.task_pool.create_task(
            title="Routine maintenance backlog",
            creator="test",
            priority="medium",
        )
        medium_result = medium_loop.run("2026-08-26")
        assert medium_result["outcome"] == "adopt"
        medium_task = medium_loop.task_pool.load_task(medium_result["task_id"])
        assert medium_task.outputs["admission"]["source_type"] == "learning"
        assert medium_task.outputs["admission"]["source_ref"] == "medium-backlog-learning"
        assert medium_task.outputs["admission"]["learning_contract"] == CONTRACT

        high_root = root / "high_backlog"
        high_candidate = candidate("high-backlog-learning", "Defer to high priority work")
        high_loop = make_loop(
            high_root,
            internal_sources=[lambda: [(high_candidate, learning_evidence("high-backlog"))]],
        )
        high_loop.task_pool.create_task(
            title="Blocking high priority work",
            creator="test",
            priority="high",
        )
        high_result = high_loop.run("2026-08-27")
        assert high_result["outcome"] == "adopt"
        assert high_result["execution_deferred_by"]
        assert high_loop.task_pool.list_tasks(status="pending", priority="high")
        assert len(high_loop.task_pool.list_tasks()) == 2

        lifecycle = loop.lifecycle_manager.get("day-1-runtime-gap")
        assert lifecycle is not None
        history = lifecycle.stage_history
        restarted_manager = LifecycleManager(str(root / "governance" / "lifecycle.jsonl"))
        restored = restarted_manager.get("day-1-runtime-gap")
        assert restored is not None
        assert restored.stage_history == history

        source = (Path(__file__).resolve().parent.parent / "core" / "daily_learning.py").read_text(encoding="utf-8")
        for forbidden in ("tg_notifier", "stock_data_reliability", "AUTO_RUN", "AUTO_PUSH"):
            assert forbidden not in source

    print("daily autonomous learning simulation passed")


if __name__ == "__main__":
    main()
