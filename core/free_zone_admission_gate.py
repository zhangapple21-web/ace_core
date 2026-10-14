"""Admission gate for the reflection relay: work is discovered, not manufactured.

The defect
----------
`_create_followup_task` deduplicates on a source_ref that includes the
distillation hash. Each new Free Zone distillation therefore has a different
hash, so it never matches an existing task and a new ACE-side task is created
for it - every time. Wired to the served pool on 2026-10-13, the relay admitted
over a hundred tasks in a day, all of which ran the same research->validate
mould and hit the validator's non-convergence ceiling. One night's repair
bosomed the pool by an order of magnitude.

Deduplication was never the missing piece. A per-distillation hash makes
duplicates structurally impossible while saying nothing about whether this
distillation merits an ACE-side task at all. Work Conservation: work is
discovered, assessed, and accepted - not manufactured to satisfy activity.
"This Free Zone turn produced a conclusion" is not the same statement as "ACE
needs a task for it".

The gate
--------
Three conditions, all resolvable from records, and all three required:

  receivable    the Free Zone result carries an observable, checkable claim -
                a pattern with content, not an empty or stub record. A
                conclusion ACE could not verify even in principle does not
                become work.
  unmet         no live ACE-side task or experience already covers this
                experiment. If the conclusion is already being verified, or
                was already verified, a second task manufactures a duplicate.
  bounded       a daily admission cap, because an unbounded producer turns the
                pool into a queue again even when every individual admission
                is defensible.

A refusal names its reason and is recorded, so a blocked distillation is a
visible decision rather than a silent drop. Refusals are not errors: the
relay's job is to admit what is worth verifying, and most free-zone chatter is
not.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

CONTRACT_VERSION = "ace.free_zone_admission_gate.v1"

#: How many relay-admitted tasks per day. The linked path had no cap at all;
#: two is deliberately austere, because a cap that admits as much as it likes
#: is not a cap.
DAILY_ADMISSION_CAP = 2

#: Where the gate records its refusals. Beside the relay's own state, not in
#: the task pool, because a refusal is not work.
REFUSAL_LOG = "08_GOVERNANCE/free_zone_exchange/relay_admission_refusals.jsonl"
STATE_FILE = "08_GOVERNANCE/free_zone_exchange/relay_admission_state.json"

#: A pattern shorter than this carries no checkable claim.
MIN_PATTERN_CHARS = 40


def _normalise(text: Any) -> str:
    return " ".join(str(text or "").split()).lower()


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def is_receivable(distillation: Mapping[str, Any]) -> tuple[bool, str]:
    """Does this Free Zone result carry a claim ACE could verify at all?"""
    if not isinstance(distillation, Mapping):
        return False, "distillation is not a record"
    pattern = str(distillation.get("pattern") or "").strip()
    if len(pattern) < MIN_PATTERN_CHARS:
        return False, (f"pattern too short to verify ({len(pattern)} chars < "
                       f"{MIN_PATTERN_CHARS})")
    experiment_id = str(distillation.get("experiment_id") or "").strip()
    if not experiment_id:
        return False, "no experiment_id: the claim cannot be traced back"
    return True, "carries a checkable, traceable claim"


def is_unmet(experiment_id: str, distillation: Mapping[str, Any],
             live_tasks: Iterable[Mapping[str, Any]],
             experiences: Iterable[Mapping[str, Any]] = ()) -> tuple[bool, str]:
    """Is this already covered by a live task or a deposited experience?

    Coverage is by experiment id, not by hash: two distillations of the same
    experiment are the same finding twice, and only the first is unmet.
    """
    target = str(experiment_id).strip()
    for task in live_tasks or []:
        outputs = task.get("outputs") if isinstance(task, Mapping) else None
        holder = (outputs or {}).get("free_zone_reflection") if isinstance(outputs, Mapping) else None
        if isinstance(holder, Mapping) and str(holder.get("experiment_id", "")).strip() == target:
            return False, f"a live task already verifies {target}"
        admission = (outputs or {}).get("admission") if isinstance(outputs, Mapping) else None
        if isinstance(admission, Mapping):
            source_ref = str(admission.get("source_ref") or "")
            if target and target in source_ref:
                return False, f"a live task already covers {target} by admission ref"
    for experience in experiences or []:
        if not isinstance(experience, Mapping):
            continue
        if target and target in str(experience.get("source_task_id") or ""):
            return False, f"an experience was already deposited for {target}"
    return True, "not yet covered"


def _today(state: Mapping[str, Any], today: str) -> int:
    days = state.get("admits") or {}
    return int((days.get(today) or 0)) if isinstance(days, dict) else 0


def within_cap(state: Mapping[str, Any], today: str) -> tuple[bool, str]:
    count = _today(state, today)
    if count >= DAILY_ADMISSION_CAP:
        return False, f"daily admission cap reached ({count}/{DAILY_ADMISSION_CAP})"
    return True, f"{count}/{DAILY_ADMISSION_CAP} admitted today"


def record_refusal(root: Path, experiment_id: str, reason: str) -> None:
    path = root / REFUSAL_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": experiment_id,
        "reason": reason,
        "contract_version": CONTRACT_VERSION,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def record_admission(root: Path, experiment_id: str) -> None:
    path = root / STATE_FILE
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    today = datetime.now(timezone.utc).date().isoformat()
    days = state.setdefault("admits", {})
    days[today] = int(days.get(today) or 0) + 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2,
                               sort_keys=True) + "\n", encoding="utf-8")


def should_admit(root: Path, distillation: Mapping[str, Any], *,
                 live_tasks: Iterable[Mapping[str, Any]],
                 experiences: Iterable[Mapping[str, Any]] = (),
                 state: Mapping[str, Any] | None = None) -> tuple[bool, str, str]:
    """The whole gate. Returns (admit, reason, experiment_id).

    Every reason is recorded by the caller - a refusal is a decision that has
    to stay visible, not a silent drop.
    """
    experiment_id = str(distillation.get("experiment_id") or "UNKNOWN")
    if state is None:
        state = _read_json(root / STATE_FILE) or {}
    today = datetime.now(timezone.utc).date().isoformat()

    ok, why = is_receivable(distillation)
    if not ok:
        return False, why, experiment_id
    ok, why = is_unmet(experiment_id, distillation, live_tasks, experiences)
    if not ok:
        return False, why, experiment_id
    ok, why = within_cap(state, today)
    if not ok:
        return False, why, experiment_id
    return True, "receivable, unmet, and within the daily cap", experiment_id