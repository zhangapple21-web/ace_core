import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.persona_matrix_router import (
    PERSONA_DEFS, route, arbitrate, deshell, memory_envelope,
    worker_capabilities, route_to_capability, semantic_route,
)
from core.worker_router import WorkerRouter, WorkerCapability
from core.observation_to_task import persona_hint_for


def test_five_personas_cover_cognitive_loop():
    assert set(PERSONA_DEFS.keys()) == {"engineer", "scholar", "assistant", "librarian", "underworld_judge"}
    for pid in ("engineer", "scholar", "assistant", "librarian", "underworld_judge"):
        assert PERSONA_DEFS[pid]["role_id"] == pid
        assert PERSONA_DEFS[pid]["capability"]


def test_engineer_routing_single_match():
    r = route("工程师，帮我看下这个错误日志现在是怎么回事。")
    assert r["selected"] == "engineer"
    assert "engineer" in r["matched"]
    assert r["needs_arbitration"] is False


def test_scholar_routing():
    r = route("学霸，把刚才这份讨论总结成备忘录。")
    assert r["selected"] == "scholar"


def test_librarian_routing():
    r = route("馆长，我之前丢给你的芯片蓝图，在哪一层？")
    assert r["selected"] == "librarian"


def test_multi_match_goes_to_arbitration():
    r = route("帮我整理一下代码")
    # 同时命中工程师(代码)与学霸(整理) -> 仲裁
    assert r["needs_arbitration"] is True
    assert r["selected"] == "underworld_judge"
    a = arbitrate(r["matched"], context="帮我整理一下代码")
    assert a["selected"] in ("engineer", "scholar")
    assert a["judge"] == "underworld_judge"


def test_conflict_triggers_judge():
    r = route("冥界，刚才工程师和助理的说法不一样，你帮我定一个方案。")
    assert r["conflict_detected"] is True
    assert r["selected"] == "underworld_judge"


def test_deshell_right():
    assert deshell("按原话来，不要包装", "")["deshelled"] is True
    assert deshell("正常回答", "")["deshelled"] is False
    assert deshell("xxx", "去壳")["output_mode"] == "raw"


def test_memory_envelope_schema():
    e = memory_envelope(source="RQ-20261014-019", fact="路由5/5通过", inference="可继承", unknown="语义路由未做",
                        scope="task-local", continuity_impact="路由可复用", authority="observation",
                        reusable=True, counterevidence="无", retention_days=90)
    for k in ("source", "at", "fact", "inference", "unknown", "scope", "continuity_impact",
              "authority", "reusable", "counterevidence", "retention_days", "schema"):
        assert k in e
    assert e["schema"] == "ace.memory_envelope.v1"


def test_worker_router_integration_no_model_call():
    caps = worker_capabilities()
    assert len(caps) == 5
    workers = [WorkerCapability(worker_id=c["worker_id"], runtime=c["runtime"],
                                capabilities=frozenset(c["capabilities"])) for c in caps]
    router = WorkerRouter(workers)
    # 五种能力都可被现有路由选中, 不新增调度器
    assert router.choose("code_exec").worker_id == "persona-engineer"
    assert router.choose("knowledge_distill").worker_id == "persona-scholar"
    assert router.choose("customer_dialog").worker_id == "persona-assistant"
    assert router.choose("retrieval").worker_id == "persona-librarian"
    assert router.choose("arbitration").worker_id == "persona-judge"
    # 端到端: 文本 -> capability -> worker
    assert router.choose(route_to_capability("报错日志")).worker_id == "persona-engineer"


def test_no_ten_agents():
    # 约束: 不复活十人格为十个独立Agent, 本模块只允许5角色
    assert len(PERSONA_DEFS) == 5


def test_semantic_resolves整理代码_without_error_to_scholar():
    # A09局限性核心用例：无错误信号的“整理代码”应偏学霸，而非硬仲裁
    s = semantic_route("帮我整理一下代码")
    assert s["selected"] == "scholar"
    assert s["method"] == "semantic"


def test_semantic_error_with整理_prefers_engineer():
    s = semantic_route("这段代码报错了，帮我整理一下错误日志并排查")
    assert s["selected"] == "engineer"


def test_semantic_ambiguous_goes_to_judge():
    # 分数接近或冲突时交冥界，不硬选
    s = semantic_route("工程师和助理说法不一样，定一个方案")
    assert s["selected"] == "underworld_judge"


def test_persona_hint_prefers_semantic_in_production():
    h = persona_hint_for("帮我整理一下代码", "整理成备忘录")
    assert h["persona"] == "scholar"
    assert h["capability"] == "knowledge_distill"
    h2 = persona_hint_for("处理系统异常错误", "近24小时出现5个错误")
    assert h2["persona"] == "engineer"


def test_state_machine_order_and_budget_fallback():
    from core.persona_matrix_router import MiniStateMachine
    m = MiniStateMachine()
    assert m.state == "A"
    assert m.enter("U", reason="explore")["ok"] is True
    assert m.allow("explore") is True
    assert m.allow("execute") is False
    bad = m.enter("TURIYA")
    assert bad["ok"] is False  # 不许跳跃
    assert m.enter("M", reason="smelt")["ok"] is True
    assert m.enter("TURIYA", reason="commit")["ok"] is True
    assert m.allow("commit") is True
    over = m.consume(999999)
    assert over["ok"] is False and m.state == "A"  # 预算超回退，不堆积


if __name__ == "__main__":
    test_semantic_resolves整理代码_without_error_to_scholar()
    test_semantic_error_with整理_prefers_engineer()
    test_semantic_ambiguous_goes_to_judge()
    test_persona_hint_prefers_semantic_in_production()
    test_five_personas_cover_cognitive_loop()
    test_engineer_routing_single_match()
    test_scholar_routing()
    test_librarian_routing()
    test_multi_match_goes_to_arbitration()
    test_conflict_triggers_judge()
    test_deshell_right()
    test_memory_envelope_schema()
    test_worker_router_integration_no_model_call()
    test_no_ten_agents()
    print("persona_matrix_router checks passed")
