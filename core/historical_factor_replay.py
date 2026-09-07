"""Deterministic, read-only replay for a small cross-sectional factor baseline.

The replay accepts an explicit point-in-time OHLCV snapshot.  It refuses
benchmark summaries, live endpoints, incomplete rows, and datasets without
observable source references.  It never fetches data or writes production
state; the CLI writes only a caller-selected research report.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.historical_factor_replay.v1"
REQUIRED_ROW_FIELDS = ("timestamp", "symbol", "open", "high", "low", "close", "volume")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _finite(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field}_must_be_finite")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_must_be_finite") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field}_must_be_finite")
    return result


def _rank(values: Sequence[float]) -> list[float]:
    """Average ranks for ties, preserving input order."""

    pairs = sorted(enumerate(values), key=lambda item: item[1])
    result = [0.0] * len(values)
    index = 0
    while index < len(pairs):
        end = index + 1
        while end < len(pairs) and pairs[end][1] == pairs[index][1]:
            end += 1
        rank = (index + 1 + end) / 2.0
        for original, _ in pairs[index:end]:
            result[original] = rank
        index = end
    return result


def _spearman(left: Sequence[float], right: Sequence[float]) -> float | None:
    if len(left) != len(right) or len(left) < 2:
        return None
    x, y = _rank(left), _rank(right)
    x_mean, y_mean = mean(x), mean(y)
    numerator = sum((a - x_mean) * (b - y_mean) for a, b in zip(x, y))
    x_dev = math.sqrt(sum((a - x_mean) ** 2 for a in x))
    y_dev = math.sqrt(sum((b - y_mean) ** 2 for b in y))
    if x_dev == 0 or y_dev == 0:
        return None
    return numerator / (x_dev * y_dev)


def _ndcg_at_k(scores: Sequence[float], outcomes: Sequence[float], k: int) -> float | None:
    if len(scores) != len(outcomes) or not scores:
        return None
    k = max(1, min(k, len(scores)))
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    ideal = sorted(outcomes, reverse=True)[:k]
    dcg = sum((2**outcomes[i] - 1) / math.log2(position + 2) for position, i in enumerate(order[:k]))
    ideal_dcg = sum((2**value - 1) / math.log2(position + 2) for position, value in enumerate(ideal))
    return 0.0 if ideal_dcg == 0 else dcg / ideal_dcg


def load_snapshot(path: str | Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Load and validate a snapshot, returning ``(dataset, rejection)``."""

    path = Path(path)
    if not path.exists() or not path.is_file():
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "snapshot_file_missing", "path": str(path)}
    raw = path.read_bytes()
    file_hash = _sha256_bytes(raw)
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "snapshot_not_json", "path": str(path), "file_hash": file_hash}
    if isinstance(value, list):
        metadata: dict[str, Any] = {}
        rows = value
    elif isinstance(value, Mapping):
        metadata = dict(value.get("metadata", {})) if isinstance(value.get("metadata"), Mapping) else {}
        rows = value.get("rows")
    else:
        rows = None
        metadata = {}
    if not isinstance(rows, list) or not rows:
        return None, {
            "status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT",
            "reason": "snapshot_has_no_row_level_ohlcv; benchmark_summary_not_accepted",
            "path": str(path),
            "file_hash": file_hash,
        }
    source_refs = metadata.get("source_refs")
    if not isinstance(source_refs, list) or not source_refs or any(not isinstance(item, str) or not item.strip() for item in source_refs):
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "source_refs_missing", "path": str(path), "file_hash": file_hash}
    if metadata.get("lineage_observable") is not True:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "lineage_not_observable", "path": str(path), "file_hash": file_hash}
    if not isinstance(metadata.get("point_in_time_rule"), str) or not metadata["point_in_time_rule"].strip():
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "point_in_time_rule_missing", "path": str(path), "file_hash": file_hash}
    split = metadata.get("out_of_sample_split")
    if not isinstance(split, Mapping) or any(not isinstance(split.get(key), str) or not split[key].strip() for key in ("train", "validation", "test")):
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "out_of_sample_split_missing_or_incomplete", "path": str(path), "file_hash": file_hash}
    cost_model = metadata.get("cost_model")
    if not isinstance(cost_model, Mapping) or not cost_model:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "cost_model_missing", "path": str(path), "file_hash": file_hash}
    if metadata.get("cross_source_consistency") is not True:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "cross_source_consistency_not_confirmed", "path": str(path), "file_hash": file_hash}

    normalized = []
    seen_keys: set[tuple[str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or any(field not in row for field in REQUIRED_ROW_FIELDS):
            return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": f"row_{index}_missing_required_field", "path": str(path), "file_hash": file_hash}
        symbol = str(row["symbol"]).strip()
        timestamp = str(row["timestamp"]).strip()
        if not symbol or not timestamp:
            return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": f"row_{index}_identity_missing", "path": str(path), "file_hash": file_hash}
        key = (timestamp, symbol)
        if key in seen_keys:
            return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": f"duplicate_row:{timestamp}:{symbol}", "path": str(path), "file_hash": file_hash}
        seen_keys.add(key)
        item = {"timestamp": timestamp, "symbol": symbol}
        for field in ("open", "high", "low", "close", "volume"):
            item[field] = _finite(row[field], f"row_{index}.{field}")
        if item["close"] <= 0 or item["volume"] < 0:
            return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": f"row_{index}_invalid_price_or_volume", "path": str(path), "file_hash": file_hash}
        if item["high"] < max(item["open"], item["close"]) or item["low"] > min(item["open"], item["close"]) or item["low"] > item["high"]:
            return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": f"row_{index}_ohlc_relationship_invalid", "path": str(path), "file_hash": file_hash}
        normalized.append(item)
    sessions = sorted({row["timestamp"] for row in normalized})
    symbols = sorted({row["symbol"] for row in normalized})
    if len(sessions) < 20:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "fewer_than_20_sessions", "sessions": len(sessions), "symbols": len(symbols), "path": str(path), "file_hash": file_hash}
    if len(symbols) < 3:
        return None, {"status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": "fewer_than_3_symbols", "sessions": len(sessions), "symbols": len(symbols), "path": str(path), "file_hash": file_hash}
    return {
        "metadata": {**metadata, "file_hash": file_hash, "sessions": sessions, "symbols": symbols},
        "rows": normalized,
    }, {"status": "ELIGIBLE", "sessions": len(sessions), "symbols": len(symbols), "file_hash": file_hash}


def replay_momentum(snapshot: Mapping[str, Any], *, lookback: int = 5) -> dict[str, Any]:
    """Replay a simple cross-sectional momentum baseline without side effects."""

    rows = snapshot.get("rows") if isinstance(snapshot, Mapping) else None
    metadata = snapshot.get("metadata") if isinstance(snapshot, Mapping) else None
    if not isinstance(rows, list) or not isinstance(metadata, Mapping):
        raise ValueError("validated_snapshot_required")
    by_symbol: dict[str, dict[str, dict[str, float]]] = {}
    for row in rows:
        by_symbol.setdefault(row["symbol"], {})[row["timestamp"]] = row
    sessions = list(metadata["sessions"])
    per_date_ic: list[float] = []
    per_date_ndcg: list[float] = []
    per_date_turnover: list[float] = []
    previous_rank: dict[str, float] | None = None
    slices: dict[str, list[float]] = {"up": [], "down": [], "flat": []}
    for index in range(lookback, len(sessions) - 1):
        current_session, forward_session = sessions[index], sessions[index + 1]
        factors: list[float] = []
        outcomes: list[float] = []
        names: list[str] = []
        for symbol, series in by_symbol.items():
            current = series.get(current_session)
            past = series.get(sessions[index - lookback])
            forward = series.get(forward_session)
            if not current or not past or not forward or past["close"] <= 0 or current["close"] <= 0:
                continue
            factors.append(current["close"] / past["close"] - 1.0)
            outcomes.append(forward["close"] / current["close"] - 1.0)
            names.append(symbol)
        if len(factors) < 3:
            continue
        ic = _spearman(factors, outcomes)
        ndcg = _ndcg_at_k(factors, outcomes, max(1, len(factors) // 5))
        if ic is None or ndcg is None:
            continue
        per_date_ic.append(ic)
        per_date_ndcg.append(ndcg)
        ranks = {name: rank for name, rank in zip(names, _rank(factors))}
        if previous_rank is not None:
            common = sorted(set(previous_rank) & set(ranks))
            if common:
                distance = mean(abs(previous_rank[name] - ranks[name]) for name in common)
                max_rank = max(len(common) - 1, 1)
                per_date_turnover.append(min(1.0, distance / max_rank))
        previous_rank = ranks
        market_return = mean(outcomes)
        slices["up" if market_return > 0.002 else "down" if market_return < -0.002 else "flat"].append(ic)
    if not per_date_ic:
        raise ValueError("replay_has_no_complete_cross_sectional_windows")
    ic_mean = mean(per_date_ic)
    ic_ir = ic_mean / stdev(per_date_ic) if len(per_date_ic) > 1 and stdev(per_date_ic) else 0.0
    return {
        "contract_version": CONTRACT_VERSION,
        "status": "REPLAY_COMPLETED",
        "mode": "FACTOR_RESEARCH_ONLY",
        "factor_id": f"baseline.momentum_{lookback}d",
        "dataset_snapshot_hash": metadata["file_hash"],
        "source_refs": list(metadata["source_refs"]),
        "point_in_time_rule": metadata["point_in_time_rule"],
        "sessions_used": len(per_date_ic),
        "metrics": {
            "rank_ic": round(ic_mean, 8),
            "ic_ir": round(ic_ir, 8),
            "ndcg_at_k": round(mean(per_date_ndcg), 8),
            "turnover": round(mean(per_date_turnover), 8) if per_date_turnover else None,
            "complexity": 1.0,
            "missingness": 0.0,
            "ic_hit_rate": round(sum(value > 0 for value in per_date_ic) / len(per_date_ic), 8),
        },
        "semantic_slices": {
            key: {"sessions": len(values), "rank_ic": round(mean(values), 8) if values else None}
            for key, values in slices.items()
        },
        "out_of_sample_split": metadata.get("out_of_sample_split", {}),
        "execution_friction": {
            "evidence_status": "MISSING_REAL_WORLD_EXECUTION_EVIDENCE",
            "capacity": {"status": "NOT_EVALUATED"},
            "market_impact": {"status": "NOT_EVALUATED"},
            "crowding": {"status": "NOT_EVALUATED"},
            "execution_feasibility": {"status": "NOT_EVALUATED"},
            "downgrade_conditions": [
                "execution-layer evidence is absent",
                "do not construct an ACE factor-contract candidate from this replay",
            ],
        },
        "factor_contract_candidate": False,
        "factor_contract_candidate_reason": "execution_friction_evidence_not_available",
        "production_integration": False,
        "recommendation_authority": False,
        "teacher_review_required": True,
    }


def run_replay(path: str | Path) -> dict[str, Any]:
    snapshot, status = load_snapshot(path)
    if snapshot is None:
        return {"contract_version": CONTRACT_VERSION, **status, "mode": "FACTOR_RESEARCH_ONLY", "production_integration": False, "recommendation_authority": False}
    try:
        return replay_momentum(snapshot)
    except ValueError as exc:
        return {"contract_version": CONTRACT_VERSION, "status": "NO_ELIGIBLE_HISTORICAL_SNAPSHOT", "reason": str(exc), "mode": "FACTOR_RESEARCH_ONLY", "dataset_snapshot_hash": status["file_hash"], "production_integration": False, "recommendation_authority": False}


def write_report(report: Mapping[str, Any], output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(dict(report), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(encoded, encoding="utf-8")
    temporary.replace(output)
    return output
