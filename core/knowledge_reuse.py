"""Archived-knowledge reuse: let a new task be told what the archive already knows.

The point of this module is not to raise reference counts. A rising count is
cited, never a win. The win is a changed piece of work: a traceable old
artifact that shows up in what the task actually produced.

Three rules define what may be attached:

1. Identity, not similarity. A candidate is found through a content/file
   identity key (`source_file`, `from_obs:` tag, `intent:` tag, admission
   `source_ref`, trigger `experience_id`). A title is never a key.
2. One voice per group. Duplicate storms collapsed into one representative
   (the task the rest already reference). 140 identical scans of one file must
   not become 140 pieces of "prior art".
3. Traceable or nothing. Every attached item carries a
   ``knowledge_join:<key>`` source plus the triple needed to walk back:
   archived task id, the artifact path, and the identity key that matched.
   Without the triple the attachment is refused, because a daily report that
   cannot be traced is a daily report that cannot be believed.

Modes are deliberately ordered: ``dry-run`` computes and writes nothing,
``canary`` attaches for exactly one nominated task, ``full`` attaches for any
task. Skipping a level is refused. Until a canary run produces an artifact
that carries a ``knowledge_join:`` trace, the verdict stays ``NOT_YET`` and
the system keeps its own leash.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.delivery_execution import resolve_delivery_path

INDEX_PROTOCOL = "ace.knowledge.join.v1"
JOIN_SOURCE_PREFIX = "knowledge_join:"

MODE_ORDER = ("dry-run", "canary", "full")

DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "mode": "dry-run",
    "budget_evidence_per_task": 3,
    "budget_evidence_per_day": 20,
    "stage_timeout_s": 120,
    "index_max_age_days": 7,
    "canary_task": None,
    "index_path": "09_KNOWLEDGE/join_index.v1.json",
    "report_dir": "06_RUNTIME/ace/data/knowledge_reuse",
}

IDENTITY_KEY_LABELS = ("file", "obs", "intent", "adm", "exp")


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def identity_keys(task: Any) -> Dict[str, str]:
    """Identity keys of a task. Title is deliberately absent."""
    outputs = getattr(task, "outputs", None) or {}
    if not isinstance(outputs, dict):
        outputs = {}
    keys: Dict[str, str] = {}
    source_file = _text(outputs.get("source_file"))
    if source_file:
        keys["file"] = source_file
    for tag in (getattr(task, "tags", None) or []):
        tag = _text(tag)
        if tag.startswith("from_obs:") and tag[len("from_obs:"):]:
            keys.setdefault("obs", tag[len("from_obs:"):])
        if tag.startswith("intent:") and tag[len("intent:"):]:
            keys.setdefault("intent", tag[len("intent:"):])
    admission = outputs.get("admission")
    if isinstance(admission, dict) and admission.get("source_ref"):
        # Full-string exact match. Splitting on ":" would cut a Windows path
        # down to "C" and manufacture thousands of false friends.
        keys.setdefault("adm", _text(admission["source_ref"]))
    trigger = outputs.get("trigger")
    if isinstance(trigger, dict) and trigger.get("experience_id"):
        keys.setdefault("exp", _text(trigger["experience_id"]))
    return keys


def match_keys(subject_keys: Dict[str, str], candidate: Any) -> List[str]:
    outputs = getattr(candidate, "outputs", None) or {}
    if not isinstance(outputs, dict):
        outputs = {}
    matched: List[str] = []
    if "file" in subject_keys and _text(outputs.get("source_file")) == subject_keys["file"]:
        matched.append("file")
    tags = [_text(t) for t in (getattr(candidate, "tags", None) or [])]
    if "obs" in subject_keys and f"from_obs:{subject_keys['obs']}" in tags:
        matched.append("obs")
    if "intent" in subject_keys and f"intent:{subject_keys['intent']}" in tags:
        matched.append("intent")
    admission = outputs.get("admission")
    if ("adm" in subject_keys and isinstance(admission, dict)
            and _text(admission.get("source_ref")) == subject_keys["adm"]):
        matched.append("adm")
    trigger = outputs.get("trigger")
    if ("exp" in subject_keys and isinstance(trigger, dict)
            and _text(trigger.get("experience_id")) == subject_keys["exp"]):
        matched.append("exp")
    return matched


def join_key(matched: List[str], keys: Dict[str, str]) -> str:
    label = matched[0] if matched else "unknown"
    value = keys.get(label, "")
    digest = hashlib.sha256(f"{label}|{value}".encode("utf-8")).hexdigest()[:12]
    return f"{label}:{digest}"


class KnowledgeReuseGate:
    """Decides whether a task may be told about archived knowledge.

    The gate owns no scheduler. The daemon calls it once per in-flight task;
    scheduling, budgets and the daily report are the caller's bookkeeping.
    """

    def __init__(self, base_dir: Path, task_pool: Any, settings: Optional[Dict[str, Any]] = None):
        self.base_dir = Path(base_dir)
        self.task_pool = task_pool
        self.settings = {**DEFAULTS, **(settings or {})}
        self._archive_cache: Optional[Tuple[Tuple[int, float], List[Any]]] = None
        self._index_cache: Optional[Dict[str, Any]] = None

    # ── switch ────────────────────────────────────────────
    @property
    def enabled(self) -> bool:
        return bool(self.settings.get("enabled"))

    @property
    def mode(self) -> str:
        mode = _text(self.settings.get("mode") or "dry-run").strip().lower()
        return mode if mode in MODE_ORDER else "dry-run"

    def may_write(self, task_id: str) -> bool:
        """Dry-run never writes. Canary writes for exactly one nominated task."""
        if not self.enabled:
            return False
        if self.mode == "dry-run":
            return False
        if self.mode == "canary":
            return bool(self.settings.get("canary_task")) and task_id == self.settings.get("canary_task")
        return True

    # ── index health ──────────────────────────────────────
    def index_path(self) -> Path:
        return self.base_dir / _text(self.settings.get("index_path"))

    def load_index(self) -> Tuple[Optional[Dict[str, Any]], str]:
        path = self.index_path()
        if not path.exists():
            return None, "INDEX_MISSING"
        if self._index_cache is not None and self._index_cache.get("_path") == str(path):
            return self._index_cache, "OK"
        try:
            index = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return None, f"INDEX_UNREADABLE:{type(exc).__name__}"
        if index.get("protocol") != INDEX_PROTOCOL:
            return None, "INDEX_PROTOCOL_MISMATCH"
        max_age_days = float(self.settings.get("index_max_age_days") or 7)
        try:
            from datetime import datetime

            built = datetime.fromisoformat(_text(index.get("built_at")))
            age_days = (datetime.now() - built).total_seconds() / 86400.0
        except (TypeError, ValueError):
            return None, "INDEX_BUILT_AT_INVALID"
        if age_days > max_age_days:
            return None, f"INDEX_STALE:{age_days:.1f}d"
        index["_path"] = str(path)
        self._index_cache = index
        return index, "OK"

    # ── archive view ──────────────────────────────────────
    def archived(self) -> List[Any]:
        tasks = self.task_pool.list_tasks(status="archived", limit=10000)
        signature = (len(tasks), time.time())
        if self._archive_cache is not None and self._archive_cache[0][0] == signature[0]:
            return self._archive_cache[1]
        self._archive_cache = (signature, tasks)
        return tasks

    @staticmethod
    def group_of(task: Any) -> Optional[str]:
        """Group id of an archived task: the primary its references point at.

        Derived from the pool itself, so no external manifest is needed at run
        time and a rebuilt archive cannot desynchronise a side file.
        """
        references = [r for r in (getattr(task, "references", None) or []) if r]
        if not references:
            return None
        if getattr(task, "reference_count", 0) and len(references) != 1:
            return None  # ambiguous: not a clean single-primary collapse
        return references[0]

    # ── the reader ────────────────────────────────────────
    def plan(self, task: Any, evidence_budget: Optional[int] = None) -> Dict[str, Any]:
        """Compute what would be attached. Pure: never writes."""
        started = time.perf_counter()
        index, status = self.load_index()
        report: Dict[str, Any] = {
            "task": getattr(task, "task_id", None),
            "mode": self.mode,
            "enabled": self.enabled,
            "would_write": False,
            "index_status": status,
            "selected": [],
            "skipped": [],
            "expected_writes": {"evidence": 0, "reference_counts": 0},
            "verdict": "NOT_YET",
            "reason": None,
        }
        if not self.enabled:
            report["reason"] = "DISABLED"
            report["skipped_status"] = "DISABLED"
            return report
        if index is None:
            report["reason"] = status
            return report

        limit = int(evidence_budget if evidence_budget is not None
                    else self.settings.get("budget_evidence_per_task") or 3)
        subject_keys = identity_keys(task)
        report["identity_keys"] = subject_keys
        if not subject_keys:
            report["reason"] = "NO_IDENTITY_KEY"
            report["skipped_status"] = "NO_IDENTITY_KEY"
            return report

        archive = self.archived()
        by_id = {t.task_id: t for t in archive}
        referenced = set(getattr(task, "references", None) or [])
        existing_sources = {
            _text(e.get("source")) for e in (getattr(task, "evidence", None) or [])
            if isinstance(e, dict)
        }

        candidates: Dict[str, List[str]] = {}
        for candidate in archive:
            matched = match_keys(subject_keys, candidate)
            if matched:
                candidates[candidate.task_id] = matched

        # One voice per group: a task that already references a primary is a
        # member of that collapse group, so the primary speaks for it.
        collapsed = 0
        kept: Dict[str, List[str]] = {}
        for tid, matched in candidates.items():
            candidate = by_id[tid]
            if getattr(candidate, "references", None) and self.group_of(candidate):
                collapsed += 1
                continue
            kept[tid] = matched
        if collapsed:
            report["skipped"].append({
                "reason": "GROUP_COLLAPSED_TO_PRIMARY",
                "count": collapsed,
            })

        def newest_first(tid: str) -> str:
            return _text(getattr(by_id[tid], "created_at", ""))

        selected: List[Dict[str, Any]] = []
        chosen_sources: set = set()
        for tid in sorted(kept, key=newest_first, reverse=True):
            candidate = by_id[tid]
            matched = kept[tid]
            entry = candidate_evidence(candidate, matched, subject_keys, index,
                                       workspace=self.base_dir)
            if entry is None:
                report["skipped"].append({"task": tid, "via": matched,
                                          "reason": "NO_TRACEABLE_ARTIFACT"})
                continue
            if tid in referenced:
                report["skipped"].append({"task": tid, "via": matched,
                                          "reason": "ALREADY_REFERENCED"})
                continue
            if entry["source"] in existing_sources:
                report["skipped"].append({"task": tid, "via": matched,
                                          "reason": "ALREADY_ATTACHED"})
                continue
            if entry["source"] in chosen_sources:
                # Two archived tasks can answer to one identity key. They are
                # one piece of prior art, not two, and the report must not
                # inflate its citation count with the echo.
                report["skipped"].append({"task": tid, "via": matched,
                                          "reason": "SAME_IDENTITY_AS_SELECTED"})
                continue
            outputs = getattr(candidate, "outputs", None) or {}
            if isinstance(outputs, dict) and outputs.get("terminal_non_convergent"):
                report["skipped"].append({"task": tid, "via": matched,
                                          "reason": "TERMINAL_NON_CONVERGENT"})
                continue
            if len(selected) < limit:
                selected.append(entry)
                chosen_sources.add(entry["source"])
            else:
                report["skipped"].append({"task": tid, "via": matched,
                                          "reason": "OVER_EVIDENCE_BUDGET"})

        report["selected"] = selected
        report["expected_writes"] = {
            "evidence": len(selected),
            "reference_counts": len({e["archived_task"] for e in selected}),
        }
        report["would_write"] = self.may_write(_text(getattr(task, "task_id", "")))
        elapsed = time.perf_counter() - started
        report["elapsed_s"] = round(elapsed, 3)
        timeout = float(self.settings.get("stage_timeout_s") or 120)
        # perf_counter, not time(): on Windows time() has ~15ms granularity and
        # can step backwards, so a real overrun could read as zero.
        if elapsed > timeout:
            report["reason"] = "STAGE_TIMEOUT"
            report["selected"] = []
            report["expected_writes"] = {"evidence": 0, "reference_counts": 0}
            report["would_write"] = False
        return report

    # ── the only write, gated ─────────────────────────────
    def attach(self, task: Any, plan: Dict[str, Any]) -> Dict[str, Any]:
        """Attach planned evidence. Refuses unless the gate says this task may write."""
        task_id = _text(getattr(task, "task_id", ""))
        if not self.may_write(task_id):
            return {"attached": 0, "reason": "WRITE_NOT_PERMITTED", "mode": self.mode}
        entries = plan.get("selected") or []
        if not entries:
            return {"attached": 0, "reason": "NOTHING_SELECTED", "mode": self.mode}
        evidence = getattr(task, "evidence", None)
        if evidence is None:
            evidence = []
            task.evidence = evidence
        attached = 0
        for entry in entries:
            if entry["source"] in {_text(e.get("source")) for e in evidence if isinstance(e, dict)}:
                continue
            evidence.append({
                "source": entry["source"],
                "kind": "archived_knowledge",
                "detail": entry["note"],
                "archived_task": entry["archived_task"],
                "artifact": entry["artifact"],
                "identity_key": entry["identity_key"],
                "matched_via": entry["matched_via"],
                "read_only": True,
                "at": None,
            })
            attached += 1
        if attached:
            self.task_pool.update_task(task)
        return {"attached": attached, "reason": None, "mode": self.mode}


def candidate_evidence(candidate: Any, matched: List[str], subject_keys: Dict[str, str],
                       index: Optional[Dict[str, Any]],
                       workspace: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Build the traceable triple, or None when no artifact can be named.

    The artifact must be a real file inside the workspace. A citation that points
    at a deleted EXP record or at a path nobody can open is a claim, not
    evidence, and a report built on claims is worse than no report.
    """
    task_id = _text(getattr(candidate, "task_id", ""))
    outputs = getattr(candidate, "outputs", None)
    if not isinstance(outputs, dict):
        outputs = {}
    artifact = None
    by_task = (index or {}).get("by_task") or {}
    record = by_task.get(task_id) or {}
    paths = list(record.get("patterns") or []) + list(record.get("cards") or [])
    if workspace is not None:
        for candidate_path in paths:
            resolved = resolve_delivery_path(workspace, _text(candidate_path))
            if resolved is not None and resolved.is_file():
                artifact = _text(candidate_path).replace("\\", "/")
                break
        if artifact is None:
            # A declared delivery is the strongest artifact a task can produce,
            # and the delivery contract already governs where it may live.
            delivery = outputs.get("delivery")
            required = _text((delivery or {}).get("required_path")).strip().replace("\\", "/")
            if required:
                resolved = resolve_delivery_path(workspace, required)
                if resolved is not None and resolved.is_file():
                    artifact = required
    if artifact is None:
        return None
    key = join_key(matched, subject_keys)
    if not artifact:
        # A task with no knowledge artifact can still be cited, but only by its
        # own identity; without an artifact path the triple is incomplete.
        return None
    return {
        "source": f"{JOIN_SOURCE_PREFIX}{key}",
        "archived_task": task_id,
        "artifact": artifact,
        "identity_key": f"{matched[0]}={subject_keys.get(matched[0], '')}",
        "matched_via": list(matched),
        "created": _text(getattr(candidate, "created_at", ""))[:10],
        "note": f"archived {task_id} produced {artifact}; matched by "
                f"{'+'.join(matched)} identity key",
    }


def artifact_contributions(task: Any, artifact_path: str, workspace: Path,
                           max_bytes: int = 2_000_000) -> List[Dict[str, Any]]:
    """Did the delivered artifact actually use the knowledge it was handed?

    Only a ``knowledge_join:`` id that this task really carries counts, and only
    when that literal id appears in the artifact text. A citation the artifact
    did not write, or an id the task never held, is ignored — a report must not
    quote the intent to reuse as proof of reuse.
    """
    target = resolve_delivery_path(Path(workspace), _text(artifact_path).replace("\\", "/"))
    if target is None or not target.is_file():
        return []
    try:
        text = target.read_text(encoding="utf-8", errors="ignore")[:max_bytes]
    except OSError:
        return []
    held: Dict[str, Dict[str, Any]] = {}
    for entry in (getattr(task, "evidence", None) or []):
        if not isinstance(entry, dict):
            continue
        source = _text(entry.get("source"))
        if source.startswith(JOIN_SOURCE_PREFIX):
            held[source] = entry
    contributions: List[Dict[str, Any]] = []
    for source, entry in held.items():
        if source not in text:
            continue
        contributions.append({
            "artifact": _text(artifact_path).replace("\\", "/"),
            "source": source,
            "archived_task": entry.get("archived_task"),
            "cited_artifact": entry.get("artifact"),
            "identity_key": entry.get("identity_key"),
        })
    return contributions


def build_daily_report(date: str, mode: str, entries: List[Dict[str, Any]],
                       skip_reason: Optional[str] = None,
                       contributions: Optional[List[Dict[str, Any]]] = None
                       ) -> Dict[str, Any]:
    """The report must never confuse 'cited' with 'changed'."""
    cited_evidence: List[Dict[str, Any]] = []
    changed: Dict[str, Any] = {
        "duplicates_avoided": 0,
        "revive_instead_of_create": 0,
        "artifact_contributions": [],
        "deliveries": [],
        "failures": [],
        "misattributions": [],
    }
    skipped_reasons: List[str] = []
    for entry in entries:
        if entry.get("skipped_status"):
            skipped_reasons.append(entry["skipped_status"])
        for item in entry.get("selected") or []:
            cited_evidence.append({
                "task": entry.get("task"),
                "source": item.get("source"),
                "archived_task": item.get("archived_task"),
                "artifact": item.get("artifact"),
            })
        # A collapsed group is only a *saved duplicate* when reuse actually
        # reached a real task. In dry-run nothing was influenced, so counting
        # it would let a plan that cited nothing claim a win.
        if int(entry.get("attached") or 0) > 0:
            for item in entry.get("skipped") or []:
                if item.get("reason") == "GROUP_COLLAPSED_TO_PRIMARY":
                    changed["duplicates_avoided"] += int(item.get("count") or 0)
    changed["artifact_contributions"] = [
        c for c in (contributions or []) if c
    ]
    verdict = "BENEFIT_PROVEN" if _changed_nonempty(changed) else "NOT_YET"
    if skip_reason:
        verdict = "NO_RUN"
    return {
        "date": date,
        "mode": mode,
        "cited": {
            "evidence_selected": len(cited_evidence),
            "evidence_attached": sum(int(e.get("attached") or 0) for e in entries),
            "items": cited_evidence,
        },
        "changed": changed,
        "skipped": {"reasons": sorted(set(skipped_reasons)) or [skip_reason] if (skipped_reasons or skip_reason) else [None]},
        "verdict": verdict,
    }


def _changed_nonempty(changed: Dict[str, Any]) -> bool:
    for key, value in changed.items():
        if isinstance(value, list) and value:
            return True
        if isinstance(value, int) and value:
            return True
    return False


def write_report(base_dir: Path, report: Dict[str, Any], report_dir: str = "06_RUNTIME/ace/data/knowledge_reuse") -> Path:
    """Overwrite-by-date: rerunning a day rewrites the same bytes, never appends."""
    directory = Path(base_dir) / report_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"report-{report['date']}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                    encoding="utf-8", newline="\n")
    return path