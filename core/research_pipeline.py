"""Deterministic research-pipeline helpers for the ACE sandbox.

This module connects evidence containers, transparent factor candidates and
walk-forward summaries.  It is intentionally not a recommender: no network
calls, model fitting, order routing or Advisor/Risk/Telegram writes occur
here.  Missing or conflicting evidence is represented explicitly.
"""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from .research_sandbox import (
    STATUS,
    build_snapshot,
    classify_market_regime,
    compute_crowding,
    compute_cvar,
)


CONTRACT_VERSION = "ace.research_pipeline.v1"
EVIDENCE_KINDS = ("market", "sector", "funds", "announcements")
EVIDENCE_STATUSES = ("VERIFIED", "PARTIAL", "UNVERIFIED", "CONFLICTED")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _clip(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def normalize_evidence(
    kind: str,
    payload: Mapping[str, Any] | None,
    *,
    observed_at: str,
    source_refs: Sequence[str] = (),
    status: str = "UNVERIFIED",
    coverage: Any = None,
    conflict_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Normalize one point-in-time evidence bucket without filling gaps."""

    if kind not in EVIDENCE_KINDS:
        raise ValueError("unsupported_evidence_kind")
    if status not in EVIDENCE_STATUSES:
        raise ValueError("unsupported_evidence_status")
    refs = [str(ref).strip() for ref in source_refs if str(ref).strip()]
    conflicts = [str(ref).strip() for ref in conflict_refs if str(ref).strip()]
    normalized_coverage = _number(coverage)
    if normalized_coverage is not None:
        normalized_coverage = round(_clip(normalized_coverage), 6)
    return {
        "kind": kind,
        "observed_at": str(observed_at or ""),
        "status": status,
        "source_refs": refs,
        "coverage": normalized_coverage,
        "conflict_refs": conflicts,
        "payload": dict(payload or {}),
    }


def build_evidence_bundle(
    *,
    observed_at: str,
    market: Mapping[str, Any] | None = None,
    sector: Mapping[str, Any] | None = None,
    funds: Mapping[str, Any] | None = None,
    announcements: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the four evidence containers used by the research workflow.

    Each input may contain ``payload``, ``source_refs``, ``status``,
    ``coverage`` and ``conflict_refs``.  A raw mapping is retained as payload
    and defaults to ``UNVERIFIED`` so the caller cannot accidentally claim
    that an unlabelled source was checked.
    """

    buckets = {"market": market, "sector": sector, "funds": funds, "announcements": announcements}
    result: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "observed_at": str(observed_at or ""),
        "evidence": {},
    }
    for kind in EVIDENCE_KINDS:
        item = buckets[kind] or {}
        item_payload = item.get("payload", item) if isinstance(item, Mapping) else {}
        result["evidence"][kind] = normalize_evidence(
            kind,
            item_payload if isinstance(item_payload, Mapping) else {},
            observed_at=str(item.get("observed_at", observed_at)) if isinstance(item, Mapping) else observed_at,
            source_refs=item.get("source_refs", ()) if isinstance(item, Mapping) else (),
            status=str(item.get("status", "UNVERIFIED")) if isinstance(item, Mapping) else "UNVERIFIED",
            coverage=item.get("coverage") if isinstance(item, Mapping) else None,
            conflict_refs=item.get("conflict_refs", ()) if isinstance(item, Mapping) else (),
        )
    statuses = [result["evidence"][kind]["status"] for kind in EVIDENCE_KINDS]
    if all(status == "VERIFIED" for status in statuses):
        bundle_status = "COMPLETE"
    elif any(status == "CONFLICTED" for status in statuses):
        bundle_status = "CONFLICTED"
    elif any(status == "PARTIAL" for status in statuses):
        bundle_status = "PARTIAL"
    else:
        bundle_status = "INCOMPLETE"
    result["status"] = bundle_status
    result["missing_or_unverified"] = [
        kind for kind in EVIDENCE_KINDS if result["evidence"][kind]["status"] != "VERIFIED"
    ]
    return result


def _candidate(
    *,
    candidate_id: str,
    family: str,
    required: Sequence[str],
    features: Mapping[str, Any],
    score: float | None,
    direction: str,
) -> dict[str, Any]:
    missing = [name for name in required if _number(features.get(name)) is None]
    return {
        "candidate_id": candidate_id,
        "family": family,
        "required_features": list(required),
        "missing_features": missing,
        "score": round(_clip(score), 6) if score is not None and not missing else None,
        "direction": direction,
        "status": "COMPLETE" if not missing and score is not None else "UNKNOWN",
        "research_only": True,
        "formula_version": "deterministic_baseline_v1",
    }


def generate_factor_candidates(features: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Generate auditable baseline candidates, never inventing missing inputs.

    These are seed candidates for later factor evolution.  They are not
    genetic/RL discoveries and carry no production eligibility.
    """

    def value(name: str) -> float | None:
        return _number(features.get(name))

    return [
        _candidate(
            candidate_id="trend_momentum_seed",
            family="trend",
            required=("return_5d", "close_vs_ma20", "volume_ratio"),
            features=features,
            score=(
                0.4 * _clip((value("return_5d") or 0.0) / 0.12 + 0.5)
                + 0.35 * _clip((value("close_vs_ma20") or 0.0) / 0.12 + 0.5)
                + 0.25 * _clip((value("volume_ratio") or 0.0) / 2.0)
                if all(value(name) is not None for name in ("return_5d", "close_vs_ma20", "volume_ratio"))
                else None
            ),
            direction="positive_trend_confirmation",
        ),
        _candidate(
            candidate_id="flow_price_confirmation_seed",
            family="flow",
            required=("main_flow_pct", "price_change_pct", "turnover_ratio"),
            features=features,
            score=(
                0.45 * _clip((value("main_flow_pct") or 0.0) / 0.08 + 0.5)
                + 0.35 * _clip((value("price_change_pct") or 0.0) / 0.10 + 0.5)
                + 0.20 * _clip((value("turnover_ratio") or 0.0) / 2.0)
                if all(value(name) is not None for name in ("main_flow_pct", "price_change_pct", "turnover_ratio"))
                else None
            ),
            direction="price_and_flow_alignment",
        ),
        _candidate(
            candidate_id="crowding_risk_seed",
            family="risk",
            required=("turnover_percentile", "attention_percentile", "price_acceleration"),
            features=features,
            score=(
                0.35 * _clip(value("turnover_percentile") or 0.0)
                + 0.35 * _clip(value("attention_percentile") or 0.0)
                + 0.30 * _clip(value("price_acceleration") or 0.0)
                if all(value(name) is not None for name in ("turnover_percentile", "attention_percentile", "price_acceleration"))
                else None
            ),
            direction="higher_means_more_crowded",
        ),
    ]


def summarize_walk_forward(results: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Aggregate OOS windows while keeping adoption permanently gated here."""

    windows = [dict(item) for item in results]
    returns = [_number(item.get("oos_mean_return", item.get("mean_return"))) for item in windows]
    clean = [value for value in returns if value is not None]
    hit_rates = [_number(item.get("hit_rate")) for item in windows]
    clean_hits = [value for value in hit_rates if value is not None]
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "COMPLETE" if len(clean) >= 2 else "LOW_SAMPLE",
        "windows": len(windows),
        "valid_windows": len(clean),
        "positive_windows": sum(value > 0 for value in clean),
        "negative_windows": sum(value < 0 for value in clean),
        "oos_mean_return": round(sum(clean) / len(clean), 8) if clean else None,
        "mean_hit_rate": round(sum(clean_hits) / len(clean_hits), 6) if clean_hits else None,
        "production_eligible": False,
        "reason": "research_only_until_live_sample_validation_and_teacher_review",
    }


def build_research_snapshot(
    *,
    observed_at: str,
    evidence_bundle: Mapping[str, Any],
    market_features: Mapping[str, Any],
    returns: Sequence[Any] = (),
    crowding_features: Mapping[str, Any] | None = None,
    factor_features: Mapping[str, Any] | None = None,
    source_refs: Sequence[str] = (),
    validation_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble one sealed research record for later human review."""

    observations = {
        "pipeline_contract_version": CONTRACT_VERSION,
        "evidence_bundle": dict(evidence_bundle),
        "market_regime": classify_market_regime(market_features),
        "factor_candidates": generate_factor_candidates(factor_features or {}),
        "validation_summary": dict(validation_summary or {}),
    }
    risk_state = {
        "cvar": compute_cvar(returns),
        "crowding": compute_crowding(crowding_features or {}),
        "risk_budget_target_is_research_only": True,
    }
    return build_snapshot(
        observed_at=observed_at,
        observations=observations,
        source_refs=source_refs,
        factor_candidates=observations["factor_candidates"],
        strategy_state={"mode": "RESEARCH_ONLY", "production_eligible": False},
        risk_state=risk_state,
    )
