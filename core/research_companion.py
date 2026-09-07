"""Report-only research questions and append-only research threads.

This module is the small context layer between exploratory work and a human
research brief.  It records what was asked, what would change the answer and
which independent evidence supports or contradicts the current hypothesis.
It deliberately has no model, scheduler, TaskPool, Advisor, Risk or delivery
integration.  A card or thread is context, never an admission decision.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.research_companion.v1"
EPISTEMIC_STATES = frozenset({"FACT", "INFERENCE", "HYPOTHESIS", "UNKNOWN", "INVALIDATED"})
THREAD_STATUSES = frozenset({"OPEN", "VERIFICATION_PENDING", "INVALIDATED", "CLOSED"})
EVENT_TYPES = frozenset(
    {
        "question_created",
        "evidence_added",
        "counterevidence_added",
        "hypothesis_changed",
        "verification_pending",
        "invalidated",
    }
)
EVIDENCE_KEYS = frozenset({"ref", "kind", "independence_group", "observed_at"})
CARD_KEYS = frozenset(
    {
        "contract_version",
        "question_id",
        "thread_id",
        "subject",
        "original_question",
        "decomposed_questions",
        "hypothesis",
        "research_dimensions",
        "expected_evidence",
        "support_refs",
        "counterevidence_refs",
        "unknowns",
        "next_verification",
        "epistemic_status",
        "created_at",
        "updated_at",
        "profile_version",
        "production_integration",
        "card_hash",
    }
)
THREAD_KEYS = frozenset(
    {
        "contract_version",
        "thread_id",
        "subject",
        "initial_question",
        "events",
        "current_status",
        "previous_event_hash",
        "thread_hash",
        "created_at",
        "updated_at",
        "profile_version",
        "production_integration",
    }
)
EVENT_KEYS = frozenset({"event_id", "event_type", "recorded_at", "payload", "previous_event_hash", "event_hash"})
FORBIDDEN_KEYS = frozenset(
    {
        "advisor",
        "risk",
        "telegram",
        "broker",
        "order",
        "orders",
        "guarantee",
        "recommendation",
        "target_price",
    }
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _strings(value: Any, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple)) or (not allow_empty and not value):
        raise ValueError(f"{label} must be a non-empty list")
    result = [_text(item, label) for item in value]
    return result


def _reject_forbidden(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key).strip().lower() in FORBIDDEN_KEYS:
                raise ValueError(f"research artifact contains forbidden field: {key}")
            _reject_forbidden(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden(item)


def _evidence_refs(value: Any, label: str) -> list[dict[str, str]]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{label} must be a list")
    refs: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping) or set(item) != EVIDENCE_KEYS:
            raise ValueError(f"{label} contains malformed evidence ref")
        refs.append({key: _text(item[key], f"{label}.{key}") for key in EVIDENCE_KEYS})
    refs.sort(key=lambda item: (item["independence_group"], item["ref"]))
    return refs


def _validate_card(value: Mapping[str, Any], *, verify_hash: bool = True) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != CARD_KEYS:
        raise ValueError("research question card has missing or unknown fields")
    if value["contract_version"] != CONTRACT_VERSION:
        raise ValueError("unsupported research card contract_version")
    for key in ("question_id", "thread_id", "subject", "original_question", "hypothesis", "next_verification", "profile_version", "created_at", "updated_at"):
        _text(value[key], f"card {key}")
    questions = _strings(value["decomposed_questions"], "card decomposed_questions")
    dimensions = _strings(value["research_dimensions"], "card research_dimensions")
    expected = _strings(value["expected_evidence"], "card expected_evidence")
    unknowns = _strings(value["unknowns"], "card unknowns", allow_empty=True)
    support = _evidence_refs(value["support_refs"], "card support_refs")
    counter = _evidence_refs(value["counterevidence_refs"], "card counterevidence_refs")
    status = _text(value["epistemic_status"], "card epistemic_status")
    if status not in EPISTEMIC_STATES:
        raise ValueError("invalid card epistemic_status")
    if value["production_integration"] is not False:
        raise ValueError("research card production_integration must be false")
    # A missing counterevidence pass is an epistemic gap, never silent support.
    if not counter and status != "UNKNOWN":
        raise ValueError("card without counterevidence must be marked UNKNOWN")
    normalized = {
        "contract_version": CONTRACT_VERSION,
        "question_id": str(value["question_id"]).strip(),
        "thread_id": str(value["thread_id"]).strip(),
        "subject": str(value["subject"]).strip(),
        "original_question": str(value["original_question"]).strip(),
        "decomposed_questions": questions,
        "hypothesis": str(value["hypothesis"]).strip(),
        "research_dimensions": dimensions,
        "expected_evidence": expected,
        "support_refs": support,
        "counterevidence_refs": counter,
        "unknowns": unknowns,
        "next_verification": str(value["next_verification"]).strip(),
        "epistemic_status": status,
        "created_at": str(value["created_at"]).strip(),
        "updated_at": str(value["updated_at"]).strip(),
        "profile_version": str(value["profile_version"]).strip(),
        "production_integration": False,
        "card_hash": str(value["card_hash"]).strip(),
    }
    _reject_forbidden(normalized)
    if verify_hash and normalized["card_hash"] != _digest({k: v for k, v in normalized.items() if k != "card_hash"}):
        raise ValueError("research question card hash mismatch")
    return normalized


def build_research_question_card(
    *,
    question_id: str,
    thread_id: str,
    subject: str,
    original_question: str,
    decomposed_questions: Sequence[str],
    hypothesis: str,
    research_dimensions: Sequence[str],
    expected_evidence: Sequence[str],
    support_refs: Sequence[Mapping[str, Any]] = (),
    counterevidence_refs: Sequence[Mapping[str, Any]] = (),
    unknowns: Sequence[str] = (),
    next_verification: str,
    epistemic_status: str = "UNKNOWN",
    profile_version: str = "research-companion.v1",
    created_at: str | None = None,
    updated_at: str | None = None,
) -> dict[str, Any]:
    """Build a hash-bound card; this function has no side effects."""
    created = created_at or _now()
    draft = {
        "contract_version": CONTRACT_VERSION,
        "question_id": question_id,
        "thread_id": thread_id,
        "subject": subject,
        "original_question": original_question,
        "decomposed_questions": list(decomposed_questions),
        "hypothesis": hypothesis,
        "research_dimensions": list(research_dimensions),
        "expected_evidence": list(expected_evidence),
        "support_refs": [dict(item) for item in support_refs],
        "counterevidence_refs": [dict(item) for item in counterevidence_refs],
        "unknowns": list(unknowns),
        "next_verification": next_verification,
        "epistemic_status": epistemic_status,
        "created_at": created,
        "updated_at": updated_at or created,
        "profile_version": profile_version,
        "production_integration": False,
    }
    # The default UNKNOWN status makes a newly opened question honest until a
    # sourced counterevidence pass has actually been recorded.
    if not draft["counterevidence_refs"]:
        draft["epistemic_status"] = "UNKNOWN"
    draft["card_hash"] = _digest(draft)
    return _validate_card(draft)


def _validate_event(value: Mapping[str, Any], previous_hash: str, *, verify_hash: bool = True) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != EVENT_KEYS:
        raise ValueError("research thread event has missing or unknown fields")
    event_type = _text(value["event_type"], "event event_type")
    if event_type not in EVENT_TYPES:
        raise ValueError("unknown research thread event_type")
    event_id = _text(value["event_id"], "event event_id")
    recorded_at = _text(value["recorded_at"], "event recorded_at")
    if not isinstance(value["payload"], Mapping):
        raise ValueError("event payload must be a mapping")
    if value["previous_event_hash"] != previous_hash:
        raise ValueError("research thread event hash chain is broken")
    normalized = {
        "event_id": event_id,
        "event_type": event_type,
        "recorded_at": recorded_at,
        "payload": deepcopy(dict(value["payload"])),
        "previous_event_hash": previous_hash,
        "event_hash": _text(value["event_hash"], "event event_hash"),
    }
    _reject_forbidden(normalized)
    if verify_hash and normalized["event_hash"] != _digest({k: v for k, v in normalized.items() if k != "event_hash"}):
        raise ValueError("research thread event hash mismatch")
    return normalized


def _validate_thread(value: Mapping[str, Any], *, verify_hash: bool = True) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != THREAD_KEYS:
        raise ValueError("research thread has missing or unknown fields")
    if value["contract_version"] != CONTRACT_VERSION:
        raise ValueError("unsupported research thread contract_version")
    for key in ("thread_id", "subject", "initial_question", "created_at", "updated_at", "profile_version"):
        _text(value[key], f"thread {key}")
    if value["current_status"] not in THREAD_STATUSES:
        raise ValueError("invalid research thread current_status")
    if value["production_integration"] is not False:
        raise ValueError("research thread production_integration must be false")
    if not isinstance(value["events"], list) or not value["events"]:
        raise ValueError("research thread events must be non-empty")
    previous = ""
    events = []
    for event in value["events"]:
        normalized = _validate_event(event, previous, verify_hash=verify_hash)
        events.append(normalized)
        previous = normalized["event_hash"]
    if value["previous_event_hash"] != previous:
        raise ValueError("research thread previous_event_hash does not match events")
    normalized_thread = dict(value)
    normalized_thread["events"] = events
    normalized_thread["previous_event_hash"] = previous
    if verify_hash and value["thread_hash"] != _digest({k: v for k, v in normalized_thread.items() if k != "thread_hash"}):
        raise ValueError("research thread hash mismatch")
    _reject_forbidden(normalized_thread)
    return deepcopy(normalized_thread)


def create_research_thread(
    *,
    thread_id: str,
    subject: str,
    initial_question: str,
    profile_version: str = "research-companion.v1",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Create a thread with one explicit question-created event."""
    timestamp = created_at or _now()
    event = {
        "event_id": f"{thread_id}:question-created",
        "event_type": "question_created",
        "recorded_at": timestamp,
        "payload": {"question": _text(initial_question, "initial_question")},
        "previous_event_hash": "",
    }
    event["event_hash"] = _digest(event)
    thread = {
        "contract_version": CONTRACT_VERSION,
        "thread_id": _text(thread_id, "thread_id"),
        "subject": _text(subject, "subject"),
        "initial_question": _text(initial_question, "initial_question"),
        "events": [event],
        "current_status": "OPEN",
        "previous_event_hash": event["event_hash"],
        "created_at": timestamp,
        "updated_at": timestamp,
        "profile_version": _text(profile_version, "profile_version"),
        "production_integration": False,
    }
    thread["thread_hash"] = _digest(thread)
    return _validate_thread(thread)


def append_research_event(
    thread: Mapping[str, Any],
    *,
    event_id: str,
    event_type: str,
    payload: Mapping[str, Any],
    recorded_at: str | None = None,
) -> dict[str, Any]:
    """Return a new thread with one append-only event and a new hash."""
    current = _validate_thread(thread)
    if event_type not in EVENT_TYPES:
        raise ValueError("unknown research thread event_type")
    event = {
        "event_id": _text(event_id, "event_id"),
        "event_type": event_type,
        "recorded_at": recorded_at or _now(),
        "payload": deepcopy(dict(payload)),
        "previous_event_hash": current["previous_event_hash"],
    }
    _reject_forbidden(event)
    event["event_hash"] = _digest(event)
    result = deepcopy(current)
    result["events"].append(event)
    result["previous_event_hash"] = event["event_hash"]
    result["updated_at"] = event["recorded_at"]
    if event_type == "verification_pending":
        result["current_status"] = "VERIFICATION_PENDING"
    elif event_type == "invalidated":
        result["current_status"] = "INVALIDATED"
    elif event_type in {"evidence_added", "counterevidence_added", "hypothesis_changed"}:
        result["current_status"] = "OPEN"
    result.pop("thread_hash", None)
    result["thread_hash"] = _digest(result)
    return _validate_thread(result)


def validate_research_card(card: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_card(card)


def validate_research_thread(thread: Mapping[str, Any]) -> dict[str, Any]:
    return _validate_thread(thread)

