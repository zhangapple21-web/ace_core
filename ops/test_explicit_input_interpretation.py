from core.explicit_input_interpretation import CONTRACT_VERSION, interpret_explicit_input


def test_literal_and_metaphor_are_separate_and_side_effect_free():
    packet = interpret_explicit_input("自由区是ACE进化的催化剂，人可以上天入地还会魔法")
    assert packet["contract_version"] == CONTRACT_VERSION
    assert packet["literal_text"].startswith("自由区是")
    assert packet["literal_status"] == "FACT"
    assert packet["metaphor_or_analogy"][0]["status"] == "HYPOTHESIS"
    assert packet["execution_boundary"] == "DISCUSSION_OR_FREE_ZONE_RESEARCH_ONLY"
    assert packet["decision_candidate"]["action"] == "DISCUSS_OR_SANDBOX_RESEARCH"
    assert packet["memory_route"][-1] == "FREE_ZONE_RESEARCH_ONLY"
    assert packet["side_effects"] == {"persistent_write": False, "task_created": False, "model_called": False, "external_action": False}


def test_vague_execution_request_requires_confirmation_without_dispatch():
    packet = interpret_explicit_input("你自己看着办，尽可能修复好")
    assert packet["confirmation_required"] is True
    assert packet["execution_boundary"] == "CONFIRMATION_REQUIRED"
    assert packet["ambiguity_flags"] == ["VAGUE_REFERENCE_OR_HEDGE"]
    assert packet["side_effects"]["task_created"] is False
    assert packet["decision_candidate"]["action"] == "ASK_FOR_CLARIFICATION_OR_CONFIRMATION"


def test_common_chinese_words_do_not_create_false_question_or_metaphor_flags():
    packet = interpret_explicit_input("这个好像都没什么变化")
    assert packet["ambiguity_flags"] == ["VAGUE_REFERENCE_OR_HEDGE"]
    assert packet["metaphor_or_analogy"] == []


def test_diagnostic_and_learning_candidates_are_hypotheses_not_facts():
    packet = interpret_explicit_input("自动化任务失败，看看问题出在哪里并持续学习")
    kinds = {item["kind"] for item in packet["candidate_intents"]}
    assert {"DIAGNOSIS_OR_ROOT_CAUSE", "LEARNING_OR_SYSTEM_DESIGN"} <= kinds
    assert all(item["status"] in {"INFERENCE", "HYPOTHESIS"} for item in packet["candidate_intents"])
    assert packet["decision_candidate"]["action"] == "DIAGNOSE_BEFORE_CHANGE"
    assert packet["memory_route"][-1] == "VERIFIED_EXPERIENCE"


def test_shot_review_routes_to_director_with_drama_memory():
    packet = interpret_explicit_input("S04A 力度不够，重做")
    kinds = {item["kind"] for item in packet["candidate_intents"]}
    assert "SHOT_OR_ACTION_REVIEW" in kinds
    assert packet["decision_candidate"]["action"] == "ROUTE_TO_DIRECTOR_CRITIC"
    assert packet["execution_boundary"] == "DIRECTOR_REVIEW_REQUIRED"
    assert "SHOT_CONTRACT" in packet["memory_route"]
    assert "CHARACTER_ANCHORS" in packet["memory_route"]


def test_emotional_review_uses_same_director_boundary():
    packet = interpret_explicit_input("检查这一镜的绝望情绪是否到位")
    assert any(item["kind"] == "EMOTIONAL_FUNCTION_CHECK" for item in packet["candidate_intents"])
    assert packet["decision_candidate"]["action"] == "ROUTE_TO_DIRECTOR_CRITIC"
    assert packet["execution_boundary"] == "DIRECTOR_REVIEW_REQUIRED"


def test_purpose_and_continuity_are_preserved_for_novel_question():
    packet = interpret_explicit_input("之前R1就做过，为什么要让系统吃小说，真正的目的是什么？")
    layers = packet["semantic_layers"]
    assert layers["surface_intent"]["value"] == "提供或讨论叙事素材"
    assert layers["purpose_signal"] == {"status": "FACT", "detected": True}
    assert layers["historical_continuity"]["status"] == "INFERENCE"
    assert "R1" in layers["historical_continuity"]["signals"]
    assert layers["model_must_resolve_before_execution"] is True
    assert layers["semantic_loss_risk"] == "HIGH"


