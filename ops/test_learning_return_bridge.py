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
