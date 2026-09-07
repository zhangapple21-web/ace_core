import copy

import pytest

from core.research_companion import (
    append_research_event,
    build_research_question_card,
    create_research_thread,
    validate_research_card,
    validate_research_thread,
)


def _ref(name: str, group: str = "runtime"):
    return {
        "ref": f"evidence://{name}",
        "kind": "observation",
        "independence_group": group,
        "observed_at": "2026-08-30T09:30:00+08:00",
    }


def _card(**overrides):
    values = {
        "question_id": "Q-001",
        "thread_id": "T-001",
        "subject": "早盘板块强度",
        "original_question": "板块强度是否能解释早盘延续？",
        "decomposed_questions": ["强度如何定义？", "延续窗口多长？"],
        "hypothesis": "首 15 分钟相对强度可能与延续有关",
        "research_dimensions": ["量价", "板块", "情绪"],
        "expected_evidence": ["带时间戳的行情快照", "独立来源一致性"],
        "support_refs": [_ref("quote", "quote")],
        "counterevidence_refs": [_ref("counter", "sentiment")],
        "unknowns": ["样本外稳定性"],
        "next_verification": "回放过去 20 个交易日的首 15 分钟",
        "epistemic_status": "INFERENCE",
        "profile_version": "research-companion.v1",
    }
    values.update(overrides)
    return build_research_question_card(**values)


def test_card_is_hash_bound_and_round_trips():
    card = _card()
    assert validate_research_card(card) == card
    assert len(card["card_hash"]) == 64
    assert card["production_integration"] is False


def test_new_card_without_counterevidence_is_honest_unknown():
    card = _card(counterevidence_refs=[], epistemic_status="FACT")
    assert card["epistemic_status"] == "UNKNOWN"
    assert card["counterevidence_refs"] == []


def test_non_unknown_card_cannot_claim_no_counterevidence():
    card = _card()
    forged = copy.deepcopy(card)
    forged["counterevidence_refs"] = []
    forged["epistemic_status"] = "INFERENCE"
    forged["card_hash"] = card["card_hash"]
    with pytest.raises(ValueError, match="counterevidence"):
        validate_research_card(forged)


def test_card_rejects_malformed_evidence_with_production_fields():
    with pytest.raises(ValueError, match="malformed evidence ref"):
        _card(support_refs=[_ref("quote") | {"target_price": "10"}])


def test_thread_has_initial_event_and_chain_hash():
    thread = create_research_thread(
        thread_id="T-001", subject="板块研究", initial_question="为什么今天强？"
    )
    assert thread["current_status"] == "OPEN"
    assert len(thread["events"]) == 1
    assert validate_research_thread(thread) == thread


def test_append_event_preserves_history_and_updates_status():
    thread = create_research_thread(
        thread_id="T-002", subject="研究", initial_question="需要什么证据？"
    )
    updated = append_research_event(
        thread,
        event_id="T-002:pending",
        event_type="verification_pending",
        payload={"missing": "独立来源"},
    )
    assert len(updated["events"]) == 2
    assert updated["current_status"] == "VERIFICATION_PENDING"
    assert updated["events"][1]["previous_event_hash"] == thread["events"][0]["event_hash"]
    assert thread["current_status"] == "OPEN"


def test_thread_hash_chain_detects_tampering():
    thread = create_research_thread(
        thread_id="T-003", subject="研究", initial_question="原始问题"
    )
    forged = copy.deepcopy(thread)
    forged["events"][0]["payload"]["question"] = "篡改"
    with pytest.raises(ValueError, match="event hash mismatch"):
        validate_research_thread(forged)


def test_invalidated_event_is_terminal_context_not_deletion():
    thread = create_research_thread(
        thread_id="T-004", subject="研究", initial_question="假设成立吗？"
    )
    invalidated = append_research_event(
        thread,
        event_id="T-004:invalidated",
        event_type="invalidated",
        payload={"reason": "反方证据否定假设"},
    )
    assert invalidated["current_status"] == "INVALIDATED"
    assert len(invalidated["events"]) == 2


def test_thread_rejects_forbidden_payload():
    thread = create_research_thread(
        thread_id="T-005", subject="研究", initial_question="边界？"
    )
    with pytest.raises(ValueError, match="forbidden field"):
        append_research_event(
            thread,
            event_id="T-005:bad",
            event_type="evidence_added",
            payload={"advisor": "enabled"},
        )


