"""Research-only company/odds view for A-share candidate cards.

The source principle is simple: a stock candidate must still stand for an
explainable business, industry or trading thesis; price action alone is not a
thesis.  This module turns that principle into a small, auditable context
object.  It is deliberately *not* a score, signal, admission gate, or
long-term value-investing system.  Missing fields remain missing and the
context can never change ``attack_grade``, ``conviction`` or ``risk_level``.

For ultra-short research, ``business_thesis`` may describe a real company
business or a clearly stated industry/expectation trade.  ``execution_quality``
is an observation about the company's/sector's ability to convert the current
expectation, not a claim about management quality without evidence.
"""

from __future__ import annotations

from typing import Any, Mapping


CONTRACT_VERSION = "ace.company_view.v1"
REQUIRED_FIELDS = (
    "business_thesis",
    "why_now",
    "price_and_odds",
    "execution_quality",
    "time_window",
    "counterfactual_company_test",
)

CHAT_GUIDANCE = (
    "每个候选都要能说清：买的是什么业务、行业或交易预期；为什么是现在；"
    "当前位置和价格是否仍有赔率；时间窗口是否匹配。短线不等于长期价值投资，"
    "但不能只拿涨幅、盘口或指标当作完整逻辑。"
)


def _text(value: Any, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"company_view_{field}_must_be_non_empty")
    return text


def _counterfactual(value: Any) -> str:
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    normalized = str(value or "").strip().upper()
    if normalized in {"PASS", "FAIL", "UNKNOWN"}:
        return normalized
    raise ValueError("company_view_counterfactual_company_test_must_be_pass_fail_unknown")


def normalize_company_view(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a candidate's company/odds explanation.

    The returned status is descriptive only.  ``INCOMPLETE`` or ``UNKNOWN``
    must not be filled by the caller with optimistic prose.
    """

    if not isinstance(value, Mapping):
        raise ValueError("company_view_must_be_mapping")
    normalized = {
        "business_thesis": _text(value.get("business_thesis"), "business_thesis"),
        "why_now": _text(value.get("why_now"), "why_now"),
        "price_and_odds": _text(value.get("price_and_odds"), "price_and_odds"),
        "execution_quality": _text(value.get("execution_quality"), "execution_quality"),
        "time_window": _text(value.get("time_window"), "time_window"),
        "counterfactual_company_test": _counterfactual(value.get("counterfactual_company_test")),
    }
    for optional in ("evidence_refs", "counter_evidence"):
        raw = value.get(optional, ())
        if raw is None:
            raw = ()
        if not isinstance(raw, (list, tuple)):
            raise ValueError(f"company_view_{optional}_must_be_sequence")
        normalized[optional] = [str(item).strip() for item in raw if str(item).strip()]

    if normalized["counterfactual_company_test"] == "UNKNOWN":
        status = "INCONCLUSIVE"
    elif not normalized["evidence_refs"]:
        status = "RESEARCH_ONLY_NO_DIRECT_EVIDENCE"
    else:
        status = "COMPLETE_RESEARCH_CONTEXT"

    return {
        "contract_version": CONTRACT_VERSION,
        **normalized,
        "status": status,
        "research_status": "RESEARCH_ONLY",
        "score_contribution": 0.0,
        "changes_candidate_grade": False,
        "changes_conviction": False,
        "changes_risk_level": False,
        "can_consume_as_market_signal": False,
        "semantics": "explanation_and_counterfactual_context_only",
    }


def attach_company_view(candidate: Mapping[str, Any], view: Mapping[str, Any]) -> dict[str, Any]:
    """Attach a validated context while preserving all decision axes."""

    if not isinstance(candidate, Mapping):
        raise ValueError("candidate_must_be_mapping")
    normalized = normalize_company_view(view)
    result = dict(candidate)
    result["company_view"] = normalized
    return result


def metadata() -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "required_fields": list(REQUIRED_FIELDS),
        "status": "RESEARCH_ONLY",
        "score_contribution": 0.0,
        "production_integration": False,
        "recommendation_authority": False,
        "purpose": "business_thesis_price_odds_execution_time_context",
        "chat_guidance": CHAT_GUIDANCE,
    }
