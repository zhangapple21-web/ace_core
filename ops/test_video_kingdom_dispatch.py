from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.video_kingdom_dispatch import CLAIM_LEASE_SECONDS, QueueUnreadableError, VideoKingdomDispatch
import ace_daemon


def test_dispatch_turns_patrol_signal_into_idempotent_research_card(tmp_path: Path):
    dispatcher = VideoKingdomDispatch(tmp_path)
    first = dispatcher.observe_and_dispatch(trigger="daemon_cycle", patrol={"warnings": [{"issue": "FACE_DRIFT"}]})
    second = dispatcher.observe_and_dispatch(trigger="daemon_cycle", patrol={"warnings": [{"issue": "FACE_DRIFT"}]})
    assert first["status"] == "DISPATCHED"
    assert first["task_type"] == "CONTINUITY_REPAIR"
    assert second["status"] == "ALREADY_DISPATCHED"
    assert (tmp_path / "research" / "dispatch_queue.v1.json").exists()


def test_daemon_consumes_prior_card_before_queuing_new_one(monkeypatch, tmp_path: Path):
    calls = []

    class FakeConsumer:
        def __init__(self, root):
            calls.append(("consumer_init", root))

        def consume_one(self, patrol=None):
            calls.append("consume")
            return {"status": "NO_PENDING_CARD", "production_integration": False}

    class FakeDispatch:
        def __init__(self, root):
            calls.append(("dispatch_init", root))

        def observe_and_dispatch(self, *, trigger, patrol):
            calls.append("dispatch")
            return {"status": "DISPATCHED", "task_type": "CONTINUITY_REPAIR"}

    monkeypatch.setattr(ace_daemon, "VideoKingdomConsumer", FakeConsumer)
    monkeypatch.setattr(ace_daemon, "VideoKingdomDispatch", FakeDispatch)
    daemon = object.__new__(ace_daemon.AceDaemon)
    daemon.config = {"runtime": {"video_kingdom_root": str(tmp_path)}}
    daemon.base_dir = tmp_path
    result = daemon._dispatch_video_kingdom()
    assert calls.index("consume") < calls.index("dispatch")
    assert result["linkage"]["ace_to_video_kingdom"] == "CARD_QUEUED"
    assert result["linkage"]["next_owner"] == "video_kingdom_shift"


def test_corrupt_queue_is_not_overwritten(tmp_path: Path):
    dispatcher = VideoKingdomDispatch(tmp_path)
    dispatcher.observe_and_dispatch(trigger="test", patrol={"warnings": [{"issue": "FACE_DRIFT"}]})
    queue = tmp_path / "research" / "dispatch_queue.v1.json"
    original = queue.read_text(encoding="utf-8")
    queue.write_text("{not-json", encoding="utf-8")
    with pytest.raises(QueueUnreadableError):
        dispatcher.observe_and_dispatch(trigger="later", patrol={})
    assert queue.read_text(encoding="utf-8") == "{not-json"
    isolated = list((tmp_path / "research").glob("dispatch_queue.v1.json.corrupt.*"))
    assert isolated
    assert isolated[0].read_text(encoding="utf-8") == "{not-json"
    assert original.startswith("{")


def test_claimed_card_is_reclaimed_after_lease_expires(tmp_path: Path):
    dispatcher = VideoKingdomDispatch(tmp_path)
    dispatcher.observe_and_dispatch(trigger="test", patrol={"warnings": [{"issue": "FACE_DRIFT"}]})
    first = dispatcher.claim_next()
    assert first is not None
    assert first["status"] == "CLAIMED"
    assert dispatcher.claim_next() is None
    payload = dispatcher._read()
    card = payload["cards"][0]
    expired = datetime.now(timezone.utc) - timedelta(seconds=CLAIM_LEASE_SECONDS + 1)
    card["claimed_at"] = expired.isoformat()
    card["claim_expires_at"] = expired.isoformat()
    dispatcher._write(payload, payload["cards"])
    reclaimed = dispatcher.claim_next()
    assert reclaimed is not None
    assert reclaimed["task_id"] == first["task_id"]
    assert reclaimed["status"] == "CLAIMED"
    assert reclaimed["reclaimed"] is True


