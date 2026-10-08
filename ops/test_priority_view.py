# Regression: the prioritization view ranks with receipts and excludes hard-blocked.
import pytest

from core.priority_view import POLICY_VERSION, WEIGHTS, rank, score


def _cand(task_id, **overrides):
    base = {
        "id": task_id,
        "value": 0.5,
        "urgency": 0.5,
        "uncertainty": 0.5,
        "learning": 0.5,
        "consequence": 0.5,
        "age": 0.5,
        "cost": 0.5,
    }
    base.update(overrides)
    return base


def test_highest_value_wins_and_receipt_names_rejects():
    receipt = rank([
        _cand("RQ-B", value=0.2),
        _cand("RQ-A", value=0.9, learning=0.9, cost=0.2),
        _cand("RQ-C", value=0.5),
    ])
    assert receipt["selected"] == "RQ-A"
    assert receipt["policy_version"] == POLICY_VERSION
    assert receipt["why_factors"]["value"] == 0.9
    rejected = {r["id"] for r in receipt["rejected_alternatives"]}
    assert rejected == {"RQ-B", "RQ-C"}
    assert receipt["ranking"][0]["score"] > receipt["ranking"][-1]["score"]


def test_hard_excluded_never_rank():
    receipt = rank([
        _cand("RQ-X", value=1.0, terminal_non_convergent=True),
        _cand("RQ-Y", value=0.1),
    ])
    assert receipt["selected"] == "RQ-Y"
    assert receipt["excluded"] == [{"id": "RQ-X", "blocked_by": ["terminal_non_convergent"]}]


def test_empty_field_scores_zero_without_rewarding_silence():
    receipt = rank([_cand("RQ-Z"), _cand("RQ-W", value=0.9)])
    assert receipt["selected"] == "RQ-W"
    assert receipt["weights"] == WEIGHTS


def test_score_is_bounded_and_missing_means_zero():
    assert score({"id": "x"}) == 0.0
    assert 0.0 <= score(_cand("y", value=2.0, cost=99.0)) <= 1.0
