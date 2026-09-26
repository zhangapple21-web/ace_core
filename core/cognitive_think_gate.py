"""Cognitive-hub think gate.

Thinking is the default right of ACE's cognitive hub.  It forms judgments
and never grants execution.  Judgments that would change future behavior
must sediment as facts, evidence, inference, unknowns, and experience.
Thinking must converge instead of looping.

This module is deterministic: no model, no network, no filesystem writes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Mapping


CONTRACT_VERSION = "ace.cognitive_think.v1"
SCHEMA_VERSION = 1

COGNITIVE_HUB = "cognitive_hub"
EXECUTION_NODE = "execution_node"
PRODUCTION_LEAF = "production_leaf"

THINK = "THINK"
JUDGMENT_READY = "JUDGMENT_READY"
CONVERGED = "CONVERGED"
LOOP_BLOCKED = "LOOP_BLOCKED"
NEEDS_HUMAN_DECISION = "NEEDS_HUMAN_DECISION"

SEDIMENT_FIELDS = ("facts", "evidence", "inference", "unknowns", "experience")
MAX_THINK_ROUNDS = 8

CHARTER = (
    "ACE 的认知中枢拥有充分、动态、可恢复的思考权；"
    "思考用于形成判断，不自动获得执行权；"
    "改变未来行为的判断必须沉淀为事实、证据、推断、未知与经验；"
    "思考必须能够收敛，而不是无限循环。"
)


def dynamic_think_budget(unknown_count: int = 0, complexity: str = "medium") -> int:
    """Return a sufficient, dynamic think budget.  Never unbounded."""

    if not isinstance(unknown_count, int) or unknown_count < 0:
        unknown_count = 0
    budget = 2
    if unknown_count >= 1:
        budget += 1
    if unknown_count >= 3:
        budget += 2
    lowered = str(complexity or "").strip().lower()
    if lowered == "complex":
        budget += 2
    elif lowered == "simple":
        budget = max(1, budget - 1)
    return min(max(budget, 1), MAX_THINK_ROUNDS)


def _nonempty_sediment_field(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def sediment_complete(sediment: Mapping[str, Any] | None) -> bool:
    payload = sediment if isinstance(sediment, Mapping) else {}
    return all(_nonempty_sediment_field(payload.get(name)) for name in SEDIMENT_FIELDS)


def evaluate_cognitive_think_gate(
    *,
    actor_role: str = COGNITIVE_HUB,
    unknown_count: int = 0,
    think_rounds: int = 0,
    new_evidence_since_last_think: bool = False,
    judgment_formed: bool = False,
    judgment_changes_future_behavior: bool = False,
    sediment: Mapping[str, Any] | None = None,
    execution_requested: bool = False,
    existing_execution_authorized: bool = False,
    human_decision_required: bool = False,
    complexity: str = "medium",
) -> Dict[str, Any]:
    """Return the default think/judgment/execute/converge decision.

    thinking_grants_execution is always False.  Execution may proceed only
    when an existing authorized path already said yes, sediment is complete
    when future behavior would change, and thinking has not looped.
    """

    reasons: list[str] = []
    role = str(actor_role or "").strip() or COGNITIVE_HUB
    if role not in {COGNITIVE_HUB, EXECUTION_NODE, PRODUCTION_LEAF}:
        reasons.append("ACTOR_ROLE_UNKNOWN")
        role = EXECUTION_NODE

    if not isinstance(unknown_count, int) or unknown_count < 0:
        reasons.append("UNKNOWN_COUNT_INVALID")
        unknown_count = 0
    if not isinstance(think_rounds, int) or think_rounds < 0:
        reasons.append("THINK_ROUNDS_INVALID")
        think_rounds = 0

    budget = dynamic_think_budget(unknown_count, complexity)
    sediment_needed = judgment_changes_future_behavior is True
    sediment_ok = sediment_complete(sediment) if sediment_needed else True
    if sediment_needed and not sediment_ok:
        reasons.append("SEDIMENT_REQUIRED")

    loop_blocked = (
        role != PRODUCTION_LEAF
        and think_rounds >= budget
        and new_evidence_since_last_think is not True
    )
    if loop_blocked:
        reasons.append("THINK_LOOP_BLOCKED")

    if human_decision_required is True:
        reasons.append("NEEDS_HUMAN_DECISION")

    if role == PRODUCTION_LEAF:
        thinking_permitted = False
        reasons.append("PRODUCTION_LEAF_HAS_NO_THINK_RIGHT")
    else:
        thinking_permitted = not loop_blocked and human_decision_required is not True

    thinking_grants_execution = False
    execution_permitted = (
        execution_requested is True
        and existing_execution_authorized is True
        and thinking_grants_execution is False
        and sediment_ok
        and human_decision_required is not True
        and not loop_blocked
    )
    if execution_requested is True and not execution_permitted:
        reasons.append("EXECUTION_DENIED_BY_THINK_GATE")

    if human_decision_required is True:
        status = NEEDS_HUMAN_DECISION
    elif loop_blocked:
        status = LOOP_BLOCKED
    elif judgment_formed is True and sediment_ok and unknown_count == 0:
        status = CONVERGED
    elif judgment_formed is True:
        status = JUDGMENT_READY
    elif thinking_permitted:
        status = THINK
    else:
        status = LOOP_BLOCKED

    next_step = {
        THINK: "think_then_form_judgment",
        JUDGMENT_READY: "sediment_if_future_behavior_changes_then_stop",
        CONVERGED: "stop_thinking",
        LOOP_BLOCKED: "stop_loop_keep_unknown",
        NEEDS_HUMAN_DECISION: "escalate_human_do_not_execute",
    }.get(status, "stop_thinking")

    return {
        "contract_version": CONTRACT_VERSION,
        "schema_version": SCHEMA_VERSION,
        "charter": CHARTER,
        "status": status,
        "actor_role": role,
        "thinking_permitted": thinking_permitted,
        "thinking_grants_execution": thinking_grants_execution,
        "execution_permitted": execution_permitted,
        "sediment_required": sediment_needed,
        "sediment_complete": sediment_ok,
        "think_budget": budget,
        "think_rounds": think_rounds,
        "unknown_count": unknown_count,
        "recoverable": True,
        "reason_codes": reasons,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "next_step": next_step,
    }


__all__ = [
    "CHARTER",
    "CONTRACT_VERSION",
    "CONVERGED",
    "COGNITIVE_HUB",
    "EXECUTION_NODE",
    "JUDGMENT_READY",
    "LOOP_BLOCKED",
    "MAX_THINK_ROUNDS",
    "NEEDS_HUMAN_DECISION",
    "PRODUCTION_LEAF",
    "SEDIMENT_FIELDS",
    "THINK",
    "dynamic_think_budget",
    "evaluate_cognitive_think_gate",
    "sediment_complete",
]
