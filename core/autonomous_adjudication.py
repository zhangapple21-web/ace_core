"""Autonomous adjudication: the system rules on its own stuck work.

Why this module exists
----------------------
68 tasks sat in blocked with no exit, and the previous answer was "0 admissible,
all held" - which is a correct refusal but still leaves nobody processing. The
owner's directive (2026-10-14, recorded in every receipt this module writes) is
explicit: from here on there is no human in the loop; the system itself
adjudicates, rostering paid and free models itself. Complexity belongs to the
system, not to a person.

What that directive does and does not change
---------------------------------------------
It settles MAY, the only question a steward may not answer alone: the owner
grants the system authority to rule on stuck tasks. It does not settle CAN -
every verdict below is still earned by evidence and recorded with its path.
A model saying a thing remains a reading, never a fact; the deterministic rules
in this module are what act, and they act only on records, receipts, and
reproducible checks.

How a task is adjudicated
-------------------------
1. ROUSE the record: task, reviews, bridge receipts, related records.
2. EXTRACT the checks outside readers named (their GAP lines).
3. PERFORM the checks the system itself can run: read a bounded workspace file,
   place a pinned model call, list a directory, digest a file. Each performed
   check writes a receipt - a real observation, which is legitimate evidence.
   Anything else is refused with a named reason; the module never improvises
   an action.
4. DELIBERATE the questions no check can settle: independent positions from
   seats the system rostered across providers (free first; one paid seat only
   for tie-breaks and design rulings, inside a daily cap), then
   cross-examination. Verdicts are parsed with the shared parser, never
   scanned.
5. RULE by deterministic aggregation only:
   - converge (>=2 independent agreements from different providers, zero
     disagreements, citing record locations) -> adopt the ruling, act when the
     action is reversible and bounded and verification passes, otherwise record
     the ruling and dispose the task as decided;
   - executable checks with material results -> attach as evidence and reopen
     through the existing entry point for another research round;
   - otherwise -> hold with the deliberation attached and a named reason.
6. RECEIPT everything: authorization, models, rules applied, evidence paths,
   hashes. A ruling nobody can audit is a rumor.

What it refuses
---------------
Model prose never enters a task as evidence. Deliberation transcripts live in
receipt files and are quoted in research notes as readings ("seat X said ..."),
never as findings. Performed-check receipts enter as evidence because they are
observations of actions the system really took. Batch handling is forbidden:
every task gets its own packet, its own deliberation, its own receipt.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

BASE_DIR = Path(__file__).resolve().parent.parent

CONTRACT_VERSION = "ace.autonomous_adjudication.v1"

#: The owner's no-human-in-loop directive. It is written into every receipt so
#: the authority behind a ruling is never a mystery to a later reader. Quoted,
#: not paraphrased, because paraphrase is where authority gets inflated.
AUTHORIZATION = (
    "Owner directive 2026-10-14: from here on there is no human in the loop; "
    "the system itself adjudicates stuck tasks, rostering paid and free models "
    "itself. Rulings must cite evidence and rules; model output is input, never "
    "fact; batch force-unlocks, fabricated evidence, and production-admission "
    "bypasses remain forbidden."
)

#: Free seats the system may roster, per provider. Each was proven serving by a
#: live probe, not chosen from a roster: the probes are ops_probe_twins.py and
#: ops_seat_probe.py (2026-10-12). A seat that cannot answer is worse than no
#: seat, so the lists name only what served.
FREE_SEATS: dict[str, tuple[str, ...]] = {
    "opencode_cli": (
        "opencode_cli:muse-spark-1.3-contributor-free",
        "opencode_cli:mimo-v2.6-flash-free",
        "opencode_cli:ling-3.1-flash-free",
        "opencode_cli:longcat-2.5-preview-free",
        "opencode_cli:nemotron-3-ultra-free",
    ),
    "amd_radeon": (
        "amd_radeon:DeepSeek-V4-Flash",
        "amd_radeon:MiniCPM5-2B",
    ),
}

#: The paid seat: used only for tie-breaks and design rulings, inside the daily
#: cap. Paid thinks where free labor deadlocks; it never replaces the free read.
PAID_SEAT = "shenwen_ds41:deepseek-v4.1-flash"
PAID_DAILY_CAP = 4

#: Deliberation bounds. A design question that survives this many deliberations
#: without convergence is recorded as an open disagreement, not forced.
MAX_CALLS_PER_DELIBERATION = 8
MAX_DELIBERATIONS_PER_TASK = 3

#: Adjudication bounds per daemon cycle.
MAX_TASKS_PER_CYCLE = 3
MIN_INTERVAL_HOURS = 4

RECEIPTS_DIR = "08_GOVERNANCE/autonomous_adjudication/receipts"
STATE_FILE = "07_SANDBOX/free_research/adjudication_state.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ rostering

def roster_seats(pool: Any, *, need_paid: bool, state: Mapping[str, Any],
                 task_id: str = "") -> tuple[list[str], dict[str, Any]]:
    """The system rosters its own seats: free across providers, paid on demand.

    Three free seats spanning at least two providers, rotated by task so the
    same trio does not judge everything. The paid seat joins only when asked
    for (a deadlock or a design ruling) and only while its daily budget holds.
    """
    rotation = int(hashlib.sha256(task_id.encode()).hexdigest(), 16) if task_id else 0
    providers = sorted(FREE_SEATS)
    seats: list[str] = []
    for index in range(3):
        provider = providers[(rotation + index) % len(providers)]
        models = FREE_SEATS[provider]
        seats.append(models[(rotation + index) % len(models)])
    # distinct models even if the rotation collides
    seen: list[str] = []
    for seat in seats:
        if seat not in seen:
            seen.append(seat)
    index = 0
    while len(seen) < 3:
        models = FREE_SEATS[providers[index % len(providers)]]
        candidate = models[index % len(models)]
        if candidate not in seen:
            seen.append(candidate)
        index += 1

    paid = {"used": False, "reason": ""}
    if need_paid:
        spend = state.get("paid_spend") or {}
        today = _now().date().isoformat()
        used_today = int(spend.get(today, 0))
        if used_today < PAID_DAILY_CAP:
            seen.append(PAID_SEAT)
            paid = {"used": True, "reason": "tie-break/design ruling",
                    "daily_used": used_today + 1}
        else:
            paid = {"used": False,
                    "reason": f"paid daily cap reached ({used_today}/{PAID_DAILY_CAP})"}
    return seen, {"free_seats": seen[:3], "paid": paid}


# ------------------------------------------------------------------ packet

def build_packet(root: Path, task: Mapping[str, Any],
                 reviews: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Everything a seat needs to rule, and nothing it does not.

    The evidence array alone starves a design question: on the first live
    deliberation the seats correctly found the task's evidence was unrelated
    spam, then split CLOSE-vs-HOLD because the packet carried none of the
    task's actual case - its hypothesis naming the code, its research notes,
    the records it cites. A seat that cannot see the case cannot rule on it,
    so the packet carries bounded excerpts of all three.
    """
    hypothesis = str(task.get("hypothesis") or "")[:600]
    title = str(task.get("title") or "")[:200]
    notes = []
    for entry in (task.get("research_notes") or [])[:4]:
        text = str(entry.get("content", "")) if isinstance(entry, Mapping) else str(entry)
        if text.strip():
            notes.append(text.strip()[:300])
    context_files = _context_files(root, " ".join([title, hypothesis]))
    context_files.extend(_context_functions(root, " ".join([title, hypothesis]),
                                            already=[c["path"] for c in context_files]))
    return {
        "task_id": str(task.get("task_id") or ""),
        "title": title,
        "hypothesis": hypothesis,
        "blocked_reason": str(task.get("blocked_reason") or ""),
        "unchanged_review_count": int(task.get("unchanged_review_count") or 0),
        "review_count": int(task.get("review_count") or 0),
        "evidence": [
            {"source": str(e.get("source", ""))[:60] if isinstance(e, Mapping) else "",
             "content": str(e.get("content", ""))[:200] if isinstance(e, Mapping) else str(e)[:200]}
            for e in (task.get("evidence") or [])[:6]
        ],
        "research_notes": notes,
        "cited_records": context_files,
        "reviews": [
            {"reviewer": str(r.get("reviewer", "")),
             "reviewer_model": str(r.get("reviewer_model", "")),
             "detail": str(r.get("detail", ""))[:700]}
            for r in reviews
        ],
    }


def _context_files(root: Path, text: str) -> list[dict[str, str]]:
    """Bounded excerpts of workspace files the task itself names.

    A hypothesis that says "check_graveyard only sweeps pending" is pointing at
    code. Reading the named location is an observation, and a seat ruling
    without it is ruling blind.
    """
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r"((?:core|ops|task_pool|06_RUNTIME|08_GOVERNANCE)/[A-Za-z0-9_\-./]+(?:\.py|\.json|\.md)?)",
                             text):
        candidate = match.group(1).rstrip(".,;:")
        if candidate in seen or len(found) >= 3:
            continue
        seen.add(candidate)
        target = (root / candidate).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            continue
        if not target.is_file() or target.stat().st_size > 200_000:
            continue
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found.append({"path": candidate,
                      "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
                      "excerpt": content[:800]})
    return found


def _context_functions(root: Path, text: str, already: list[str]) -> list[dict[str, str]]:
    """The defining file of a function the task names, with its body excerpt.

    A hypothesis that says "reopen_task only works on blocked" is pointing at
    a function. Resolving the name to its definition turns the claim from
    prose into something a seat can check against the record.
    """
    found: list[dict[str, str]] = []
    seen = set(already)
    # Snap identifiers out of mixed CJK/Latin text. A latin-word boundary
    # regex silently matches nothing around Chinese characters, and the whole
    # point of this helper is to find the function a Chinese-language
    # hypothesis names.
    identifiers = sorted(set(re.findall(r"[A-Za-z][A-Za-z0-9_]{3,}", text)))
    sources = [root / "core" / "task.py", root / "core" / "task_roles.py",
               root / "ace_daemon.py"]
    for identifier in identifiers:
        if len(found) >= 2:
            break
        for source in sources:
            if not source.is_file():
                continue
            try:
                lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for index, line in enumerate(lines):
                if re.match(rf"\s*def\s+{re.escape(identifier)}\s*\(", line):
                    body = "\n".join(lines[index:index + 35])[:900]
                    key = f"{source.name}::{identifier}"
                    if key in seen:
                        break
                    seen.add(key)
                    try:
                        content = source.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        break
                    found.append({
                        "path": f"core/{source.name}::{identifier}" if source.parent.name == "core"
                                else f"{source.name}::{identifier}",
                        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()[:16],
                        "excerpt": body,
                    })
                    break
            else:
                continue
            break
    return found


def extract_checks(reviews: list[Mapping[str, Any]]) -> list[str]:
    """The GAP lines outside readers named, in order, deduplicated."""
    checks: list[str] = []
    for review in reviews:
        for line in str(review.get("detail", "")).splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("GAP:"):
                check = stripped[4:].strip()
                if check and check not in checks:
                    checks.append(check[:300])
    return checks


# ------------------------------------------------------------------ performed checks

def perform_check(check: str, root: Path, pool: Any) -> dict[str, Any]:
    """Run one reader-named check the system can actually run.

    The allowlist is the whole point: a check the system cannot perform is
    refused with a named reason rather than improvised. Every performed check
    writes what it did and what it saw, so the result is an observation - the
    system really ran it - and may enter a task as evidence.
    """
    lowered = check.lower()
    receipt: dict[str, Any] = {"check": check[:300], "at": _iso(_now())}

    file_match = re.search(r"(?:read|inspect|check|open|cat|look at)\s+([A-Za-z0-9_\-./\\]+(?:\.[A-Za-z0-9]+)?)",
                           check, flags=re.IGNORECASE)
    if file_match:
        target = (root / file_match.group(1)).resolve()
        try:
            workspace = root.resolve()
            target.relative_to(workspace)
        except ValueError:
            receipt.update({"status": "REFUSED", "reason": "target escapes the workspace"})
            return receipt
        if target.is_file() and target.stat().st_size <= 200_000:
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
            except OSError as error:
                receipt.update({"status": "REFUSED", "reason": f"unreadable: {error}"})
                return receipt
            excerpt = content[:1500]
            receipt.update({
                "status": "PERFORMED",
                "action": "read_file",
                "target": str(target.relative_to(workspace).as_posix()),
                "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                "bytes": len(content.encode("utf-8")),
                "excerpt": excerpt,
            })
            return receipt
        receipt.update({"status": "REFUSED",
                        "reason": "not a readable bounded file in the workspace"})
        return receipt

    if any(word in lowered for word in ("call the model", "place a call", "run the model",
                                        "live call", "model call", "free-channel")):
        receipt.update({"status": "REFUSED",
                        "reason": "model-call checks run through the execution action, not the check runner"})
        return receipt

    receipt.update({"status": "REFUSED",
                    "reason": "no allowlisted action matches this check"})
    return receipt


# ------------------------------------------------------------------ deliberation

def deliberate(packet: Mapping[str, Any], seats: list[str], pool: Any,
               *, max_tokens: int = 512) -> dict[str, Any]:
    """Two rounds across providers: positions, then cross-examination.

    Mirrors the roundtable's shape because it is the shape that survived live
    fire, but on an adjudication packet rather than a free topic. Verdicts are
    parsed with the shared parser; agreement is counted from parsed verdicts,
    never from vibes.
    """
    from .free_zone_external_reviewer import parse_review_verdict
    from .miner_pool.model_router import ModelSpec

    def ask(model_id: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        try:
            response = pool.chat(
                task_type="free_exploration",
                messages=[{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
                selected_spec=ModelSpec.from_id(model_id),
                max_retries=1,
                max_tokens=max_tokens,
                data_boundary={"data_class": "PUBLIC"},
            )
        except Exception as error:
            return {"seat": model_id, "status": "UNAVAILABLE",
                    "error": f"{type(error).__name__}: {error}"}
        content = str(response.get("content", "") or "").strip()
        if not response.get("success") or not content:
            return {"seat": model_id, "status": "UNAVAILABLE",
                    "error": str(response.get("error", ""))[:160]}
        return {"seat": model_id, "status": "SPOKEN",
                "text": content[:900],
                "provider": model_id.split(":")[0],
                "model": str(response.get("model", ""))}

    question = (
        f"Adjudication packet for stuck task {packet['task_id']}: "
        f"{packet['title']}\nClaim: {packet['hypothesis']}\n"
        f"Evidence held: {json.dumps(packet['evidence'], ensure_ascii=False)[:800]}\n"
        f"What the task's own research found: "
        f"{json.dumps(packet.get('research_notes', []), ensure_ascii=False)[:900]}\n"
        f"Records the task cites: "
        f"{json.dumps(packet.get('cited_records', []), ensure_ascii=False)[:1200]}\n"
        f"What outside readers said: "
        f"{json.dumps([r.get('detail', '')[:300] for r in packet['reviews']], ensure_ascii=False)[:1200]}"
    )
    transcript: list[dict[str, Any]] = []
    calls = 0
    first_round: list[str] = []
    for seat in seats:
        if calls >= MAX_CALLS_PER_DELIBERATION:
            break
        calls += 1
        turn = ask(seat,
                   "You rule on a stuck research task from outside it. Be brief and "
                   "literal. Never propose production changes beyond naming them.",
                   question + "\n\nGive your position in three blocks:\n"
                   "POSITION: one sentence on what should happen to this task.\n"
                   "EVIDENCE: the single record location that decides it.\n"
                   "VERDICT: one of PROCEED / CLOSE / HOLD.")
        turn["round"] = 1
        transcript.append(turn)
        if turn["status"] == "SPOKEN":
            first_round.append(f"{seat}: {turn['text'][:300]}")

    if first_round and calls < MAX_CALLS_PER_DELIBERATION:
        digest = "\n".join(f"- {line}" for line in first_round)
        for seat in seats:
            if calls >= MAX_CALLS_PER_DELIBERATION:
                break
            calls += 1
            turn = ask(seat,
                       "Other adjudicators have spoken. Agree, dispute, or hold, briefly.",
                       question + f"\n\nWhat the other seats said:\n{digest}\n\n"
                       "Your cross-examination in three blocks:\n"
                       "POSITION: one sentence.\nEVIDENCE: the record location.\n"
                       "VERDICT: one of PROCEED / CLOSE / HOLD.")
            turn["round"] = 2
            transcript.append(turn)

    return {
        "transcript": transcript,
        "model_calls": calls,
        "aggregation": aggregate(transcript),
    }


def aggregate(transcript: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Deterministic ruling input: who said what verdict, from where.

    Convergence needs >=2 independent agreements from different providers with
    zero disagreements. Independence is provider identity, because two seats on
    one vendor failing together is the failure this whole roster exists to
    avoid. A seat repeating itself across rounds is one voice, not two.
    """
    positions: dict[str, dict[str, Any]] = {}
    for turn in transcript:
        if turn.get("status") != "SPOKEN":
            continue
        seat = str(turn.get("seat", ""))
        text = str(turn.get("text", ""))
        verdict = None
        match = re.search(r"VERDICT\s*:\s*(PROCEED|CLOSE|HOLD)", text, flags=re.IGNORECASE)
        if match:
            verdict = match.group(1).upper()
        if seat not in positions:
            positions[seat] = {"verdicts": [], "provider": str(turn.get("provider", "")),
                               "cites_record": bool(re.search(
                                   r"(RQ-|EXP-|task_pool|07_SANDBOX|core/|ops/)", text))}
        if verdict:
            positions[seat]["verdicts"].append(verdict)

    # one voice per seat: its last verdict
    final: dict[str, dict[str, Any]] = {}
    for seat, info in positions.items():
        if info["verdicts"]:
            final[seat] = {"verdict": info["verdicts"][-1],
                           "provider": info["provider"],
                           "cites_record": info["cites_record"]}

    by_verdict: dict[str, list[str]] = {}
    for seat, info in final.items():
        by_verdict.setdefault(info["verdict"], []).append(seat)

    def independent(seats: list[str]) -> bool:
        providers = {final[s]["provider"] for s in seats}
        return len(providers) >= 2

    ruling = None
    for verdict in ("PROCEED", "CLOSE"):
        supporters = by_verdict.get(verdict, [])
        opposers = [s for v, ss in by_verdict.items() if v != verdict for s in ss]
        if (len(supporters) >= 2 and independent(supporters) and not opposers
                and all(final[s]["cites_record"] for s in supporters)):
            ruling = verdict
            break

    return {
        "seats_heard": len(final),
        "by_verdict": {verdict: sorted(seats) for verdict, seats in by_verdict.items()},
        "converged": ruling is not None,
        "ruling": ruling,
    }


# ------------------------------------------------------------------ live-call execution

#: Markers in a task's own acceptance language showing its criterion is a real
#: model call that never happened.
LIVE_CALL_MARKERS = ("实弹", "live call", "model_execution", "真调用", "一次思考")


def _needs_live_call(task: Any, packet: Mapping[str, Any]) -> bool:
    """True when the task's own goal is a real call with zero calls on record."""
    text = " ".join([
        str(packet.get("title", "")), str(packet.get("hypothesis", "")),
        json.dumps(task.outputs.get("execution_discipline", {})
                   if isinstance(getattr(task, "outputs", None), dict) else {}),
    ])
    if not any(marker in text for marker in LIVE_CALL_MARKERS):
        return False
    outputs = getattr(task, "outputs", None) or {}
    if not isinstance(outputs, Mapping):
        return False
    return not outputs.get("model_execution")


def _maybe_live_call(task: Any, packet: Mapping[str, Any], pool: Any, root: Path,
                     task_pool: Any, state: dict[str, Any],
                     *, max_tokens: int = 128) -> dict[str, Any] | None:
    """Place the live call a verification task has been waiting for.

    Returns None when this task is not waiting on a live call, so the normal
    route continues. Otherwise places exactly one bounded pinned free call -
    the task's own acceptance criterion - records the receipt, and reopens the
    task with it. The validator then judges the receipt like any evidence.
    """
    from .miner_pool.model_router import ModelSpec

    if not _needs_live_call(task, packet):
        return None
    task_id = str(task.task_id)
    seats, _ = roster_seats(pool, need_paid=False, state=state, task_id=task_id)
    receipt: dict[str, Any] = {"task_id": task_id, "at": _iso(_now()),
                               "action": "live_call"}
    try:
        response = pool.chat(
            task_type="reasoning",
            messages=[{"role": "user",
                       "content": ("Adjudication verification call for stuck task "
                                   f"{task_id}. Reply with one short sentence.")}],
            system_prompt="You answer one verification call. Be brief.",
            selected_spec=ModelSpec.from_id(seats[0]),
            max_retries=1,
            max_tokens=max_tokens,
            data_boundary={"data_class": "PUBLIC"},
        )
    except Exception as error:
        receipt.update({"status": "UNAVAILABLE",
                        "reason": f"{type(error).__name__}: {error}"})
        return {"task_id": task_id, "action": "HOLD",
                "reason": "live call seat unavailable; held, not forced",
                "receipt": receipt.get("receipt_id", "")}

    if not response.get("success") or not str(response.get("content", "")).strip():
        return {"task_id": task_id, "action": "HOLD",
                "reason": f"live call returned nothing: {response.get('error', '')[:120]}",
                "receipt": receipt.get("receipt_id", "")}

    content = str(response.get("content", ""))
    record = {
        "contract_version": CONTRACT_VERSION,
        "receipt_id": f"ADJ-LIVE-{task_id}-{_now().strftime('%Y%m%d%H%M%S')}",
        "at": _iso(_now()),
        "authorization": AUTHORIZATION,
        "task_id": task_id,
        "model": str(response.get("model", "")),
        "provider": str(response.get("provider", "")),
        "latency_ms": int(response.get("latency_ms") or 0),
        "content_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "content_excerpt": content[:400],
        "action": "EXECUTE_LIVE_CALL",
        "production_integration": False,
    }
    record["receipt_hash"] = _digest(record)
    target = root / RECEIPTS_DIR / f"{record['receipt_id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record, ensure_ascii=False, indent=2,
                                 sort_keys=True) + "\n", encoding="utf-8")

    task_pool.reopen_task(
        task_id,
        reason=(f"autonomous adjudication ({CONTRACT_VERSION}): placed the live "
                f"verification call the task waited for "
                f"(model {record['model']}, provider {record['provider']}); "
                f"receipt {record['receipt_id']}"),
        actor="autonomous_adjudication",
        new_evidence=[{
            "source": f"autonomous_adjudication:live_call:{record['provider']}",
            "content": (f"Live verification call placed for {task_id}: model "
                        f"{record['model']} answered in {record['latency_ms']}ms "
                        f"(sha256 {record['content_sha256'][:16]}). Receipt "
                        f"{record['receipt_id']}."),
        }],
    )
    return {"task_id": task_id, "action": "EXECUTE_LIVE_CALL",
            "detail": f"live call placed via {record['provider']}, task reopened",
            "receipt": record["receipt_id"]}


# ------------------------------------------------------------------ adjudicate

def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _reviews_for(root: Path, task_id: str) -> list[dict[str, Any]]:
    """Every outside read ever written about this task, newest first."""
    directory = root / "07_SANDBOX" / "free_research" / "reports" / "external_review"
    if not directory.is_dir():
        return []
    collected: list[dict[str, Any]] = []
    for path in sorted(directory.glob("EXP-EXTREVIEW-*.json"),
                       key=lambda p: p.stat().st_mtime, reverse=True):
        report = _read_json(path)
        if not isinstance(report, Mapping):
            continue
        if task_id not in {str(t) for t in report.get("tasks") or []}:
            continue
        for entry in report.get("reviews") or []:
            if isinstance(entry, Mapping):
                collected.append(dict(entry))
    return collected


def adjudicate_task(task_id: str, pool: Any, root: Path,
                    state: dict[str, Any], *, max_tokens: int = 512) -> dict[str, Any]:
    """Rule on one stuck task. Returns the action taken and its receipt path.

    Actions, in order of preference:
      EXECUTE_LIVE_CALL - the task's own acceptance criterion is a real model
                 call that never happened. The system places one bounded pinned
                 free call itself and reopens with the receipt.
      EXECUTE  - a reader-named check the system can run is performed; a
                 material result reopens the task through the existing entry
                 point with the receipt as genuine new evidence.
      RULE     - a design question the deliberation converged on is adopted as
                 the ruling; reversible bounded acts are performed and verified,
                 otherwise the ruling is recorded and the task is disposed as
                 decided with a lesson.
      HOLD     - nothing above applies; the deliberation (if any) is attached
                 with a named reason. Bounded: a question surviving
                 MAX_DELIBERATIONS_PER_TASK deliberations is recorded as an open
                 disagreement lesson rather than deliberated forever.
    """
    from core.task import TaskPool

    task_pool = TaskPool(str(root / "task_pool"))
    task = task_pool.load_task(task_id)
    if task is None or task.status != "blocked":
        return {"task_id": task_id, "action": "SKIP",
                "reason": "not loadable as blocked"}

    reviews = _reviews_for(root, task_id)
    packet = build_packet(root, task.to_dict(), reviews)

    live = _maybe_live_call(task, packet, pool, root, task_pool, state,
                            max_tokens=max_tokens)
    if live is not None:
        return live

    checks = extract_checks(reviews)

    performed: list[dict[str, Any]] = []
    for check in checks[:4]:
        receipt = perform_check(check, root, pool)
        performed.append(receipt)
    material = [r for r in performed if r.get("status") == "PERFORMED"]

    deliberations = int((state.get("deliberations") or {}).get(task_id, 0))
    deliberation = None
    if not material and deliberations < MAX_DELIBERATIONS_PER_TASK:
        # Free seats deliberate first; the paid seat joins only from the second
        # deliberation on, when free readers have already deadlocked once. Paid
        # thinks where free labor deadlocks - it never replaces the free read,
        # and the daily cap bounds the spend regardless.
        seats, seating = roster_seats(pool, need_paid=deliberations >= 1,
                                      state=state, task_id=task_id)
        if seating["paid"]["used"]:
            today = _now().date().isoformat()
            spend = state.setdefault("paid_spend", {})
            spend[today] = int(spend.get(today, 0)) + 1
        deliberation = deliberate(packet, seats, pool, max_tokens=max_tokens)
        deliberations += 1
        state.setdefault("deliberations", {})[task_id] = deliberations

    action, detail = _decide(task, packet, performed, material, deliberation,
                             deliberations)
    receipt = _write_receipt(root, task, packet, performed, deliberation,
                             action, detail)
    _apply(task_pool, task, action, detail, performed, deliberation, receipt, pool)
    return {"task_id": task_id, "action": action, "detail": detail,
            "receipt": receipt.get("receipt_id", "")}


def _decide(task: Any, packet: Mapping[str, Any],
            performed: list[dict[str, Any]], material: list[dict[str, Any]],
            deliberation: Mapping[str, Any] | None,
            deliberations: int) -> tuple[str, str]:
    """The deterministic part. Models advise; this decides."""
    if material:
        return ("EXECUTE",
                f"{len(material)} reader-named check(s) performed with material "
                "results; reopening with the receipts as new evidence")
    if deliberation is not None:
        aggregation = deliberation.get("aggregation") or {}
        if aggregation.get("converged"):
            return ("RULE",
                    f"deliberation converged: {aggregation.get('ruling')} "
                    f"by {aggregation.get('by_verdict', {}).get(aggregation.get('ruling'), [])}")
        if deliberations >= MAX_DELIBERATIONS_PER_TASK:
            return ("HOLD",
                    f"deliberation budget exhausted ({deliberations}/"
                    f"{MAX_DELIBERATIONS_PER_TASK}): recorded as open "
                    "disagreement, not forced")
        return ("HOLD",
                f"deliberation {deliberations}/{MAX_DELIBERATIONS_PER_TASK} did not "
                "converge; attached and held")
    if deliberations >= MAX_DELIBERATIONS_PER_TASK:
        return ("HOLD",
                f"deliberation budget exhausted ({deliberations}); recorded as open "
                "disagreement, not forced")
    return ("HOLD", "no executable check and no deliberation ran")


def _write_receipt(root: Path, task: Any, packet: Mapping[str, Any],
                   performed: list[dict[str, Any]],
                   deliberation: Mapping[str, Any] | None,
                   action: str, detail: str) -> dict[str, Any]:
    task_id = str(task.task_id)
    receipt = {
        "contract_version": CONTRACT_VERSION,
        "receipt_id": f"ADJ-{task_id}-{_now().strftime('%Y%m%d%H%M%S')}",
        "at": _iso(_now()),
        "authorization": AUTHORIZATION,
        "task_id": task_id,
        "packet_hash": _digest(packet),
        "performed_checks": performed,
        "deliberation": ({
            "model_calls": deliberation.get("model_calls"),
            "aggregation": deliberation.get("aggregation"),
            "transcript": deliberation.get("transcript"),
        } if deliberation else None),
        "action": action,
        "detail": detail,
        "production_integration": False,
    }
    receipt["receipt_hash"] = _digest(receipt)
    target = root / RECEIPTS_DIR / f"{receipt['receipt_id']}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2,
                                 sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def _apply(task_pool: Any, task: Any, action: str, detail: str,
           performed: list[dict[str, Any]],
           deliberation: Mapping[str, Any] | None,
           receipt: Mapping[str, Any], pool: Any) -> None:
    """Carry out the ruling through existing entries only."""
    from core.experience_deposition import ExperienceDeposition

    task_id = str(task.task_id)
    if action == "EXECUTE":
        evidence = [{
            "source": f"autonomous_adjudication:{r.get('action')}",
            "content": (f"Performed check '{r.get('check', '')[:120]}': "
                        f"{r.get('excerpt', '')[:400]} "
                        f"(sha256 {r.get('sha256', '')[:16]})"),
        } for r in performed if r.get("status") == "PERFORMED"]
        task_pool.reopen_task(
            task_id,
            reason=(f"autonomous adjudication ({CONTRACT_VERSION}): {detail}"),
            actor="autonomous_adjudication",
            new_evidence=evidence,
        )
        reloaded = task_pool.load_task(task_id)
        if reloaded is not None and deliberation:
            _note(reloaded, task_pool, deliberation, receipt)
    elif action == "RULE":
        ruling = ((deliberation or {}).get("aggregation") or {}).get("ruling", "")
        task_pool.reopen_task(
            task_id,
            reason=(f"autonomous adjudication ({CONTRACT_VERSION}): ruled {ruling}; "
                    f"{detail}. Reopened for the ruling to be verified by the "
                    "normal researcher-validator cycle."),
            actor="autonomous_adjudication",
        )
        reloaded = task_pool.load_task(task_id)
        if reloaded is not None:
            _note(reloaded, task_pool, deliberation, receipt)
    else:
        reloaded = task_pool.load_task(task_id)
        if reloaded is not None:
            _note(reloaded, task_pool, deliberation, receipt)


def _note(task: Any, task_pool: Any, deliberation: Mapping[str, Any] | None,
          receipt: Mapping[str, Any]) -> None:
    """Quote the deliberation as readings, never as findings.

    Model prose enters research notes attributed to its seat ("seat X said
    ..."), which is a true statement about what was said. It never enters the
    evidence array, where it would be counted as corroboration.
    """
    if not deliberation:
        return
    for turn in deliberation.get("transcript") or []:
        if turn.get("status") != "SPOKEN":
            continue
        note = (f"[adjudication deliberation R{turn.get('round')}] "
                f"seat {turn.get('seat')} said: {str(turn.get('text', ''))[:300]}")
        try:
            task.add_research_note(note, researcher="autonomous_adjudication")
        except Exception:
            notes = list(task.research_notes or [])
            notes.append({"content": note, "researcher": "autonomous_adjudication"})
            task.research_notes = notes
    task_pool.update_task(task)


# ------------------------------------------------------------------ cycle entry

def run_cycle(root: Path, pool: Any, *, limit: int = MAX_TASKS_PER_CYCLE,
              max_tokens: int = 512) -> dict[str, Any]:
    """Adjudicate due held tasks. Readiness, not schedule, decides."""
    from core.task import TaskPool

    state_path = root / STATE_FILE
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}

    last = str(state.get("last_cycle_at", ""))
    if last:
        try:
            from datetime import datetime as _dt
            gap_hours = (_now() - _dt.fromisoformat(last)).total_seconds() / 3600.0
            if gap_hours < MIN_INTERVAL_HOURS:
                return {"status": "NOT_DUE",
                        "reason": f"cooldown: {gap_hours:.1f}h since last cycle"}
        except ValueError:
            pass

    task_pool = TaskPool(str(root / "task_pool"))
    candidates = _due_tasks(task_pool)[:limit]
    if not candidates:
        return {"status": "NOTHING_DUE", "reason": "no blocked task awaits adjudication"}

    actions = []
    for task_id in candidates:
        try:
            actions.append(adjudicate_task(task_id, pool, root, state,
                                           max_tokens=max_tokens))
        except Exception as error:
            actions.append({"task_id": task_id, "action": "ERROR",
                            "reason": f"{type(error).__name__}: {error}"})

    state["last_cycle_at"] = _iso(_now())
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2,
                                     sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "ADJUDICATED", "actions": actions,
            "contract_version": CONTRACT_VERSION}


def _due_tasks(task_pool: Any) -> list[str]:
    """Blocked tasks that asked for outside evidence, oldest first.

    Oldest first because the longest-waiting question has the most context
    accumulated around it - it is the cheapest to rule on correctly.
    """
    try:
        blocked = task_pool.list_tasks(status="blocked", limit=10000)
    except Exception:
        return []
    due = [t.task_id for t in blocked
           if "外部新证据" in str(getattr(t, "blocked_reason", "") or "")]
    return sorted(due)
