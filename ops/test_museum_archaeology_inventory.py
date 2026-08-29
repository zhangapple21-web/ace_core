import json
from pathlib import Path

from core.museum_archaeology_inventory import (
    ADAPT,
    HISTORICAL_EXECUTED,
    MuseumArchaeologyInventory,
)
from ops.run_museum_archaeology_turn import run_turn


def _write_daily_reports(history_root, count=7):
    reports = history_root / "private_claw-soul" / "07_OPERATIONS" / "knowledge_reports"
    reports.mkdir(parents=True)
    for day in range(1, count + 1):
        (reports / f"daily_report_202606{day:02d}.json").write_text(
            json.dumps(
                {
                    "report_date": f"2026-06-{day:02d}",
                    "generated_at": f"2026-06-{day:02d}T20:04:00+00:00",
                    "observation": [],
                    "experience": [],
                    "signals": [],
                    "decisions": [],
                    "summary": {},
                }
            ),
            encoding="utf-8",
        )


def test_inventory_separates_historical_series_from_code_only_and_superseded(tmp_path):
    _write_daily_reports(tmp_path)
    knowledge_script = tmp_path / "private_claw-soul" / "lab_02" / "06_SCRIPTS" / "01_knowledge"
    knowledge_script.mkdir(parents=True)
    (knowledge_script / "knowledge_shift.py").write_text("# historical source\n", encoding="utf-8")
    loops = tmp_path / "mine-seed" / "04_PROTOCOLS"
    loops.mkdir(parents=True)
    (loops / "daily_self_loop.py").write_text("# old loop\n", encoding="utf-8")

    inventory = MuseumArchaeologyInventory(tmp_path).scan()
    artifacts = {item["artifact_id"]: item for item in inventory["artifacts"]}

    reports = artifacts["R2_DAILY_KNOWLEDGE_REPORTS"]
    assert reports["status"] == HISTORICAL_EXECUTED
    assert reports["disposition"] == ADAPT
    assert reports["evidence_strength"] == "SERIES_EXECUTION_EVIDENCE"
    assert reports["fragment_types"] == ["CONTINUITY_EVIDENCE", "RUN_TRACE"]
    assert len(reports["files"]) == 7
    assert artifacts["MINE_SEED_DAILY_SELF_LOOP"]["status"] == "CODE_ONLY"
    assert artifacts["MINE_SEED_DAILY_SELF_LOOP"]["fragment_types"] == ["TOOL_RELIC"]
    assert artifacts["R1_FIVE_FACTORY_FREEZONE"]["present"] is False


def test_museum_turn_creates_inbound_food_then_observes_no_change(tmp_path):
    history = tmp_path / "history"
    _write_daily_reports(history)
    archaeology = history / "r1-archaeology" / "analysis"
    archaeology.mkdir(parents=True)
    (archaeology / "archaeology_report_20260627.md").write_text("# dated archaeology\n", encoding="utf-8")
    root = tmp_path / "sandbox"

    first = run_turn(sandbox_root=root, history_root=history)
    assert first["event"] == "MUSEUM_FOOD_RECORDED"
    assert first["food_path"]
    assert Path(first["food_path"]).exists()
    assert not list((root / "experiments").glob("*.json"))
    assert first["court_status"] == "DEFERRED_TO_OUTBOUND_DISTILLATION"
    assert first["production_integration"] is False

    second = run_turn(sandbox_root=root, history_root=history)
    assert second["event"] == "NO_NEW_MUSEUM_WORK"
    assert second["food_path"] is None


def test_r1_ecology_constitution_seed_is_explicitly_non_production():
    seed = Path(__file__).resolve().parents[1] / "07_SANDBOX" / "free_research" / "constitution" / "R1_ECOLOGY_CONSTITUTION_v1.json"
    value = json.loads(seed.read_text(encoding="utf-8"))
    assert value["status"] == "DESIGN_SEED"
    assert value["mode"] == "FREE_RESEARCH_ONLY"
    assert value["promotion_contract"]["production_integration"] is False
    assert value["promotion_contract"]["automatic_promotion"] is False
    assert "failure_is_material" in {item["name"] for item in value["invariants"]}
    assert value["reinstantiation_mapping"]["R1_freezone"].startswith("07_SANDBOX")


def test_environment_awareness_is_inventory_as_constitution_not_a_live_sensor(tmp_path):
    asset = tmp_path / "mine-seed" / "02_MEMORY" / "assets" / "cognition"
    asset.mkdir(parents=True)
    (asset / "CG-002-environmental-awareness.md").write_text("# perception before action\n", encoding="utf-8")

    artifacts = {item["artifact_id"]: item for item in MuseumArchaeologyInventory(tmp_path).scan()["artifacts"]}
    awareness = artifacts["R1_ENVIRONMENT_AWARENESS"]
    assert awareness["present"] is True
    assert awareness["status"] == "DESIGN_ONLY"
    assert awareness["disposition"] == ADAPT
    assert awareness["fragment_types"] == ["ECOLOGY_CONSTITUTION"]
