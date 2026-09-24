"""Expose Video Kingdom learning receipts to ACE's existing DailyLearningLoop.

This is an adapter, not another queue: candidates are deduplicated against the
existing TaskPool and then pass through DailyLearningLoop -> Researcher /
Validator / Guardian as ordinary governed research work.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .discovery import DiscoveryCandidate
from .evolution_kernel import route_learning


class VideoLearningBridgeBacklog:
    def __init__(self, task_pool: Any, receipt_path: str | Path):
        self.task_pool = task_pool
        self.receipt_path = Path(receipt_path)

    def candidates(self) -> list[tuple[DiscoveryCandidate, list[dict[str, Any]]]]:
        if not self.receipt_path.is_file():
            return []
        existing = {
            task.outputs.get("discovery", {}).get("fingerprint")
            for task in self.task_pool.list_tasks(limit=10000)
            if isinstance(task.outputs.get("discovery", {}), dict)
        }
        packets: list[dict[str, Any]] = []
        for line in self.receipt_path.read_text(encoding="utf-8").splitlines():
            try:
                packet = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(packet, dict) or packet.get("scope") != "video":
                continue
            if packet.get("execution_authorized") is not False or packet.get("production_integration") is not False:
                continue
            if (packet.get("decision") or {}).get("status") != "RESEARCH":
                continue
            if str(packet.get("source_status") or "").upper() != "NEW_OR_CHANGED":
                continue
            if not str(packet.get("source_content_key") or "").strip():
                continue
            packet_id = str(packet.get("packet_id") or "").strip()
            fingerprint = f"video_learning_bridge:{packet_id}" if packet_id else ""
            if fingerprint and fingerprint not in existing:
                packets.append(packet)
        if not packets:
            return []

        # Use the same kernel route as other branches before handing one item
        # to the existing DailyLearningLoop. TaskPool still owns fairness and
        # leases; this adapter never becomes a second scheduler.
        routed = route_learning([
            {
                "candidate_id": packet.get("packet_id"),
                "title": packet.get("title"),
                "source_kind": "video_receipt",
                "observation": packet.get("observation"),
            }
            for packet in packets
        ])
        selected_id = (routed.get("selected") or {}).get("candidate_id")
        packet = next((item for item in packets if item.get("packet_id") == selected_id), packets[0])
        fingerprint = f"video_learning_bridge:{packet['packet_id']}"
        title = str(packet.get("title") or packet.get("candidate_id") or packet["packet_id"])
        observation = packet.get("observation") or {}
        learning = {
            "why_learn": "视频王国的真实学习收据已进入 ACE；先对照本地失败与生产边界复核。",
            "learning_objective": "核验该视频工作流候选是否能改善本地可观测指标；外部仓库主张仅为假设。",
            "required_evidence": ["视频王国源收据", "ACE 独立研究", "本地 baseline/change/test/evaluation"],
            "mastery_criteria": ["完成反例审计和 painful_review；无改善则拒绝，有回归则回滚；未验证前不得改生产默认。"],
            "requires_miner": True,
        }
        candidate = DiscoveryCandidate(
            fingerprint=fingerprint,
            title=f"受理视频学习收据：{title}",
            description="从视频王国单向桥接的研究候选；不得自动进入生产。",
            reason=learning["why_learn"],
            objective=learning["learning_objective"],
            completion_criteria=learning["mastery_criteria"][0],
            verification_method="使用现有 MinerPool/Researcher/Validator/Guardian 进行本地证据核对和隔离验证。",
            priority="medium",
            task_type="reasoning",
            severity="medium",
            candidate_source="video_learning_bridge",
            metadata={
                "learning": learning,
                "evolution_packet_id": packet["packet_id"],
                "governance": {"execution_authorized": False, "production_integration": False},
            },
        )
        refs = observation.get("source_refs", []) if isinstance(observation, dict) else []
        evidence = [{
            "source": "video_kingdom_learning_receipt",
            "source_ref": ref,
            "content": json.dumps({
                "packet_id": packet.get("packet_id"),
                "packet_sha256": packet.get("packet_sha256"),
                "facts": observation.get("facts", []),
                "evidence": observation.get("evidence", []),
                "unknowns": observation.get("unknowns", []),
            }, ensure_ascii=False, sort_keys=True),
            "confidence": 0.5,
            "author": "ACE Evolution Kernel",
            "source_location": ref,
            "metadata": {
                "source_tier": "primary",
                "independence_group": f"video_learning_packet:{packet.get('packet_id')}",
                "lineage_observable": True,
                "directness": "primary",
                "cross_validation_source": "local",
                "production_authority": "NONE",
            },
        } for ref in refs if isinstance(ref, str) and ref.strip()]
        if not evidence:
            evidence = [{
                "source": "video_kingdom_learning_receipt",
                "source_ref": f"ace-evolution://{packet['packet_id']}",
                "content": json.dumps(packet, ensure_ascii=False, sort_keys=True),
                "confidence": 0.5,
                "author": "ACE Evolution Kernel",
                "source_location": f"ace-evolution://{packet['packet_id']}",
                "metadata": {
                    "source_tier": "primary",
                    "independence_group": f"video_learning_packet:{packet.get('packet_id')}",
                    "lineage_observable": True,
                    "directness": "primary",
                    "cross_validation_source": "local",
                    "production_authority": "NONE",
                },
            }]
        return [(candidate, evidence)]


__all__ = ["VideoLearningBridgeBacklog"]
