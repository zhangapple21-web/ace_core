"""Tests for the free-zone social room: gate decides, seat may pass, memory rolls.

These use a scripted pool so the *policy* is what is under test - who is allowed
to speak next, what happens when the gate fails, whether PASS really skips a
turn, and whether a room that cannot reach its gate degrades quietly or loudly.
A live-model test would only prove the models answer, which is not the risk.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.free_zone_social_room import (  # noqa: E402
    CONTRACT_VERSION,
    MAX_CALLS_PER_SESSION,
    MAX_TURNS,
    MEMBERS,
    FreeZoneSocialRoom,
)


class ScriptedPool:
    """Answers with a scripted sequence so the room's control flow is visible."""

    def __init__(self, replies=None):
        # replies keyed by substring of the prompt; falls back in order.
        self._replies = list(replies or [])
        self.calls = []

    def chat(self, task_type="", messages=None, system_prompt="",
             selected_spec=None, max_retries=1, max_tokens=0, data_boundary=None, **kwargs):
        self.calls.append({
            "model": str(selected_spec),
            "system": system_prompt,
            "user": (messages or [{}])[0].get("content", "") if messages else "",
            "data_boundary": data_boundary,
        })
        reply = self._replies.pop(0) if self._replies else ""
        return {"success": bool(reply), "content": reply, "error": "",
                "provider": "amd_radeon", "model": str(selected_spec)}


class GateOnlyPool(ScriptedPool):
    """The gate always picks the sceptic; members always decline to speak."""

    def chat(self, **kwargs):
        super().chat(**kwargs)
        if "gate of a free-model" in kwargs.get("messages", [{}])[0].get("content", ""):
            return {"success": True, "content": "radeon", "error": "", "provider": "amd_radeon"}
        return {"success": True, "content": "PASS", "error": "", "provider": "amd_radeon"}


def _seed(tmp_path, question):
    root = tmp_path / "07_SANDBOX" / "free_research"
    channel = root / "inbox" / "room"
    channel.mkdir(parents=True, exist_ok=True)
    (channel / "question.json").write_text(json.dumps({
        "question": question,
        "source_ref": "unit_test",
    }), encoding="utf-8")
    return root


def test_members_cover_more_than_one_provider(tmp_path):
    providers = {m["model"].split(":", 1)[0] for m in MEMBERS}
    assert len(providers) > 1, "a room of one provider is an echo chamber"


def test_unavailable_gate_stops_the_room_instead_of_round_robining(tmp_path):
    """A gate that cannot answer must not be mistaken for a gate that chose nobody.

    The first live fire of this room recorded six 'silences' with a dead gate
    seat - the room looked like it had run and said nothing worth reporting.
    An empty gate reply is now its own named kind and stops the session.
    """
    root = _seed(tmp_path, " ".join(["what should the room do when evidence is thin"] * 2))
    room = FreeZoneSocialRoom(root, ScriptedPool(replies=[]))
    result = room.run_once(force=True, max_tokens=64)
    assert result["status"] == "SOCIAL_ROOM_RECORDED"
    assert result["speeches"] == 0, "an empty gate must not silently seat everyone"
    assert result["gate_unavailable"] >= 1
    session = json.loads(
        (root / "reports" / "social_room" / f"{result['session_id']}.json").read_text(encoding="utf-8")
    )
    # every turn is an honest silence, not a disguised round-robin
    assert all(t["kind"] == "gate_unavailable" for t in session["transcript"])
    # one gate attempt, then stop: no fallback round-robin, no budget burn
    assert result["model_calls"] == 1, "a dead gate must cost one call, not MAX_TURNS"
    assert session["gate_failures"] >= 1

    session_files = (root / "experiments" / result["experiment_id"]).name
    experiment = json.loads(session_files or "{}") if False else None


def test_pass_skips_the_turn_and_is_recorded(tmp_path):
    root = _seed(tmp_path, " ".join(["is a fixed retry defensible without knowing why"] * 2))
    room = FreeZoneSocialRoom(root, GateOnlyPool())
    result = room.run_once(force=True, max_tokens=64)
    assert result["status"] == "SOCIAL_ROOM_RECORDED"
    assert result["passes"] == MAX_TURNS
    assert result["speeches"] == 0
    assert result["distinct_speakers"] == 0
    # a pass is a legal answer, not a failure
    session = json.loads(
        (root / "reports" / "social_room" / f"{result['session_id']}.json").read_text(encoding="utf-8")
    )
    assert all(t["kind"] == "pass" for t in session["transcript"])


def test_call_budget_is_respected(tmp_path):
    root = _seed(tmp_path, " ".join(["should a blocked task deposit an experience"] * 2))
    pool = ScriptedPool(replies=["muse"] * 40 + ["a real answer about evidence"] * 40)
    room = FreeZoneSocialRoom(root, pool)
    result = room.run_once(force=True, max_tokens=64)
    assert result["status"] == "SOCIAL_ROOM_RECORDED"
    assert result["model_calls"] <= MAX_CALLS_PER_SESSION


class CyclingRoomPool(ScriptedPool):
    """Gate cycles members so the room really talks; members give real answers."""

    def __init__(self):
        super().__init__()
        self._turn = 0

    def chat(self, **kwargs):
        self.calls.append({
            "model": str(kwargs.get("selected_spec")),
            "system": kwargs.get("system_prompt", ""),
            "user": (kwargs.get("messages") or [{}])[0].get("content", ""),
            "data_boundary": kwargs.get("data_boundary"),
        })
        user = (kwargs.get("messages") or [{}])[0].get("content", "")
        if "gate of a free-model" in user:
            self._turn += 1
            name = MEMBERS[self._turn % len(MEMBERS)]["name"]
            return {"success": True, "content": name, "error": "", "provider": "amd_radeon"}
        self._turn_text = getattr(self, "_turn_text", 0) + 1
        return {
            "success": True,
            "content": f"member answer {self._turn_text} about evidence and retries",
            "error": "",
            "provider": "amd_radeon",
        }


def test_room_memory_carries_across_sessions(tmp_path):
    root = _seed(tmp_path, " ".join(["does the room remember what it already said"] * 2))
    room = FreeZoneSocialRoom(root, CyclingRoomPool())
    first = room.run_once(force=True, max_tokens=64)
    assert first["status"] == "SOCIAL_ROOM_RECORDED"
    assert first["speeches"] > 0, "a room that never spoke has nothing to remember"
    assert room._read(room.state_path).get("room_memory")


def test_production_boundary_flags_are_all_false(tmp_path):
    root = _seed(tmp_path, " ".join(["can free models ever be independent evidence"] * 2))
    room = FreeZoneSocialRoom(root, ScriptedPool(replies=[]))
    result = room.run_once(force=True, max_tokens=64)
    session = json.loads(
        (root / "reports" / "social_room" / f"{result['session_id']}.json").read_text(encoding="utf-8")
    )
    assert session["production_integration"] is False
    assert session["taskpool_mutated"] is False
    assert session["automatic_promotion"] is False


def test_contract_version_is_declared(tmp_path):
    root = _seed(tmp_path, " ".join(["what is this room actually for"] * 2))
    room = FreeZoneSocialRoom(root, ScriptedPool(replies=[]))
    result = room.run_once(force=True, max_tokens=64)
    assert result["contract_version"] == CONTRACT_VERSION
    session = json.loads(
        (root / "reports" / "social_room" / f"{result['session_id']}.json").read_text(encoding="utf-8")
    )
    assert session["contract_version"] == CONTRACT_VERSION


def test_no_topic_is_named_not_crashed(tmp_path):
    root = tmp_path / "07_SANDBOX" / "free_research"
    root.mkdir(parents=True, exist_ok=True)
    room = FreeZoneSocialRoom(root, ScriptedPool(replies=[]))
    result = room.run_once(force=True, max_tokens=64)
    assert result["status"] == "NO_TOPIC"
    assert result["model_calls"] == 0


def test_disabled_pool_is_a_named_gate(tmp_path):
    root = _seed(tmp_path, " ".join(["what happens when the pool is absent"] * 2))
    room = FreeZoneSocialRoom(root, None)
    result = room.run_once(force=True, max_tokens=64)
    assert result["status"] == "NOT_DUE"
    assert result["reason"] == "MINER_POOL_ABSENT"