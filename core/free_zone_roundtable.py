"""A bounded free-model roundtable inside the existing Free Zone sandbox.

Purpose: give the free twins a place to talk to each other about something ACE
genuinely does not know, and keep the transcript as sandbox material.

Reuse, not reinvention:
  * ``MinerPool.chat`` supplies routing, provider health, the data-boundary
    gate and the free CLI transport.  Seats are pinned with ``selected_spec``
    so a seat can never silently fall through to a paid provider.
  * ``FreeResearchSandbox`` supplies hashed experiment records, distillation
    and the one-way production boundary.  The roundtable never writes outside
    the sandbox.
  * ``stage_gates`` supplies the shared due/gate vocabulary so a silent skip
    stays distinguishable from "not due".

Non-goals (deliberately absent): a second scheduler, a TaskPool producer, an
admission path, a promotion path, and any raw prompt retention beyond a bounded
sandbox transcript.
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

CONTRACT_VERSION = "ace.free_zone_roundtable.v1"

# Free seats only. A pinned seat is a governance boundary as much as a routing
# choice: with selected_spec the pool retries the same seat and never selects a
# paid route, so "free by default" is structural, not a preference.
#
# The fourth seat comes from an unrelated vendor on purpose: a room made of one
# provider's twins is an echo chamber. It is pinned to DeepSeek-V4-Flash rather
# than V4.1 because a live probe (2026-10-12, ops_seat_probe.py) showed V4.1
# returning 429 repeatedly while V4-Flash served every request. A seat that
# cannot answer is worse than no seat - it makes the report look like it ran.
SEATS: tuple[tuple[str, str], ...] = (
    ("muse", "opencode_cli:muse-spark-1.3-contributor-free"),
    ("ling", "opencode_cli:ling-3.1-flash-free"),
    ("longcat", "opencode_cli:longcat-2.5-preview-free"),
    ("nemotron", "opencode_cli:nemotron-3-ultra-free"),
    ("radeon", "amd_radeon:DeepSeek-V4-Flash"),
    ("minicpm", "amd_radeon:MiniCPM5-2B"),
)

# Two rounds of every seat, so the budget is the roster size doubled. It was 8
# for four seats; raising the roster without raising the budget would silently
# truncate the cross-examination round, which is the whole point of the room.
MAX_CALLS_PER_SESSION = len(SEATS) * 2
MIN_INTERVAL_HOURS = 4
MAX_SEAT_CHARS = 800


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


class FreeZoneRoundtable:
    """Two bounded rounds of free-model discussion, receipt in the sandbox."""

    def __init__(self, root: str | Path, miner_pool: Any) -> None:
        self.root = Path(root)
        self.pool = miner_pool
        self.sandbox = FreeResearchSandbox(self.root)
        self.state_path = self.root / "roundtable_state.json"
        self.reports = self.root / "reports" / "roundtable"

    # ------------------------------------------------------------------ run

    def run_once(self, *, force: bool = False, max_tokens: int = 512) -> dict[str, Any]:
        """One roundtable session, or an honest reason why not."""
        state = self._read(self.state_path)
        gates = self._due(state, force=force)
        if not gates["due"]:
            return {
                "status": "NOT_DUE",
                "reason": gates["reason"],
                "contract_version": CONTRACT_VERSION,
                "gate_evaluation": gates,
                "production_integration": False,
            }
        topic = self._topic(state)
        if topic is None:
            result = {
                "status": "NO_TOPIC",
                "reason": "no open question and no roundtable seed available",
                "contract_version": CONTRACT_VERSION,
                "seats_available": [name for name, _ in SEATS],
                "model_calls": 0,
                "production_integration": False,
            }
            self._record_state(state, result, ran=False)
            return result

        session_id = "RT-" + topic["topic_hash"][:16].upper()
        seats, calls = [], 0
        first_round = []
        for name, model_id in SEATS:
            if calls >= MAX_CALLS_PER_SESSION:
                break
            calls += 1
            seat = self._speak(
                name,
                model_id,
                system_prompt=(
                    "Free Zone roundtable, sandbox only. You are one seat among "
                    "several free models. State your own position in at most four "
                    "sentences. Say plainly when you do not know. Never propose "
                    "production changes, task creation, or external actions."
                ),
                user_prompt=(
                    f"Question under discussion: {topic['question']}\n\n"
                    "Give your position. No preamble."
                ),
                max_tokens=max_tokens,
            )
            seats.append(seat)
            if seat["status"] == "SPOKEN":
                first_round.append(f"{name}: {seat['text']}")

        cross_round = []
        if first_round and calls < MAX_CALLS_PER_SESSION:
            digest = "\n".join(f"- {line}" for line in first_round)
            for name, model_id in SEATS:
                if calls >= MAX_CALLS_PER_SESSION:
                    break
                calls += 1
                seat = self._speak(
                    name,
                    model_id,
                    system_prompt=(
                        "Free Zone roundtable, sandbox only. Other free models have "
                        "spoken. In at most four sentences: what do you agree with, "
                        "what do you dispute, and what single piece of evidence would "
                        "settle it? Never propose production changes."
                    ),
                    user_prompt=(
                        f"Question under discussion: {topic['question']}\n\n"
                        f"What the other seats said:\n{digest}\n\n"
                        "Your cross-examination."
                    ),
                    max_tokens=max_tokens,
                )
                seat["round"] = 2
                seats.append(seat)
                if seat["status"] == "SPOKEN":
                    cross_round.append(f"{name}: {seat['text']}")

        spoken = [s for s in seats if s["status"] == "SPOKEN"]
        agreement = self._agreement(cross_round)
        session = {
            "contract_version": CONTRACT_VERSION,
            "sandbox_contract_version": SANDBOX_CONTRACT,
            "session_id": session_id,
            "at": _iso(_now()),
            "topic": topic,
            "seats": seats,
            "seats_spoken": len(spoken),
            "seats_requested": len(SEATS) * (2 if cross_round else 1),
            "model_calls": calls,
            "call_budget": MAX_CALLS_PER_SESSION,
            "agreement": agreement,
            "transcript_retention": "bounded_sandbox_local",
            "max_seat_chars": MAX_SEAT_CHARS,
            "production_integration": False,
            "taskpool_mutated": False,
            "automatic_promotion": False,
        }
        session["session_hash"] = _digest(session)

        report_path = self._write_session(session)
        experiment = self._record_experiment(session)

        result = {
            "status": "ROUNDTABLE_RECORDED",
            "contract_version": CONTRACT_VERSION,
            "session_id": session_id,
            "topic_hash": topic["topic_hash"],
            "topic_source": topic["source"],
            "seats_spoken": len(spoken),
            "model_calls": calls,
            "agreement": agreement,
            "report": str(report_path),
            "experiment_id": experiment["experiment_id"],
            "record_hash": experiment["record_hash"],
            "distillation_status": experiment["distillation_status"],
            "production_integration": False,
        }
        self._record_state(state, result, ran=True, topic_hash=topic["topic_hash"],
                           session_hash=session["session_hash"])
        return result

    # --------------------------------------------------------------- seats

    def _speak(self, name: str, model_id: str, *, system_prompt: str,
               user_prompt: str, max_tokens: int) -> dict[str, Any]:
        started = _now()
        try:
            response = self.pool.chat(
                task_type="free_exploration",
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                selected_spec=ModelSpec.from_id(model_id),
                # One attempt: a pinned seat must not spend the session budget
                # retrying itself, and must never be replaced by a paid route.
                max_retries=1,
                max_tokens=max_tokens,
                data_boundary={"data_class": "PUBLIC"},
            )
        except Exception as exc:  # a seat must never take down the session
            return {
                "seat": name, "model": model_id, "round": 1, "status": "UNAVAILABLE",
                "error_class": type(exc).__name__,
                "error": str(exc)[:200],
                "latency_ms": int((_now() - started).total_seconds() * 1000),
                "text": "", "text_sha256": "", "chars": 0,
            }
        content = str(response.get("content", "") or "")
        served = bool(response.get("success")) and content.strip() != ""
        text = content.strip()[:MAX_SEAT_CHARS]
        return {
            "seat": name,
            "model": model_id,
            "served_by": str(response.get("model", "")),
            "provider": str(response.get("provider", "")),
            "round": 1,
            "status": "SPOKEN" if served else "UNAVAILABLE",
            "error": str(response.get("error", ""))[:200] if not served else "",
            "latency_ms": int(response.get("latency_ms") or 0),
            "text": text,
            "text_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
            "chars": len(content),
        }

    @staticmethod
    def _agreement(round_two: list[str]) -> dict[str, Any]:
        """Agreement is a reading of the transcript, never a verified fact."""
        if not round_two:
            return {"status": "NOT_ASSESSED", "reason": "no cross round ran"}
        blob = " ".join(round_two).lower()
        markers = ("agree", "dispute", "disagree", "i do not know", "uncertain", "evidence")
        hits = {m: blob.count(m) for m in markers}
        return {
            "status": "READ_FROM_TRANSCRIPT",
            "method": "marker_count_only",
            "markers": hits,
            "dissent_markers": hits.get("dispute", 0) + hits.get("disagree", 0),
            "verified": False,
        }

    # --------------------------------------------------------------- topic

    def _topic(self, state: Mapping[str, Any]) -> dict[str, Any] | None:
        """Pick an honest question: an explicit seed first, else an open one.

        Roundtable seeds live in their own ``inbox/roundtable`` channel, so the
        model shift - which scans the flat inbox for semantic seeds - never
        counts a roundtable seed as an invalid one. Deriving from a distillation
        could otherwise feed the sandbox its own output forever, so a topic that
        has already been discussed is skipped.
        """
        done = set(state.get("completed_topic_hashes", []))
        channel = self.root / "inbox" / "roundtable"
        seed_paths = sorted(channel.glob("*.json")) if channel.is_dir() else []
        # Legacy: flat inbox files named *roundtable* remain readable.
        seed_paths += sorted((self.root / "inbox").glob("*roundtable*.json"))
        for path in seed_paths:
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
        question = str(payload.get("question") or payload.get("counterexample_question") or "").strip()
        if len(question) < 12:
            return None
        return self._topic_record(question, f"seed:{path.name}", str(payload.get("source_ref", "")))

    def _open_questions(self, done: set[str]) -> list[dict[str, Any] | None]:
        """Newest open questions, excluding this stage's own output.

        A roundtable files its transcript as an OPEN_QUESTION, so without this
        guard the next session would rediscover its own transcript as a fresh
        topic and the sandbox would feed on its exhaust forever - the same
        failure the model shift guards against for derived seeds.
        """
        directory = self.root / "distillations"
        if not directory.is_dir():
            return []
        found: list[dict[str, Any] | None] = []
        for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(record, Mapping) or record.get("status") != "OPEN_QUESTION":
                continue
            if self._from_roundtable(record):
                continue
            pattern = str(record.get("pattern", "")).strip()
            if not pattern:
                continue
            topic = self._topic_record(pattern, f"open_question:{record.get('experiment_id', '')}", "")
            if topic and topic["topic_hash"] not in done:
                found.append(topic)
                if len(found) >= 3:
                    break
        return found

    def _from_roundtable(self, distillation: Mapping[str, Any]) -> bool:
        """True when this distillation came out of a roundtable turn."""
        experiment_id = str(distillation.get("experiment_id", ""))
        if not experiment_id:
            return False
        candidates = [self.sandbox.experiments / f"{experiment_id}.json",
                      self.sandbox.quarantine / f"{experiment_id}.json"]
        for candidate in candidates:
            try:
                experiment = json.loads(candidate.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            metadata = experiment.get("metadata") if isinstance(experiment, Mapping) else None
            if isinstance(metadata, Mapping) and metadata.get("source_kind") == "free_zone_roundtable":
                return True
        return False

    @staticmethod
    def _topic_record(question: str, source: str, source_ref: str) -> dict[str, Any]:
        normalized = " ".join(question.split())
        return {
            "question": normalized[:400],
            "topic_hash": hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
            "source": source,
            "source_ref": source_ref,
        }

    # ------------------------------------------------------------ retention

    def _record_experiment(self, session: Mapping[str, Any]) -> dict[str, Any]:
        """Hand the transcript to the existing sandbox record + distillation.

        Free talk is never a PASS by itself, so the outcome is INCONCLUSIVE and
        the existing distillation rule files it as an OPEN_QUESTION.  A round
        table that converged is still a hypothesis, not production evidence.
        """
        experiment_id = "EXP-" + session["session_id"]
        transcript = {
            "seats": [
                {"seat": s["seat"], "round": s["round"], "status": s["status"],
                 "model": s["model"], "text": s["text"], "text_sha256": s["text_sha256"]}
                for s in session["seats"]
            ],
            "agreement": session["agreement"],
            "session_hash": session["session_hash"],
        }
        record = self.sandbox.record_experiment(
            experiment_id=experiment_id,
            hypothesis=session["topic"]["question"],
            method="two bounded free-model rounds with cross-examination",
            outcome="INCONCLUSIVE",
            evidence={
                "session_hash": session["session_hash"],
                "seats_spoken": session["seats_spoken"],
                "model_calls": session["model_calls"],
                "transcript": transcript,
            },
            metadata={
                "source_kind": "free_zone_roundtable",
                "source_ref": session["topic"]["source"],
                "free_zone_only": True,
                "automatic_model_call": True,
                "paid_provider_used": any(
                    str(s.get("provider", "")).lower() in {"oneapi", "oneapi_free", "glm", "nim", "github_models"}
                    for s in session["seats"]
                ),
            },
        )
        distilled = self.sandbox.distill(experiment_id)
        return {
            "experiment_id": experiment_id,
            "record_hash": record["record_hash"],
            "distillation_status": distilled.get("status"),
        }

    def _write_session(self, session: Mapping[str, Any]) -> Path:
        self.reports.mkdir(parents=True, exist_ok=True)
        target = self.reports / f"{session['session_id']}.json"
        self._write(target, session)
        self._write(self.reports / "roundtable_latest.json", session)
        return target

    # ----------------------------------------------------------------- due

    def _due(self, state: Mapping[str, Any], *, force: bool) -> dict[str, Any]:
        """Name every gate, so a silent skip is distinguishable from idle."""
        from .stage_gates import evaluate_gates

        now = _now()
        if self.pool is None:
            gates = {
                "miner_pool_present": (False, "miner pool not wired in this process"),
                "cooldown_elapsed": (True, "not evaluated without a pool"),
                "budget_available": (True, "not evaluated without a pool"),
            }
            passed, blocking = evaluate_gates(gates)
            return {"due": False, "reason": "MINER_POOL_ABSENT", "at": _iso(now),
                    "gates": {k: {"passed": v[0], "detail": v[1]} for k, v in gates.items()},
                    "decision": blocking}

        if force:
            gates = {
                "miner_pool_present": (True, "pool present"),
                "cooldown_elapsed": (True, "forced by caller"),
                "budget_available": (True, "forced by caller"),
            }
        else:
            last = str(state.get("last_session_at", ""))
            elapsed, detail = True, "no prior session"
            if last:
                try:
                    waited = now - datetime.fromisoformat(last)
                    elapsed = waited >= timedelta(hours=MIN_INTERVAL_HOURS)
                    detail = f"{waited.total_seconds() / 3600:.1f}h since last session"
                except ValueError:
                    elapsed, detail = True, "unreadable timestamp treated as elapsed"
            sessions_today = sum(
                1 for stamp in state.get("recent_sessions", [])
                if str(stamp).startswith(now.strftime("%Y-%m-%d"))
            )
            gates = {
                "miner_pool_present": (True, "pool present"),
                "cooldown_elapsed": (elapsed, detail),
                "budget_available": (sessions_today < MAX_CALLS_PER_SESSION,
                                     f"{sessions_today} sessions today, cap {MAX_CALLS_PER_SESSION}"),
            }
        passed, blocking = evaluate_gates(gates)
        return {
            "due": passed,
            "reason": "GO" if passed else f"BLOCKED_BY_{blocking}",
            "at": _iso(now),
            "gates": {name: {"passed": ok, "detail": text} for name, (ok, text) in gates.items()},
            "decision": blocking,
        }

    def _record_state(self, state: dict[str, Any], result: Mapping[str, Any], *,
                      ran: bool, topic_hash: str = "", session_hash: str = "") -> None:
        if topic_hash:
            done = set(state.get("completed_topic_hashes", []))
            done.add(topic_hash)
            state["completed_topic_hashes"] = sorted(done)
        if session_hash:
            state["last_session_hash"] = session_hash
        if ran:
            state["last_session_at"] = _iso(_now())
            recent = [s for s in state.get("recent_sessions", []) if s]
            recent.append(_iso(_now()))
            state["recent_sessions"] = recent[-16:]
        state["last_roundtable"] = {
            "status": result.get("status"),
            "at": _iso(_now()),
            "session_id": result.get("session_id", ""),
            "seats_spoken": result.get("seats_spoken", 0),
            "model_calls": result.get("model_calls", 0),
            "production_integration": False,
        }
        self._write(self.state_path, state)

    # ----------------------------------------------------------------- io

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
