import json
from pathlib import Path

from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.self_evolution import EvolutionSignal, SelfEvolutionCoordinator
from core.task import TaskPool


def test_fuse_requires_cross_source_evidence_and_is_stable(tmp_path):
    coordinator = SelfEvolutionCoordinator(tmp_path / "ace")
    assert coordinator.fuse([
        EvolutionSignal("runtime", "evolution_gap", "主动发现", "缺少入口", 1.0),
    ]) is None

    proposal = coordinator.fuse([
        EvolutionSignal("runtime", "evolution_gap", "主动发现", "缺少入口", 1.0),
        EvolutionSignal("archaeology", "evolution_gap", "主动发现", "历史材料存在入口", 1.1),
    ])
    assert proposal is not None
    assert proposal.route == "self_evolution"
    assert proposal.confidence >= 0.45
    same = coordinator.fuse([
        EvolutionSignal("archaeology", "evolution_gap", "主动发现", "历史材料存在入口", 1.1),
        EvolutionSignal("runtime", "evolution_gap", "主动发现", "缺少入口", 1.0),
    ])
    assert same.fingerprint == proposal.fingerprint


def test_run_cycle_emits_one_observation_and_deduplicates(tmp_path):
    base = tmp_path / "ace"
    (base / "08_ARCHAEOLOGY").mkdir(parents=True)
    (base / "09_KNOWLEDGE").mkdir(parents=True)
    (base / "08_ARCHAEOLOGY" / "主动演化.md").write_text(
        "历史记录：主动发现与自我融合，evolution report。", encoding="utf-8"
    )
    observer = RuntimeObserver(str(base / "06_RUNTIME" / "ace" / "data" / "observations"))
    coordinator = SelfEvolutionCoordinator(base, observer=observer)
    state = {"task_pool": {"by_status": {"review": 5, "pending": 0}}, "recent_error_count": 0}

    first = coordinator.run_cycle(state)
    second = coordinator.run_cycle(state)
    assert first["status"] == "OBSERVED"
    assert second["status"] == "ALREADY_ACTIVE"
    assert len(observer.get_recent(10)) == 1
    assert (base / "09_KNOWLEDGE" / "self_evolution" / "proposals.jsonl").exists()
    record = json.loads((base / "09_KNOWLEDGE" / "self_evolution" / "proposals.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert record["route"] == "self_evolution"

    pool = TaskPool(str(base / "06_RUNTIME" / "ace" / "data" / "tasks"))
    conversion = ObservationToTaskConverter(observer=observer, task_pool=pool).convert()
    assert conversion["tasks_created"] == 1
    assert conversion["details"][0]["rule"] == "discovery_candidate"
