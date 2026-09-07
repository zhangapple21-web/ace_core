from pathlib import Path

from core.video_kingdom_dispatch import VideoKingdomDispatch
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


