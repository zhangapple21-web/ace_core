"""Read-only admission decisions for evidence-backed task candidates.

This module deliberately has no TaskPool or Daemon integration.  It provides a
deterministic, side-effect-free decision that producers and offline auditors
can use before deciding whether a candidate should become a task.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional

from .task_admission import validate_admission

CAPABILITY_ID = "ACE-CAP-evidence-admission"
VERSION = "1.0.0"
TERMINAL_STATUSES = frozenset(("archived", "graveyard", "rejected"))
ARM_INJECTED = "injected"
ARM_COLD_ENVIRONMENT = "absent_cold_environment"
ARM_UNINSTALLED = "uninstalled"
VALIDATOR_ARMS = frozenset((ARM_INJECTED, ARM_COLD_ENVIRONMENT, ARM_UNINSTALLED))


class EvidenceAdmissionError(ValueError):
    """Invalid input or assembly state for the evidence admission contract."""


@dataclass(frozen=True)
class Thresholds:
    minimum_unique_evidence: int = 3
    minimum_independent_sources: int = 2
    minimum_first_evidence_length: int = 50


@dataclass(frozen=True)
class EvidenceQuality:
    evidence_count: int
    unique_evidence_count: int
    source_count: int
    independent_source_count: int
    first_evidence_length: int
    has_empty_content: bool


@dataclass(frozen=True)
class EvidenceAdmissionDecision:
    decision: str
    reason: str
    evidence_signature: str
    quality: EvidenceQuality
    admission_valid: bool
    admission_error: str = ""
    duplicate_task_ids: tuple[str, ...] = field(default_factory=tuple)
    validator_arm: str = ARM_INJECTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "reason": self.reason,
            "evidence_signature": self.evidence_signature,
            "quality": {
                "evidence_count": self.quality.evidence_count,
                "unique_evidence_count": self.quality.unique_evidence_count,
                "source_count": self.quality.source_count,
                "independent_source_count": self.quality.independent_source_count,
                "first_evidence_length": self.quality.first_evidence_length,
                "has_empty_content": self.quality.has_empty_content,
            },
            "admission_valid": self.admission_valid,
            "admission_error": self.admission_error,
            "duplicate_task_ids": list(self.duplicate_task_ids),
            "validator_arm": self.validator_arm,
        }


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, Mapping):
        return item.get(name, default)
    return getattr(item, name, default)


def _evidence_pair(item: Any) -> tuple[str, str]:
    if isinstance(item, Mapping):
        source = item.get("source", item.get("source_ref", ""))
        content = item.get("content", item.get("detail", ""))
    else:
        source = ""
        content = str(item)
    return str(source or "").strip(), str(content or "").strip()


def canonical_evidence(evidence: Optional[Iterable[Any]]) -> tuple[tuple[str, str], ...]:
    """Return the same source/content identity used by Validator signatures."""
    pairs = {_evidence_pair(item) for item in (evidence or [])}
    return tuple(sorted(pairs))


def evidence_signature(evidence: Optional[Iterable[Any]]) -> str:
    canonical = canonical_evidence(evidence)
    if not canonical or not any(source or content for source, content in canonical):
        return ""
    return hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def quality_facts(evidence: Optional[Iterable[Any]]) -> EvidenceQuality:
    items = list(evidence or [])
    canonical = canonical_evidence(items)
    sources = {source for source, _ in canonical if source}
    # A source_ref is the strongest available independence signal at this layer.
    independent_sources = sources
    first_length = len(_evidence_pair(items[0])[1]) if items else 0
    return EvidenceQuality(
        evidence_count=len(items),
        unique_evidence_count=len(canonical),
        source_count=len(sources),
        independent_source_count=len(independent_sources),
        first_evidence_length=first_length,
        has_empty_content=any(not content for _, content in map(_evidence_pair, items)),
    )


def _task_signature(task: Any) -> str:
    outputs = _value(task, "outputs", {}) or {}
    if isinstance(outputs, Mapping):
        stored = outputs.get("last_validated_evidence_signature")
        if stored and canonical_evidence(_value(task, "evidence", [])):
            return str(stored)
    evidence = _value(task, "evidence", [])
    return evidence_signature(evidence)


def evaluate(
    candidate: Mapping[str, Any],
    existing_tasks: Iterable[Any] = (),
    *,
    thresholds: Thresholds = Thresholds(),
    admission_validator: Optional[Callable[[dict[str, Any]], Any]] = validate_admission,
    validator_arm: str = ARM_INJECTED,
) -> EvidenceAdmissionDecision:
    """Evaluate a candidate with an explicit admission-validation arm.

    The validator is injected so this pure capability has no hidden environment
    or filesystem dependency.  An explicitly declared cold environment may
    perform shape-only research; an uninstalled validator fails closed.
    """
    if not isinstance(candidate, Mapping):
        raise EvidenceAdmissionError(
            "candidate_not_a_mapping:%s" % type(candidate).__name__
        )
    if validator_arm not in VALIDATOR_ARMS:
        raise EvidenceAdmissionError("unknown_validator_arm:%s" % validator_arm)

    evidence = candidate.get("evidence", [])
    quality = quality_facts(evidence)
    signature = evidence_signature(evidence)
    duplicate_ids: list[str] = []

    admission = candidate.get("admission")
    if admission is None:
        outputs = candidate.get("outputs", {})
        admission = outputs.get("admission") if isinstance(outputs, Mapping) else None
    admission_error = ""
    if admission_validator is None:
        if not isinstance(admission, Mapping):
            admission_error = "task_admission_required"
        elif validator_arm != ARM_COLD_ENVIRONMENT:
            admission_error = "admission_unvalidated:%s" % validator_arm
    else:
        validator_arm = ARM_INJECTED
        if not isinstance(admission, Mapping):
            admission_error = "task_admission_required"
        else:
            try:
                admission_validator(dict(admission))
            except Exception as exc:  # noqa: BLE001 - preserve injected failure shape
                admission_error = str(exc)

    for task in existing_tasks:
        status = str(_value(task, "status", ""))
        if status in TERMINAL_STATUSES:
            continue
        if signature and _task_signature(task) == signature:
            task_id = str(_value(task, "task_id", ""))
            if task_id:
                duplicate_ids.append(task_id)

    if duplicate_ids:
        decision, reason = "duplicate", "duplicate_evidence_signature"
    elif admission_error:
        decision, reason = "defer", admission_error
    elif quality.has_empty_content:
        decision, reason = "defer", "empty_evidence_content"
    elif quality.unique_evidence_count < thresholds.minimum_unique_evidence:
        decision, reason = "defer", "minimum_evidence_required"
    elif quality.independent_source_count < thresholds.minimum_independent_sources:
        decision, reason = "defer", "independent_evidence_required"
    elif quality.first_evidence_length < thresholds.minimum_first_evidence_length:
        decision, reason = "defer", "first_evidence_too_short"
    else:
        decision, reason = "admit", "evidence_quality_satisfied"

    return EvidenceAdmissionDecision(
        decision=decision,
        reason=reason,
        evidence_signature=signature,
        quality=quality,
        admission_valid=(validator_arm == ARM_INJECTED and not admission_error),
        admission_error=admission_error,
        duplicate_task_ids=tuple(sorted(set(duplicate_ids))),
        validator_arm=validator_arm,
    )


def evaluate_candidate(
    candidate: Mapping[str, Any],
    existing_tasks: Iterable[Any] = (),
    *,
    minimum_unique_evidence: int = 3,
    minimum_independent_sources: int = 2,
    minimum_first_evidence_length: int = 50,
) -> EvidenceAdmissionDecision:
    """Backward-compatible wrapper for the original ACE entry point."""
    return evaluate(
        candidate,
        existing_tasks,
        thresholds=Thresholds(
            minimum_unique_evidence=minimum_unique_evidence,
            minimum_independent_sources=minimum_independent_sources,
            minimum_first_evidence_length=minimum_first_evidence_length,
        ),
        admission_validator=validate_admission,
        validator_arm=ARM_INJECTED,
    )
