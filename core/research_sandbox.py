"""Auditable, point-in-time research sandbox for stock-system experiments.

This module is deliberately research-only.  It does not fetch data, call a
model, place orders, write Advisor/Risk/Telegram records, or produce a
recommendation.  Callers must provide point-in-time observations and source
references; missing or conflicting evidence is preserved as a downgrade.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.research_sandbox.v1"
STATUS = "RESEARCH_ONLY"
NO_DECISION = "NO_PRODUCTION_DECISION"


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _bounded(value: Any, low: float = 0.0, high: float = 1.0) -> float | None:
    number = _finite(value)
    if number is None:
        return None
    return max(low, min(high, number))


def classify_market_regime(features: Mapping[str, Any]) -> dict[str, Any]:
    """Classify a market snapshot without fitting or looking ahead.

    Required inputs are intentionally small and interpretable.  Unknown
    values produce ``UNKNOWN`` rather than a guessed regime.
    """

    trend = _finite(features.get("index_return"))
    breadth = _finite(features.get("breadth_ratio"))
    vol_ratio = _finite(features.get("volume_ratio"))
    realized_vol = _finite(features.get("realized_volatility"))
    if any(value is None for value in (trend, breadth, vol_ratio, realized_vol)):
        return {
            "regime": "UNKNOWN",
            "confidence": 0.0,
            "reason": "missing_required_point_in_time_features",
            "status": "INCOMPLETE",
        }

    if realized_vol >= 0.035 and abs(trend) >= 0.012:
        regime = "HIGH_VOL_DIRECTIONAL"
    elif trend >= 0.006 and breadth >= 0.58 and vol_ratio >= 1.05:
        regime = "TREND_UP"
    elif trend <= -0.006 and breadth <= 0.42:
        regime = "TREND_DOWN"
    else:
        regime = "RANGE_OR_TRANSITION"

    evidence_strength = sum(
        1 for value in (trend, breadth, vol_ratio, realized_vol) if value is not None
    ) / 4.0
    return {
        "regime": regime,
        "confidence": round(evidence_strength, 4),
        "reason": "interpretable_point_in_time_rule",
        "status": "COMPLETE",
    }


def compute_cvar(returns: Sequence[Any], alpha: float = 0.95) -> dict[str, Any]:
    """Return historical loss CVaR while preserving insufficient-sample state."""

    clean = sorted(
        number for number in (_finite(item) for item in returns) if number is not None
    )
    if not clean or not (0.5 < alpha < 1.0):
        return {"cvar": None, "var": None, "sample_size": len(clean), "status": "INCOMPLETE"}

    tail_count = max(1, math.ceil(len(clean) * (1.0 - alpha)))
    tail = clean[:tail_count]
    return {
        "cvar": round(sum(tail) / len(tail), 8),
        "var": round(tail[-1], 8),
        "sample_size": len(clean),
        "tail_count": tail_count,
        "alpha": alpha,
        "status": "COMPLETE" if len(clean) >= 30 else "LOW_SAMPLE",
    }


def compute_crowding(features: Mapping[str, Any]) -> dict[str, Any]:
    """Compute a transparent crowding score; no sentiment model is implied."""

    components = {
        "turnover_percentile": _bounded(features.get("turnover_percentile")),
        "attention_percentile": _bounded(features.get("attention_percentile")),
        "valuation_percentile": _bounded(features.get("valuation_percentile")),
        "price_acceleration": _bounded(features.get("price_acceleration")),
    }
    present = [value for value in components.values() if value is not None]
    if len(present) < 3:
        return {
            "score": None,
            "components": components,
            "status": "INCOMPLETE",
            "reason": "need_at_least_three_independent_crowding_components",
        }

    score = sum(present) / len(present)
    return {
        "score": round(score, 4),
        "components": components,
        "status": "COMPLETE",
        "interpretation": "HIGH_CROWDING" if score >= 0.75 else "NORMAL_OR_LOW_CROWDING",
    }


def build_snapshot(
    *,
    observed_at: str,
    observations: Mapping[str, Any],
    source_refs: Sequence[str],
    factor_candidates: Sequence[Mapping[str, Any]] = (),
    strategy_state: Mapping[str, Any] | None = None,
    risk_state: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a sealed research snapshot with no production decision authority."""

    refs = [str(ref).strip() for ref in source_refs if str(ref).strip()]
    evidence_status = "COMPLETE" if observed_at and refs else "INCOMPLETE_GAPS"
    payload = {
        "contract_version": CONTRACT_VERSION,
        "status": STATUS,
        "decision": NO_DECISION,
        "observed_at": observed_at,
        "observations": dict(observations),
        "source_refs": refs,
        "factor_candidates": [dict(item) for item in factor_candidates],
        "strategy_state": dict(strategy_state or {}),
        "risk_state": dict(risk_state or {}),
        "evidence_status": evidence_status,
        "production_integration": False,
        "recommendation_authority": False,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    payload["snapshot_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return payload


def write_snapshot(path: str | Path, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Persist a sealed snapshot without granting it production authority.

    The writer verifies the content hash before touching disk.  It deliberately
    accepts only ``RESEARCH_ONLY`` records and writes a single JSON artifact;
    production/advisor/risk/telegram paths are outside this contract.
    """

    record = dict(snapshot)
    if record.get("status") != STATUS:
        raise ValueError("snapshot_must_be_research_only")
    if record.get("production_integration") is not False:
        raise ValueError("production_integration_must_be_false")
    if record.get("recommendation_authority") is not False:
        raise ValueError("recommendation_authority_must_be_false")

    stored_hash = str(record.get("snapshot_sha256", ""))
    unsigned = dict(record)
    unsigned.pop("snapshot_sha256", None)
    canonical = json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    calculated_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if not stored_hash or stored_hash != calculated_hash:
        raise ValueError("snapshot_hash_mismatch")

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "WRITTEN_RESEARCH_ONLY",
        "path": str(target),
        "snapshot_sha256": stored_hash,
    }


def metadata() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "status": STATUS,
        "no_production_decision": True,
        "no_future_data": True,
        "point_in_time_sources_required": True,
        "out_of_sample_validation_required": True,
        "live_sample_validation_required_before_adoption": True,
        "teacher_augmented_not_replaced": True,
    }
