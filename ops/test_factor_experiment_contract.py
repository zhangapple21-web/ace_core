import pytest

from core.factor_experiment_contract import (
    build_factor_experiment,
    pareto_dominates,
    pareto_frontier,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def _record(**overrides):
    payload = {
        "factor_id": "factor-001",
        "parent_ids": [],
        "formula_ast": {"op": "delta", "args": ["close", 5]},
        "feature_sources": ["research://ohlcv#snapshot=abc"],
        "dataset_snapshot_hash": HASH_A,
        "point_in_time_rule": "features_at_t_only; forward_return_after_t",
        "cost_model": {"version": "v1", "commission_bps": 3, "slippage_bps": 5},
        "execution_friction": {
            "evidence_status": "ASSUMPTION_ONLY",
            "capacity": {"basis": "ADV participation cap", "max_participation_rate": 0.05},
            "market_impact": {"model": "square_root", "calibration": "not yet observed"},
            "crowding": {"proxy": "ownership concentration", "threshold": "research-only"},
            "execution_feasibility": {"market": "A-share", "rule": "T+1 and limit rules considered"},
            "downgrade_conditions": ["no point-in-time execution evidence", "liquidity regime shift"],
        },
        "random_seed": 7,
        "code_hash": HASH_B,
        "metrics": {
            "rank_ic": 0.05,
            "ic_ir": 0.4,
            "ndcg_at_k": 0.2,
            "turnover": 0.5,
            "complexity": 3,
            "missingness": 0.01,
        },
        "semantic_slices": [{"market_state": "trend", "rows": 120}],
        "out_of_sample_split": {"train": "2020-2023", "validation": "2024", "test": "2025"},
        "counterexamples": ["fails in thin liquidity"],
        "created_at": "2026-08-31T12:00:00+08:00",
    }
    payload.update(overrides)
    return build_factor_experiment(**payload)


def test_build_factor_experiment_is_hash_bound_and_non_publishing():
    record = _record()
    data = record.to_dict()
    assert len(record.record_hash) == 64
    assert data["mode"] == "FACTOR_RESEARCH_ONLY"
    assert data["production_integration"] is False
    assert data["recommendation_authority"] is False
    assert data["dataset_snapshot_hash"] == HASH_A
    assert data["metrics"]["turnover"] == 0.5
    assert data["execution_friction"]["evidence_status"] == "ASSUMPTION_ONLY"
    assert data["execution_friction"]["capacity"]["max_participation_rate"] == 0.05


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("dataset_snapshot_hash", "not-a-hash", "dataset_snapshot_hash_must_be_sha256"),
        ("code_hash", "not-a-hash", "code_hash_must_be_sha256"),
        ("random_seed", True, "random_seed_must_be_integer"),
        ("metrics", {"rank_ic": 0.1}, "metrics_missing"),
        ("out_of_sample_split", {"train": "x"}, "out_of_sample_split_requires_train_validation_test"),
        ("execution_friction", {}, "execution_friction_required"),
        ("execution_friction", {"evidence_status": "ASSUMPTION_ONLY"}, "execution_friction_missing"),
    ],
)
def test_contract_rejects_unreplayable_metadata(field, value, error):
    with pytest.raises(ValueError, match=error):
        _record(**{field: value})


def test_pareto_comparison_uses_both_predictive_and_cost_objectives():
    better = _record(factor_id="better", metrics={"rank_ic": 0.06, "ic_ir": 0.45, "ndcg_at_k": 0.21, "turnover": 0.4, "complexity": 3, "missingness": 0.01})
    worse = _record(factor_id="worse")
    assert pareto_dominates(better, worse)
    assert not pareto_dominates(worse, better)


def test_pareto_frontier_retains_tradeoff_and_drops_dominated_record():
    baseline = _record(factor_id="baseline")
    high_ic = _record(factor_id="high-ic", metrics={"rank_ic": 0.08, "ic_ir": 0.5, "ndcg_at_k": 0.25, "turnover": 0.7, "complexity": 5, "missingness": 0.02})
    dominated = _record(factor_id="dominated", metrics={"rank_ic": 0.04, "ic_ir": 0.3, "ndcg_at_k": 0.15, "turnover": 0.8, "complexity": 6, "missingness": 0.03})
    frontier = pareto_frontier([baseline, high_ic, dominated])
    assert [item.factor_id for item in frontier] == ["baseline", "high-ic"]


def test_execution_friction_is_hash_bound_and_never_changes_research_only_mode():
    baseline = _record()
    changed = _record(execution_friction={
        "evidence_status": "ASSUMPTION_ONLY",
        "capacity": {"basis": "ADV participation cap", "max_participation_rate": 0.01},
        "market_impact": {"model": "square_root", "calibration": "not yet observed"},
        "crowding": {"proxy": "ownership concentration", "threshold": "research-only"},
        "execution_feasibility": {"market": "A-share", "rule": "T+1 and limit rules considered"},
        "downgrade_conditions": ["no point-in-time execution evidence", "liquidity regime shift"],
    })

    assert baseline.record_hash != changed.record_hash
    assert changed.mode == "FACTOR_RESEARCH_ONLY"
    assert changed.production_integration is False
    assert changed.recommendation_authority is False


