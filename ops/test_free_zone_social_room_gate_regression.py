"""Two tests for the two defects the first live fire exposed.

Live fire on 2026-10-11 recorded SOCIAL_ROOM_RECORDED with 6 silences and 0
speeches. Reading the transcript showed every reason was "gate returned nothing",
and a probe of the gate seat showed why: `amd_radeon:Qwen3.8-Flash-Next`
returns empty content on every call. The room had never actually run.

Both of these are regression pins for the two separate mistakes, not a
re-description of the happy path.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.free_zone_social_room import GATE_MODEL, FreeZoneSocialRoom, MEMBERS  # noqa: E402


class _PoolReturning:
    """A pool whose gate seat behaves exactly like the dead one did."""

    def chat(self, task_type="", messages=None, system_prompt="",
             selected_spec=None, max_retries=1, max_tokens=0,
             data_boundary=None, **kwargs):
        user = (messages or [{}])[0].get("content", "")
        if "gate of a free-model" in user:
            # Qwen3.8-Flash-Next returns success=True with empty content, so
            # this is exactly the live signature: no exception, no error, nothing.
            return {"success": True, "content": "", "error": "", "latency_ms": 0}
        return {"success": True, "content": "a real answer", "error": ""}


def test_gate_seat_is_not_one_that_answers_with_empty_content():
    """The gate seat must be one that has been observed serving.

    Qwen3.8-Flash-Next returns `success=True` with empty content on every call,
    which is the worst possible gate failure: no exception, no error code, and a
    room that records silence and looks like it ran.
    """
    assert GATE_MODEL != "amd_radeon:Qwen3.8-Flash-Next", (
        "this seat returns empty content on every call; see the live probe of 2026-10-12"
    )


def test_gate_unavailable_is_named_in_the_result(tmp_path):
    room_dir = tmp_path / "07_SANDBOX" / "free_research"
    channel = room_dir / "inbox" / "room"
    channel.mkdir(parents=True, exist_ok=True)
    (channel / "q.json").write_text(
        '{"question": "can an outside model supply evidence ace cannot?","source_ref": "t"}',
        encoding="utf-8",
    )
    room = FreeZoneSocialRoom(room_dir, _PoolReturning())
    result = room.run_once(force=True, max_tokens=64)
    assert result["status"] == "SOCIAL_ROOM_RECORDED"
    # the failure is visible without opening the transcript
    assert result["gate_unavailable"] >= 1
    assert result["speeches"] == 0

    import json

    transcript = json.loads(
        (room_dir / "reports" / "social_room" / f"{result['session_id']}.json")
        .read_text(encoding="utf-8")
    )["transcript"]
    kinds = {t["kind"] for t in transcript}
    assert kinds == {"gate_unavailable"}, "the room must not disguise a dead gate"


def test_a_prose_gate_answer_is_still_read_as_a_decision(tmp_path):
    """A free preview model asked for one word often answers with prose.

    Refusing to read prose means treating a working gate as dead, which is the
    first live-fire defect in mirror image.
    """
    room_dir = tmp_path / "07_SANDBOX" / "free_research"
    channel = room_dir / "inbox" / "room"
    channel.mkdir(parents=True, exist_ok=True)
    (channel / "q.json").write_text(
        '{"question": "who should speak first about shared evidence?","source_ref": "t"}',
        encoding="utf-8",
    )

    class _ProseGate:
        def chat(self, task_type="", messages=None, system_prompt="",
                 selected_spec=None, max_retries=1, max_tokens=0,
                 data_boundary=None, **kwargs):
            user = (messages or [{}])[0].get("content", "")
            if "gate of a free-model" in user:
                name = MEMBERS[0]["name"]
                return {"success": True, "content": f"I think {name} should speak first.", "error": ""}
            return {"success": True, "content": "a real answer", "error": ""}

    room = FreeZoneSocialRoom(room_dir, _ProseGate())
    result = room.run_once(force=True, max_tokens=64)
    assert result["gate_unavailable"] == 0, "prose containing a member name is a decision"
    assert result["speeches"] >= 1


def test_no_member_may_hold_every_turn(tmp_path):
    """The gate is asked not to repeat the last speaker, and must not be trusted.

    Live fire of the second run: the gate seat picked the same member on all six
    turns and the result read `distinct_speakers: 1`. The anti-repeat rule lived
    only in the prompt, so a small gate model simply ignored it. Enforcing it
    structurally is what turns this from a monologue into a room.
    """
    room_dir = tmp_path / "07_SANDBOX" / "free_research"
    channel = room_dir / "inbox" / "room"
    channel.mkdir(parents=True, exist_ok=True)
    (channel / "q.json").write_text(
        '{"question": "can an outside model supply evidence ace itself cannot?","source_ref": "t"}',
        encoding="utf-8",
    )

    class _BrokenGate:
        """Ignores every instruction and always names the first member."""

        def chat(self, task_type="", messages=None, system_prompt="",
                 selected_spec=None, max_retries=1, max_tokens=0,
                 data_boundary=None, **kwargs):
            user = (messages or [{}])[0].get("content", "")
            if "gate of a free-model" in user:
                return {"success": True, "content": MEMBERS[0]["name"], "error": ""}
            return {"success": True, "content": "a substantive answer", "error": ""}

    room = FreeZoneSocialRoom(room_dir, _BrokenGate())
    result = room.run_once(force=True, max_tokens=64)
    assert result["speeches"] >= 2
    assert result["distinct_speakers"] >= 2, (
        "the anti-repeat rule must be structural, not a request to the gate"
    )
    assert result["gate_overrides"] >= 1, "every override must be recorded"

    import json

    transcript = json.loads(
        (room_dir / "reports" / "social_room" / f"{result['session_id']}.json")
        .read_text(encoding="utf-8")
    )["transcript"]
    speakers = [t["speaker"] for t in transcript if t["kind"] == "speech"]
    assert speakers[0] != speakers[1], "no member may speak twice in a row"