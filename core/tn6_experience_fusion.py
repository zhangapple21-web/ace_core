"""Turn the TN6 archive into auditable structural hypotheses.

This module is deliberately narrower than a TN6 parser.  It combines the
metadata-only bridge with explicitly supplied veteran principles so ACE can
learn *what to test* without pretending that a filename is a decoded formula.
The result is research context only: it cannot change factor scores, grades,
conviction, risk, admission, or delivery authority.
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

from .indicator_archive import CONTRACT_VERSION as TN6_BRIDGE_CONTRACT_VERSION


CONTRACT_VERSION = "ace.tn6_experience_fusion.v1"

# These are the local, old-hand principles that ACE is allowed to use when it
# interprets the archive.  They are deliberately phrased as questions to
# validate, not as score bonuses or trading signals.  Keeping them here makes
# the "learn from the 100 codes, then walk our own path" boundary explicit and
# reproducible.
DEFAULT_VETERAN_PRINCIPLES: tuple[dict[str, Any], ...] = (
    {
        "rule_id": "veteran-position-before-strength-v1",
        "statement": "先看预期差和可参与位置，再看涨幅；末端加速不等于机会。",
        "motifs": ["first_breakout", "first_pullback_position"],
    },
    {
        "rule_id": "veteran-sector-before-single-v1",
        "statement": "个股强必须放回板块梯队验证，单点脉冲不能冒充主线。",
        "motifs": ["sector_breadth_expansion", "market_regime_gate"],
    },
    {
        "rule_id": "veteran-confirm-then-act-v1",
        "statement": "竞价或分时主动性要在开盘后得到承接；确认后敢做，失效后敢退。",
        "motifs": ["opening_agency", "active_orderflow_retest"],
    },
    {
        "rule_id": "veteran-flow-continuity-v1",
        "statement": "资金看当日与近1–3日连续性，价格没有有效响应就不把流入当强势。",
        "motifs": ["flow_continuity"],
    },
    {
        "rule_id": "veteran-risk-conviction-separate-v1",
        "statement": "机会强度、当前信念和风险等级分开；高风险可以高信念，但必须缩短验证窗口。",
        "motifs": ["first_breakout", "active_orderflow_retest", "market_regime_gate"],
    },
)

# A tag is mapped to a testable market structure, not to a buy/sell signal.
_MOTIFS: dict[str, dict[str, Any]] = {
    "auction": {
        "motif_id": "opening_agency",
        "label": "竞价主动性与开盘承接",
        "factor": "auction_opening_support",
        "question": "竞价强度是否在开盘后得到承接，而非高开低走？",
    },
    "intraday_orderflow": {
        "motif_id": "active_orderflow_retest",
        "label": "主动买盘与分时回踩",
        "factor": "intraday_volume_price_turnover",
        "question": "拉升是否有量、回踩是否缩量、放量后是否滞涨？",
    },
    "flow_turnover": {
        "motif_id": "flow_continuity",
        "label": "资金连续性与换手效率",
        "factor": "flow_continuity_1_3d",
        "question": "当日资金是否与近1–3日方向一致，价格是否有效响应？",
    },
    "sector_rotation": {
        "motif_id": "sector_breadth_expansion",
        "label": "板块扩散与梯队",
        "factor": "sector_strength_rotation",
        "question": "强势是否由至少两个代表标的同步，而非单点脉冲？",
    },
    "breakout_momentum": {
        "motif_id": "first_breakout",
        "label": "首段启动与平台突破",
        "factor": "intraday_volume_price_turnover",
        "question": "是否仍在启动段或首次突破，而不是末端加速？",
    },
    "early_structure": {
        "motif_id": "first_pullback_position",
        "label": "低位结构与第一次回踩",
        "factor": "intraday_volume_price_turnover",
        "question": "回踩是否守住关键结构，且距离失效点仍可接受？",
    },
    "market_regime": {
        "motif_id": "market_regime_gate",
        "label": "指数环境与风险开关",
        "factor": "market_sentiment_index_environment",
        "question": "个股强势是否得到指数/风格环境支持？",
    },
}


def _validate_bridge(bridge: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    if not isinstance(bridge, Mapping):
        raise ValueError("tn6_bridge_must_be_mapping")
    if bridge.get("contract_version") != TN6_BRIDGE_CONTRACT_VERSION:
        raise ValueError("unsupported_tn6_bridge_contract")
    if bridge.get("research_status") != "RESEARCH_ONLY":
        raise ValueError("tn6_bridge_must_be_research_only")
    if bridge.get("can_consume_as_market_signal") is not False:
        raise ValueError("tn6_bridge_cannot_be_market_signal")
    entries = bridge.get("entries")
    if not isinstance(entries, (list, tuple)):
        raise ValueError("tn6_bridge_entries_required")
    declared_count = bridge.get("entry_count")
    if declared_count is not None and int(declared_count) != len(entries):
        raise ValueError("tn6_bridge_entry_count_mismatch")
    if not str(bridge.get("inventory_hash", "")).strip():
        raise ValueError("tn6_bridge_inventory_hash_required")
    return [entry for entry in entries if isinstance(entry, Mapping)]


def _validate_veteran_principles(
    veteran_principles: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(veteran_principles):
        if not isinstance(raw, Mapping):
            raise ValueError(f"veteran_principle_{index}_must_be_mapping")
        rule_id = str(raw.get("rule_id", "")).strip()
        statement = str(raw.get("statement", "")).strip()
        motifs = raw.get("motifs", ())
        if not rule_id or not statement or not isinstance(motifs, (list, tuple)):
            raise ValueError(f"veteran_principle_{index}_requires_rule_id_statement_motifs")
        normalized.append({
            "rule_id": rule_id,
            "statement": statement,
            "motifs": [str(m).strip() for m in motifs if str(m).strip()],
            "epistemic_status": "EXPERIENCE_TO_VALIDATE",
        })
    return normalized


def build_tn6_experience_prior(
    bridge: Mapping[str, Any],
    *,
    veteran_principles: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a structure-prior card from TN6 metadata and old-hand rules.

    Filename prevalence is reported as a sample descriptor only.  It is not a
    hit rate, confidence, probability, or score contribution.
    """

    entries = _validate_bridge(bridge)
    principles = _validate_veteran_principles(veteran_principles)
    tag_counts = Counter(
        str(tag)
        for entry in entries
        for tag in (entry.get("semantic_tags") or [])
        if str(tag) in _MOTIFS
    )
    sample_count = len(entries)
    motifs: list[dict[str, Any]] = []
    for tag, definition in _MOTIFS.items():
        count = tag_counts.get(tag, 0)
        if not count:
            continue
        motifs.append({
            "motif_id": definition["motif_id"],
            "label": definition["label"],
            "source_tag": tag,
            "mapped_factor": definition["factor"],
            "observed_name_count": count,
            "sample_ratio": round(count / sample_count, 6) if sample_count else 0.0,
            "test_question": definition["question"],
            "epistemic_status": "HYPOTHESIS_ONLY",
            "validation_required": "point_in_time_market_replay",
        })

    motif_ids = {motif["motif_id"] for motif in motifs}
    alignment = []
    for principle in principles:
        matched = sorted(set(principle["motifs"]).intersection(motif_ids))
        alignment.append({
            **principle,
            "matched_tn6_motifs": matched,
            "alignment_status": "UNVALIDATED_ALIGNMENT" if matched else "NO_MATCH_IN_ARCHIVE",
        })

    return {
        "contract_version": CONTRACT_VERSION,
        "source_bridge_contract": TN6_BRIDGE_CONTRACT_VERSION,
        "source_inventory_hash": str(bridge["inventory_hash"]),
        "source_entry_count": sample_count,
        "motifs": motifs,
        "veteran_alignment": alignment,
        "operating_path": [
            "position_or_expectation_gap",
            "sector_confirmation",
            "opening_or_intraday_confirmation",
            "invalidation_and_exit",
        ],
        "use": "research_hypothesis_generation_only",
        "epistemic_status": "HYPOTHESIS_ONLY",
        "score_contribution": 0.0,
        "changes_candidate_grade": False,
        "changes_conviction": False,
        "changes_risk_level": False,
        "can_consume_as_market_signal": False,
        "research_status": "RESEARCH_ONLY",
        "next_action": "replay_each_motif_against_point_in_time_data_with_veteran_counterexamples",
    }


def annotate_candidate_with_prior(
    candidate: Mapping[str, Any],
    prior: Mapping[str, Any],
    *,
    matched_motifs: Sequence[str] = (),
) -> dict[str, Any]:
    """Attach TN6 context without changing the candidate's decision axes."""

    if not isinstance(candidate, Mapping):
        raise ValueError("candidate_must_be_mapping")
    if not isinstance(prior, Mapping) or prior.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("unsupported_tn6_experience_prior")
    if prior.get("research_status") != "RESEARCH_ONLY" or prior.get("can_consume_as_market_signal") is not False:
        raise ValueError("tn6_experience_prior_must_be_research_only")
    result = dict(candidate)
    result["tn6_prior_annotation"] = {
        "matched_motifs": sorted({str(m).strip() for m in matched_motifs if str(m).strip()}),
        "effect": "context_only",
        "score_delta": 0.0,
        "decision_axes_unchanged": True,
        "research_status": "RESEARCH_ONLY",
    }
    return result
