"""Grok-led shadow routing team for Free Zone adversarial research.

The team is deliberately opt-in and sandbox-facing: Grok opens the search
space, while a caller-supplied audit function (normally Terra/Sol) reviews the
material.  No production task, provider routing, or outbound action is
created here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Mapping


class ShadowRoutingTeam:
    """One Grok exploration followed by an independent audit callback."""

    def __init__(self, miner_pool: Any):
        self.pool = miner_pool

    def run(
        self,
        *,
        task_type: str,
        prompt: str,
        audit: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
        max_tokens: int = 1800,
        timeout: int = 300,
    ) -> dict[str, Any]:
        result = self.pool.chat(
            task_type=task_type,
            messages=[{"role": "user", "content": prompt}],
            include_shadow=True,
            max_retries=1,
            max_tokens=max_tokens,
            timeout=timeout,
        )
        exploration = {
            "success": bool(result.get("success")),
            "provider": result.get("provider", ""),
            "model": result.get("model", ""),
            "content": result.get("content", ""),
            "usage": result.get("usage", {}),
            "cost": result.get("cost", {}),
            "latency_ms": result.get("latency_ms", 0),
            "error": result.get("error", ""),
        }
        audit_result = None
        if exploration["success"] and audit is not None:
            try:
                audit_result = dict(audit(exploration))
            except Exception as error:  # audit failure is retained, never hidden
                audit_result = {"status": "AUDIT_FAILED", "error": f"{type(error).__name__}: {error}"}
        return {
            "contract_version": "ace.shadow_routing_team.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "task_type": task_type,
            "explorer": "GROK_SHADOW",
            "auditor": "INDEPENDENT_CALLBACK",
            "exploration": exploration,
            "audit": audit_result,
            "decision": "PENDING_AUDIT" if exploration["success"] and audit_result is None else ("AUDITED" if audit_result is not None else "EXPLORATION_FAILED"),
            "scope": "FREE_ZONE_RESEARCH_ONLY",
            "production_integration": False,
            "automatic_production_promotion": False,
            "outbound_authority": False,
        }
