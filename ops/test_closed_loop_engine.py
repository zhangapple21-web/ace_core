from core.closed_loop_engine import ClosedLoopEngine


def review(**overrides):
    value = {
        "cost": "一次可回滚的小范围实验",
        "counterfactual": "若不修复，下一轮会重复同一失败",
        "recurrence_risk": "中",
        "reusable_lesson": "先记录基线再比较结果",
        "retain": True,
    }
    value.update(overrides)
    return value


def test_closed_loop_promotes_only_after_measurable_gain_and_review(tmp_path):
    engine = ClosedLoopEngine(tmp_path / "ace")
    receipt = engine.run_cycle(
        {"source": "test", "failure": "旧方案失败"},
        "降低重复失败率",
        {"failure_rate": 0.18},
        {"failure_rate": 0.09},
        review(),
        directions={"failure_rate": "lower"},
    )
    assert receipt["decision"] == "PROMOTED_TO_CAPABILITY_GROWTH"
    assert receipt["next_observation"]["trigger"] == "PROMOTED_TO_CAPABILITY_GROWTH"
    assert len((tmp_path / "ace" / "09_KNOWLEDGE" / "closed_loop" / "capability_growth.jsonl").read_text(encoding="utf-8").splitlines()) == 1


def test_missing_painful_review_cannot_promote(tmp_path):
    engine = ClosedLoopEngine(tmp_path / "ace")
    receipt = engine.run_cycle({"source": "test"}, "修复路由", {"success": 1}, {"success": 2}, {"cost": "unknown"})
    assert receipt["decision"] == "REJECTED_MISSING_PAINFUL_REVIEW"


def test_regression_requires_rollback(tmp_path):
    engine = ClosedLoopEngine(tmp_path / "ace")
    receipt = engine.run_cycle(
        {"source": "test"},
        "改进稳定性",
        {"success": 0.95, "latency": 1.0},
        {"success": 0.80, "latency": 0.8},
        review(),
        directions={"success": "higher", "latency": "lower"},
    )
    assert receipt["decision"] == "ROLLBACK_REQUIRED"


def test_no_gain_is_recorded_as_failure_not_capability(tmp_path):
    engine = ClosedLoopEngine(tmp_path / "ace")
    receipt = engine.run_cycle({"source": "test"}, "无效优化", {"quality": 1}, {"quality": 1}, review())
    assert receipt["decision"] == "REJECTED_NO_MEASURABLE_GAIN"
    assert not (tmp_path / "ace" / "09_KNOWLEDGE" / "closed_loop" / "capability_growth.jsonl").exists()


def test_decomposition_is_bounded_and_traceable(tmp_path):
    engine = ClosedLoopEngine(tmp_path / "ace")
    nodes = engine.decompose({"source": "test"}, "测试拆解")
    assert [node.node_id for node in nodes] == ["N01", "N02", "N03"]
    assert nodes[1].depends_on == ["N01"]


def test_cyclic_decomposition_is_rejected(tmp_path):
    engine = ClosedLoopEngine(tmp_path / "ace")
    try:
        engine.decompose(
            {"source": "test"},
            "循环依赖",
            [
                {"node_id": "A", "objective": "a", "acceptance": "a", "depends_on": ["B"]},
                {"node_id": "B", "objective": "b", "acceptance": "b", "depends_on": ["A"]},
            ],
        )
    except ValueError as error:
        assert str(error).startswith("cyclic_dependency:")
    else:
        raise AssertionError("cyclic decomposition must be rejected")


def test_missing_retain_flag_cannot_promote(tmp_path):
    engine = ClosedLoopEngine(tmp_path / "ace")
    incomplete = review()
    incomplete.pop("retain")
    receipt = engine.run_cycle({"source": "test"}, "没有保留结论", {"quality": 1}, {"quality": 2}, incomplete)
    assert receipt["decision"] == "REJECTED_MISSING_PAINFUL_REVIEW"
