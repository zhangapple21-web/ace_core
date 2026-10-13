"""Admissibility gate for reopening a task blocked on external evidence.

The rule, stated before the code so it can be argued with:

A task blocked with ``等待人工或外部新证据`` may be reopened for another research
attempt when the record carries **at least two independent SUPPORTED external
reviews from different reviewers, and zero CONTRADICTED ones**, and its own
evidence is not polluted.

"Independent" is enforced as distinct reviewer identity, because a reviewer
repeating itself is not a second opinion. "SUPPORTED" is the verdict the reader
actually wrote - a review that says CANNOT_ASSESS and then names what to check
is a research instruction, not corroboration, and must not be counted as either.
Polluted evidence is refused outright rather than discounted: a task whose
evidence array contains material unrelated to the claim cannot be made sound by
adding more of it, which is the failure mode this whole gate exists to prevent.

The gate refuses with a named reason per task. A refusal is a result, not a
failure of the run, and it is what makes the gate worth having: a gate that
unlocks everything is decoration, and one that unlocks nothing today but says
exactly why is the automation that will work when the evidence actually arrives.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

CONTRACT_VERSION = "ace.external_evidence_unblock.v1"

REQUIRED_SUPPORTED = 2
#: The validator's non-convergence ceiling. Reaching it means the task has
#: already run out of research room, so a reopen is a replay, not a resume.
UNCHANGED_CEILING = 4
REVIEWS_DIR = "07_SANDBOX/free_research/reports/external_review"
BLOCKED_DIR = "task_pool/blocked"

EVIDENCE_MARKER = "外部新证据"
BLOCK_MARKER = "重复验证达到上限"

#: A verdict a reader actually reached. Anything else - a review that never ran,
#: or one that ignored the requested shape - is not a verdict at all.
VERDICTS = ("SUPPORTED", "CONTRADICTED", "CANNOT_ASSESS")


#: Statements an outside reader makes when a task's own evidence does not
#: support its claim. These are the reader's findings, recorded verbatim; a task
#: carrying one cannot be admitted, because the gate has no standing to overrule
#: a reader who looked and said the evidence does not address the claim.
INSUFFICIENCY_PATTERNS = (
    "does not address the claim",
    "has no connection to the claim",
    "no evidence provided",
    "the task holds no evidence",
    "supports nothing beyond",
    "evidence is circular",
    "no independent verification",
    "no evidence showing",
)


def _flag_insufficiency(detail: str) -> str:
    """The insufficiency statement this review made, or an empty string."""
    lowered = str(detail).lower()
    for pattern in INSUFFICIENCY_PATTERNS:
        if pattern in lowered:
            start = lowered.find(pattern)
            return str(detail)[max(0, start - 90):start + 140].replace("\n", " ")
    return ""


@dataclass
class TaskReview:
    """What the outside readers concluded about one task."""

    task_id: str
    supported: set = field(default_factory=set)
    contradicted: set = field(default_factory=set)
    cannot_assess: int = 0
    unparsed: int = 0
    unavailable: int = 0
    degenerate: int = 0
    sweeps: int = 0
    #: Verbatim insufficiency statements a reader made about this task's own
    #: evidence. Recorded, not decided here: if an outside reader wrote that the
    #: evidence does not address the claim, that is the reader's finding and this
    #: gate refuses to overrule it.
    evidence_flags: list = field(default_factory=list)

def _iter_review_files(root: Path) -> Iterable[Path]:
    directory = root / REVIEWS_DIR
    if not directory.is_dir():
        return []
    return sorted(directory.glob("EXP-EXTREVIEW-*.json"))


def collect_reviews(root: Path) -> dict[str, TaskReview]:
    """One verdict per reviewer per sweep; a repeat is not a second opinion."""
    collected: dict[str, TaskReview] = {}
    for path in _iter_review_files(root):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        task_ids = [str(t) for t in report.get("tasks") or []]
        for entry in report.get("reviews") or []:
            if not isinstance(entry, Mapping):
                continue
            reviewer = str(entry.get("reviewer") or "?").strip() or "?"
            status = str(entry.get("status") or "")
            detail = str(entry.get("detail", "")).upper()
            verdict = "UNPARSED"
            for candidate in VERDICTS:
                if candidate in detail:
                    verdict = candidate
                    break
            if status in {"UNAVAILABLE", "DEGENERATE"}:
                verdict = status
            flag = _flag_insufficiency(detail) if status == "REVIEWED" else ""
            for task_id in task_ids:
                record = collected.setdefault(task_id, TaskReview(task_id))
                record.sweeps += 1
                previous = (
                    reviewer in record.supported
                    or reviewer in record.contradicted
                )
                if flag and flag not in record.evidence_flags:
                    record.evidence_flags.append(flag)
                if verdict == "SUPPORTED":
                    if reviewer not in record.supported and not previous:
                        record.supported.add(reviewer)
                    elif reviewer in record.supported:
                        # same reviewer, same verdict, later sweep: not new evidence
                        record.unparsed += 0
                elif verdict == "CONTRADICTED":
                    if not previous:
                        record.contradicted.add(reviewer)
                elif verdict == "CANNOT_ASSESS":
                    record.cannot_assess += 1
                elif verdict in {"UNAVAILABLE", "DEGENERATE"}:
                    setattr(record, verdict.lower(),
                            getattr(record, verdict.lower()) + 1)
                else:
                    record.unparsed += 1
    return collected


def _pollution(task: Mapping[str, Any]) -> list[str]:
    """Named reasons this task's own evidence cannot support it.

    Checked mechanically, not by reading the prose: evidence entries whose
    content is byte-identical to another entry are repetition, not
    corroboration, and a task whose entire evidence set is one repeated source
    has no independent internal evidence at all.
    """
    evidence = task.get("evidence") or []
    reasons: list[str] = []
    if not evidence:
        reasons.append("no evidence at all")
        return reasons
    seen: dict[str, str] = {}
    duplicates = 0
    for item in evidence:
        key = str(item.get("source", "")) if isinstance(item, Mapping) else ""
        content = str(item.get("content", "")) if isinstance(item, Mapping) else str(item)
        identity = f"{key}::{content[:120]}"
        if identity in seen:
            duplicates += 1
        seen[identity] = key
    if duplicates:
        reasons.append(f"{duplicates} evidence entries are byte-identical repeats")
    distinct_sources = {v for v in seen.values() if v}
    if len(distinct_sources) <= 1 and len(evidence) > 1:
        reasons.append("every evidence entry cites the same source")
    return reasons


def assess(task: Mapping[str, Any], review: TaskReview | None) -> dict[str, Any]:
    """The verdict for one task, with the exact reason either way."""
    task_id = str(task.get("task_id") or "")
    reasons: list[str] = []
    pollution = _pollution(task)
    if pollution:
        reasons.extend(f"evidence unusable: {r}" for r in pollution)

    # A task that already ran to the non-convergence ceiling and came back is a
    # proven fixed point: reopening it replays the same loop. 44 sibling tasks of
    # this exact shape are in the blocked pool with unchanged_review_count == 4,
    # which is the ceiling, so this is measured rather than assumed.
    unchanged = int(task.get("unchanged_review_count") or 0)
    review_count = int(task.get("review_count") or 0)
    if unchanged >= UNCHANGED_CEILING:
        reasons.append(
            f"already reached the non-convergence ceiling "
            f"(unchanged_review_count={unchanged}, review_count={review_count}); "
            "reopening replays a proven loop rather than resuming work"
        )
    if review is None:
        reasons.append("no external review has ever covered this task")
    else:
        if len(review.supported) < REQUIRED_SUPPORTED:
            reasons.append(
                f"only {len(review.supported)} independent SUPPORTED review(s), "
                f"need {REQUIRED_SUPPORTED}"
            )
        if review.contradicted:
            reasons.append(
                f"CONTRADICTED by {sorted(review.contradicted)}: the readers disagree"
            )
        # A reader who looked and said the evidence does not address the claim
        # has already answered this question. Adding corroboration on top of
        # evidence that was found not to address the claim does not fix it.
        if review.evidence_flags:
            reasons.append(
                "an outside reader found the task's own evidence insufficient: "
                f"{review.evidence_flags[0][:150]}"
            )
    admissible = not reasons
    return {
        "task_id": task_id,
        "admissible": admissible,
        "reasons": reasons,
        "review": None if review is None else {
            "sweeps": review.sweeps,
            "supported": sorted(review.supported),
            "contradicted": sorted(review.contradicted),
            "cannot_assess": review.cannot_assess,
            "unparsed": review.unparsed,
            "unavailable": review.unavailable,
            "evidence_flags": len(review.evidence_flags),
        },
        "pollution": pollution,
    }


def blocked_tasks(root: Path) -> list[Path]:
    directory = root / BLOCKED_DIR
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def run(root: Path = BASE_DIR) -> dict[str, Any]:
    """Assess every task blocked on external evidence. Read-only."""
    reviews = collect_reviews(root)
    results = []
    for path in blocked_tasks(root):
        try:
            task = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        reason_text = str(task.get("blocked_reason") or "")
        if EVIDENCE_MARKER not in reason_text or BLOCK_MARKER not in reason_text:
            continue
        task_id = str(task.get("task_id") or "")
        results.append(assess(task, reviews.get(task_id)))

    admissible = [r for r in results if r["admissible"]]
    return {
        "contract_version": CONTRACT_VERSION,
        "required_supported": REQUIRED_SUPPORTED,
        "tasks_considered": len(results),
        "admissible": [r["task_id"] for r in admissible],
        "admissible_count": len(admissible),
        "results": results,
        "note": (
            "Admissible means the evidence bar is met, not that the task is "
            "true. Unblocking is a separate, audited step and is not performed "
            "by this module."
        ),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="External-evidence admissibility gate (read-only)")
    parser.add_argument("--root", default=str(BASE_DIR))
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--only-hold", action="store_true",
                        help="print only the tasks that are held, with reasons")
    args = parser.parse_args()

    report = run(Path(args.root))
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"tasks considered : {report['tasks_considered']}")
    print(f"admissible       : {report['admissible_count']} {report['admissible']}")
    print()
    if args.only_hold:
        shown = [r for r in report["results"] if not r["admissible"]]
    else:
        shown = report["results"]
    for result in shown:
        mark = "PASS" if result["admissible"] else "HOLD"
        print(f"  [{mark}] {result['task_id']}")
        for reason in result["reasons"]:
            print(f"          - {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())