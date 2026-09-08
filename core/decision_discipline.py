"""老手式决策纪律的可验证、研究期契约。

这不是新的选股模型，也不是 TN6 解析器。它把 ACE 已经采用的判断顺序
固化成一个小对象，供候选卡、复盘和老师审阅共同使用：

事实 -> 结构 -> 位置/价格/预期 -> 确认 -> 失效 -> 赔率

缺赔率时必须停在 ``NO_ODDS_DO_NOT_ACT``；指标（包括 TN6）只能作为
``context_only``，不能改变分数、机会等级、信念或风险轴。
"""

from __future__ import annotations

from typing import Any, Mapping


CONTRACT_VERSION = "ace.decision_discipline.v1"
PRINCIPLE = "先看事实，再看结构；再看位置、价格与预期。确认后敢做，失效后敢退；没有赔率不做，指标只作借鉴，不替我们下判断。"
STAGES = (
    "facts",
    "structure",
    "position_price_expectation",
    "confirmation",
    "invalidation",
    "odds",
)

CHAT_PROTOCOL_VERSION = "ace.stock_chat_decision_protocol.v1"
CHAT_PROTOCOL = (
    "股票问题按这条顺序判断：先核验事实，再看结构；再看位置、价格与预期；"
    "然后写清确认条件、失效条件和赔率。\n"
    "必须把 FACT（已核验事实）、INFERENCE（基于事实的判断）、HYPOTHESIS（待验证假设）"
    "和 UNKNOWN（缺证据）分开。先回答：现在交易的是什么业务、题材或预期差，为什么是现在，"
    "当前位置是否仍有可参与的赔率，1–2 个交易日怎样验证。没有可执行的确认条件、失效条件或"
    "赔率时，明确写“没有赔率不做”，不要为了给答案而凑票。\n"
    "4–5% 的早期转强可以进入观察，但只有在首段启动/首次回踩、板块有联动、承接和量价得到确认、"
    "失效距离可接受时才值得承担波动；尾段加速、单点脉冲、放量滞涨或无法退出时只观察。高风险"
    "不自动压低机会等级，但必须缩短验证窗口、减小暴露并写清退出。\n"
    "TN6 和其他指标只能提供结构问题与反方问题，不能替代行情、公告、板块、资金、位置或历史回放，"
    "也不能单独改变攻击等级、信念或风险。当天最高只有 B，就直说“今天没有 A”；数据不足就说数据不足。\n"
    "推票先检查消息时效和可执行窗口：快照距离当前过久、个股涨幅已接近 9%、已经封板或客户无法成交时，"
    "不得再写“上车/介入”，只能标为窗口已过、等待回踩或次日观察。4–5% 的早期转强可以进入观察，"
    "但必须在首段承接、板块联动和量价确认后才保留。小群由小妍转述时，语气可以坚定、专业、有机构筛选感；"
    "坚定来自已核验事实和明确条件，不写必涨、稳赚、满仓或催促追高。"
)


def chat_protocol_prompt() -> str:
    """Return the stable stock-chat judgment protocol for model prompts."""

    return f"【ACE 股票判断协议 {CHAT_PROTOCOL_VERSION}】\n{CHAT_PROTOCOL}"


def _items(value: Any, field: str) -> list[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, (list, tuple)):
        values = list(value)
    else:
        raise ValueError(f"decision_discipline_{field}_must_be_text_or_sequence")
    result = [str(item).strip() for item in values if str(item).strip()]
    if not result:
        raise ValueError(f"decision_discipline_{field}_must_be_non_empty")
    return result


def normalize_decision_discipline(value: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a point-in-time discipline record without inventing evidence."""

    if not isinstance(value, Mapping):
        raise ValueError("decision_discipline_must_be_mapping")

    normalized: dict[str, Any] = {
        "facts": _items(value.get("facts"), "facts"),
        "structure": _items(value.get("structure"), "structure"),
        "position_price_expectation": _items(
            value.get("position_price_expectation"), "position_price_expectation"
        ),
        "confirmation": _items(value.get("confirmation"), "confirmation"),
        "invalidation": _items(value.get("invalidation"), "invalidation"),
    }
    raw_odds = value.get("odds")
    odds = str(raw_odds or "").strip()
    normalized["odds"] = odds
    normalized["indicator_role"] = "context_only"
    normalized["tn6_role"] = "context_only_unless_point_in_time_replay_admitted"

    if not odds:
        status = "NO_ODDS_DO_NOT_ACT"
        decision_ready = False
    else:
        status = "READY_FOR_CONFIRMATION"
        decision_ready = True

    return {
        "contract_version": CONTRACT_VERSION,
        "principle": PRINCIPLE,
        "stages": list(STAGES),
        **normalized,
        "status": status,
        "decision_ready": decision_ready,
        "research_status": "RESEARCH_ONLY",
        "score_contribution": 0.0,
        "changes_candidate_grade": False,
        "changes_conviction": False,
        "changes_risk_level": False,
        "can_consume_as_market_signal": False,
    }


def attach_decision_discipline(
    candidate: Mapping[str, Any], discipline: Mapping[str, Any]
) -> dict[str, Any]:
    """Attach the contract while preserving all existing decision axes."""

    if not isinstance(candidate, Mapping):
        raise ValueError("candidate_must_be_mapping")
    normalized = normalize_decision_discipline(discipline)
    result = dict(candidate)
    result["decision_discipline"] = normalized
    return result


def metadata() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "principle": PRINCIPLE,
        "stages": list(STAGES),
        "indicator_role": "context_only",
        "no_odds_action": "NO_ODDS_DO_NOT_ACT",
        "research_status": "RESEARCH_ONLY",
        "production_integration": False,
        "recommendation_authority": False,
        "chat_protocol_version": CHAT_PROTOCOL_VERSION,
    }
