"""Physical delivery verification and worker-backed execution for ACE tasks.

A task may promise a physical artifact through ``outputs.delivery``::

    {"required_path": "docs/EXAMPLE.md",
     "success_metric": "file_exists_nonempty",
     "domain": "document"}

Before this module existed, ACE never read that field.  ``Validator`` judged
evidence quality only, so a task that promised a file could loop
``research -> rework -> research -> rework`` for five rounds and finally be
blocked with the reason ``相同证据集重复验证达到上限`` while the file was never
created and never checked.  The declared ``success_metric`` was decoration.

Two responsibilities, deliberately small:

1. :func:`verify_delivery` - pure, read-only, deterministic.  Returns a receipt
   proving whether the declared artifact exists and satisfies the declared
   ``success_metric``.  No model, no network, no writes.
2. :class:`DeliveryExecutor` - dispatches a bounded task to a worker selected
   by ``WorkerRouter``.  Fails closed.  Never fabricates a receipt.

The executor refuses to invent content.  If no worker can run, the truthful
answer is ``NO_WORKER_AVAILABLE`` and the task stays honestly undelivered.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Dict, Optional

PROTOCOL = "ace.delivery.execution.v1"

#: Metrics this module can decide on its own, without a human or a test run.
SELF_VERIFIABLE_METRICS = ("file_exists_nonempty", "schema_valid_json")

#: Metrics that need an external receipt; the gate stays silent on these so no
#: existing task behaviour changes.
EXTERNAL_METRICS = ("tests_pass", "user_accepted")

KNOWN_METRICS = SELF_VERIFIABLE_METRICS + EXTERNAL_METRICS

ALLOWED_OUTPUT_EXTS = frozenset({".md", ".json", ".py", ".txt", ".csv", ".yaml", ".yml"})

#: Reasons a verification receipt can come back unsatisfied.
REASON_OK = "delivery_satisfied"
REASON_MISSING = "delivery_file_missing"
REASON_EMPTY = "delivery_file_empty"
REASON_BAD_JSON = "delivery_json_invalid"
REASON_OUT_OF_BOUNDS = "delivery_path_escapes_workspace"
REASON_UNDECLARED = "no_delivery_declared"
REASON_EXTERNAL = "requires_external_receipt"
REASON_BAD_CONTRACT = "delivery_contract_invalid"


def declares_delivery(task: Any) -> bool:
    """Return True when the task carries a well-formed ``outputs.delivery`` block."""
    outputs = task.outputs if isinstance(getattr(task, "outputs", None), dict) else {}
    delivery = outputs.get("delivery")
    return isinstance(delivery, dict) and bool(str(delivery.get("required_path") or "").strip())


def delivery_contract(task: Any) -> Dict[str, Any]:
    """Extract and normalise the declared delivery contract of a task."""
    outputs = task.outputs if isinstance(getattr(task, "outputs", None), dict) else {}
    delivery = outputs.get("delivery") if isinstance(outputs.get("delivery"), dict) else {}
    metric = str(delivery.get("success_metric") or "").strip()
    raw_path = str(delivery.get("required_path") or "").strip().replace("\\", "/")
    errors: list[str] = []
    if not raw_path:
        errors.append("required_path_required")
    elif Path(raw_path).is_absolute():
        errors.append("required_path_must_be_relative")
    elif Path(raw_path).suffix.lower() not in ALLOWED_OUTPUT_EXTS:
        errors.append("required_path_suffix_not_allowed")
    if metric not in KNOWN_METRICS:
        errors.append("success_metric_unknown")
    return {
        "protocol": PROTOCOL,
        "required_path": raw_path,
        "success_metric": metric,
        "domain": str(delivery.get("domain") or "other"),
        "valid": not errors,
        "errors": errors,
    }


def resolve_delivery_path(workspace: Path, required_path: str) -> Optional[Path]:
    """Resolve ``required_path`` inside ``workspace``; None if it escapes."""
    candidate = (workspace / required_path).resolve()
    root = workspace.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def verify_delivery(task: Any, workspace: Path) -> Dict[str, Any]:
    """Check the declared artifact on disk. Pure and read-only."""
    if not declares_delivery(task):
        return {
            "protocol": PROTOCOL,
            "declared": False,
            "satisfied": False,
            "reason": REASON_UNDECLARED,
        }

    contract = delivery_contract(task)
    if not contract["valid"]:
        return {
            "protocol": PROTOCOL,
            "declared": True,
            "satisfied": False,
            "reason": REASON_BAD_CONTRACT,
            "errors": contract["errors"],
            "contract": contract,
        }

    metric = contract["success_metric"]
    receipt: Dict[str, Any] = {
        "protocol": PROTOCOL,
        "declared": True,
        "satisfied": False,
        "required_path": contract["required_path"],
        "success_metric": metric,
    }

    if metric in EXTERNAL_METRICS:
        # No verdict available here. Staying silent keeps existing behaviour.
        receipt["satisfied"] = None
        receipt["reason"] = REASON_EXTERNAL
        return receipt

    target = resolve_delivery_path(workspace, contract["required_path"])
    if target is None:
        receipt["reason"] = REASON_OUT_OF_BOUNDS
        return receipt
    if not target.exists():
        receipt["reason"] = REASON_MISSING
        return receipt
    if not target.is_file():
        receipt["reason"] = REASON_MISSING
        return receipt

    size = target.stat().st_size
    receipt["size_bytes"] = size
    if size == 0:
        receipt["reason"] = REASON_EMPTY
        return receipt
    if metric == "schema_valid_json":
        try:
            json.loads(target.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            receipt["reason"] = REASON_BAD_JSON
            receipt["detail"] = f"{type(exc).__name__}: {exc}"
            return receipt

    receipt["satisfied"] = True
    receipt["reason"] = REASON_OK
    receipt["modified_at"] = target.stat().st_mtime
    try:
        # Content hash, not mtime: a genuine edit to the artifact must change
        # this value (so the validator sees new evidence and can converge),
        # while a no-op re-run must not.
        receipt["content_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
    except OSError:
        pass
    return receipt


#: Instruction-governance evidence that must survive verdict reduction. A gate
#: refusal is only auditable if the receipt still names the file, its class and
#: the rule that refused -- ``{"ok": False, "error": "..."}`` cannot be acted on.
INSTRUCTION_EVIDENCE_KEYS = (
    "instruction_gate",
    "instruction_gate_blocked",
    "instruction_classes",
    "instruction_context_sources",
    "instruction_context_sha256",
    "instruction_context_state",
    "instruction_mode",
    "instruction_staged",
    "instruction_source",
    "instruction_sha256",
    "instruction_reuse",
)


def instruction_evidence(report: Any) -> Dict[str, Any]:
    """Pull the instruction-governance verdict out of a worker receipt."""
    if not isinstance(report, dict):
        return {}
    return {key: report[key] for key in INSTRUCTION_EVIDENCE_KEYS if key in report}


def worker_verdict(report: Any) -> Dict[str, Any]:
    """Read what a worker *claimed*, without inflating it.

    ``bool(report)`` is useless as a success signal: the real
    :class:`~core.opencode_worker.OpenCodeWorker` returns a mapping, and
    ``bool({"success": False})`` is True.  Recording that as ``ok: true`` would
    write a false claim into a receipt that is supposed to be evidence, so the
    worker's own ``success``/``ok`` field decides, and its ``error`` rides along.

    Instruction-governance evidence rides along too, for the same reason in the
    other direction: dropping it would turn a recorded refusal into an
    unexplained failure.
    """
    evidence = instruction_evidence(report)
    if isinstance(report, dict):
        for key in ("success", "ok"):
            if key in report:
                verdict: Dict[str, Any] = {"ok": bool(report[key])}
                if not verdict["ok"] and report.get("error"):
                    verdict["error"] = str(report["error"])
                verdict.update(evidence)
                return verdict
        # A mapping with no verdict field cannot be trusted either way.
        return {"ok": bool(report), "claim": "unverifiable_no_verdict_field", **evidence}
    return {"ok": bool(report), **evidence}


class DeliveryExecutor:
    """Run one declared delivery through a router-selected worker, then verify.

    The worker is injected so that this module stays free of model bindings and
    testable without a CLI on PATH.  ``worker_runner`` receives a keyword set of
    ``task_id``, ``title``, ``hypothesis``, ``required_path``, ``workspace`` and
    must return a mapping.  Whatever it claims, the receipt comes from
    :func:`verify_delivery` -- never from the worker.
    """

    def __init__(
        self,
        workspace: Path,
        worker_runner: Optional[Callable[..., Dict[str, Any]]] = None,
        capability: str = "document",
    ):
        self.workspace = Path(workspace)
        self.worker_runner = worker_runner
        self.capability = capability

    @property
    def has_worker(self) -> bool:
        return callable(self.worker_runner)

    def execute(self, task: Any, max_attempts: int = 1) -> Dict[str, Any]:
        """Attempt the delivery, then verify. Never raises for missing worker."""
        before = verify_delivery(task, self.workspace)
        if before.get("satisfied") is True:
            return {"status": "ALREADY_DELIVERED", "verification": before}

        contract = delivery_contract(task)
        if not contract["valid"]:
            return {"status": "INVALID_CONTRACT", "verification": before, "errors": contract["errors"]}
        if not self.has_worker:
            return {
                "status": "NO_WORKER_AVAILABLE",
                "verification": before,
                "capability": self.capability,
            }

        attempts: list[Dict[str, Any]] = []
        status = "WORKER_FAILED"
        for _ in range(max(1, max_attempts)):
            try:
                report = self.worker_runner(
                    task_id=getattr(task, "task_id", ""),
                    title=getattr(task, "title", ""),
                    hypothesis=getattr(task, "hypothesis", ""),
                    required_path=contract["required_path"],
                    workspace=str(self.workspace),
                )
            except Exception as exc:  # fail closed, never fabricate
                report = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
            attempts.append(worker_verdict(report))
            after = verify_delivery(task, self.workspace)
            if after.get("satisfied") is True:
                status = "DELIVERED"
                break
            if after.get("satisfied") is None:
                status = "EXTERNAL_RECEIPT_REQUIRED"
                break

        return {
            "status": status,
            "attempts": attempts,
            "verification": verify_delivery(task, self.workspace),
            "required_path": contract["required_path"],
            "success_metric": contract["success_metric"],
        }