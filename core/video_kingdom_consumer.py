"""Bounded consumer for Video Kingdom dispatch cards.

This is deliberately not a scheduler: it consumes at most one card per ACE
cycle and records an auditable handoff.  Provider/media runners remain the
dedicated shift's responsibility; no duplicate video submission can occur.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.video_kingdom_dispatch import VideoKingdomDispatch


class VideoKingdomConsumer:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.dispatch = VideoKingdomDispatch(self.root)
        self.receipts = self.root / "research" / "dispatch_receipts.v1.jsonl"
        self.result_outbox = self.root / "research" / "ace_result_outbox.v1.jsonl"
        self.result_receipts = self.root / "research" / "ace_result_receipts.v1.jsonl"

    def consume_one(self, *, patrol: dict[str, Any] | None = None) -> dict[str, Any]:
        bridge = self.consume_one_result()
        if bridge["status"] == "RESULT_CONSUMED":
            return bridge
        card = self.dispatch.claim_next()
        if not card:
            return {"status": "NO_PENDING_CARD", "production_integration": False}
        try:
            evidence = self._evidence(card, patrol or {})
            finished = self.dispatch.finish(card["task_id"], status="HANDOFF_READY", evidence=evidence)
            self._receipt({"event": "DISPATCH_HANDOFF_READY", "task": finished, "production_integration": False})
            return {"status": "HANDOFF_READY", "task_id": card["task_id"], "task_type": card.get("task_type"),
                    "evidence": evidence, "production_integration": False}
        except Exception as exc:  # leave a durable failure instead of silently retrying
            finished = self.dispatch.finish(card["task_id"], status="FAILED", error=str(exc))
            self._receipt({"event": "DISPATCH_FAILED", "task": finished, "production_integration": False})
            return {"status": "FAILED", "task_id": card["task_id"], "error": str(exc), "production_integration": False}

    def consume_one_result(self) -> dict[str, Any]:
        """Accept at most one validated controlled-production result per cycle.

        The source outbox remains append-only.  ACE records its own receipt and
        never treats a result as a provider submission or DELIVERY_APPROVED.
        """
        seen = self._consumed_bridge_ids()
        if not self.result_outbox.is_file():
            return {"status": "NO_PENDING_RESULT", "production_integration": False}
        for line in self.result_outbox.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            bridge_id = item.get("bridge_id")
            if not isinstance(bridge_id, str) or bridge_id in seen:
                continue
            result = self._validate_result_bridge(item)
            if result["status"] == "RESULT_CONSUMED":
                self._result_receipt(result)
            else:
                self._result_receipt(result)
            return result
        return {"status": "NO_PENDING_RESULT", "production_integration": False}

    def _consumed_bridge_ids(self) -> set[str]:
        if not self.result_receipts.is_file():
            return set()
        values: set[str] = set()
        for line in self.result_receipts.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value.get("bridge_id"), str):
                values.add(value["bridge_id"])
        return values

    def _validate_result_bridge(self, item: dict[str, Any]) -> dict[str, Any]:
        required = {"bridge_id", "record_id", "episode_id", "scope_ref", "decision_verdict", "result_status", "record_path", "record_sha256", "source_realm", "production_integration", "delivery_approved"}
        if not isinstance(item, dict) or required - set(item):
            return {"status": "RESULT_REJECTED", "bridge_id": item.get("bridge_id"), "reason": "missing_fields", "production_integration": False}
        if item["production_integration"] is not False or item["delivery_approved"] is not False:
            return {"status": "RESULT_REJECTED", "bridge_id": item["bridge_id"], "reason": "authority_boundary", "production_integration": False}
        if item["decision_verdict"] not in {"PASS", "REWORK", "BLOCKED", "CONDITIONAL"} or item["result_status"] not in {"NOT_EXECUTED", "COMPLETED", "FAILED", "SUPERSEDED"}:
            return {"status": "RESULT_REJECTED", "bridge_id": item["bridge_id"], "reason": "invalid_verdict", "production_integration": False}
        record = (self.root / item["record_path"]).resolve()
        try:
            record.relative_to(self.root)
        except ValueError:
            return {"status": "RESULT_REJECTED", "bridge_id": item["bridge_id"], "reason": "path_outside_root", "production_integration": False}
        if not record.is_file() or self._sha256(record) != item["record_sha256"]:
            return {"status": "RESULT_REJECTED", "bridge_id": item["bridge_id"], "reason": "record_hash_mismatch", "production_integration": False}
        return {"status": "RESULT_CONSUMED", "bridge_id": item["bridge_id"], "record_id": item["record_id"], "episode_id": item["episode_id"], "scope_ref": item["scope_ref"], "decision_verdict": item["decision_verdict"], "result_status": item["result_status"], "production_integration": False, "delivery_approved": False}

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _result_receipt(self, value: dict[str, Any]) -> None:
        self.result_receipts.parent.mkdir(parents=True, exist_ok=True)
        with self.result_receipts.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), **value}, ensure_ascii=False) + "\n")

    def _evidence(self, card: dict[str, Any], patrol: dict[str, Any]) -> dict[str, Any]:
        task_type = card.get("task_type")
        if task_type == "RESUME_MEDIA_WORK":
            jobs = patrol.get("resumable_jobs", []) if isinstance(patrol.get("resumable_jobs"), list) else []
            return {"action": "RESUME_POLL_ONLY", "resumable_jobs": len(jobs), "duplicate_submission": False}
        if task_type == "CONTINUITY_REPAIR":
            warnings = patrol.get("warnings", []) if isinstance(patrol.get("warnings"), list) else []
            digest = hashlib.sha256(json.dumps(warnings, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            return {"action": "REPAIR_REVIEW_RECORDED", "warning_count": len(warnings), "warning_digest": digest}
        return {"action": "LEARNING_SLOT_OPENED", "source_boundary": "PUBLIC_ONLY",
                "next_step": "deduplicate against public_street_learning_ledger", "provider_calls": 0}

    def _receipt(self, value: dict[str, Any]) -> None:
        self.receipts.parent.mkdir(parents=True, exist_ok=True)
        with self.receipts.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), **value}, ensure_ascii=False) + "\n")
