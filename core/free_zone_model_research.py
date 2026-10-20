"""Bounded Free Zone model turns using a fresh, ephemeral MinerPool call."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Mapping

from .miner_pool.model_router import ModelSpec


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


class FreeZoneModelResearch:
    """A research-only adapter: no TaskPool, no daemon ownership, no promotion.

    A ``selected_model`` is an explicit one-call pin, useful for a named bounded
    review seat. The adapter never grants DSH tools or persistent identity; a
    true DSH Agent backend requires its own authenticated Host service boundary.
    """

    def __init__(self, miner_pool: Any):
        self.miner_pool = miner_pool

    def run(
        self,
        seed: Mapping[str, Any],
        *,
        max_tokens: int = 1024,
        system_prompt: str = "Free Zone only. Treat all conclusions as hypotheses.",
        selected_model: str = "",
        role: str = "free_zone_research",
        response_contract: str = "hypotheses",
    ) -> dict[str, Any]:
        required = ("transfer_hypothesis", "counterexample_question", "next_verification", "seed_hash")
        if any(not isinstance(seed.get(key), str) or not seed[key].strip() for key in required):
            raise ValueError("valid semantic seed required")
        if response_contract not in {"hypotheses", "independent_review"}:
            raise ValueError("unsupported response_contract")
        if not isinstance(system_prompt, str) or len(system_prompt) > 2000 or "ace.execution_contract.v1" in system_prompt:
            raise ValueError("system_prompt exceeds bounded research contract")
        if not isinstance(role, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", role):
            raise ValueError("role must be a bounded lowercase responsibility label")
        if isinstance(max_tokens, bool) or not isinstance(max_tokens, int) or not 1 <= max_tokens <= 2048:
            raise ValueError("max_tokens must be between 1 and 2048")
        if response_contract == "independent_review":
            instructions = (
                "Return strict JSON with exactly four keys: hypotheses, counterexamples, "
                "evidence_gaps, next_verification. Each value must be an array of at most "
                "two concise strings. No markdown and no extra keys."
            )
        else:
            instructions = (
                "Return strict JSON with exactly four keys: hypotheses, counterexamples, "
                "evidence_gaps, next_verification. Each value must be an array of at most "
                "three concise strings. No markdown and no extra keys."
            )
        prompt = (
            "You are a Free Zone research scientist. Produce competing hypotheses, "
            "counterexamples, missing evidence, and one next verification. Do not propose "
            "production changes, recommendations, external actions, or task creation. "
            + instructions
            + "\nHypothesis: "
            + seed["transfer_hypothesis"]
            + "\nCounterexample question: "
            + seed["counterexample_question"]
            + "\nNext verification: "
            + seed["next_verification"]
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
        # Sandbox research prompts carry hypotheses, never production corpus:
        # fixed template plus a sandbox seed. Declared PUBLIC so the standing
        # fail-closed boundary can judge the bytes (credential shapes still
        # refuse regardless of label); without a declaration every turn dies
        # at the gate and the shift starves while reporting healthy.
        request = {
            "task_type": "free_exploration",
            "messages": [{"role": "user", "content": prompt}],
            "system_prompt": system_prompt,
            "governance_role": role,
            "governance_task_type": "free_exploration",
            # The default exploration route retains its existing bounded
            # fallback behavior. Explicit model pins are handled below as
            # one-shot and never rotate to an unapproved route.
            "max_retries": 2,
            "max_tokens": max_tokens,
            "data_boundary": {"data_class": "PUBLIC"},
        }
        model_id = selected_model.strip() if isinstance(selected_model, str) else ""
        if model_id:
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}:[A-Za-z0-9._/-]{1,120}", model_id):
                raise ValueError("selected_model must be a bounded provider:model id")
            request["selected_spec"] = ModelSpec.from_id(model_id)
            # A pinned model is one attempt only; never rotate to a paid route.
            request["max_retries"] = 1
        response = self.miner_pool.chat(**request)
        response = response if isinstance(response, Mapping) else {}
        raw_content = response.get("content", "")
        raw_content = raw_content if isinstance(raw_content, str) else ""
        content = raw_content[:12000]
        provider = str(response.get("provider", ""))[:40].strip().lower()
        execution_realm = self._execution_realm(provider)
        material = self._material(content) if response.get("success") else {"status": "UNAVAILABLE"}
        material["contract"] = response_contract
        if response.get("success") and material["status"] != "STRUCTURED_DISTILLATION":
            material["status"] = "UNSTRUCTURED_RESPONSE"
        reported_attempts = response.get("attempts", [])
        reported_attempts = [item for item in reported_attempts if isinstance(item, Mapping)][:2] if isinstance(reported_attempts, list) else []
        # Keep only attribution and integrity evidence; never retain prompt or raw response.
        usage = response.get("usage")
        usage = {
            str(key)[:40]: value
            for key, value in usage.items()
            if isinstance(key, str) and (isinstance(value, (str, int, float, bool)) or value is None)
        } if isinstance(usage, Mapping) else {}
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
            "model": str(response.get("model", ""))[:160],
            "usage": usage,
            "latency_ms": self._bounded_int(response.get("latency_ms"), upper=3_600_000),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "response_sha256": hashlib.sha256(raw_content.encode("utf-8")).hexdigest() if raw_content else "",
            "response_chars": len(raw_content),
            "research_material": material,
            "selected_model": str(selected_model or ""),
            "attempts": [{k: item.get(k) for k in ("model", "provider", "success", "retryable", "latency_ms", "error")} for item in reported_attempts[:2]],
            "raw_content_retained": False,
            "production_integration": False,
            "taskpool_mutated": False,
            "automatic_promotion": False,
        }

    @staticmethod
    def _bounded_int(value: Any, *, upper: int) -> int:
        try:
            return min(max(0, int(value or 0)), upper)
        except (TypeError, ValueError, OverflowError):
            return 0

    @staticmethod
    def _execution_realm(provider: str) -> str:
        """Classify only the execution location needed for honest receipts."""
        if provider in {"glm", "nim", "shenwen_ds41", "oneapi", "amd_radeon"}:
            return "CLOUD"
        if provider == "ollama":
            return "LOCAL"
        if provider == "opencode_cli":
            return "CLI"
        return "UNKNOWN"

    @staticmethod
    def _dual_source_status(success: bool, execution_realm: str) -> str:
        if not success:
            return "LOCAL_BASELINE_ONLY"
        if execution_realm == "CLOUD":
            return "LOCAL_BASELINE_PLUS_CLOUD"
        if execution_realm == "LOCAL":
            return "LOCAL_BASELINE_PLUS_LOCAL_MODEL"
        if execution_realm == "CLI":
            return "LOCAL_BASELINE_PLUS_CLI_MODEL"
        return "LOCAL_BASELINE_PLUS_UNCLASSIFIED_MODEL"

    @staticmethod
    def _invitation(response: Mapping[str, Any], execution_realm: str) -> dict[str, Any]:
        """Explain a missing model result without retaining prompt/response text."""
        attempts = response.get("attempts")
        attempts = attempts if isinstance(attempts, list) else []
        attempted_providers = sorted({str(item.get("provider", "")).strip() for item in attempts if isinstance(item, Mapping) and str(item.get("provider", "")).strip()})
        if response.get("success") and execution_realm == "CLOUD":
            cloud_status = "CLOUD_RESPONSE_RECORDED"
        elif response.get("success") and execution_realm == "CLI":
            cloud_status = "MODEL_RESPONSE_RECORDED_NON_CLOUD"
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
                if not isinstance(text, str):
                    continue
                text = text.strip().replace("\n", " ")
                if text: items.append({"kind": kind, "text": text[:240]})
        return {"status": "STRUCTURED_DISTILLATION" if items else "UNSTRUCTURED_RESPONSE", "items": items[:12]}
