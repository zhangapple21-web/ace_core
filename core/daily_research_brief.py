"""Governed daily A-share research briefs.

This is a research-review boundary, deliberately separate from Advisor, Risk,
Telegram, broker gateways, and model execution.  It turns already-admitted
observations into a reviewable record for a teacher; it never produces an
order, a BUY/SELL instruction, or an outbound message.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.daily_research_brief.v1"
REQUIRED_OPERATIONS = frozenset({"quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index"})
_BRIEF_KEYS = frozenset({
    "contract_version", "brief_id", "market_date", "generated_at", "brief_status",
    "data_quality", "admission", "candidate_cards", "teacher_decisions", "delivery", "disclaimer",
})
_CARD_KEYS = frozenset({
    "candidate_id", "symbol", "observed_at", "rule_card_id", "trigger_reasons",
    "invalidating_conditions", "source_refs", "data_snapshot_hash", "research_summary", "backtest_summary",
})
_DELIVERY = {
    "mode": "MANUAL_ONLY",
    "telegram_send_requested": False,
    "telegram_send_performed": False,
    "outbound_message": None,
}
_FORBIDDEN_FIELD_NAMES = frozenset({
    "advisor", "broker", "order", "orders", "risk", "telegram", "target_price", "guarantee",
})


class BriefStatus(str, Enum):
    RESEARCH_ONLY = "RESEARCH_ONLY"
    REVIEW_READY = "REVIEW_READY"


class TeacherDecision(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class CandidateCard:
    """A descriptive, point-in-time candidate for human review only."""

    candidate_id: str
    symbol: str
    observed_at: str
    rule_card_id: str
    trigger_reasons: tuple[str, ...]
    invalidating_conditions: tuple[str, ...]
    source_refs: tuple[str, ...]
    data_snapshot_hash: str
    research_summary: str
    backtest_summary: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CandidateCard":
        required = (
            "candidate_id", "symbol", "observed_at", "rule_card_id",
            "trigger_reasons", "invalidating_conditions", "source_refs",
            "data_snapshot_hash", "research_summary", "backtest_summary",
        )
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"candidate card missing: {', '.join(missing)}")
        for collection in ("trigger_reasons", "invalidating_conditions", "source_refs"):
            if not isinstance(value[collection], (list, tuple)) or not value[collection]:
                raise ValueError(f"candidate card {collection} must be non-empty")
        if not str(value["data_snapshot_hash"]).strip():
            raise ValueError("candidate card data_snapshot_hash must be non-empty")
        if not isinstance(value["backtest_summary"], Mapping):
            raise ValueError("candidate card backtest_summary must be a mapping")
        return cls(
            candidate_id=str(value["candidate_id"]),
            symbol=str(value["symbol"]),
            observed_at=str(value["observed_at"]),
            rule_card_id=str(value["rule_card_id"]),
            trigger_reasons=tuple(str(item) for item in value["trigger_reasons"]),
            invalidating_conditions=tuple(str(item) for item in value["invalidating_conditions"]),
            source_refs=tuple(str(item) for item in value["source_refs"]),
            data_snapshot_hash=str(value["data_snapshot_hash"]),
            research_summary=str(value["research_summary"]),
            backtest_summary=dict(value["backtest_summary"]),
        )


def _strict_phase_two_admitted(matrix: Mapping[str, Any]) -> bool:
    admission = matrix.get("phase_two_admission", {})
    if not isinstance(admission, Mapping) or admission.get("status") != "ADMITTED":
        return False
    operations = admission.get("core_operations", {})
    if not isinstance(operations, Mapping) or set(operations) != REQUIRED_OPERATIONS:
        return False
    return all(
        isinstance(operations.get(name), Mapping)
        and bool(operations[name].get("production_sources"))
        and len(set(operations[name].get("independence_groups", []))) >= 2
        and operations[name].get("has_independent_cross_validation") is True
        for name in REQUIRED_OPERATIONS
    )


def _readiness(data_quality: Mapping[str, Any], capability_matrix: Mapping[str, Any]) -> tuple[BriefStatus, list[str]]:
    reasons: list[str] = []
    if data_quality.get("recommendation_eligibility") != "eligible":
        reasons.append("data_quality_not_recommendation_eligible")
    if data_quality.get("data_quality_status") != "READY":
        reasons.append("data_quality_not_ready")
    if not _strict_phase_two_admitted(capability_matrix):
        reasons.append("a_share_phase_two_not_strictly_admitted")
    return (BriefStatus.REVIEW_READY, []) if not reasons else (BriefStatus.RESEARCH_ONLY, reasons)


def build_daily_research_brief(
    *,
    brief_id: str,
    market_date: str,
    generated_at: str,
    data_quality: Mapping[str, Any],
    capability_matrix: Mapping[str, Any],
    candidates: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build an auditable review packet and fail closed on data admission.

    A blocked brief remains valuable as a research/operations record, but its
    candidate list is always empty and it can never become forward-eligible.
    """
    status, blockers = _readiness(data_quality, capability_matrix)
    cards = [CandidateCard.from_mapping(candidate) for candidate in candidates]
    if len({card.candidate_id for card in cards}) != len(cards):
        raise ValueError("candidate_id values must be unique")
    if status != BriefStatus.REVIEW_READY:
        cards = []
    return {
        "contract_version": CONTRACT_VERSION,
        "brief_id": str(brief_id),
        "market_date": str(market_date),
        "generated_at": str(generated_at),
        "brief_status": status.value,
        "data_quality": dict(data_quality),
        "admission": {
            "phase_two_strictly_admitted": status == BriefStatus.REVIEW_READY,
            "blockers": blockers,
        },
        "candidate_cards": [asdict(card) for card in cards],
        "teacher_decisions": {},
        "delivery": dict(_DELIVERY),
        "disclaimer": "Research brief for teacher review only. It is not an order, performance guarantee, or outbound recommendation.",
    }


def record_teacher_decision(
    brief: Mapping[str, Any],
    *,
    candidate_id: str,
    decision: TeacherDecision | str,
    decided_at: str,
    rationale: str,
) -> dict[str, Any]:
    """Record a human decision without sending anything externally."""
    result = json.loads(json.dumps(brief, ensure_ascii=False))
    decision = TeacherDecision(decision)
    cards = {card["candidate_id"] for card in result.get("candidate_cards", [])}
    if candidate_id not in cards:
        raise ValueError("candidate_id is not present in a review-ready brief")
    if result.get("brief_status") != BriefStatus.REVIEW_READY.value:
        raise ValueError("teacher decisions require a review-ready brief")
    if not str(rationale).strip():
        raise ValueError("teacher decision rationale must be non-empty")
    result.setdefault("teacher_decisions", {})[candidate_id] = {
        "decision": decision.value,
        "decided_at": str(decided_at),
        "rationale": str(rationale),
        "forward_eligible": decision == TeacherDecision.APPROVED,
        "manual_transfer_required": True,
    }
    # This module owns no outbound mechanism.  Preserve the hard no-send state.
    result["delivery"] = dict(_DELIVERY)
    return result


def _reject_forbidden_fields(value: Any) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_FIELD_NAMES:
                raise ValueError(f"brief contains forbidden field: {key}")
            _reject_forbidden_fields(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden_fields(item)


def validate_brief(brief: Mapping[str, Any]) -> dict[str, Any]:
    """Validate an artifact before persistence; reject spoofed delivery state."""
    if not isinstance(brief, Mapping):
        raise ValueError("brief must be a mapping")
    if set(brief) != _BRIEF_KEYS:
        raise ValueError("brief has missing or unknown top-level fields")
    if brief.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("unsupported brief contract_version")
    if brief.get("delivery") != _DELIVERY:
        raise ValueError("brief delivery must remain MANUAL_ONLY")
    status = brief.get("brief_status")
    if status not in {item.value for item in BriefStatus}:
        raise ValueError("unknown brief_status")
    admission = brief.get("admission")
    if not isinstance(admission, Mapping) or set(admission) != {"phase_two_strictly_admitted", "blockers"}:
        raise ValueError("brief admission is malformed")
    if not isinstance(admission["blockers"], list):
        raise ValueError("brief blockers must be a list")
    cards = brief.get("candidate_cards")
    decisions = brief.get("teacher_decisions")
    if not isinstance(cards, list) or not isinstance(decisions, Mapping):
        raise ValueError("brief candidate_cards or teacher_decisions is malformed")
    if status == BriefStatus.RESEARCH_ONLY.value and (cards or decisions or admission["phase_two_strictly_admitted"]):
        raise ValueError("research-only brief cannot contain cards, decisions, or admission")
    if status == BriefStatus.REVIEW_READY.value and (admission["blockers"] or not admission["phase_two_strictly_admitted"]):
        raise ValueError("review-ready brief requires strict admission without blockers")
    for card in cards:
        if not isinstance(card, Mapping) or set(card) != _CARD_KEYS:
            raise ValueError("candidate card has missing or unknown fields")
        CandidateCard.from_mapping(card)
        _reject_forbidden_fields(card["backtest_summary"])
    card_ids = {card["candidate_id"] for card in cards}
    for candidate_id, decision in decisions.items():
        if candidate_id not in card_ids or not isinstance(decision, Mapping):
            raise ValueError("teacher decision has no matching candidate card")
        required = {"decision", "decided_at", "rationale", "forward_eligible", "manual_transfer_required"}
        if set(decision) != required:
            raise ValueError("teacher decision has missing or unknown fields")
        choice = TeacherDecision(decision["decision"])
        if not str(decision["rationale"]).strip():
            raise ValueError("teacher decision rationale must be non-empty")
        if decision["forward_eligible"] != (choice == TeacherDecision.APPROVED) or decision["manual_transfer_required"] is not True:
            raise ValueError("teacher decision forward eligibility is malformed")
    return json.loads(json.dumps(brief, ensure_ascii=False))


def write_brief(path: str | Path, brief: Mapping[str, Any]) -> Path:
    """Atomically persist a review artifact owned by this module."""
    safe_brief = validate_brief(brief)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(safe_brief, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, target)
    return target
