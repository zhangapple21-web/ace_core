"""Time-boxed A-share early-session research protocol.

The module converts the human morning checklist into an auditable *readiness*
record.  It does not select securities, issue trade instructions, fetch market
data, invoke a model, or relax ACE's stock-data admission requirements.

Its immediate purpose is historical replay and human-operated dry-runs.  A
future candidate engine may consume this record only after its own validated
rule profile and ACE Phase 2 data admission are both present.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from .indicator_archive import CONTRACT_VERSION as TN6_BRIDGE_CONTRACT_VERSION


CONTRACT_VERSION = "ace.early_session_research_protocol.v1"
TIMEZONE = ZoneInfo("Asia/Shanghai")

# These are data-completeness gates, not price-prediction thresholds.  Numeric
# signal thresholds need frozen historical validation before they are allowed
# into a rule profile, so this protocol deliberately does not invent them.
PHASES: dict[str, dict[str, Any]] = {
    "premarket": {
        "start": time(9, 0), "end": time(9, 15),
        "required_fields": frozenset({"announcement_scan", "overnight_context", "sector_hypotheses"}),
    },
    "auction": {
        "start": time(9, 15), "end": time(9, 25),
        "required_fields": frozenset({"auction_quote", "auction_volume", "index_auction"}),
    },
    "first_minute": {
        "start": time(9, 30), "end": time(9, 31),
        "required_fields": frozenset({"quote", "minute_kline_1m", "index"}),
    },
    "open_validation": {
        "start": time(9, 30), "end": time(9, 45),
        "required_fields": frozenset({"quote", "minute_kline_1m", "index", "sector_breadth", "volume_price"}),
    },
}
_PHASE_ORDER = tuple(PHASES)

_REQUIRED_LIVE_OPERATIONS = frozenset({"quote", "minute_kline_1m", "index"})


def _parse_local(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value))
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include an explicit timezone")
    return parsed.astimezone(TIMEZONE)


def _phase_for(observed_at: datetime) -> str | None:
    current = observed_at.time()
    for name, definition in PHASES.items():
        if definition["start"] <= current <= definition["end"]:
            return name
    return None


def _strict_live_admission(admission: Mapping[str, Any]) -> bool:
    operations = admission.get("operations")
    if admission.get("phase_two_status") != "ADMITTED" or not isinstance(operations, Mapping):
        return False
    return all(
        isinstance(operations.get(operation), Mapping)
        and operations[operation].get("independent_cross_validation") is True
        and operations[operation].get("lineage_observable") is True
        and operations[operation].get("fresh") is True
        and operations[operation].get("coverage_complete") is True
        and operations[operation].get("fields_complete") is True
        and operations[operation].get("cross_source_consistent") is True
        for operation in _REQUIRED_LIVE_OPERATIONS
    )


def build_early_session_research_record(
    *,
    observed_at: str,
    phase_observations: Mapping[str, Mapping[str, Any]],
    data_admission: Mapping[str, Any],
    rule_profile: Mapping[str, Any] | None = None,
    context_questions: Sequence[Mapping[str, Any]] = (),
    indicator_bridge: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a fail-closed early-session research/replay record.

    ``phase_observations`` holds retained, point-in-time evidence.  Every
    completed phase needs an explicit source reference and all of its required
    fields.  Context questions (forum disagreement, public clues) remain
    questions and cannot satisfy an omitted hard-data field.
    """
    local_now = _parse_local(observed_at)
    active_phase = _phase_for(local_now)
    due_phases = {
        name for name, definition in PHASES.items()
        if local_now.time() >= definition["start"]
    }
    blockers: list[str] = []
    phase_results: dict[str, dict[str, Any]] = {}
    for name, definition in PHASES.items():
        observation = phase_observations.get(name)
        if observation is None:
            phase_results[name] = {"status": "NOT_RECORDED", "missing_fields": sorted(definition["required_fields"])}
            if name in due_phases:
                blockers.append(f"{name}_not_recorded")
            continue
        if not isinstance(observation, Mapping):
            raise ValueError(f"{name} observation must be a mapping")
        fields = observation.get("fields")
        refs = observation.get("source_refs")
        if not isinstance(fields, Mapping) or not isinstance(refs, (list, tuple)) or not refs:
            raise ValueError(f"{name} requires fields and non-empty source_refs")
        missing = sorted(field for field in definition["required_fields"] if fields.get(field) is None)
        status = "COMPLETE" if not missing else "INCOMPLETE"
        phase_results[name] = {
            "status": status,
            "observed_at": str(observation.get("observed_at", observed_at)),
            "source_refs": [str(ref) for ref in refs],
            "missing_fields": missing,
        }
        if name in due_phases and missing:
            blockers.append(f"{name}_missing_required_fields")

    if active_phase is None:
        blockers.append("outside_early_session_window")
    if not _strict_live_admission(data_admission):
        blockers.append("live_quote_1m_index_not_strictly_admitted")

    profile = dict(rule_profile or {})
    if profile:
        if not str(profile.get("profile_id", "")).strip() or not profile.get("historical_validation_ref"):
            blockers.append("rule_profile_not_historically_validated")
    else:
        blockers.append("no_frozen_rule_profile")

    normalized_questions = []
    for question in context_questions:
        if not isinstance(question, Mapping) or not str(question.get("source_ref", "")).strip() or not str(question.get("question", "")).strip():
            raise ValueError("context questions require source_ref and question")
        normalized_questions.append({
            "source_ref": str(question["source_ref"]),
            "question": str(question["question"]),
            "status": "CROSS_VALIDATE_WITH_HARD_DATA",
        })

    normalized_indicator_bridge = None
    if indicator_bridge is not None:
        if not isinstance(indicator_bridge, Mapping):
            raise ValueError("indicator_bridge_must_be_mapping")
        if indicator_bridge.get("contract_version") != TN6_BRIDGE_CONTRACT_VERSION:
            raise ValueError("unsupported_indicator_bridge_contract")
        if indicator_bridge.get("research_status") != "RESEARCH_ONLY":
            raise ValueError("indicator_bridge_must_be_research_only")
        if indicator_bridge.get("can_consume_as_market_signal") is not False:
            raise ValueError("indicator_bridge_cannot_be_market_signal")
        if not str(indicator_bridge.get("inventory_hash", "")).strip():
            raise ValueError("indicator_bridge_inventory_hash_required")
        entries = indicator_bridge.get("entries")
        if not isinstance(entries, (list, tuple)):
            raise ValueError("indicator_bridge_entries_required")
        # Preserve the bridge as a research reference.  It is intentionally
        # not used to fill a missing quote, minute bar, index, or factor score.
        normalized_indicator_bridge = dict(indicator_bridge)

    return {
        "contract_version": CONTRACT_VERSION,
        "observed_at": local_now.isoformat(),
        "timezone": "Asia/Shanghai",
        "active_phase": active_phase,
        "mode": "HISTORICAL_REPLAY_OR_HUMAN_DRY_RUN",
        "research_status": "RESEARCH_ONLY",
        "recommendation_authority": False,
        "automatic_delivery": False,
        "phase_results": phase_results,
        "data_admission": {"strict_live_admission": _strict_live_admission(data_admission)},
        "rule_profile": profile or None,
        "context_questions": normalized_questions,
        "indicator_bridge": normalized_indicator_bridge,
        "blockers": sorted(set(blockers)),
        "next_action": "record_missing_evidence_or_replay_a_frozen_historical_case",
    }
