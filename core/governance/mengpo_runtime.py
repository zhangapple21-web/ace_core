"""Mengpo runtime: make forgetting real, and make it selective.

Why this module exists
----------------------
Mengpo's design work is finished and its running is not. Three specific defects,
each pinned in ops/test_mengpo_never_runs.py:

1. ``MengpoAutoTrigger`` - the component written to do the forgetting, with
   thresholds, cooldown, daily cap, backup-first - has zero call sites. It was
   built and never wired.
2. ``MengpoMemoryDecay.forget()`` writes a graveyard tombstone and nothing
   else. The artifact is never removed from the store, which is why all 2837
   records in mengpo_records.jsonl carry ``affected_items: []``.
3. Nothing reads the question the owner actually asks. ``ForgettingCandidate``
   has an ``alternatives_exist`` field, and neither ``forget()`` nor
   ``identify_forgetting_candidates()`` ever reads it. What to forget is decided
   by "is this dirty" alone; "what would I lose by forgetting it" is unasked.

What this adds
--------------
Substitution is the gate, not a tiebreaker. A candidate is only forgettable
when something else can cover its job. Four sources of substitution, each
resolvable from records rather than from a model's opinion:

  a substitute    - another artifact with the same normalised name and a
                    superseding record, the classic supersede-not-delete path.
  structured       - a MemoryLine (core principle, axiom, constraint, invariant,
                     identity) covering the same category: forgetting the detail
                     loses nothing because the rule stands.
  absorbed         - a later artifact whose record cites this one as a
                    reference: its content was already carried forward.
  never            - protected by lineage, or core-typed.

The runtime then forgets for real: it removes the artifact from the lexicon or
the experience store, records the affected item and its substitution in the
mengpo record, and keeps the tombstone. Reversible, because the tombstone
carries the original payload.

Bounded: a daily cap, a per-run cap, and a cooldown. A run that finds no
substitute forgets nothing and says so, because a deletion that cannot be
undone is the one failure this subsystem must never have.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

BASE_DIR = Path(__file__).resolve().parent.parent

CONTRACT_VERSION = "ace.governance.mengpo_runtime.v1"

#: How many artifacts one run may forget. Small on purpose.
MAX_PER_RUN = 5
#: How many runs per day. Conservative, mirrored from the auto-trigger's design.
MAX_RUNS_PER_DAY = 3
MIN_RUN_INTERVAL_HOURS = 6

STATE_FILE = "08_GOVERNANCE/decisions/mengpo_runtime_state.json"


@dataclass(frozen=True)
class Substitution:
    """Why forgetting this artifact costs nothing."""

    kind: str            # substitute / structured / absorbed
    detail: str
    evidence: str        # a path or id, so the claim is checkable


@dataclass
class Assessment:
    """Whether one artifact is forgettable, and why."""

    artifact_id: str
    forgettable: bool
    reason: str
    substitution: Substitution | None = None
    pollution_score: float = 0.0


def _normalise(text: Any) -> str:
    return "".join(str(text or "").split()).lower()


def _substitution_dict(substitution: Substitution | None) -> dict[str, str] | None:
    """A substitution as a plain mapping, so reports stay JSON-serialisable."""
    if substitution is None:
        return None
    return {"kind": substitution.kind, "detail": substitution.detail,
            "evidence": substitution.evidence}


def find_substitution(artifact: Mapping[str, Any], *,
                      lexicon: Mapping[str, Any] | None = None,
                      experiences: Iterable[Mapping[str, Any]] = (),
                      memory_lines: Iterable[Mapping[str, Any]] = (),
                      protected: Iterable[str] = ()) -> Substitution | None:
    """Where forgetting this artifact costs nothing, or None.

    Order matters: a concrete substitute beats a category-level rule, because
    "something covers it" is a weaker claim than "this specific thing takes over
    its job".
    """
    lexicon = lexicon or {}
    name = _normalise(artifact.get("name") or artifact.get("artifact"))
    category = str(artifact.get("category") or artifact.get("artifact_type") or "").lower()

    # (a) a substitute artifact with a superseding record
    if name:
        for other in lexicon.get("concepts", []) or []:
            if not isinstance(other, Mapping):
                continue
            if _normalise(other.get("name")) != name:
                continue
            if str(other.get("id")) == str(artifact.get("id") or artifact.get("artifact_id")):
                continue
            if other.get("superseded_by") or other.get("supersedes"):
                return Substitution(
                    "substitute",
                    "a superseding artifact carries the same name",
                    f"{other.get('id')}:{other.get('superseded_by') or other.get('supersedes')}")

    # (b) a structured rule covering the same category
    for line in memory_lines or []:
        if not isinstance(line, Mapping):
            continue
        scope = _normalise(line.get("category") or line.get("scope"))
        if scope and category and scope == category:
            return Substitution(
                "structured",
                "a MemoryLine covers this category, so the detail is redundant",
                str(line.get("id") or line.get("name") or "memory_line"))

    # (c) absorbed by a later artifact that cites this one
    target = str(artifact.get("id") or artifact.get("experience_id") or artifact.get("artifact_id") or "")
    if target:
        for later in experiences:
            if not isinstance(later, Mapping):
                continue
            if str(later.get("experience_id") or later.get("id") or "") == target:
                continue
            if target in [str(r) for r in (later.get("related") or []) + (later.get("cites") or [])]:
                return Substitution(
                    "absorbed",
                    "a later artifact already carries this one forward",
                    str(later.get("experience_id") or later.get("id") or "unknown"))

    # (d) protected by lineage
    if any(target and str(p) == target for p in protected):
        return Substitution("never", "protected by a MemoryLine", str(target))

    return None


def assess(artifact: Mapping[str, Any], *, pollution_score: float,
           lexicon: Mapping[str, Any] | None = None,
           experiences: Iterable[Mapping[str, Any]] = (),
           memory_lines: Iterable[Mapping[str, Any]] = (),
           protected: Iterable[str] = ()) -> Assessment:
    """Forgettable only when dirty AND substitutable.

    Both conditions, deliberately. A dirty artifact with nothing to replace it
    creates a hole; a clean-but-substituted artifact has no reason to be
    forgotten. The first is the failure that makes forgetting dangerous, and
    the reason substitution is a gate rather than a tiebreaker.
    """
    artifact_id = str(artifact.get("id") or artifact.get("experience_id")
                      or artifact.get("artifact_id") or "")
    if pollution_score <= 0:
        return Assessment(artifact_id, False,
                          "not polluted: nothing to forget", None, pollution_score)

    substitution = find_substitution(
        artifact, lexicon=lexicon, experiences=experiences,
        memory_lines=memory_lines, protected=protected)

    category = str(artifact.get("category") or artifact.get("artifact_type") or "").lower()
    if any(word in category for word in ("core", "principle", "axiom",
                                         "constraint", "invariant", "identity")):
        return Assessment(artifact_id, False,
                          "core-typed: never forgettable", None, pollution_score)
    if substitution is not None and substitution.kind == "never":
        return Assessment(artifact_id, False,
                         "protected by a MemoryLine", substitution, pollution_score)
    if substitution is None:
        return Assessment(
            artifact_id, False,
            "no substitution found: forgetting this would remove what no "
            "other artifact can replace", None, pollution_score)
    return Assessment(artifact_id, True,
                     f"substitutable via {substitution.kind}: {substitution.detail}",
                     substitution, pollution_score)


class MengpoRuntime:
    """Forget for real: remove, record, keep the tombstone, stay bounded."""

    def __init__(self, workspace_root: str | Path,
                 *, records_path: str | Path | None = None,
                 graveyard_path: str | Path | None = None,
                 state_path: str | Path | None = None,
                 protected: Iterable[str] = ()) -> None:
        self.root = Path(workspace_root)
        self.records_path = Path(records_path or
                                self.root / "08_GOVERNANCE" / "decisions"
                                / "mengpo_records.jsonl")
        self.graveyard_path = Path(graveyard_path or
                                  self.root / "08_GOVERNANCE" / "civilization"
                                  / "graveyard" / "runtime")
        self.state_path = Path(state_path or self.root / STATE_FILE)
        self.protected = list(protected)
        for directory in (self.records_path.parent, self.graveyard_path,
                           self.state_path.parent):
            directory.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ state

    def _load_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            return state if isinstance(state, dict) else {}
        except (OSError, ValueError):
            return {}

    def _due(self, state: Mapping[str, Any]) -> tuple[bool, str]:
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()
        runs = state.get("runs") or {}
        today_runs = int((runs.get(today) or 0))
        if today_runs >= MAX_RUNS_PER_DAY:
            return False, f"daily run cap reached ({today_runs}/{MAX_RUNS_PER_DAY})"
        last = str(state.get("last_run_at") or "")
        if last:
            try:
                gap = (now - datetime.fromisoformat(last)).total_seconds() / 3600.0
                if gap < MIN_RUN_INTERVAL_HOURS:
                    return False, f"cooldown: {gap:.1f}h since last run"
            except ValueError:
                pass
        return True, "due"

    def _record_run(self, forgotten: int, skipped: int) -> None:
        state = self._load_state()
        today = datetime.now(timezone.utc).date().isoformat()
        runs = state.setdefault("runs", {})
        runs[today] = int(runs.get(today) or 0) + 1
        state["last_run_at"] = datetime.now(timezone.utc).isoformat()
        state["last_run_result"] = {"forgotten": forgotten, "skipped": skipped}
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")

    # ------------------------------------------------------------------- run

    def run(self, *, lexicon: Mapping[str, Any],
            experiences: Iterable[Mapping[str, Any]] = (),
            memory_lines: Iterable[Mapping[str, Any]] = (),
            pollution_scores: Mapping[str, float] | None = None,
            dry_run: bool = False) -> dict[str, Any]:
        """Forget the substitutable-and-polluted, in one bounded run.

        Returns what it forgot, what it refused, and why. A refusal is a result:
        the runtime's whole value is that it declines to delete what it cannot
        replace.
        """
        experiences = list(experiences)
        memory_lines = list(memory_lines)
        state = self._load_state()
        due, why = self._due(state)
        if not due:
            return {"status": "NOT_DUE", "reason": why,
                    "contract_version": CONTRACT_VERSION,
                    "forgotten": [], "refused": []}

        pollution_scores = pollution_scores or {}
        lexicon_ids = {
            str(c.get("id") or c.get("name") or "")
            for c in (lexicon.get("concepts") or []) if isinstance(c, Mapping)
        }

        forgotten: list[dict[str, Any]] = []
        refused: list[dict[str, Any]] = []

        pool: list[tuple[Mapping[str, Any], float]] = []
        for concept in lexicon.get("concepts") or []:
            if not isinstance(concept, Mapping):
                continue
            identifier = str(concept.get("id") or concept.get("name") or "")
            pool.append((concept, float(pollution_scores.get(identifier, 0.0))))
        for experience in experiences:
            identifier = str(experience.get("experience_id")
                             or experience.get("id") or "")
            pool.append((experience, float(pollution_scores.get(identifier, 0.0))))

        pool.sort(key=lambda item: item[1], reverse=True)
        for artifact, score in pool:
            if len(forgotten) >= MAX_PER_RUN:
                break
            verdict = assess(
                artifact, pollution_score=score,
                lexicon=lexicon, experiences=experiences,
                memory_lines=memory_lines, protected=self.protected)
            if not verdict.forgettable:
                refused.append({"artifact_id": verdict.artifact_id,
                                "reason": verdict.reason,
                                "pollution_score": score})
                continue
            if dry_run:
                forgotten.append({"artifact_id": verdict.artifact_id,
                                  "reason": verdict.reason,
                                  "substitution": _substitution_dict(verdict.substitution),
                                  "applied": False})
                continue
            applied = self._forget(artifact, verdict)
            forgotten.append({"artifact_id": verdict.artifact_id,
                              "reason": verdict.reason,
                              "substitution": _substitution_dict(verdict.substitution),
                              "applied": applied})

        if not dry_run:
            self._record_run(len(forgotten), len(refused))
        return {
            "status": "APPLIED" if not dry_run else "DRY_RUN",
            "contract_version": CONTRACT_VERSION,
            "forgotten": forgotten,
            "refused": refused,
            "counts": {"forgotten": len(forgotten), "refused": len(refused)},
        }

    # --------------------------------------------------------------- forgetting

    def _forget(self, artifact: Mapping[str, Any], verdict: Assessment) -> bool:
        """Remove for real, in every store, and leave a reversible tombstone."""
        payload = json.loads(json.dumps(artifact, ensure_ascii=False, default=str))
        identifier = verdict.artifact_id or "unknown"

        tombstone = {
            "contract_version": CONTRACT_VERSION,
            "id": identifier,
            "payload": payload,
            "forgotten_at": datetime.now(timezone.utc).isoformat(),
            "forgotten_reason": verdict.reason,
            "substitution": (verdict.substitution.__dict__
                             if verdict.substitution else None),
            "pollution_score": verdict.pollution_score,
            "recoverable_by": "restore payload from this tombstone into the store",
        }
        target = self.graveyard_path / f"{identifier}.json"
        if not target.exists():
            target.write_text(json.dumps(tombstone, ensure_ascii=False, indent=2)
                             + "\n", encoding="utf-8")

        removed = self._remove_from_store(identifier, payload)

        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "forget",
            "artifact_id": identifier,
            "artifact_type": str(artifact.get("category")
                                or artifact.get("artifact_type") or "unknown"),
            "reason": verdict.reason,
            "pollution_score": verdict.pollution_score,
            "affected_items": removed,
            "substitution": (verdict.substitution.__dict__
                            if verdict.substitution else None),
            "tombstone": str(target),
            "contract_version": CONTRACT_VERSION,
        }
        with self.records_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        return bool(removed)

    def _remove_from_store(self, identifier: str, payload: Mapping[str, Any]) -> list[str]:
        """Remove from the lexicon and the experience store. Returns what it hit.

        The removal is real. This is the part the original forget() was missing,
        and it is the difference between a tombstone and a deletion.
        """
        removed: list[str] = []
        lexicon_path = self.root / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
        try:
            lexicon = json.loads(lexicon_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            lexicon = None
        if isinstance(lexicon, dict):
            concepts = lexicon.get("concepts")
            if isinstance(concepts, list):
                kept = [c for c in concepts
                        if str(c.get("id") or c.get("name") or "") != identifier]
                if len(kept) != len(concepts):
                    backup = lexicon_path.with_suffix(".json.mengpo-backup")
                    if not backup.exists():
                        shutil.copy2(lexicon_path, backup)
                    lexicon["concepts"] = kept
                    lexicon_path.write_text(
                        json.dumps(lexicon, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
                    removed.append(f"lexicon:{identifier}")

        experiences_path = self.root / "09_KNOWLEDGE" / "experiences.json"
        try:
            experiences = json.loads(experiences_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            experiences = None
        if isinstance(experiences, dict):
            items = experiences.get("experiences")
            if isinstance(items, list):
                kept = [e for e in items
                        if str(e.get("experience_id") or e.get("id") or "") != identifier]
                if len(kept) != len(items):
                    backup = experiences_path.with_suffix(".json.mengpo-backup")
                    if not backup.exists():
                        shutil.copy2(experiences_path, backup)
                    experiences["experiences"] = kept
                    experiences_path.write_text(
                        json.dumps(experiences, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
                    removed.append(f"experiences:{identifier}")
        return removed