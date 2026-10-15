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

#: The set of refusals already written, so the log stays a record of distinct
#: facts. Measured on 2026-10-14: 183 lines held 3 experiments, each repeated 61
#: times, because the relay re-scans the same distillations every cycle and every
#: scan re-refused the same ones. Unbounded repetition is not more evidence; it
#: buries the refusals that are new. The `.jsonl` stays append-only and readable;
#: this file is what makes "already said" cheap to ask.
#:
#: Keyed by experiment, holding the normalised reasons already recorded for it,
#: because "the same experiment was refused for a new reason" is a new fact and
#: must still be written.
REFUSAL_SEEN_FILE = "08_GOVERNANCE/free_zone_exchange/relay_admission_refusals_seen.json"

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


def _load_refusal_seen(path: Path) -> dict[str, list[str]]:
    """The refusals already on record, or an empty map when there is no file."""
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    seen = state.get("reasons") if isinstance(state, dict) else None
    if not isinstance(seen, dict):
        return {}
    return {str(k): [str(r) for r in v] for k, v in seen.items()
            if isinstance(v, list)}


def _bootstrap_refusal_seen(log: Path) -> dict[str, list[str]]:
    """Adopt the refusals already in the log, so history is never re-appended.

    Without this the first run after the dedup lands would treat every existing
    line as new and write the whole backlog a second time - the exact growth the
    change exists to stop.
    """
    seen: dict[str, list[str]] = {}
    try:
        text = log.read_text(encoding="utf-8")
    except OSError:
        return seen
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        experiment_id = str(entry.get("experiment_id") or "").strip()
        reason = _normalise(entry.get("reason"))
        if experiment_id and reason and reason not in seen.setdefault(experiment_id, []):
            seen[experiment_id].append(reason)
    return seen


def record_refusal(root: Path, experiment_id: str, reason: str) -> bool:
    """Write one refusal, once per (experiment, reason).

    Returns True when a line was appended and False when this refusal was
    already on record. The caller does not have to branch on it; the return
    value exists so a test can tell the two cases apart without reading files.

    A refusal is a fact about one experiment, so repeating it does not add
    information - the same experiment re-scanned each cycle would otherwise
    write the same line forever. An empty experiment id is still written every
    time, because "something was refused and we cannot name it" is not a fact
    that can be deduplicated without losing the occurrence count.
    """
    path = root / REFUSAL_LOG
    seen_path = root / REFUSAL_SEEN_FILE
    experiment_id = str(experiment_id or "").strip()
    normalised = _normalise(reason)

    seen = _load_refusal_seen(seen_path)
    if not seen:
        # Either there is no memory file yet, or it is unreadable. Both mean the
        # same thing: we do not know what has been said, so the log is asked.
        # Keying this on `not seen` rather than on the file's existence matters -
        # a truncated or corrupt memory file must not turn the whole backlog into
        # "new" and write it again.
        seen = _bootstrap_refusal_seen(path)

    if experiment_id and normalised and normalised in seen.get(experiment_id, []):
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": datetime.now(timezone.utc).isoformat(),
        "experiment_id": experiment_id,
        "reason": reason,
        "contract_version": CONTRACT_VERSION,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if experiment_id and normalised:
        seen.setdefault(experiment_id, []).append(normalised)
        seen_path.parent.mkdir(parents=True, exist_ok=True)
        seen_path.write_text(
            json.dumps({"contract_version": CONTRACT_VERSION, "reasons": seen},
                       ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    return True


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