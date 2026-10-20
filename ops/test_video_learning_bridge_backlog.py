import json
from types import SimpleNamespace

from core.video_learning_bridge_backlog import VideoLearningBridgeBacklog
from core.evolution_kernel import make_packet


class Pool:
    def __init__(self, tasks=None):
        self.tasks = tasks or []

    def list_tasks(self, **_kwargs):
        return self.tasks


def _packet(**changes):
    packet = make_packet(
        scope="video",
        candidate={
            "candidate_id": "video:run:source",
            "title": "video workflow idea",
            "source_kind": "video_receipt",
            "source_status": "NEW_OR_CHANGED",
            "source_content_key": "source:v1",
            "source_refs": ["https://example.org/readme"],
        },
        observation={
            "facts": ["receipt exists"],
            "evidence": ["abc"],
            "unknowns": ["local fit"],
            "source_refs": ["https://example.org/readme"],
        },
    )
    packet.update(changes)
    return packet


def test_video_packet_becomes_one_governed_candidate(tmp_path):
    receipts = tmp_path / "packets.jsonl"
    receipts.write_text(json.dumps(_packet()) + "\n", encoding="utf-8")
    candidates = VideoLearningBridgeBacklog(Pool(), receipts).candidates()
    candidate, evidence = candidates[0]
    assert candidate.candidate_source == "video_learning_bridge"
    assert candidate.metadata["learning"]["requires_miner"] is True
    assert evidence[0]["metadata"]["production_authority"] == "NONE"


def test_packet_is_not_consumed_twice_after_task_creation(tmp_path):
    receipts = tmp_path / "packets.jsonl"
    packet = _packet()
    receipts.write_text(json.dumps(packet) + "\n", encoding="utf-8")
    task = SimpleNamespace(outputs={"discovery": {"fingerprint": f"video_learning_bridge:{packet['packet_id']}"}})
    assert VideoLearningBridgeBacklog(Pool([task]), receipts).candidates() == []


def test_unsafe_or_non_research_packet_is_fail_closed(tmp_path):
    receipts = tmp_path / "packets.jsonl"
    receipts.write_text(json.dumps(_packet(execution_authorized=True)) + "\n", encoding="utf-8")
    assert VideoLearningBridgeBacklog(Pool(), receipts).candidates() == []


def test_legacy_packet_without_changed_source_key_is_not_consumed(tmp_path):
    receipts = tmp_path / "packets.jsonl"
    legacy = _packet()
    legacy.pop("source_status", None)
    legacy.pop("source_content_key", None)
    receipts.write_text(json.dumps(legacy) + "\n", encoding="utf-8")
    assert VideoLearningBridgeBacklog(Pool(), receipts).candidates() == []
