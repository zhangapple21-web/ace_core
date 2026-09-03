from pathlib import Path
import hashlib
import json

from core.video_kingdom_consumer import VideoKingdomConsumer
from core.video_kingdom_dispatch import VideoKingdomDispatch


def test_consumer_claims_once_and_records_evidence(tmp_path: Path):
    dispatcher = VideoKingdomDispatch(tmp_path)
    dispatcher.observe_and_dispatch(trigger="test", patrol={"warnings": [{"issue": "DRIFT"}]})
    consumer = VideoKingdomConsumer(tmp_path)
    result = consumer.consume_one(patrol={"warnings": [{"issue": "DRIFT"}]})
    assert result["status"] == "HANDOFF_READY"
    assert result["task_type"] == "CONTINUITY_REPAIR"
    assert consumer.consume_one()["status"] == "NO_PENDING_CARD"
    assert '"status": "HANDOFF_READY"' in (tmp_path / "research" / "dispatch_queue.v1.json").read_text(encoding="utf-8")


def test_consumer_keeps_external_learning_research_only(tmp_path: Path):
    dispatcher = VideoKingdomDispatch(tmp_path)
    dispatcher.observe_and_dispatch(trigger="test", patrol={})
    result = VideoKingdomConsumer(tmp_path).consume_one()
    assert result["status"] == "HANDOFF_READY"
    assert result["evidence"]["provider_calls"] == 0
    assert result["production_integration"] is False


def test_consumer_imports_one_hash_bound_result_without_delivery_authority(tmp_path: Path):
    record = tmp_path / "research" / "decision_records" / "ep1.json"
    record.parent.mkdir(parents=True)
    record.write_text('{"result":"evidence only"}\n', encoding="utf-8")
    digest = hashlib.sha256(record.read_bytes()).hexdigest()
    outbox = tmp_path / "research" / "ace_result_outbox.v1.jsonl"
    outbox.write_text(json.dumps({
        "bridge_id": "VK-RESULT-1", "record_id": "ep1-s01", "episode_id": "ep1", "scope_ref": "S01",
        "decision_verdict": "REWORK", "result_status": "COMPLETED", "record_path": "research/decision_records/ep1.json",
        "record_sha256": digest, "source_realm": "CONTROLLED_ORIGIN", "production_integration": False, "delivery_approved": False
    }) + "\n", encoding="utf-8")
    consumer = VideoKingdomConsumer(tmp_path)
    first = consumer.consume_one()
    assert first["status"] == "RESULT_CONSUMED"
    assert first["delivery_approved"] is False
    assert consumer.consume_one_result()["status"] == "NO_PENDING_RESULT"


def test_consumer_rejects_tampered_result_hash(tmp_path: Path):
    outbox = tmp_path / "research" / "ace_result_outbox.v1.jsonl"
    outbox.parent.mkdir(parents=True)
    outbox.write_text(json.dumps({
        "bridge_id": "VK-RESULT-BAD", "record_id": "ep1-s01", "episode_id": "ep1", "scope_ref": "S01",
        "decision_verdict": "PASS", "result_status": "COMPLETED", "record_path": "missing.json",
        "record_sha256": "0" * 64, "source_realm": "CONTROLLED_ORIGIN", "production_integration": False, "delivery_approved": False
    }) + "\n", encoding="utf-8")
    assert VideoKingdomConsumer(tmp_path).consume_one_result()["status"] == "RESULT_REJECTED"
