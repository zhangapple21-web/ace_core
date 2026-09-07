"""Bounded model turns for the Free Zone, using the existing MinerPool only."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Mapping


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


class FreeZoneModelResearch:
    """A research-only adapter: no TaskPool, no daemon ownership, no promotion."""

    def __init__(self, miner_pool: Any):
        self.miner_pool = miner_pool

    def run(self, seed: Mapping[str, Any], *, max_tokens: int = 1024) -> dict[str, Any]:
        required = ("transfer_hypothesis", "counterexample_question", "next_verification", "seed_hash")
        if any(not isinstance(seed.get(key), str) or not seed[key].strip() for key in required):
            raise ValueError("valid semantic seed required")
        prompt = (
            "You are a Free Zone research scientist. Produce competing hypotheses, "
            "counterexamples, missing evidence, and one next verification. Do not propose "
            "production changes, recommendations, external actions, or task creation.\n"
            f"Hypothesis: {seed['transfer_hypothesis']}\n"
            f"Counterexample question: {seed['counterexample_question']}\n"
            f"Next verification: {seed['next_verification']}"
        )
        local_baseline = {
            "contract_version": "ace.free_zone.local_baseline.v1",
            "seed_hash": seed["seed_hash"],
            "hypothesis": seed["transfer_hypothesis"][:240],
            "counterexample_question": seed["counterexample_question"][:240],
            "next_verification": seed["next_verification"][:240],
            "computed_locally": True,
        }
        local_baseline["baseline_hash"] = _digest(local_baseline)
        response = self.miner_pool.chat(
            task_type="free_exploration",
            messages=[{"role": "user", "content": prompt}],
            system_prompt="Free Zone only. Treat all conclusions as hypotheses.",
            max_retries=1,
            max_tokens=max_tokens,
        )
        content = str(response.get("content", ""))
        provider = str(response.get("provider", "")).strip().lower()
        execution_realm = self._execution_realm(provider)
        material = self._material(content) if response.get("success") else {"status": "UNAVAILABLE"}
        # Keep only attribution and integrity evidence; never retain prompt or raw response.
        return {
            "contract_version": "ace.free_zone_model_turn.v1",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "seed_hash": seed["seed_hash"],
            "outcome": "MODEL_TURN_RECORDED" if response.get("success") else "MODEL_TURN_UNAVAILABLE",
            # The deterministic baseline is always local.  A remote model is an
            # accelerator, never an authority or a substitute for that baseline.
            "dual_source_status": self._dual_source_status(bool(response.get("success")), execution_realm),
            "local_baseline": local_baseline,
            "model_execution_realm": execution_realm,
            "invitation": self._invitation(response, execution_realm),
            "provider": provider,
            "model": str(response.get("model", "")),
            "usage": dict(response.get("usage") or {}),
            "latency_ms": int(response.get("latency_ms") or 0),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "response_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest() if content else "",
            "response_chars": len(content),
            "research_material": material,
            "attempts": [{k: item.get(k) for k in ("model", "provider", "success", "retryable", "latency_ms", "error")} for item in response.get("attempts", []) if isinstance(item, Mapping)],
            "raw_content_retained": False,
            "production_integration": False,
            "taskpool_mutated": False,
            "automatic_promotion": False,
        }

    @staticmethod
    def _execution_realm(provider: str) -> str:
        """Classify only the execution location needed for honest receipts."""
        if provider in {"glm", "nim"}:
            return "CLOUD"
        if provider == "ollama":
            return "LOCAL"
        return "UNKNOWN"

    @staticmethod
    def _dual_source_status(success: bool, execution_realm: str) -> str:
        if not success:
            return "LOCAL_BASELINE_ONLY"
        if execution_realm == "CLOUD":
            return "LOCAL_BASELINE_PLUS_CLOUD"
        if execution_realm == "LOCAL":
            return "LOCAL_BASELINE_PLUS_LOCAL_MODEL"
        return "LOCAL_BASELINE_PLUS_UNCLASSIFIED_MODEL"

    @staticmethod
    def _invitation(response: Mapping[str, Any], execution_realm: str) -> dict[str, Any]:
        """Explain a missing model result without retaining prompt/response text."""
        attempts = response.get("attempts")
        attempts = attempts if isinstance(attempts, list) else []
        attempted_providers = sorted({str(item.get("provider", "")).strip() for item in attempts if isinstance(item, Mapping) and str(item.get("provider", "")).strip()})
        if response.get("success") and execution_realm == "CLOUD":
            cloud_status = "CLOUD_RESPONSE_RECORDED"
        elif response.get("success"):
            cloud_status = "MODEL_RESPONSE_RECORDED_NON_CLOUD"
        elif attempts:
            cloud_status = "CLOUD_ROUTE_ATTEMPTED_NO_RESPONSE"
        else:
            cloud_status = "CLOUD_ROUTE_NOT_ATTEMPTED"
        return {
            "research_object_status": "ELIGIBLE_SEED_SELECTED",
            "local_baseline_status": "RECORDED",
            "miner_pool_invitation_status": "DISPATCHED",
            "cloud_invitation_status": cloud_status,
            "attempt_count": len(attempts),
            "attempted_providers": attempted_providers,
            "fallback": "LOCAL_BASELINE_RETAINED" if not response.get("success") else "NOT_NEEDED",
            "raw_error_retained": False,
        }

    @staticmethod
    def _material(content: str) -> dict[str, Any]:
        """Retain only a bounded, declarative distillation of model JSON."""
        try:
            value = json.loads(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"status": "UNSTRUCTURED_RESPONSE", "items": []}
        if not isinstance(value, Mapping):
            return {"status": "UNSTRUCTURED_RESPONSE", "items": []}
        items = []
        for kind in ("hypotheses", "counterexamples", "evidence_gaps", "next_verification"):
            raw = value.get(kind, [])
            if isinstance(raw, str): raw = [raw]
            if not isinstance(raw, list): continue
            for text in raw[:3]:
                text = str(text).strip().replace("\n", " ")
                if text: items.append({"kind": kind, "text": text[:240]})
        return {"status": "STRUCTURED_DISTILLATION" if items else "UNSTRUCTURED_RESPONSE", "items": items[:12]}
