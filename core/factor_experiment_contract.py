"""Evidence-bound contract for ACE-side factor research experiments.

This module is intentionally pure and research-only.  It validates the
metadata needed to replay a factor experiment and provides a deterministic
Pareto comparison helper.  It does not fetch market data, call a model, write
TaskPool/Advisor/Risk/Telegram records, or emit a recommendation.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.factor_experiment.v2"
MODE = "FACTOR_RESEARCH_ONLY"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_EXECUTION_FRICTION_REQUIRED_FIELDS = (
    "evidence_status",
    "capacity",
    "market_impact",
    "crowding",
    "execution_feasibility",
    "downgrade_conditions",
)
_EXECUTION_FRICTION_EVIDENCE_STATUSES = {
    "ASSUMPTION_ONLY",
    "PARTIALLY_OBSERVED",
    "VERIFIED_REPLAY_EVIDENCE",
}

# Higher is better for predictive metrics; lower is better for cost/quality
# penalties.  This is a research ordering, not a probability or target return.
OBJECTIVE_DIRECTIONS: dict[str, str] = {
    "rank_ic": "max",
    "ic_ir": "max",
    "ndcg_at_k": "max",
    "turnover": "min",
    "complexity": "min",
    "missingness": "min",
}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-compatible value."""

    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field}_required")
    return value.strip()


def _hash(value: Any, field: str) -> str:
    value = _required_text(value, field)
    if not _SHA256.fullmatch(value):
        raise ValueError(f"{field}_must_be_sha256")
    return value


def _string_list(value: Any, field: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field}_must_be_list")
    result = [_required_text(item, field) for item in value]
    if not allow_empty and not result:
        raise ValueError(f"{field}_must_not_be_empty")
    if len(set(result)) != len(result):
        raise ValueError(f"{field}_must_be_unique")
    return result


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field}_must_be_finite_number")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}_must_be_finite_number") from exc
    if not math.isfinite(result):
        raise ValueError(f"{field}_must_be_finite_number")
    return result


def _execution_friction(value: Any) -> dict[str, Any]:
    """Validate declared real-world trading-friction boundaries.

    These are evidence declarations, not a licence to treat a theoretical
    friction model as a verified live-trading result.  A record always remains
    ``FACTOR_RESEARCH_ONLY`` regardless of its declared evidence status.
    """
    if not isinstance(value, Mapping) or not value:
        raise ValueError("execution_friction_required")
    normalized = dict(value)
    missing = [field for field in _EXECUTION_FRICTION_REQUIRED_FIELDS if field not in normalized]
    if missing:
        raise ValueError(f"execution_friction_missing:{','.join(missing)}")
    status = _required_text(normalized["evidence_status"], "execution_friction.evidence_status")
    if status not in _EXECUTION_FRICTION_EVIDENCE_STATUSES:
        raise ValueError("execution_friction.evidence_status_invalid")
    normalized["evidence_status"] = status
    for field in ("capacity", "market_impact", "crowding", "execution_feasibility"):
        item = normalized[field]
        if not isinstance(item, Mapping) or not item:
            raise ValueError(f"execution_friction.{field}_required")
        normalized[field] = dict(item)
    normalized["downgrade_conditions"] = _string_list(
        normalized["downgrade_conditions"], "execution_friction.downgrade_conditions"
    )
    return normalized


@dataclass(frozen=True)
class FactorExperiment:
    """A validated, serializable, non-publishing factor experiment."""

    factor_id: str
    parent_ids: tuple[str, ...]
    formula_ast: Any
    feature_sources: tuple[str, ...]
    dataset_snapshot_hash: str
    point_in_time_rule: str
    cost_model: Mapping[str, Any]
    execution_friction: Mapping[str, Any]
    random_seed: int
    code_hash: str
    metrics: Mapping[str, float]
    semantic_slices: tuple[Mapping[str, Any], ...]
    out_of_sample_split: Mapping[str, Any]
    counterexamples: tuple[str, ...]
    created_at: str
    record_hash: str
    mode: str = MODE
    production_integration: bool = False
    recommendation_authority: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "mode": self.mode,
            "factor_id": self.factor_id,
            "parent_ids": list(self.parent_ids),
            "formula_ast": self.formula_ast,
            "feature_sources": list(self.feature_sources),
            "dataset_snapshot_hash": self.dataset_snapshot_hash,
            "point_in_time_rule": self.point_in_time_rule,
            "cost_model": dict(self.cost_model),
            "execution_friction": dict(self.execution_friction),
            "random_seed": self.random_seed,
            "code_hash": self.code_hash,
            "metrics": dict(self.metrics),
            "semantic_slices": [dict(item) for item in self.semantic_slices],
            "out_of_sample_split": dict(self.out_of_sample_split),
            "counterexamples": list(self.counterexamples),
            "created_at": self.created_at,
            "record_hash": self.record_hash,
            "production_integration": self.production_integration,
            "recommendation_authority": self.recommendation_authority,
        }


def build_factor_experiment(
    *,
    factor_id: str,
    parent_ids: Sequence[str] = (),
    formula_ast: Any,
    feature_sources: Sequence[str],
    dataset_snapshot_hash: str,
    point_in_time_rule: str,
    cost_model: Mapping[str, Any],
    execution_friction: Mapping[str, Any],
    random_seed: int,
    code_hash: str,
    metrics: Mapping[str, Any],
    semantic_slices: Sequence[Mapping[str, Any]] = (),
    out_of_sample_split: Mapping[str, Any],
    counterexamples: Sequence[str] = (),
    created_at: str,
) -> FactorExperiment:
    """Validate and build a factor experiment record.

    The caller must provide all evidence identifiers and timestamps.  No
    defaults are invented for the dataset, split, cost model, execution
    friction, or metrics.
    """

    factor_id = _required_text(factor_id, "factor_id")
    parents = tuple(_string_list(list(parent_ids), "parent_ids", allow_empty=True))
    if not isinstance(formula_ast, (str, Mapping, Sequence)) or isinstance(formula_ast, (bytes, bytearray)):
        raise ValueError("formula_ast_required")
    if isinstance(formula_ast, str) and not formula_ast.strip():
        raise ValueError("formula_ast_required")
    sources = tuple(_string_list(feature_sources, "feature_sources"))
    snapshot = _hash(dataset_snapshot_hash, "dataset_snapshot_hash")
    pit_rule = _required_text(point_in_time_rule, "point_in_time_rule")
    if not isinstance(cost_model, Mapping) or not cost_model:
        raise ValueError("cost_model_required")
    friction = _execution_friction(execution_friction)
    if not isinstance(random_seed, int) or isinstance(random_seed, bool):
        raise ValueError("random_seed_must_be_integer")
    source_code_hash = _hash(code_hash, "code_hash")
    if not isinstance(metrics, Mapping):
        raise ValueError("metrics_required")
    normalized_metrics: dict[str, float] = {}
    missing_metrics = [name for name in OBJECTIVE_DIRECTIONS if name not in metrics]
    if missing_metrics:
        raise ValueError(f"metrics_missing:{','.join(missing_metrics)}")
    for name in OBJECTIVE_DIRECTIONS:
        normalized_metrics[name] = _finite_number(metrics[name], f"metrics.{name}")
    slices: list[Mapping[str, Any]] = []
    if not isinstance(semantic_slices, (list, tuple)):
        raise ValueError("semantic_slices_must_be_list")
    for item in semantic_slices:
        if not isinstance(item, Mapping) or not item:
            raise ValueError("semantic_slice_must_be_mapping")
        slices.append(dict(item))
    if not isinstance(out_of_sample_split, Mapping) or not out_of_sample_split:
        raise ValueError("out_of_sample_split_required")
    split = dict(out_of_sample_split)
    required_split_keys = ("train", "validation", "test")
    if any(key not in split for key in required_split_keys):
        raise ValueError("out_of_sample_split_requires_train_validation_test")
    for key in required_split_keys:
        _required_text(split.get(key), f"out_of_sample_split.{key}")
    failures = tuple(_string_list(list(counterexamples), "counterexamples", allow_empty=True))
    timestamp = _required_text(created_at, "created_at")

    payload = {
        "contract_version": CONTRACT_VERSION,
        "mode": MODE,
        "factor_id": factor_id,
        "parent_ids": list(parents),
        "formula_ast": formula_ast,
        "feature_sources": list(sources),
        "dataset_snapshot_hash": snapshot,
        "point_in_time_rule": pit_rule,
        "cost_model": dict(cost_model),
        "execution_friction": friction,
        "random_seed": random_seed,
        "code_hash": source_code_hash,
        "metrics": normalized_metrics,
        "semantic_slices": slices,
        "out_of_sample_split": split,
        "counterexamples": list(failures),
        "created_at": timestamp,
        "production_integration": False,
        "recommendation_authority": False,
    }
    return FactorExperiment(
        factor_id=factor_id,
        parent_ids=parents,
        formula_ast=formula_ast,
        feature_sources=sources,
        dataset_snapshot_hash=snapshot,
        point_in_time_rule=pit_rule,
        cost_model=dict(cost_model),
        execution_friction=friction,
        random_seed=random_seed,
        code_hash=source_code_hash,
        metrics=normalized_metrics,
        semantic_slices=tuple(slices),
        out_of_sample_split=split,
        counterexamples=failures,
        created_at=timestamp,
        record_hash=digest(payload),
    )


def pareto_dominates(left: FactorExperiment | Mapping[str, Any], right: FactorExperiment | Mapping[str, Any]) -> bool:
    """Return whether ``left`` weakly dominates ``right`` on all objectives."""

    left_metrics = left.metrics if isinstance(left, FactorExperiment) else left.get("metrics", {})
    right_metrics = right.metrics if isinstance(right, FactorExperiment) else right.get("metrics", {})
    if not isinstance(left_metrics, Mapping) or not isinstance(right_metrics, Mapping):
        raise ValueError("both_experiments_require_metrics")
    values: list[tuple[float, float, str]] = []
    for name, direction in OBJECTIVE_DIRECTIONS.items():
        lval = _finite_number(left_metrics.get(name), f"left.metrics.{name}")
        rval = _finite_number(right_metrics.get(name), f"right.metrics.{name}")
        values.append((lval, rval, direction))
    no_worse = all(lval >= rval if direction == "max" else lval <= rval for lval, rval, direction in values)
    strictly_better = any(lval > rval if direction == "max" else lval < rval for lval, rval, direction in values)
    return no_worse and strictly_better


def pareto_frontier(records: Sequence[FactorExperiment]) -> list[FactorExperiment]:
    """Return a stable, input-order Pareto frontier for validated records."""

    frontier = []
    for candidate in records:
        if any(pareto_dominates(other, candidate) for other in records if other is not candidate):
            continue
        frontier.append(candidate)
    return frontier
