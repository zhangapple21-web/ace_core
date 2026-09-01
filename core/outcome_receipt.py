"""Outcome receipts: keep executed work separate from verified results.

The recorder is intentionally unable to infer success from a model response or
an archive transition.  It can stage a task for later verification and accepts
a VERIFIED receipt only when an independent verifier supplies concrete refs.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional


class OutcomeReceiptRecorder:
    PENDING = "PENDING_EXTERNAL_VERIFICATION"
    VERIFIED = "VERIFIED"

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _hash(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()

    @classmethod
    def _evidence_refs(cls, task: Any) -> List[str]:
        refs: List[str] = []
        for item in getattr(task, "evidence", []) or []:
            if not isinstance(item, dict):
                continue
            ref = cls._text(item.get("source_ref") or item.get("source"))
            if ref and ref not in refs:
                refs.append(ref)
        return refs

    def stage(self, task: Any) -> Dict[str, Any]:
        """Create a pending, non-promotional receipt after archival work."""
        outputs = task.outputs if isinstance(getattr(task, "outputs", None), dict) else {}
        existing = outputs.get("verified_outcome_receipt")
        if isinstance(existing, dict) and existing.get("status") == self.VERIFIED:
            return existing
        admission = outputs.get("admission", {})
        if not isinstance(admission, dict):
            admission = {}
        receipt = {
            "schema_version": 1,
            "status": self.PENDING,
            "task_id": task.task_id,
            "staged_at": datetime.now().isoformat(),
            "research_question": self._text(task.hypothesis or task.title),
            "expected_result": self._text(admission.get("expected_result")),
            "verification_method": self._text(admission.get("verification_method")),
            "source_evidence_refs": self._evidence_refs(task),
            "result_present": getattr(task, "result", None) is not None,
            "result_sha256": self._hash(getattr(task, "result", None)),
            "missing": [
                "independent verification evidence",
                "result_ref",
                "verification_ref",
            ],
            "production_integration": False,
        }
        outputs["outcome_receipt"] = receipt
        task.outputs = outputs
        return receipt

    def verify(
        self,
        task: Any,
        *,
        result_ref: str,
        verification_ref: str,
        evidence_refs: List[str],
        independent_evidence_groups: int,
        verifier: str,
        verified_at: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Attach a verified receipt; caller supplies all non-inferable proof."""
        if not self._text(result_ref) or not self._text(verification_ref):
            raise ValueError("result_and_verification_refs_required")
        clean_refs = [self._text(ref) for ref in evidence_refs if self._text(ref)]
        if len(clean_refs) < 2 or int(independent_evidence_groups) < 2:
            raise ValueError("independent_evidence_required")
        receipt = {
            "schema_version": 1,
            "status": self.VERIFIED,
            "task_id": task.task_id,
            "verified_at": verified_at or datetime.now().isoformat(),
            "verifier": self._text(verifier),
            "result_ref": self._text(result_ref),
            "verification_ref": self._text(verification_ref),
            "evidence_refs": clean_refs,
            "independent_evidence_groups": int(independent_evidence_groups),
            "production_integration": False,
        }
        outputs = task.outputs if isinstance(getattr(task, "outputs", None), dict) else {}
        outputs["verified_outcome_receipt"] = receipt
        task.outputs = outputs
        return receipt
