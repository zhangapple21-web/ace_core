import json
from types import SimpleNamespace

from core.learning_return_bridge import LearningReturnBridge
from core.video_kingdom_consumer import VideoKingdomConsumer


def test_learning_result_is_materialized_and_consumed_as_bounded_card(tmp_path):
    task = SimpleNamespace(
        task_id="RQ-LEARNING-001",
        guardian_decision="experience",
        evidence=[
            {"source": "https://github.com/example/pipeline", "source_ref": "https://github.com/example/pipeline"},
            {"source": "https://raw.githubusercontent.com/example/pipeline/main/README.md", "source_ref": "https://raw.githubusercontent.com/example/pipeline/main/README.md"},
        ],
        outputs={
            "external_mining": {
                "fetched": {"repository": "https://github.com/example/pipeline", "fingerprint": "abc123"},
                "miner_result": {
                    "analysis": {
                        "recommended_absorbable_capabilities": ["阶段化场景资产", "首尾帧复核"],
                        "next_verification": ["固定模型做三轮离线 A/B"],
                    }
                },
            }
        },
    )
    (tmp_path / "video").mkdir()
    bridge = LearningReturnBridge(tmp_path, video_root=tmp_path / "video")
    result = bridge.materialize(task)
    assert result["status"] == "MATERIALIZED"
    assert result["handoff"]["status"] == "DISPATCHED"
    card = json.loads((tmp_path / "09_KNOWLEDGE/capability_cards/CAP-RQ-LEARNING-001.json").read_text(encoding="utf-8"))
    assert card["capability_state"] == "RESEARCH_READY_NOT_PROMOTED"
    assert card["production_integration"] is False

    consumed = VideoKingdomConsumer(tmp_path / "video").consume_one()
    assert consumed["status"] == "HANDOFF_READY"
    assert consumed["evidence"]["action"] == "LEARNING_RESULT_RECORDED"
    assert consumed["evidence"]["source_task_id"] == "RQ-LEARNING-001"


def test_learning_card_replay_replaces_corrupt_or_stale_card(tmp_path):
    task = SimpleNamespace(
        task_id="RQ-LEARNING-002",
        guardian_decision="experience",
        evidence=[],
        outputs={
            "external_mining": {
                "fetched": {"repository": "https://github.com/example/pipeline", "fingerprint": "v1"},
                "miner_result": {"analysis": {"recommended_absorbable_capabilities": ["v1"]}},
            }
        },
    )
    bridge = LearningReturnBridge(tmp_path, video_root=tmp_path / "video")
    (tmp_path / "video").mkdir()
    first = bridge.materialize(task)
    path = tmp_path / "09_KNOWLEDGE/capability_cards/CAP-RQ-LEARNING-002.json"
    path.write_text('{"card_sha256":"stale"}', encoding="utf-8")
    second = bridge.materialize(task)
    assert second["card_sha256"] == first["card_sha256"]
    assert json.loads(path.read_text(encoding="utf-8"))["card_sha256"] == first["card_sha256"]


def test_video_learning_packet_returns_bounded_card_after_guardian(tmp_path):
    task = SimpleNamespace(
        task_id="RQ-VIDEO-001",
        guardian_decision="experience",
        evidence=[{"source_ref": "https://github.com/example/video", "source": "video"}],
        outputs={
            "discovery": {
                "candidate_source": "video_learning_bridge",
                "evolution_packet_id": "EK-abc",
                "evolution_packet_sha256": "sha",
                "source_content_key": "example:v1",
                "source_refs": ["https://github.com/example/video"],
            },
            "model_research_result": {"content": "只作为候选研究，尚未证明能改善本地指标。"},
        },
    )
    (tmp_path / "video").mkdir()
    result = LearningReturnBridge(tmp_path, video_root=tmp_path / "video").materialize(task)
    assert result["status"] == "MATERIALIZED"
    card = json.loads((tmp_path / "09_KNOWLEDGE/capability_cards/CAP-RQ-VIDEO-001.json").read_text(encoding="utf-8"))
    assert card["source_packet_id"] == "EK-abc"
    assert card["production_integration"] is False
    assert card["recommended_capabilities"] == []

def test_internal_archaeology_becomes_research_candidate_without_second_task(tmp_path):
    source = tmp_path / "08_ARCHAEOLOGY" / "2026-06-30_hunting_report.md"
    source.parent.mkdir()
    source.write_text("# 开放狩猎报告\n\n### 1. Example\n", encoding="utf-8")
    task = SimpleNamespace(
        task_id="RQ-ARCH-001",
        guardian_decision="experience",
        evidence=[{"source": str(source), "source_ref": str(source)}],
        outputs={"discovery": {"evidence": [{"ref": str(source)}]}},
    )
    result = LearningReturnBridge(tmp_path).materialize(task)
    assert result["status"] == "MATERIALIZED"
    assert result["handoff"]["status"] == "INTERNAL_ARCHAEOLOGY_NOT_DISPATCHED"
    assert result["production_integration"] is False
    card = json.loads((tmp_path / "09_KNOWLEDGE/capability_cards/CAP-RQ-ARCH-001.json").read_text(encoding="utf-8"))
    assert card["capability_state"] == "RESEARCH_READY_NOT_PROMOTED"
    assert card["source_kind"] == "internal_archaeology"
    assert card["higher_grade_eligible"] is False
    assert card["higher_grade_requires_independent_evidence"] == 2

def test_local_archaeology_intake_policy_separates_sources(tmp_path):
    from core.local_archaeologist import LocalArchaeologist

    scanner = LocalArchaeologist(tmp_path, SimpleNamespace(), SimpleNamespace())
    assert scanner._intake_policy("tg_finding", ".md", tmp_path / "finding.md")["decision"] == "research"
    assert scanner._intake_policy("tg_index", ".json", tmp_path / "index.json")["decision"] == "observe"
    assert scanner._intake_policy("archaeology", ".md", tmp_path / "secret.md")["decision"] == "skip"
    assert scanner._intake_policy("repository_material", ".md", tmp_path / "README.md")["decision"] == "research"


def test_real_local_collection_excludes_sensitive_and_keeps_policy(tmp_path):
    from core.local_archaeologist import LocalArchaeologist

    root = tmp_path / "08_ARCHAEOLOGY"
    root.mkdir()
    (root / "continuity.md").write_text("# Continuity invariants", encoding="utf-8")
    (root / "secret.md").write_text("excluded", encoding="utf-8")
    scanner = LocalArchaeologist(tmp_path, SimpleNamespace(), SimpleNamespace())
    candidates = scanner._collect_candidate_files()
    assert len(candidates) == 1
    policy = candidates[0]["intake_policy"]
    assert policy["authority"] == "local_read_only"
    assert policy["retention"] == "LINEAGE"
    assert policy["evidence_quality"] == "source_assertion"
    assert scanner.scan()["files_scanned"] == 1


def test_unknown_material_is_cold_observation_not_deletion(tmp_path):
    from core.local_archaeologist import LocalArchaeologist

    scanner = LocalArchaeologist(tmp_path, SimpleNamespace(), SimpleNamespace())
    policy = scanner._intake_policy("unknown", ".txt", tmp_path / "unknown.txt")
    assert policy["decision"] == "observe"
    assert policy["retention"] == "COLD"
    assert policy["reobserve"] is True
