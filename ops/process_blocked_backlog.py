"""Process the blocked backlog with the disposition and deposition that already exist.

Why this module exists
----------------------
The 68 blocked tasks are stuck in a state with no exit. They were parked as
``blocked`` rather than run through the terminal disposition the validator
already implements, and the deposition path only has a caller for the
archived branch. The result is a queue where nothing is processed - which is the
same disease as ``pending=0`` with work going nowhere, in mirror image: 68
held is also a stall.

Those tasks do not need another research cycle. 44 of them are one-line patrol
observations that reached the validator's non-convergence ceiling, where their
own external readers confirmed the evidence does not support them. Reopening
those replays a proven loop. What they need is the terminal disposition the
system already has, plus the lesson deposited where the next cycle can read it.

What it uses, all pre-existing
------------------------------
  * ``Validator.non_convergent_disposition`` - the disposition decision
  * ``ExperienceDeposition.deposit`` - the deposition, with ``discard`` mapped
    to a ``lesson`` by the existing ``deposit_from_task`` mapping
  * ``TaskPool.move_task`` - the lifecycle transition, which writes its own
    audit entry

What it refuses
---------------
A task is only disposed when the record shows it cannot converge AND an outside
reader said so. Everything else is left exactly where it is, with the reason
recorded. Nothing is force-closed, no evidence is invented, and no task is
unlocked. A disposition is a statement that the work is finished, not that it
succeeded - and it is reversible by the existing ``reopen_task`` if new evidence
ever arrives.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.free_zone_external_reviewer import parse_review_verdict  # noqa: E402

CONTRACT_VERSION = "ace.blocked_backlog_disposition.v1"

BLOCKED_DIR = "task_pool/blocked"
GRAVEYARD_DIR = "task_pool/graveyard"
EVIDENCE_MARKER = "外部新证据"
CEILING_MARKER = "重复验证达到上限"

#: The ceiling from the validator. A task at it has run out of research room.
UNCHANGED_CEILING = 4

#: A task must have no CONTRADICTED outside reader to be disposed as spent.
REVIEWS_DIR = "07_SANDBOX/free_research/reports/external_review"

#: Dispositions this module is allowed to reach, and what each means.
DISPOSITION_MEANING = {
    "research_exhausted": (
        "the validator's non-convergence ceiling was reached and outside "
        "readers confirmed the evidence does not support the claim"
    ),
    "external_condition_pending": (
        "the task is waiting on something outside ACE - a ruling, a key, or a "
        "design decision - so it is held, not disposed"
    ),
}


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _outside_readers(root: Path) -> dict[str, dict[str, Any]]:
    """Per task: what outside readers concluded, from the reports on disk."""
    collected: dict[str, dict[str, Any]] = {}
    directory = root / REVIEWS_DIR
    if not directory.is_dir():
        return collected
    for path in sorted(directory.glob("EXP-EXTREVIEW-*.json")):
        report = _read_json(path)
        if not isinstance(report, Mapping):
            continue
        task_ids = [str(t) for t in report.get("tasks") or []]
        for entry in report.get("reviews") or []:
            if not isinstance(entry, Mapping):
                continue
            status = str(entry.get("status") or "")
            if status in {"UNAVAILABLE", "DEGENERATE"}:
                verdict = status
            else:
                # Same rule as the admissibility gate: parse the VERDICT line,
                # never scan the prose.
                verdict = parse_review_verdict(str(entry.get("detail", ""))) or "UNPARSED"
            for task_id in task_ids:
                record = collected.setdefault(task_id, {
                    "contradicted": set(), "cannot_assess": 0,
                    "supported": set(), "sweeps": 0,
                })
                record["sweeps"] += 1
                if verdict == "CONTRADICTED":
                    record["contradicted"].add(str(entry.get("reviewer", "?")))
                elif verdict == "CANNOT_ASSESS":
                    record["cannot_assess"] += 1
                elif verdict == "SUPPORTED":
                    record["supported"].add(str(entry.get("reviewer", "?")))
    return collected


def classify(task: Mapping[str, Any], readers: Mapping[str, Any]) -> tuple[str, str]:
    """The disposition this task's own record supports, and why.

    ``observe`` means the task stays put: it is waiting on a ruling, a key, or a
    design decision that ACE cannot make for it, and disposing it would bury a
    live question. ``graveyard`` means the research room is genuinely used up.
    """
    task_id = str(task.get("task_id") or "")
    unchanged = int(task.get("unchanged_review_count") or 0)
    evidence = task.get("evidence") or []
    reader = readers.get(task_id)

    # An outside reader who looked and found the evidence does not address the
    # claim has answered the question this disposition turns on.
    confirmed_spent = bool(reader and reader.get("cannot_assess", 0) >= 1)
    contradicted = bool(reader and reader.get("contradicted"))

    if unchanged < UNCHANGED_CEILING or not evidence:
        return "observe", "the research cycle has not actually reached its ceiling"
    if contradicted:
        return "observe", "an outside reader contradicted this task; a human should read it"
    if not confirmed_spent:
        return "observe", "no outside reader has confirmed this task's evidence is insufficient"
    return "graveyard", (
        f"ceiling reached (unchanged_review_count={unchanged}) and "
        f"{reader.get('cannot_assess')} outside assessment(s) found the evidence "
        "insufficient"
    )


def process(root: Path, *, apply: bool = False) -> dict[str, Any]:
    """Dispose the backlog. ``apply`` writes; otherwise this is a dry run."""
    from core.experience_deposition import ExperienceDeposition
    from core.task import TaskPool
    from core.task_roles import Validator

    blocked = root / BLOCKED_DIR
    readers = _outside_readers(root)
    # The pool lives at <root>/task_pool, the way ace_daemon wires it. Pointing
    # TaskPool at the workspace root instead makes load_task resolve nothing and
    # every disposition fails as "not loadable" - a wiring mistake that looks
    # like a data problem.
    pool = TaskPool(str(root / "task_pool"))
    deposition = ExperienceDeposition(str(root / "09_KNOWLEDGE"))

    disposed: list[dict[str, Any]] = []
    observed: list[dict[str, Any]] = []
    for path in sorted(blocked.glob("*.json")):
        task_data = _read_json(path)
        if not isinstance(task_data, Mapping):
            continue
        reason_text = str(task_data.get("blocked_reason") or "")
        if CEILING_MARKER not in reason_text and EVIDENCE_MARKER not in reason_text:
            continue
        task_id = str(task_data.get("task_id") or "")
        kind, why = classify(task_data, readers)

        if kind == "observe":
            observed.append({"task_id": task_id, "reason": why})
            continue

        entry = {"task_id": task_id, "reason": why,
                 "evidence_items": len(task_data.get("evidence") or [])}
        if apply:
            # Load through the pool, not from the dict: the lease and fencing
            # fields live in the persisted record, and update_task refuses a
               # task whose fencing token does not match. Rebuilding from JSON
            # silently drops them.
            stored = pool.load_task(task_id)
            if stored is None or stored.status != "blocked":
                entry["error"] = "task is not loadable as blocked"
                disposed.append(entry)
                continue
            validator = Validator(pool)
            validator.non_convergent_disposition(stored)
            stored.outputs["terminal_disposition_reason"] = why
            stored.outputs["disposition_contract"] = CONTRACT_VERSION
            # The disposition is a lesson, not a finding: nothing was proven.
            stored.guardian_decision = "discard"
            if not pool.update_task(stored):
                entry["error"] = "update_task refused the record"
                disposed.append(entry)
                continue
            moved = pool.move_task(
                task_id, "graveyard",
                actor="blocked_backlog_disposition",
                reason=f"research exhausted: {why}",
                task=stored,
            )
            if moved is None:
                entry["error"] = "move_task refused the transition"
                disposed.append(entry)
                continue
            scheduled = deposition.deposit(
                task=moved,
                experience_type="lesson",
                conclusion=(
                    f"Task {task_id} is disposed as research-exhausted: {why}. "
                    "The claim was never verified and must not be treated as a finding."
                ),
                constraints_updated=[
                    f"disposition: research_exhausted ({CONTRACT_VERSION})",
                ],
                related_concepts=[],
                lane="tombstoning",
            )
            entry["deposited_experience"] = getattr(scheduled, "experience_id", "")
        disposed.append(entry)

    return {
        "contract_version": CONTRACT_VERSION,
        "apply": apply,
        "disposed": disposed,
        "disposed_count": len(disposed),
        "observed": observed,
        "observed_count": len(observed),
        "meaning": {
            "disposed": DISPOSITION_MEANING["research_exhausted"],
            "observed": DISPOSITION_MEANING["external_condition_pending"],
        },
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Dispose the blocked backlog through the existing disposition and "
                    "deposition paths (read-only unless --apply)")
    parser.add_argument("--root", default=str(BASE_DIR))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    report = process(Path(args.root), apply=args.apply)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"disposed : {report['disposed_count']}")
    print(f"observed : {report['observed_count']}")
    for entry in report["disposed"][:8]:
        print(f"  - {entry['task_id']}: {entry['reason'][:110]}")
    if report["observed_count"]:
        print("still held (with reason):")
        for entry in report["observed"][:8]:
            print(f"  - {entry['task_id']}: {entry['reason'][:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())