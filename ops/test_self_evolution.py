import json
from pathlib import Path

from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.self_evolution import EvolutionSignal, SelfEvolutionCoordinator
from core.task import TaskPool


def test_fuse_accepts_one_specific_source_and_does_not_collapse_theme(tmp_path):
    coordinator = SelfEvolutionCoordinator(tmp_path / "ace")
    proposal = coordinator.fuse([
        EvolutionSignal("archaeology", "drawer_item", "R1/认知路由", "旧报告", 1.0, "r1.md"),
    ])
    assert proposal is not None
    other = coordinator.fuse([
        EvolutionSignal("r1", "drawer_item", "R1/另一份日志", "另一份", 1.0, "other.md"),
    ])
    assert other.fingerprint != proposal.fingerprint

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

def test_archived_linked_task_releases_fingerprint_and_does_not_reopen_it(tmp_path):
    base = tmp_path / "ace"
    coordinator = SelfEvolutionCoordinator(base)
    signals = [
        EvolutionSignal("runtime", "evolution_gap", "主动发现", "缺少入口", 1.0),
        EvolutionSignal("archaeology", "evolution_gap", "主动发现", "历史材料存在入口", 1.1),
    ]
    proposal = coordinator.fuse(signals)
    task_id = "RQ-test"
    (base / "task_pool" / "archived").mkdir(parents=True)
    (base / "task_pool" / "archived" / f"{task_id}.json").write_text("{}", encoding="utf-8")
    closed = base / "06_RUNTIME" / "ace" / "data" / "closed_loop"
    closed.mkdir(parents=True)
    (closed / "background_state.json").write_text(json.dumps({
        "last_fingerprint": proposal.fingerprint,
        "last_task_id": task_id,
    }), encoding="utf-8")
    coordinator._state["active_fingerprint"] = proposal.fingerprint
    coordinator._save_state()

    result = coordinator.run_cycle({"task_pool": {"by_status": {}}, "recent_error_count": 0})
    assert result["released_fingerprint"] == proposal.fingerprint
    assert result["status"] == "NO_ACTION"
    assert proposal.fingerprint in coordinator._completed_fingerprints()
    assert coordinator._state.get("active_fingerprint") == ""
