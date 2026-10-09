"""Capability-based, governed worker/model routing for the canonical ACE lifecycle."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Sequence


@dataclass(frozen=True)
class WorkerCapability:
    worker_id: str
    runtime: str
    capabilities: frozenset[str]
    enabled: bool = True
    verification_rate: float = 0.0
    success_rate: float = 0.0
    latency_ms: float = 0.0
    evidence_count: int = 0
    metadata: Dict[str, str] = field(default_factory=dict)


class WorkerRouter:
    """Select workers and explicit model fallback order; never fabricate success."""

    def __init__(self, workers: Sequence[WorkerCapability] = (), max_attempts: int = 9):
        self._workers = {worker.worker_id: worker for worker in workers}
        self.max_attempts = max(1, int(max_attempts))

    def register(self, worker: WorkerCapability) -> None:
        self._workers[worker.worker_id] = worker

    def candidates(self, capability: str) -> List[WorkerCapability]:
        wanted = str(capability).strip().lower()
        eligible = [
            worker for worker in self._workers.values()
            if worker.enabled and wanted in {item.lower() for item in worker.capabilities}
        ]
        return sorted(eligible, key=lambda worker: (
            worker.verification_rate, worker.success_rate,
            worker.evidence_count, -worker.latency_ms,
        ), reverse=True)

    def choose(self, capability: str) -> WorkerCapability | None:
        candidates = self.candidates(capability)
        return candidates[0] if candidates else None

    def model_order(self, capability: str) -> List[str]:
        """Return a deduplicated, registry-backed fallback order.

        Registry order is evidence-ranked. An explicit ``fallback_rank`` can
        override that rank, while disabled/unregistered models are excluded.
        """
        workers = self.candidates(capability)
        workers.sort(key=lambda worker: (
            int(worker.metadata.get("fallback_rank", "9999")),
            -worker.verification_rate, -worker.success_rate,
            -worker.evidence_count, worker.latency_ms,
        ))
        result: List[str] = []
        for worker in workers:
            model = str(worker.metadata.get("model", "")).strip()
            if model and model not in result:
                result.append(model)
        return result[: self.max_attempts]

    def run(self, capability, worker, verify=None, **kwargs):
        order = self.model_order(capability)
        attempts = []
        last = {}
        for model in order:
            try:
                receipt = worker.run(model_order=[model], **kwargs)
            except (FileNotFoundError, ValueError) as error:
                receipt = {"success": False, "error": str(error), "model": model}
                attempts.append(receipt)
                last = receipt
                break
            passed = receipt.get("success") is True and (verify is None or verify(receipt))
            receipt = dict(receipt, model=model, success=bool(passed))
            if not passed and not receipt.get("error"):
                receipt["error"] = "worker_contract_failed"
            receipt["failure_class"] = self.classify_failure(receipt)
            attempts.append(receipt)
            last = receipt
            if passed or receipt.get("changed") is True:
                break
        result = dict(last)
        result.update(router_model_order=order, router_attempts=attempts,
                      fallback_used=len(attempts) > 1,
                      success=bool(last.get("success")),
                      attempts=[a for r in attempts for a in r.get("attempts", [])])
        if not result["success"]:
            result["error"] = last.get("error", "router_all_models_failed")
        return result

    @staticmethod
    def classify_failure(receipt: Dict[str, Any]) -> str:
        if receipt.get("success") is True:
            return "success"
        text = " ".join(str(receipt.get(key, "")) for key in ("error", "raw_output", "stderr_output")).lower()
        if "429" in text or "quota" in text or "rate limit" in text:
            return "quota"
        if "timeout" in text or receipt.get("timeout"):
            return "timeout"
        if receipt.get("returncode", 0) not in (0, None):
            return "nonzero_exit"
        if receipt.get("parsed_result") is None:
            return "contract_failure"
        return "worker_failure"

    def snapshot(self) -> Dict[str, object]:
        return {
            "schema_version": "ace.worker-registry.v2",
            "max_attempts": self.max_attempts,
            "workers": [{
                "worker_id": worker.worker_id, "runtime": worker.runtime,
                "capabilities": sorted(worker.capabilities), "enabled": worker.enabled,
                "verification_rate": worker.verification_rate,
                "success_rate": worker.success_rate, "latency_ms": worker.latency_ms,
                "evidence_count": worker.evidence_count, "metadata": dict(worker.metadata),
            } for worker in self._workers.values()],
        }
