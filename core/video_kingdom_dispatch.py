"""Event-driven handoff from ACE observations to the Video Kingdom.

Uses the existing ACE daemon as the only clock/control surface. It creates
bounded research cards in the kingdom's local queue; it never calls a model,
provider, TaskPool, or publishing endpoint.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class VideoKingdomDispatch:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.queue = self.root / "research" / "dispatch_queue.v1.json"

    def observe_and_dispatch(self, *, trigger: str, patrol: dict[str, Any] | None = None) -> dict[str, Any]:
        patrol = patrol or {}
        warnings = patrol.get("warnings") if isinstance(patrol.get("warnings"), list) else []
        active = patrol.get("active_jobs") if isinstance(patrol.get("active_jobs"), list) else []
        if warnings:
            task_type = "CONTINUITY_REPAIR"
            brief = "Review patrol warnings, attribute each failure, and create the smallest repair experiment."
        elif active:
            task_type = "RESUME_MEDIA_WORK"
            brief = "Resume existing video jobs by video_id; do not submit duplicates."
        else:
            task_type = "EXTERNAL_LEARNING"
            brief = "Visit one public source or shop, extract one bounded mechanism, and record a source hash and next probe."
        linkage = self._linkage_context()
        fingerprint = hashlib.sha256(json.dumps({"task_type": task_type, "trigger": trigger, "day": self._day(), "linkage": linkage}, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:16]
        existing = self._read()
        cards = existing.get("cards", []) if isinstance(existing.get("cards"), list) else []
        prior = next((card for card in cards if isinstance(card, dict) and card.get("fingerprint") == fingerprint), None)
        if prior is not None:
            return {"status": "ALREADY_DISPATCHED", "task_type": task_type, "fingerprint": fingerprint,
                    "linkage": prior.get("linkage", linkage), "production_integration": False}
        card = {
            "task_id": f"VK-AUTO-{fingerprint}", "fingerprint": fingerprint,
            "task_type": task_type, "brief": brief,
            "trigger": trigger, "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "PENDING", "production_integration": False,
            "provider_calls": 0, "automatic_promotion": False,
            "linkage": linkage,
        }
        cards.append(card)
        self.queue.parent.mkdir(parents=True, exist_ok=True)
        self.queue.write_text(json.dumps({"contract_version": "ace.video_kingdom.dispatch_queue.v1", "production_integration": False, "cards": cards[-100:]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return {"status": "DISPATCHED", "task_type": task_type, "task_id": card["task_id"], "linkage": linkage, "production_integration": False}

    def _linkage_context(self) -> dict[str, Any]:
        """Bind the handoff to current VK evidence without calling a provider."""
        candidates = {
            "episode_contract": "episodes/episode_007_virtual_data.v1.json",
            "six_module_contract": "episodes/episode_007_virtual_data.six_module.v1.json",
            "preflight": "research/episode_007_preflight_runtime_20260904.json",
            "previous_cut_audit": "research/episode_007_previous_cut_audit_latest.json",
        }
        refs: list[dict[str, Any]] = []
        for name, relative in candidates.items():
            path = self.root / relative
            entry: dict[str, Any] = {"name": name, "path": relative, "exists": path.is_file()}
            if path.is_file():
                digest = hashlib.sha256()
                try:
                    with path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    entry["sha256"] = digest.hexdigest()
                except OSError as exc:
                    entry["read_error"] = str(exc)
            refs.append(entry)
        return {
            "project_id": "episode_007_virtual_data",
            "evidence_refs": refs,
            "contract_status": "LINKED" if all(item.get("exists") for item in refs[:2]) else "GAPPED",
            "previous_cut_audit_status": "AVAILABLE" if refs[3].get("exists") else "MISSING",
            "next_owner": "video_kingdom_shift",
            "production_integration": False,
        }

    @staticmethod
    def _day() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _read(self) -> dict[str, Any]:
        try:
            value = json.loads(self.queue.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def claim_next(self) -> dict[str, Any] | None:
        """Atomically-ish claim one pending card for the next bounded shift.

        The ACE daemon is the single writer, so a small read/modify/write is
        sufficient here.  A claim is never a provider call or publication.
        """
        payload = self._read()
        cards = payload.get("cards", []) if isinstance(payload.get("cards"), list) else []
        for card in cards:
            if isinstance(card, dict) and card.get("status") == "PENDING":
                card["status"] = "CLAIMED"
                card["claimed_at"] = datetime.now(timezone.utc).isoformat()
                self._write(payload, cards)
                return dict(card)
        return None

    def finish(self, task_id: str, *, status: str, evidence: dict[str, Any] | None = None,
               error: str | None = None) -> dict[str, Any]:
        payload = self._read()
        cards = payload.get("cards", []) if isinstance(payload.get("cards"), list) else []
        for card in cards:
            if isinstance(card, dict) and card.get("task_id") == task_id:
                card["status"] = status
                card["finished_at"] = datetime.now(timezone.utc).isoformat()
                if evidence is not None:
                    card["evidence"] = evidence
                if error:
                    card["error"] = error[:500]
                self._write(payload, cards)
                return dict(card)
        return {"status": "NOT_FOUND", "task_id": task_id}

    def _write(self, payload: dict[str, Any], cards: list[Any]) -> None:
        self.queue.parent.mkdir(parents=True, exist_ok=True)
        self.queue.write_text(json.dumps({
            "contract_version": "ace.video_kingdom.dispatch_queue.v1",
            "production_integration": False,
            "cards": cards[-100:],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
