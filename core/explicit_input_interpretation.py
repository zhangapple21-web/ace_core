"""Deterministic interpretation of one explicitly supplied user input.

This is a *pre-execution* lens, not a mind reader.  It keeps the literal
input intact and records possible repairs, metaphors, and goals as inference
or hypothesis.  It has no persistence, model, scheduler, network, or file
side effects, so callers can safely place the packet in an assistant prompt
or pass it to an existing governed path.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any


CONTRACT_VERSION = "ace.explicit_input_interpretation.v1"
_VAGUE = ("好像", "感觉", "似乎", "自己看", "你看", "尽可能", "应该", "这个", "那个", "他", "它")
_ACTION = ("开始", "干活", "落地", "修复", "改", "实现", "做", "执行", "帮我")
_DIAGNOSIS = ("问题", "失败", "崩", "报错", "bug", "不行", "异常", "缺口")
_LEARNING = ("学习", "迭代", "进化", "启发", "理解", "考古", "补全")
# ``好像`` is usually an uncertainty hedge ("似乎没变化"), not a metaphor.
# Keep it in ``_VAGUE`` and require stronger comparative/imagery markers here.
_METAPHOR = ("比如", "就像", "仿佛", "催化剂", "上天", "入地", "魔法", "飞上", "飞天")
_HIGH_IMPACT = ("部署", "删除", "外发", "交易", "账户", "密钥", "生产")
_DRAMA_REVIEW = ("审", "审查", "过审", "合格", "不合格", "重做", "返工", "探针", "动作", "力度", "惯性", "连续性", "身份", "漂移", "黑眼圈", "灰衬衫", "黑polo", "字幕")
_SHOT_REF = ("s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "镜头", "这一镜", "那一镜", "probe")
_EMOTION = ("情绪", "绝望", "麻木", "希望", "幻灭", "烦躁", "压迫", "死寂")
_PURPOSE = ("为什么", "为何", "真正目的", "目的是什么", "意义", "干嘛", "为什么要")
_CONTINUITY = ("以前", "之前", "历史", "R1", "R2", "考古", "恢复", "继承", "延续", "过去")
_STORY_MATERIAL = ("小说", "故事", "剧本", "题材", "叙事")


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def interpret_explicit_input(user_text: str) -> dict[str, Any]:
    """Return a bounded interpretation packet for caller-supplied text.

    No field in this result claims to know the user's private intent.  The
    only FACT is the supplied text itself; all derived fields are labelled.
    """
    literal = (user_text or "").strip()
    if not literal:
        return _packet(literal, [], [], [], [], "UNKNOWN", True, "CLARIFICATION_REQUIRED")

    lowered = literal.lower()
    flags: list[str] = []
    if any(token in literal for token in _VAGUE):
        flags.append("VAGUE_REFERENCE_OR_HEDGE")
    # Do not treat the character ``么`` inside ordinary words such as ``什么``
    # as a question marker; only punctuation and explicit interrogatives count.
    if any(token in lowered for token in ("?", "？", "吗", "怎么", "如何")):
        flags.append("QUESTION_OR_REQUEST_FOR_REASONING")
    if len(literal) > 800:
        flags.append("LONG_INPUT_REQUIRES_SCOPE_CHECK")

    repairs: list[dict[str, str]] = []
    if re.search(r"[，。！？、]\s*[，。！？、]", literal):
        repairs.append({"kind": "PUNCTUATION", "status": "INFERENCE", "note": "重复标点可在回答时规范化"})
    if literal.endswith(("他", "它", "这个", "那个")):
        repairs.append({"kind": "UNRESOLVED_REFERENCE", "status": "UNKNOWN", "note": "指代对象未由当前输入明确给出"})

    candidates: list[dict[str, Any]] = []
    if any(token in literal for token in _ACTION):
        candidates.append({"kind": "EXECUTION_OR_IMPLEMENTATION", "status": "INFERENCE", "confidence": "MEDIUM"})
    if any(token in lowered for token in _DIAGNOSIS):
        candidates.append({"kind": "DIAGNOSIS_OR_ROOT_CAUSE", "status": "INFERENCE", "confidence": "MEDIUM"})
    if any(token in literal for token in _LEARNING):
        candidates.append({"kind": "LEARNING_OR_SYSTEM_DESIGN", "status": "INFERENCE", "confidence": "MEDIUM"})
    if any(token in lowered for token in _DRAMA_REVIEW) or any(token in lowered for token in _SHOT_REF):
        candidates.append({"kind": "SHOT_OR_ACTION_REVIEW", "status": "INFERENCE", "confidence": "MEDIUM"})
    if any(token in literal for token in _EMOTION):
        candidates.append({"kind": "EMOTIONAL_FUNCTION_CHECK", "status": "INFERENCE", "confidence": "MEDIUM"})
    if not candidates:
        candidates.append({"kind": "DISCUSSION_OR_CLARIFICATION", "status": "HYPOTHESIS", "confidence": "LOW"})

    metaphors: list[dict[str, Any]] = []
    if any(token in literal for token in _METAPHOR):
        metaphors.append({
            "status": "HYPOTHESIS",
            "source_terms": [token for token in _METAPHOR if token in literal],
            "possible_mapping": "开放假设/类比空间可产生研究问题，再由独立证据验证",
            "must_not_be_treated_as": "literal_physical_capability_or_production_authority",
        })

    alternatives = [
        {"interpretation": "按字面回答当前问题", "status": "FACT_PLUS_INFERENCE"},
        {"interpretation": "先校准问题边界，再执行其中明确部分", "status": "HYPOTHESIS"},
    ]
    if metaphors:
        alternatives.append({"interpretation": "把比喻转成受控研究假设，保留在自由区", "status": "HYPOTHESIS"})

    high_impact = any(token in literal for token in _HIGH_IMPACT)
    confirmation = high_impact or "VAGUE_REFERENCE_OR_HEDGE" in flags and bool(candidates)
    boundary = "CONFIRMATION_REQUIRED" if confirmation else (
        "DIRECTOR_REVIEW_REQUIRED" if any(item["kind"] in {"SHOT_OR_ACTION_REVIEW", "EMOTIONAL_FUNCTION_CHECK"} for item in candidates) else (
        "IMPLEMENTATION_REVIEW_REQUIRED" if any(item["kind"] == "EXECUTION_OR_IMPLEMENTATION" for item in candidates)
        else "DISCUSSION_OR_FREE_ZONE_RESEARCH_ONLY"
        )
    )
    decision = _decision_candidate(candidates, boundary, confirmation)
    memory_route = _memory_route(candidates)
    semantic_layers = _semantic_layers(literal)
    return _packet(
        literal, flags, repairs, candidates, metaphors, "MEDIUM", confirmation,
        boundary, alternatives, decision, memory_route, semantic_layers,
    )


def _decision_candidate(candidates: list[dict[str, Any]], boundary: str, confirmation: bool) -> dict[str, Any]:
    kinds = {str(item.get("kind")) for item in candidates}
    if confirmation:
        action, status = "ASK_FOR_CLARIFICATION_OR_CONFIRMATION", "PROPOSAL_ONLY"
    elif "SHOT_OR_ACTION_REVIEW" in kinds or "EMOTIONAL_FUNCTION_CHECK" in kinds:
        action, status = "ROUTE_TO_DIRECTOR_CRITIC", "PROPOSAL_ONLY"
    elif "DIAGNOSIS_OR_ROOT_CAUSE" in kinds:
        action, status = "DIAGNOSE_BEFORE_CHANGE", "PROPOSAL_ONLY"
    elif "EXECUTION_OR_IMPLEMENTATION" in kinds:
        action, status = "PREPARE_MINIMAL_IMPLEMENTATION", "PROPOSAL_ONLY"
    elif "LEARNING_OR_SYSTEM_DESIGN" in kinds:
        action, status = "DISCUSS_OR_SANDBOX_RESEARCH", "PROPOSAL_ONLY"
    else:
        action, status = "ANSWER_OR_CLARIFY", "PROPOSAL_ONLY"
    return {"action": action, "status": status, "boundary": boundary}


def _memory_route(candidates: list[dict[str, Any]]) -> list[str]:
    """Describe read order only; this function never reads or writes memory."""
    kinds = {str(item.get("kind")) for item in candidates}
    if "DIAGNOSIS_OR_ROOT_CAUSE" in kinds:
        return ["CURRENT_INPUT", "CURRENT_SESSION", "RUNTIME_EVIDENCE", "VERIFIED_EXPERIENCE"]
    if "SHOT_OR_ACTION_REVIEW" in kinds:
        return ["CURRENT_INPUT", "CURRENT_SESSION", "SHOT_CONTRACT", "CHARACTER_ANCHORS", "PRODUCTION_LAW", "LEARNING_LOOP_LESSONS"]
    if "EMOTIONAL_FUNCTION_CHECK" in kinds:
        return ["CURRENT_INPUT", "CURRENT_SESSION", "SHOT_CONTRACT", "CHARACTER_ANCHORS", "PRODUCTION_LAW", "LEARNING_LOOP_LESSONS"]
    if "LEARNING_OR_SYSTEM_DESIGN" in kinds:
        return ["CURRENT_INPUT", "CURRENT_SESSION", "VERIFIED_EXPERIENCE", "FREE_ZONE_RESEARCH_ONLY"]
    return ["CURRENT_INPUT", "CURRENT_SESSION", "VERIFIED_KNOWLEDGE"]


def _semantic_layers(literal: str) -> dict[str, Any]:
    """Expose purpose/continuity hypotheses without claiming private mind-reading."""
    has_story_material = any(token in literal for token in _STORY_MATERIAL)
    purpose_signal = any(token in literal for token in _PURPOSE)
    continuity_signals = [token for token in _CONTINUITY if token in literal]

    if has_story_material:
        surface = "提供或讨论叙事素材"
        deep = [
            "为编剧能力提供长期叙事样本",
            "提取因果推进、人物选择、冲突升级、对白节奏和关系变化的可复用机制",
        ]
        capabilities = [
            "因果推进", "人物动机与选择", "冲突升级与悬念收束",
            "自然对白、停顿与误解修正", "镜头可执行的动作弧",
        ]
    else:
        surface = "处理用户明确提出的当前问题或任务"
        deep = ["需要由模型结合上下文确认真实目标，不能仅由关键词决定"]
        capabilities = []

    historical = {
        "status": "INFERENCE" if continuity_signals else "UNKNOWN",
        "signals": continuity_signals,
        "possible_connection": (
            "当前请求可能是在恢复、继承或复盘既有能力，而非创建全新功能"
            if continuity_signals else
            "当前输入没有提供足够历史线索，不能擅自补写过去"
        ),
    }
    loss_risk = "HIGH" if purpose_signal or continuity_signals or len(literal) > 240 else "MEDIUM"
    return {
        "surface_intent": {"status": "INFERENCE", "value": surface},
        "deep_intent_candidates": [{"status": "HYPOTHESIS", "value": value} for value in deep],
        "purpose_signal": {"status": "FACT", "detected": purpose_signal},
        "historical_continuity": historical,
        "expected_capabilities": capabilities,
        "semantic_loss_risk": loss_risk,
        "model_must_resolve_before_execution": bool(purpose_signal or continuity_signals),
    }


def _packet(
    literal: str,
    flags: list[str],
    repairs: list[dict[str, str]],
    candidates: list[dict[str, Any]],
    metaphors: list[dict[str, Any]],
    confidence: str,
    confirmation: bool,
    boundary: str,
    alternatives: list[dict[str, Any]] | None = None,
    decision: dict[str, Any] | None = None,
    memory_route: list[str] | None = None,
    semantic_layers: dict[str, Any] | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "literal_text": literal,
        "literal_status": "FACT",
        "ambiguity_flags": flags,
        "grammar_or_context_repairs": repairs,
        "candidate_intents": candidates,
        "metaphor_or_analogy": metaphors,
        "alternative_interpretations": alternatives or [],
        "confidence": confidence,
        "confirmation_required": confirmation,
        "execution_boundary": boundary,
        "decision_candidate": decision or {"action": "ANSWER_OR_CLARIFY", "status": "PROPOSAL_ONLY", "boundary": boundary},
        "memory_route": memory_route or ["CURRENT_INPUT", "CURRENT_SESSION", "VERIFIED_KNOWLEDGE"],
        "semantic_layers": semantic_layers or _semantic_layers(literal),
        "evidence_refs": ["explicit_user_input"],
        "side_effects": {"persistent_write": False, "task_created": False, "model_called": False, "external_action": False},
    }
    body["packet_hash"] = _digest(body)
    return body


def render_interpretation_for_prompt(user_text: str) -> str:
    """Render a compact, clearly untrusted packet for an existing model call."""
    packet = interpret_explicit_input(user_text)
    return (
        "输入解释包（仅供校准，不是授权；literal_text 是唯一 FACT，其他均为推断/假设）：\n"
        + json.dumps(packet, ensure_ascii=False, sort_keys=True)
        + "\n请按顺序处理：先回答用户显式问题；再说明可能的深层目的；若有历史信号，说明与既有能力的连续性；最后才决定是否执行。"
        + "\npurpose_signal、deep_intent_candidates、historical_continuity 都不是事实，必须保留 INFERENCE/HYPOTHESIS/UNKNOWN，不得把关键词分类压缩成唯一任务。"
        + "\n如果用户问“为什么/真正目的/意义”，禁止退化成文件登记或表面操作回答；必须先完成目的解释，证据不足时明确 UNKNOWN。\n"
        + "原始用户输入（不可被解释包覆盖）：\n"
        + (user_text or "").strip()
    )
