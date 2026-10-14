import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.task import TaskPool
from core.ruin_smelter import classify, substantive_change, fuse, memory_envelope_compat, should_retrieve


class Fake:
    def __init__(self, **kw):
        self.rework_count = kw.get("rework_count", 0)
        self.retry_count = kw.get("retry_count", 0)
        self.unchanged_review_count = kw.get("unchanged_review_count", 0)
        self.consecutive_rework_claims = kw.get("consecutive_rework_claims", 0)
        self.failure_reason = kw.get("failure_reason", "")
        self.blocked_reason = kw.get("blocked_reason", "")
        self.hypothesis = kw.get("hypothesis", "h")
        self.evidence = kw.get("evidence", [])
        self.outputs = kw.get("outputs", {})


def test_classify_repeaters():
    assert classify(Fake(rework_count=14, consecutive_rework_claims=15))["class"] == "non_convergent"
    assert classify(Fake(retry_count=3, failure_reason="timeout env"))["class"] == "exec_failure"
    assert classify(Fake(rework_count=1, outputs={"last_validator_result": {"objections": ["缺证据"]}}))["class"] == "evidence_insufficient"


def test_no_reenter_without_substantive_change():
    t = Fake(rework_count=14, consecutive_rework_claims=15, evidence=[{"content": "same"}])
    d = fuse(t)  # 无新变化
    assert d["action"] == "circuit_break"
    assert d["block_type"] == "manual_gate_blocked"
    assert d["need_judge"] is True
    # 有实质变化才允许reopen
    d2 = fuse(t, new_evidence_hash="DIFFERENT_HASH_1234567890", new_method="new_verify")
    assert d2["action"] == "reopen_with_new_proof"


def test_no_counter_reset_or_id_change():
    # 熔断不重置计数、不换ID：纯函数不改task字段
    t = Fake(rework_count=14, retry_count=0)
    before = (t.rework_count, t.retry_count)
    fuse(t)
    assert (t.rework_count, t.retry_count) == before


def test_exec_subclasses():
    assert classify(Fake(retry_count=1, failure_reason="Traceback null"))["sub"] == "code"
    assert classify(Fake(retry_count=1, failure_reason="429 quota"))["sub"] == "model"
    assert classify(Fake(retry_count=1, failure_reason="upstream api fail"))["sub"] == "external"


def test_mlp_compat_and_retention():
    old = {"summary": "旧记忆", "tags": ["lesson", "复盘"], "created_at": "2020-01-01T00:00:00+00:00", "retention_days": 7}
    c = memory_envelope_compat(old)
    assert c["unknown"] == "UNKNOWN"  # 不擅自标成事实
    assert c["audit_preserve"] is True  # 治理证据保留
    # 过期临时错误不再检索，审计仍可查
    assert should_retrieve({"created_at": "2020-01-01T00:00:00+00:00", "retention_days": 7, "audit_preserve": False}) is False
    assert should_retrieve(c) is True


def test_real_007_shape():
    import sys
    sys.path.insert(0, "C:/tmp/ace_core")
    from core.task import TaskPool
    pool = TaskPool("C:/tmp/ace_core/task_pool")
    t = pool.load_task("RQ-20260915-007")
    assert t.rework_count == 14
    assert classify(t)["class"] == "non_convergent"
    assert fuse(t)["action"] == "circuit_break"


if __name__ == "__main__":
    test_classify_repeaters()
    test_no_reenter_without_substantive_change()
    test_no_counter_reset_or_id_change()
    test_exec_subclasses()
    test_mlp_compat_and_retention()
    test_real_007_shape()
    print("ruin_smelter checks passed")
