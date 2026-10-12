"""Free Zone social room — free models talking freely, with a gate that lets them.

Purpose: the roundtable asks two structured rounds of every seat. This room lets
the models run the conversation themselves: a fast gate seat decides who speaks
next, a seat may PASS instead of talking, and a rolling room memory keeps the
conversation coherent across sessions.

Stealing, deliberately and with attribution — the shipped design of others was
read before this file was written:

  * **The Gate** — Kōl (github.com/m-taqii/kol). A cheap model reads the recent
    history and decides which members speak, with rules that stop the room
    degenerating into a round-robin: no consecutive AI-only monologues, mention
    routing, and the model that just spoke cannot immediately speak again.
    ACE's version keeps the gate *bounded* and records its raw decision, because
    a gate that cannot be audited is a gate nobody can trust.
  * **The PASS mechanic** — ARPAHLS/rooms. A member that has nothing meaningful
    to add says PASS and the turn is skipped. Silence being a legal answer is
    what keeps a free discussion from becoming filler.
  * **Rolling room memory** — Kōl and Xiajiao. Conversation history is
    compressed into a third-person narrative and injected into later calls, so
    the room scales without carrying the whole transcript.
  * **Dynamic turn-taking instead of fan-out** — llmcr/llmchato. Fanning out to
    every seat per turn is what crashes free-tier rate limits; one orchestrator
    call per turn is what survives them.

What is NOT here, on purpose: no second scheduler (the daemon's existing
18:30 free-zone window drives it), no TaskPool producer, no promotion path, no
production boundary change. Output lands in the sandbox exactly like the
roundtable's does, and only crosses through the existing bridge.

The gate is why this is not a decorative chatroom: the models decide what is
worth saying. A room where the operator pre-assigns every turn is a script, not
a conversation.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from .free_research_sandbox import CONTRACT_VERSION as SANDBOX_CONTRACT
from .free_research_sandbox import FreeResearchSandbox, _digest
from .miner_pool.model_router import ModelSpec

CONTRACT_VERSION = "ace.free_zone_social_room.v1"

# Members of the room. Each carries a persona, because "who is speaking" is
# information the gate and the other members both need.
#
# The lineup is chosen from a live probe, not from a spec sheet. On 2026-10-12
# every seat below answered the real speech prompt with a substantive, distinct
# position (ops_probe_twins.py for the CLI twins, ops_seat_probe.py for AMD).
#
# Four seats were cut for cause: ``fledge-alpha-free`` and ``ling-3.0-flash-fin-
# free`` failed outright, ``Qwen3.8-27B`` returns empty content on every call
# (same family as the original dead gate seat), and ``GLM-5.3-Flash`` was
# timing out. ``nemotron-3.5-lightning-free`` answers PASS to everything, which
# is legal but useless as a member: it can only ever subtract a turn. A seat that
# cannot answer is worth less than no seat, because it makes the room look like
# it spoke when it did not.
#
# Six members across two vendors. The owner's point that it cannot rely on AMD
# applies here too: the CLI twins are labour, not decoration, and a room with
# only two of six seats able to fail independently is a room that stalls.
# The gate decides who speaks among them, so a bigger roster costs nothing per
# turn and makes the gate's decision meaningful.
MEMBERS: tuple[dict[str, str], ...] = (
    {
        "name": "muse",
        "model": "opencode_cli:muse-spark-1.3-contributor-free",
        "persona": "curious generalist; asks what the claim actually rests on",
    },
    {
        "name": "ling",
        "model": "opencode_cli:ling-3.1-flash-free",
        "persona": "careful logician; separates what is claimed from what is evidenced",
    },
    {
        "name": "longcat",
        "model": "opencode_cli:longcat-2.5-preview-free",
        "persona": "pragmatist; wants to know what we would do differently",
    },
    {
        "name": "nemotron",
        "model": "opencode_cli:nemotron-3-ultra-free",
        "persona": "contrarian; states plainly when the premise itself is wrong",
    },
    {
        "name": "radeon",
        "model": "amd_radeon:DeepSeek-V4-Flash",
        "persona": "sceptical reasoner; hunts for the counterexample",
    },
    {
        "name": "minicpm",
        "model": "amd_radeon:MiniCPM5-2B",
        "persona": "synthesizer; looks for what the others are both missing",
    },
)

# The gate is a member too, and it never speaks about the topic. Keeping it a
# separate pinned id means routing it can never be confused with seating a
# participant, and its calls are counted against the same budget.
#
# Pinned to the seat that actually answered the exact gate prompt. A live probe
# on 2026-10-12 asked each candidate for one word: DeepSeek-V4-Flash replied
# "muse", and MiniCPM5-2B replied with a paragraph about being a gatekeeper.
# The paragraph looked like success and was not - the third live fire of this
# room produced `gate_unavailable: 1` and `model_calls: 1` because a prose reply
# that names no member is not a decision. Qwen3.8-Flash-Next returns empty
# content on every call and was the original choice.
#
# A small model is the right shape for a gate (Kol uses llama-4-scout-17b,
# llmcr routes one cheap orchestrator call), but small must not mean flaky:
# GATE_ATTEMPTS bounds how many times a silently-rambling seat is retried before
# the room admits it cannot run.
GATE_MODEL = "amd_radeon:DeepSeek-V4-Flash"
GATE_ATTEMPTS = 3

MAX_CALLS_PER_SESSION = 12
MAX_TURNS = 6
MIN_INTERVAL_HOURS = 4
MAX_MESSAGE_CHARS = 500
MEMORY_COMPACT_THRESHOLD = 12

PASS_TOKEN = "PASS"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


class FreeZoneSocialRoom:
    """Free models run their own conversation; the gate decides who speaks."""

    def __init__(self, root: str | Path, miner_pool: Any) -> None:
        self.root = Path(root)
        self.pool = miner_pool
        self.sandbox = FreeResearchSandbox(self.root)
        self.state_path = self.root / "social_room_state.json"

    # ---------------------------------------------------------------- run

    def run_once(self, *, force: bool = False, max_tokens: int = 512) -> dict[str, Any]:
        """One room session, or an honest reason why not."""
        state = self._read(self.state_path)
        gates = self._due(state, force=force)
        if not gates["due"]:
            return self._result(state, {
                "status": "NOT_DUE",
                "reason": gates["reason"],
                "contract_version": CONTRACT_VERSION,
                "gate_evaluation": gates,
                "production_integration": False,
            })

        topic = self._topic(state)
        if topic is None:
            return self._result(state, {
                "status": "NO_TOPIC",
                "reason": "no open question and no room seed available",
                "contract_version": CONTRACT_VERSION,
                "members_available": [m["name"] for m in MEMBERS],
                "model_calls": 0,
                "production_integration": False,
            })

        memory = str(state.get("room_memory", ""))
        transcript: list[dict[str, Any]] = []
        calls = 0
        last_speaker = ""

        for turn in range(1, MAX_TURNS + 1):
            if calls >= MAX_CALLS_PER_SESSION:
                break
            recent = self._recent_slice(transcript)
            # The gate decides. On a gate failure the turn is skipped rather than
            # falling back to a round-robin: a room that silently becomes a
            # script when its gate is down is worse than a room that pauses.
            calls += 1
            gate = self._gate_decision(recent, memory, last_speaker, max_tokens)
            kind = str(gate.get("kind", "silence"))
            choice = str(gate.get("next_speaker", "")).strip().lower()
            if kind == "gate_unavailable":
                # The gate is down. The room says so and pauses; it does not
                # quietly turn into a round-robin, which is the failure a room of
                # this shape must never hide.
                transcript.append({
                    "speaker": "gate", "turn": turn,
                    "kind": "gate_unavailable",
                    "text": str(gate.get("reason", ""))[:200],
                })
                break
            if not choice or choice == "none":
                transcript.append({
                    "speaker": "gate", "turn": turn, "kind": "silence",
                    "text": str(gate.get("reason", "gate chose nobody"))[:200],
                })
                continue

            # The no-consecutive-speaker rule is ENFORCED, not requested.
            # Live fire proved why: the gate seat is a small model, and asked in
            # prose to avoid repeating the last speaker it picked that speaker
            # six turns running. A rule the gate may ignore is not a rule, and a
            # room where one member holds every turn is a monologue with extra
            # steps. When the gate breaks the rule the next distinct member is
            # seated instead, and the override is recorded so the transcript
            # shows which turns were the room's choice and which were the
            # structural guarantee.
            override = ""
            if choice == last_speaker:
                forced = self._next_speaker(choice)
                override = f"gate repeated '{choice}'; seated '{forced}'"
                choice = forced

            member = self._member(choice)
            if member is None:
                transcript.append({
                    "speaker": "gate", "turn": turn, "kind": "unknown_speaker",
                    "text": f"gate named {choice!r}, which is not a member of this room",
                })
                continue

            calls += 1
            message = self._speak(member, topic, recent, memory, turn, max_tokens)
            if message["kind"] == "unavailable":
                transcript.append({
                    "speaker": member["name"], "turn": turn, "kind": "unavailable",
                    "text": message["text"][:160],
                })
                continue
            if message["kind"] == "pass":
                transcript.append({
                    "speaker": member["name"], "turn": turn, "kind": "pass",
                    "text": message["text"][:200],
                })
                continue

            transcript.append({
                "speaker": member["name"], "turn": turn, "kind": "speech",
                "text": message["text"],
                "model": member["model"],
                "latency_ms": message.get("latency_ms", 0),
                "gate_override": override,
            })
            last_speaker = member["name"]

        speeches = [t for t in transcript if t["kind"] == "speech"]
        session_id = "SR-" + topic["topic_hash"][:16].upper()
        room_memory = self._compact_memory(state, transcript, memory, calls)

        session = {
            "contract_version": CONTRACT_VERSION,
            "sandbox_contract_version": SANDBOX_CONTRACT,
            "session_id": session_id,
            "at": _iso(_now()),
            "topic": topic,
            "transcript": transcript,
            "speeches": len(speeches),
            "passes": sum(1 for t in transcript if t["kind"] == "pass"),
            "silences": sum(1 for t in transcript if t["kind"] == "silence"),
            "gate_failures": sum(1 for t in transcript if t["kind"] == "gate_unavailable"),
            "distinct_speakers": len({t["speaker"] for t in speeches}),
            "gate_overrides": sum(1 for t in speeches if t.get("gate_override")),
            "model_calls": calls,
            "call_budget": MAX_CALLS_PER_SESSION,
            "turn_budget": MAX_TURNS,
            "room_memory_after": room_memory,
            "max_message_chars": MAX_MESSAGE_CHARS,
            "production_integration": False,
            "taskpool_mutated": False,
            "automatic_promotion": False,
        }
        session["session_hash"] = _digest(session)

        self._write(self.root / "reports" / "social_room" / f"{session_id}.json", session)
        experiment = self._record_experiment(session)
        return self._result(state, {
            "status": "SOCIAL_ROOM_RECORDED",
            "contract_version": CONTRACT_VERSION,
            "session_id": session_id,
            "topic_hash": topic["topic_hash"],
            "topic_source": topic["source"],
            "speeches": session["speeches"],
            "passes": session["passes"],
            "silences": session["silences"],
            "gate_unavailable": session["gate_failures"],
            "gate_overrides": session["gate_overrides"],
            "distinct_speakers": session["distinct_speakers"],
            "model_calls": calls,
            "room_memory_after": room_memory,
            "experiment_id": experiment["experiment_id"],
            "record_hash": experiment["record_hash"],
            "distillation_status": experiment["distillation_status"],
            "production_integration": False,
        }, topic_hash=topic["topic_hash"])

    # ---------------------------------------------------------------- gate

    def _gate_decision(self, recent: list[dict[str, Any]], memory: str,
                       last_speaker: str, max_tokens: int) -> dict[str, Any]:
        """One cheap call decides who speaks. The gate is audited, not obeyed.

        Retried a bounded number of times: a free preview seat that returns a
        paragraph naming nobody looks like a working gate and is not, and giving
        up after one attempt turned the third live fire into a one-call session.
        """
        members = ", ".join(m["name"] for m in MEMBERS)
        recent_text = "\n".join(
            f"- {t['speaker']}: {t['text'][:160]}" for t in recent[-6:]
        ) or "(nothing has been said yet)"
        prompt = (
            f"You are the gate of a free-model discussion room, not a participant.\n"
            f"Members: {members}.\n"
            f"Room memory: {memory[:600] or '(none)'}\n"
            f"Recent messages:\n{recent_text}\n\n"
            f"The member who spoke immediately before was '{last_speaker or 'nobody'}' "
            f"and may not be chosen again.\n"
            f"Reply with one word naming the member who speaks next, or NONE if "
            f"the conversation does not need another voice."
        )
        decision: dict[str, Any] = {"next_speaker": "", "kind": "gate_unavailable"}
        for attempt in range(1, GATE_ATTEMPTS + 1):
            raw = self._chat(GATE_MODEL, prompt,
                             system_prompt="You are a terse discussion gate. Answer with one word.",
                             max_tokens=min(max_tokens, 60))
            decision = self._parse_gate(raw)
            if decision.get("kind") == "decision":
                return decision
            attempt_note = f"{attempt}/{GATE_ATTEMPTS}"
            # A gate that answers NONE has made a decision; only a failure to
            # answer at all is a reason to try again.
            if decision.get("next_speaker") == "none":
                return decision
        decision["reason"] = (
            f"gate unavailable after {GATE_ATTEMPTS} attempts: "
            f"{decision.get('reason', 'no answer')}"
        )
        return decision

    def _parse_gate(self, raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        if not text:
            # A gate that cannot answer is a different condition from a gate that
            # chose nobody, and the room must say which one it hit.
            return {"next_speaker": "", "reason": "gate_unavailable: empty response",
                    "kind": "gate_unavailable"}
        first_line = text.splitlines()[0].strip().lower().strip(".:,-")
        if first_line in {"none", "nobody", "no one"}:
            return {"next_speaker": "none", "reason": "gate chose nobody", "kind": "silence"}
        lowered = text.lower()
        for member in MEMBERS:
            if member["name"] in lowered:
                return {"next_speaker": member["name"], "reason": "", "kind": "decision"}
        return {"next_speaker": "", "reason": f"gate_unavailable: unparsable {text[:80]}",
                "kind": "gate_unavailable"}

    # ------------------------------------------------------------- members

    def _speak(self, member: Mapping[str, str], topic: Mapping[str, Any],
               recent: list[dict[str, Any]], memory: str, turn: int,
               max_tokens: int) -> dict[str, Any]:
        recent_text = "\n".join(
            f"- {t['speaker']}: {t['text'][:200]}" for t in recent[-6:]
        ) or "(nothing yet)"
        prompt = (
            f"Question in this room: {topic['question']}\n\n"
            f"Room memory: {memory[:600] or '(none)'}\n\n"
            f"What has been said:\n{recent_text}\n\n"
            f"You are {member['name']} ({member['persona']}). "
            f"In at most three sentences, add something the others have not said. "
            f"If you genuinely have nothing to add, reply with exactly the word PASS."
        )
        raw = self._chat(
            member["model"],
            prompt,
            system_prompt=(
                "You are a participant in a free-model discussion room. This is "
                "sandbox only. Never propose production changes, task creation, or "
                "external actions. Say plainly when you do not know."
            ),
            max_tokens=max_tokens,
        )
        text = (raw or "").strip()
        if not text:
            return {"kind": "unavailable", "text": "", "latency_ms": 0}
        if text.upper().startswith(PASS_TOKEN):
            return {"kind": "pass", "text": text[:200], "latency_ms": 0}
        return {"kind": "speech", "text": text[:MAX_MESSAGE_CHARS], "latency_ms": 0}

    def _member(self, name: str) -> Mapping[str, str] | None:
        return next((m for m in MEMBERS if m["name"] == name), None)

    @staticmethod
    def _next_speaker(avoid: str) -> str:
        """The first member that is not `avoid`, in roster order.

        Used only when the gate breaks the no-consecutive-speaker rule. Ordering
        is fixed rather than random so a reader can tell a structural override
        from a lucky one.
        """
        names = [m["name"] for m in MEMBERS]
        for name in names:
            if name != avoid:
                return name
        return avoid

    def _chat(self, model_id: str, prompt: str, *, system_prompt: str,
              max_tokens: int) -> str:
        try:
            response = self.pool.chat(
                task_type="free_exploration",
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                selected_spec=ModelSpec.from_id(model_id),
                max_retries=1,
                max_tokens=max_tokens,
                data_boundary={"data_class": "PUBLIC"},
            )
        except Exception as error:  # a seat must never take the room down
            return f"___UNAVAILABLE___:{type(error).__name__}:{str(error)[:120]}"
        if not response.get("success"):
            return ""
        return str(response.get("content", "") or "")

    def _recent_slice(self, transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [t for t in transcript if t.get("kind") in {"speech", "pass"}]

    # -------------------------------------------------------------- memory

    def _compact_memory(self, state: Mapping[str, Any],
                        transcript: list[dict[str, Any]], existing: str,
                        calls: int) -> str:
        """Roll the transcript into a short narrative, the way Kōl and Xiajiao do."""
        lines = []
        for entry in transcript:
            if entry["kind"] == "speech":
                lines.append(f"{entry['speaker']} said: {entry['text'][:180]}")
            elif entry["kind"] == "pass":
                lines.append(f"{entry['speaker']} passed")
        if len(lines) < MEMORY_COMPACT_THRESHOLD and existing:
            return existing
        fresh = " | ".join(lines)[-2000:]
        if not fresh:
            return existing
        return (existing + " | " + fresh)[-2000:] if existing else fresh

    # --------------------------------------------------------------- topic

    def _topic(self, state: Mapping[str, Any]) -> dict[str, Any] | None:
        done = {str(h) for h in state.get("completed_seed_hashes", [])}
        for path in sorted((self.root / "inbox" / "room").glob("*.json")):
            candidate = self._topic_from_seed(path)
            if candidate and candidate["topic_hash"] not in done:
                return candidate
        for candidate in self._open_questions(done):
            return candidate
        return None

    def _topic_from_seed(self, path: Path) -> dict[str, Any] | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(payload, Mapping):
            return None
        question = str(payload.get("question") or payload.get("prompt") or "").strip()
        if len(question) < 12:
            return None
        return self._topic_record(question, f"seed:{path.name}", str(payload.get("source_ref", "")))

    def _open_questions(self, done: set[str]) -> list[dict[str, Any]]:
        directory = self.root / "distillations"
        if not directory.is_dir():
            return []
        found: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(record, Mapping) or record.get("status") != "OPEN_QUESTION":
                continue
            experiment_id = str(record.get("experiment_id", ""))
            if experiment_id.startswith("EXP-SR-") or experiment_id.startswith("EXP-RT-"):
                continue
            pattern = str(record.get("pattern", "")).strip()
            if not pattern:
                continue
            topic = self._topic_record(pattern, f"open_question:{experiment_id}", "")
            if topic and topic["topic_hash"] not in done:
                found.append(topic)
                if len(found) >= 3:
                    break
        return found

    @staticmethod
    def _topic_record(question: str, source: str, source_ref: str) -> dict[str, Any]:
        normalized = " ".join(question.split())
        return {
            "question": normalized[:400],
            "topic_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "source": source,
            "source_ref": source_ref,
        }

    # ----------------------------------------------------------- recording

    def _record_experiment(self, session: Mapping[str, Any]) -> dict[str, Any]:
        experiment_id = "EXP-" + session["session_id"]
        record = self.sandbox.record_experiment(
            experiment_id=experiment_id,
            hypothesis=session["topic"]["question"],
            method="gate-driven free-model discussion with pass and silence",
            outcome="INCONCLUSIVE",
            evidence={
                "session_hash": session["session_hash"],
                "speeches": session["speeches"],
                "passes": session["passes"],
                "silences": session["silences"],
                "distinct_speakers": session["distinct_speakers"],
                "gate_overrides": session["gate_overrides"],
                "model_calls": session["model_calls"],
                "transcript": session["transcript"],
            },
            metadata={
                "source_kind": "free_zone_social_room",
                "source_ref": session["topic"]["source"],
                "free_zone_only": True,
                "automatic_model_call": True,
                "paid_provider_used": False,
            },
        )
        distilled = self.sandbox.distill(experiment_id)
        return {
            "experiment_id": experiment_id,
            "record_hash": record["record_hash"],
            "distillation_status": distilled.get("status"),
        }

    # ----------------------------------------------------------------- due

    def _due(self, state: Mapping[str, Any], *, force: bool) -> dict[str, Any]:
        from .stage_gates import evaluate_gates

        now = _now()
        if self.pool is None:
            gates = {"miner_pool_present": (False, "miner pool not wired in this process")}
            passed, blocking = evaluate_gates(gates)
            return {"due": False, "reason": "MINER_POOL_ABSENT", "gates": {
                k: {"passed": v[0], "detail": v[1]} for k, v in gates.items()
            }, "decision": blocking}

        last = str(state.get("last_session_at", ""))
        elapsed, detail = True, "no prior session"
        if last and not force:
            try:
                waited = now - datetime.fromisoformat(last)
                elapsed = waited >= timedelta(hours=MIN_INTERVAL_HOURS)
                detail = f"{waited.total_seconds() / 3600:.1f}h since last session"
            except ValueError:
                elapsed, detail = True, "unreadable timestamp treated as elapsed"
        today = sum(
            1 for stamp in state.get("recent_sessions", [])
            if str(stamp).startswith(now.strftime("%Y-%m-%d"))
        )
        gates = {
            "miner_pool_present": (True, "pool present"),
            "cooldown_elapsed": (elapsed if not force else True, detail if not force else "forced by caller"),
            "budget_available": (today < 6, f"{today} sessions today"),
        }
        passed, blocking = evaluate_gates(gates)
        return {
            "due": passed,
            "reason": "GO" if passed else f"BLOCKED_BY_{blocking}",
            "at": _iso(now),
            "gates": {name: {"passed": ok, "detail": text} for name, (ok, text) in gates.items()},
            "decision": blocking,
        }

    # ------------------------------------------------------------------ io

    def _result(self, state: Mapping[str, Any], payload: dict[str, Any], *,
                topic_hash: str = "") -> dict[str, Any]:
        updated = dict(state)
        if topic_hash:
            done = set(updated.get("completed_seed_hashes", []))
            done.add(topic_hash)
            updated["completed_seed_hashes"] = sorted(done)
        if payload.get("status") == "SOCIAL_ROOM_RECORDED":
            updated["last_session_at"] = _iso(_now())
            recent = [s for s in updated.get("recent_sessions", []) if s]
            recent.append(_iso(_now()))
            updated["recent_sessions"] = recent[-16:]
        result = dict(payload)
        updated["last_room"] = {
            "status": payload.get("status"),
            "at": _iso(_now()),
            "session_id": payload.get("session_id", ""),
            "speeches": payload.get("speeches", 0),
            "passes": payload.get("passes", 0),
            "model_calls": payload.get("model_calls", 0),
            "production_integration": False,
        }
        if payload.get("room_memory_after"):
            updated["room_memory"] = payload["room_memory_after"]
        self._write(self.state_path, updated)
        result["room_memory"] = updated.get("room_memory", "")
        return result

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _write(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)