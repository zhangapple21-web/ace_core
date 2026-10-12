"""Free-zone external reviewer — the job ACE's blocked tasks are actually waiting for.

Every one of the 67 non-convergent blocked tasks carries the same verdict:
``相同证据集重复验证达到上限，等待人工或外部新证据`` — same evidence set re-verified
past its cap, waiting for a human or for **external new evidence**.

ACE's own researcher cannot supply that. Re-reading its own memory is exactly
what the cap was counting. An independent model on an unrelated provider can.

Stealing, and why: multi-agent systems that actually earn their keep stop asking
one model for a second opinion and instead route to a *different* model family
on a different account, because independence is a property of the source, not of
the prompt. That is the whole argument of this module.

What it does NOT do: it never reopens a task, never writes to TaskPool, never
promotes anything, and never lets a model's self-report become an ACE fact. It
writes one candidate review per call into the sandbox, exactly like a roundtable
transcript. The main steward then decides — through the existing
``FreeZoneRealityBridge`` and its required mapping — whether that candidate is
real evidence. An independent source is necessary for unblocking; it is not
sufficient, and this module is not where sufficiency is decided.

The contracts below are deliberately the same ones the roundtable already
proved: pinned ``selected_spec`` + ``max_retries=1`` so a seat can never fall
through to a paid route, a PUBLIC data boundary, and an honest outcome for every
verdict including "the task is not actually waiting for external evidence".
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .miner_pool.model_router import ModelSpec

CONTRACT_VERSION = "ace.free_zone_external_review.v1"

#: Substring every "waiting for outside input" verdict carries. The validator
#: writes two flavours of it -- ``等待人工或外部新证据`` for the manual-gate
#: disposition and ``等待外部新证据`` for the observe disposition -- so the
#: marker is the part they share rather than one full sentence. An earlier
#: version of this constant matched the observe wording only and therefore
#: found zero tasks in a pool where all 67 were blocked on the manual-gate one.
#: That is why it is derived from the live pool, not from reading one file.
EXTERNAL_EVIDENCE_MARKER = "外部新证据"

# Reviewers. Independence is the whole point of this job, so the roster must
# NOT be one vendor: the original lineup was all AMD, which made the sweep fail
# whenever that provider was rate-limited and made "independent" mean something
# narrower than it needs to.
#
# Chosen from a live probe on 2026-10-12 (ops_probe_twins.py for the CLI twins,
# ops_seat_probe.py for the AMD seats), not from a roster. Qwen3.8-27B answered
# with empty content and was cut; DeepSeek-V4.1 was returning 429 and is
# replaced by DeepSeek-V4-Flash which served every probe.
#
# Two vendors on purpose. A CLI twin reading ACE's stuck task from outside is
# not the same failure mode as an unrelated vendor's model, and "unrelated
# provider" is the only property that matters for external evidence.
REVIEWERS: tuple[dict[str, str], ...] = (
    {
        "name": "deepseek",
        "model": "amd_radeon:DeepSeek-V4-Flash",
        "stance": "independent re-derivation from the evidence as given",
    },
    {
        "name": "minicpm",
        "model": "amd_radeon:MiniCPM5-2B",
        "stance": "checks whether the question itself is well posed",
    },
    {
        "name": "muse",
        "model": "opencode_cli:muse-spark-1.3-contributor-free",
        "stance": "ACE's own twin reading the task from outside its own reviewers",
    },
    {
        "name": "longcat",
        "model": "opencode_cli:longcat-2.5-preview-free",
        "stance": "asks what would count as settling the claim at all",
    },
)

BLOCKED_DIR = "task_pool/blocked"
MAX_CLAIM_CHARS = 900
MAX_REVIEW_CHARS = 700

#: A reply is degenerate when its longest run of one repeated character reaches
#: this length. Live fire showed why it is needed: one AMD reviewer answered a
#: three-block request with several hundred solidus characters, and the first
#: version of this module filed that as a REVIEWED answer. Recording filler as a
#: review is worse than recording nothing, because the steward would then spend
#: real attention judging it. Degenerate replies get their own named kind.
DEGENERATE_RUN = 12


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


class FreeZoneExternalReviewer:
    """Ask unrelated free models to read a stuck task, as free-zone material."""

    def __init__(self, workspace_root: str | Path, sandbox_root: str | Path,
                 miner_pool: Any) -> None:
        self.workspace_root = Path(workspace_root)
        self.sandbox_root = Path(sandbox_root)
        self.pool = miner_pool
        self.state_path = self.sandbox_root / "external_review_state.json"

    # ---------------------------------------------------------------- run

    def run_once(self, *, force: bool = False, limit: int = 3,
                 max_tokens: int = 512) -> dict[str, Any]:
        state = self._read(self.state_path)
        done = {str(t) for t in state.get("reviewed_task_ids", [])}
        candidates = self._waiting_tasks(limit)
        fresh = [t for t in candidates if t["task_id"] not in done] or (
            candidates if force else []
        )
        if not fresh:
            result = {
                "status": "NO_TASK_WAITING",
                "reason": "no blocked task is waiting for external new evidence",
                "contract_version": CONTRACT_VERSION,
                "tasks_seen": len(candidates),
                "reviews_written": 0,
                "production_integration": False,
            }
            self._write_state(state, result)
            return result

        reviews: list[dict[str, Any]] = []
        calls = 0
        for task in fresh[:limit]:
            for reviewer in REVIEWERS:
                calls += 1
                review = self._review(task, reviewer, max_tokens)
                review["task_id"] = task["task_id"]
                review["reviewer"] = reviewer["name"]
                review["reviewer_model"] = reviewer["model"]
                reviews.append(review)
            done.add(task["task_id"])

        experiment_id = self._record(fresh[:limit], reviews)
        result = {
            "status": "EXTERNAL_REVIEW_RECORDED",
            "contract_version": CONTRACT_VERSION,
            "experiment_id": experiment_id,
            "tasks_reviewed": len(fresh[:limit]),
            "reviews_written": len(reviews),
            "model_calls": calls,
            "verdict_histogram": self._histogram(reviews),
            "production_integration": False,
            "taskpool_mutated": False,
        }
        self._write_state(state, result, done)
        return result

    # ------------------------------------------------------------ reviewers

    def _review(self, task: Mapping[str, Any], reviewer: Mapping[str, str],
                max_tokens: int) -> dict[str, Any]:
        claim = str(task.get("hypothesis") or task.get("title") or "")[:MAX_CLAIM_CHARS]
        evidence = self._evidence_text(task)
        prompt = (
            f"A stuck research task. Its own reviewers could not verify it because "
            f"they kept reading the same evidence. You are an unrelated model on an "
            f"unrelated account, reading this once.\n\n"
            f"Task: {str(task.get('title') or '')[:200]}\n"
            f"Claim: {claim}\n"
            f"Evidence it holds:\n{evidence}\n\n"
            f"Answer in this shape, three short blocks:\n"
            f"INDEPENDENT: one sentence on what the evidence actually supports.\n"
            f"GAP: the single most important thing a fresh verifier should check.\n"
            f"VERDICT: one of SUPPORTED / CONTRADICTED / CANNOT_ASSESS.\n"
            f"Say plainly if you cannot assess it. Never propose production changes."
        )
        raw = self._chat(
            reviewer["model"],
            prompt,
            system_prompt=(
                "You are an independent reviewer reading a stuck research task "
                "once, from outside. You are not its researcher and you did not "
                "gather its evidence. Be brief and literal."
            ),
            max_tokens=max_tokens,
        )
        if not raw:
            return {"status": "UNAVAILABLE", "stance": reviewer["stance"],
                    "detail": "provider returned nothing", "text": ""}
        if self._degenerate(raw):
            # Named, not silently dropped: a free reviewer that degenerates is a
            # fact about that seat, and it stays visible so a sweep can tell a
            # dead seat from a working one.
            return {"status": "DEGENERATE", "stance": reviewer["stance"],
                    "detail": raw[:MAX_REVIEW_CHARS], "text": ""}
        return {
            "status": "REVIEWED",
            "stance": reviewer["stance"],
            "detail": raw[:MAX_REVIEW_CHARS],
            "text": raw[:MAX_REVIEW_CHARS],
        }

    @staticmethod
    def _degenerate(raw: str) -> bool:
        """True when the reply is repetition rather than an answer.

        A free preview model occasionally answers a structured prompt by echoing
        a filler run. Longest-single-character-run catches that without parsing
        the reply and without a hardcoded notion of what a good answer looks like.
        """
        longest = run = 1
        for index in range(1, len(raw)):
            run = run + 1 if raw[index] == raw[index - 1] else 1
            longest = max(longest, run)
        return longest >= DEGENERATE_RUN

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
        except Exception as error:  # one reviewer must never sink the sweep
            return f"___UNAVAILABLE___:{type(error).__name__}:{str(error)[:120]}"
        if not response.get("success"):
            return ""
        return str(response.get("content", "") or "").strip()

    # ----------------------------------------------------------- task intake

    def _waiting_tasks(self, limit: int) -> list[dict[str, Any]]:
        """Blocked tasks whose own verdict says: waiting for external evidence."""
        directory = self.workspace_root / BLOCKED_DIR
        if not directory.is_dir():
            return []
        waiting: list[dict[str, Any]] = []
        for path in sorted(directory.glob("*.json"), key=lambda p: p.stat().st_mtime,
                           reverse=True):
            try:
                task = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if not isinstance(task, Mapping):
                continue
            reason = str(task.get("blocked_reason") or "")
            if EXTERNAL_EVIDENCE_MARKER not in reason:
                continue
            if "重复验证达到上限" not in reason:
                continue
            waiting.append(task)
            if len(waiting) >= limit:
                break
        return waiting

    @staticmethod
    def _evidence_text(task: Mapping[str, Any]) -> str:
        lines = []
        for item in (task.get("evidence") or [])[:5]:
            if isinstance(item, Mapping):
                content = str(item.get("content", ""))[:180]
                source = str(item.get("source", ""))[:40]
                lines.append(f"- [{source}] {content}")
        if not lines:
            return "(the task holds no evidence)"
        return "\n".join(lines)

    @staticmethod
    def _histogram(reviews: list[Mapping[str, Any]]) -> dict[str, int]:
        histogram: dict[str, int] = {}
        for review in reviews:
            status = str(review.get("status", ""))
            if status in {"UNAVAILABLE", "DEGENERATE"}:
                histogram[status] = histogram.get(status, 0) + 1
                continue
            detail = str(review.get("detail", "")).upper()
            for verdict in ("SUPPORTED", "CONTRADICTED", "CANNOT_ASSESS"):
                if verdict in detail:
                    histogram[verdict] = histogram.get(verdict, 0) + 1
                    break
            else:
                histogram["REVIEWED_WITHOUT_VERDICT"] = (
                    histogram.get("REVIEWED_WITHOUT_VERDICT", 0) + 1
                )
        return histogram

    # ------------------------------------------------------------- recording

    def _record(self, tasks: list[Mapping[str, Any]],
                reviews: list[Mapping[str, Any]]) -> str:
        from .free_research_sandbox import FreeResearchSandbox, _digest

        task_ids = sorted({str(t.get("task_id")) for t in tasks})
        # The id must distinguish one sweep of the same tasks from another. An
        # id derived from the task ids alone collides on any re-run, and the
        # sandbox refuses a duplicate id - so the second sweep of the same two
        # tasks crashed instead of recording. Sweeping a task again is not an
        # error, it is how an independent read gets retried.
        #
        # Microseconds plus a random suffix, not seconds: a sweep completes in
        # well under a second, so a second-resolution stamp re-collides on the
        # very next run and recreates the bug it is here to prevent.
        sweep_seed = "|".join(task_ids) + "@" + _now().isoformat() + ":" + uuid.uuid4().hex[:8]
        experiment_id = "EXP-EXTREVIEW-" + hashlib.sha256(
            sweep_seed.encode("utf-8")
        ).hexdigest()[:16].upper()
        sandbox = FreeResearchSandbox(self.sandbox_root)
        receipt = {
            "contract_version": CONTRACT_VERSION,
            "at": _iso(_now()),
            "tasks": task_ids,
            "reviews": [dict(r) for r in reviews],
            "production_integration": False,
        }
        receipt["receipt_hash"] = _digest(receipt)
        target = self.sandbox_root / "reports" / "external_review" / f"{experiment_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        # INCONCLUSIVE by construction: an independent read is a hypothesis about
        # what evidence might exist, never the evidence itself.
        sandbox.record_experiment(
            experiment_id=experiment_id,
            hypothesis="An unrelated free model reading the stuck tasks may name evidence its own reviewers could not.",
            method="independent free-model review of non-convergent blocked tasks",
            outcome="INCONCLUSIVE",
            evidence={
                "receipt_hash": receipt["receipt_hash"],
                "tasks": task_ids,
                "reviews": [dict(r) for r in reviews],
            },
            metadata={
                "source_kind": "free_zone_external_review",
                "free_zone_only": True,
                "automatic_model_call": True,
                "paid_provider_used": False,
                "taskpool_read_only": True,
            },
        )
        sandbox.distill(experiment_id)
        return experiment_id

    # ------------------------------------------------------------------ io

    def _write_state(self, state: Mapping[str, Any], result: Mapping[str, Any],
                     done: set[str] | None = None) -> None:
        updated = dict(state)
        if done:
            updated["reviewed_task_ids"] = sorted(done)
        if result.get("status") == "EXTERNAL_REVIEW_RECORDED":
            updated["last_review_at"] = _iso(_now())
            recent = [s for s in updated.get("recent_reviews", []) if s]
            recent.append(_iso(_now()))
            updated["recent_reviews"] = recent[-16:]
        updated["last_review"] = {
            "status": result.get("status"),
            "at": _iso(_now()),
            "experiment_id": result.get("experiment_id", ""),
            "tasks_reviewed": result.get("tasks_reviewed", 0),
            "reviews_written": result.get("reviews_written", 0),
            "model_calls": result.get("model_calls", 0),
            "production_integration": False,
        }
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(updated, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}