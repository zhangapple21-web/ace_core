"""把已审议的学习结果压缩成可消费的能力卡。

归档不是终点：只有 Guardian 已判为可保留的经验，才生成受限能力卡并交给
视频王国队列。能力卡仍然明确禁止自动改生产默认值，必须经过本地复测后才
能进入生产门。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from .video_kingdom_dispatch import VideoKingdomDispatch


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def _card_sha(card: Dict[str, Any]) -> str:
    """Hash semantic card content, excluding volatile creation metadata."""
    stable = {key: value for key, value in card.items() if key not in {"card_sha256", "created_at"}}
    return _sha(stable)


class LearningReturnBridge:
    """单向、幂等、带边界的知识→现实消费桥。"""

    def __init__(self, base_dir: str | Path, video_root: str | Path | None = None):
        self.base_dir = Path(base_dir).resolve()
        self.cards_dir = self.base_dir / "09_KNOWLEDGE" / "capability_cards"
        self.cards_dir.mkdir(parents=True, exist_ok=True)
        self.video_root = Path(video_root).resolve() if video_root else None

    def materialize(self, task: Any, experience: Any = None) -> Dict[str, Any]:
        outputs = getattr(task, "outputs", {}) or {}
        external = outputs.get("external_mining")
        discovery = outputs.get("discovery") if isinstance(outputs.get("discovery"), dict) else {}
        video_packet = (
            discovery.get("candidate_source") == "video_learning_bridge"
            and str(discovery.get("evolution_packet_id") or "").strip()
            and str(discovery.get("evolution_packet_sha256") or "").strip()
        )
        if not isinstance(external, dict) and not video_packet:
            return {"status": "NOT_APPLICABLE", "production_integration": False}
        decision = str(getattr(task, "guardian_decision", "") or "")
        if decision not in {"experience", "constraint", "axiom"}:
            return {"status": "NOT_ELIGIBLE", "guardian_decision": decision, "production_integration": False}

        analysis = ((external.get("miner_result") or {}).get("analysis") or {}) if isinstance(external, dict) else {}
        allowed = analysis.get("recommended_absorbable_capabilities") or analysis.get("compatibility") or []
        if not isinstance(allowed, list):
            allowed = [allowed]
        next_verification = analysis.get("next_verification") or []
        if not isinstance(next_verification, list):
            next_verification = [next_verification]
        evidence_refs = []
        for evidence in getattr(task, "evidence", []) or []:
            if isinstance(evidence, dict):
                ref = evidence.get("source_ref") or evidence.get("source")
                if ref and ref not in evidence_refs:
                    evidence_refs.append(ref)
        if video_packet:
            discovery_refs = discovery.get("source_refs", []) if isinstance(discovery.get("source_refs"), list) else []
            for ref in discovery_refs:
                if ref and ref not in evidence_refs:
                    evidence_refs.append(ref)
            # Keep the model's research as bounded context, never as an
            # automatic capability claim. A structured miner result is still
            # preferred when the normal external-mining path supplied one.
            research_result = outputs.get("model_research_result")
            if isinstance(research_result, dict) and research_result.get("content"):
                analysis = {
                    "research_summary": str(research_result["content"])[:4000],
                    "next_verification": ["在本地合成样本上完成 baseline/change/test/evaluation/painful_review"],
                }
        card = {
            "schema_version": "ace.capability-card.v1",
            "card_id": f"CAP-{task.task_id}",
            "source_task_id": task.task_id,
            "source_repository": external.get("fetched", {}).get("repository", "") if isinstance(external, dict) else (discovery.get("source_refs") or [""])[0],
            "source_fingerprint": external.get("fetched", {}).get("fingerprint", "") if isinstance(external, dict) else discovery.get("source_content_key", ""),
            "source_packet_id": discovery.get("evolution_packet_id", "") if video_packet else "",
            "source_packet_sha256": discovery.get("evolution_packet_sha256", "") if video_packet else "",
            "guardian_decision": decision,
            "experience_id": getattr(experience, "experience_id", "") if experience else "",
            "capability_state": "RESEARCH_READY_NOT_PROMOTED",
            "reuse_scope": ["research", "draft_contract", "offline_ab_test"],
            "blocked_scope": ["production_default", "provider_route", "automatic_video_submit"],
            "recommended_capabilities": allowed[:12],
            "next_verification": next_verification[:12],
            "research_summary": analysis.get("research_summary", "") if isinstance(analysis, dict) else "",
            "evidence_refs": evidence_refs[:12],
            "production_integration": False,
            "created_at": _now(),
        }
        # The task is immutable, so the capability identity must remain stable
        # across daemon replays.  ``created_at`` is metadata and must not make
        # an unchanged learning result look like a new capability.
        card["card_sha256"] = _card_sha(card)
        path = self.cards_dir / f"{card['card_id']}.json"
        existing_hash = None
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
                existing_hash = existing.get("card_sha256")
                if existing_hash == card["card_sha256"] and _card_sha(existing) == existing_hash:
                    # Replays of an unchanged task are true no-ops.
                    card = existing
                else:
                    existing_hash = None
            except (OSError, ValueError):
                # A truncated or hand-edited card must be replaced by the
                # deterministic source-of-truth below, never silently reused.
                existing_hash = None
        if existing_hash != card["card_sha256"]:
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)

        handoff: Dict[str, Any]
        if self.video_root and self.video_root.is_dir():
            handoff = VideoKingdomDispatch(self.video_root).dispatch_learning_result(card)
        else:
            handoff = {"status": "VIDEO_KINGDOM_ROOT_UNAVAILABLE", "production_integration": False}
        return {
            "status": "MATERIALIZED",
            "card_id": card["card_id"],
            "card_path": str(path),
            "card_sha256": card["card_sha256"],
            "handoff": handoff,
            "production_integration": False,
        }


__all__ = ["LearningReturnBridge"]
