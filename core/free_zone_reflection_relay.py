"""Return linked Free Zone results to ACE Reality as shadow research receipts.

The relay is deliberately weaker than acceptance: it translates a completed
Free Zone distillation carrying an ACE-origin receipt into ``MAPPED_SHADOW``.
    ACE's independent reviewer must still decide whether any reflection is usable.
    A daemon may additionally create one admission-bound verification task per
    hash-identified reflection; the task is never production promotion.
"""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from .free_zone_reality_bridge import FreeZoneRealityBridge


class FreeZoneReflectionRelay:
    def __init__(self, workspace_root: str | Path, *, sandbox_root: str | Path | None = None, task_pool: Any | None = None) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.sandbox_root = Path(
            sandbox_root or self.workspace_root / "07_SANDBOX" / "free_research"
        ).resolve()
        self.bridge = FreeZoneRealityBridge(self.workspace_root, sandbox_root=self.sandbox_root)
        # Optional by design: reflection remains usable in read-only tooling,
        # while the daemon can turn a reflected result into a normal,
        # admission-bound ACE verification task.
        self.task_pool = task_pool

    def reflect_available(self) -> dict[str, Any]:
        reflected = []
        skipped = 0
        unlinked_candidates = []
        for source in sorted((self.sandbox_root / "distillations").glob("*.json")):
            value = self._read(source)
            if not isinstance(value, dict):
                skipped += 1
                continue
            if not isinstance(value.get("origin"), dict):
                unlinked_candidates.append((source, value))
                continue
            origin = value["origin"]
            exchange_id = origin.get("exchange_id")
            receipt_sha256 = origin.get("receipt_sha256")
            if not isinstance(exchange_id, str) or not isinstance(receipt_sha256, str):
                skipped += 1
                continue
            incoming = self.workspace_root / "08_GOVERNANCE" / "free_zone_exchange" / "receipts" / f"{exchange_id}.json"
            if not incoming.is_file():
                skipped += 1
                continue
            try:
                receipt = self.bridge.build(source, self._mapping(source, value, incoming))
            except ValueError:
                # One malformed or stale historical artifact must not hide
                # later valid reflections in the same Free Zone turn.
                skipped += 1
                continue
            task = self._create_followup_task(source, value, incoming, receipt)
            reflected.append({
                "experiment_id": value.get("experiment_id"),
                "bridge_id": receipt.get("bridge_id"),
                "status": receipt.get("disposition", {}).get("status"),
                "origin_exchange_id": exchange_id,
                "task_id": getattr(task, "task_id", None),
            })
        task_created = sum(1 for item in reflected if item.get("task_id"))
        # Distillations without an ACE reality-gap origin still need a visible
        # ACE-side reply.  Process only two per daemon turn to avoid queue
        # floods while retaining deterministic, hash-bound backlog progress.
        for source, value in sorted(unlinked_candidates, key=lambda item: item[0].stat().st_mtime, reverse=True)[:2]:
            task = self._create_unlinked_feedback_task(source, value)
            if task is not None:
                reflected.append({
                    "experiment_id": value.get("experiment_id"),
                    "bridge_id": None,
                    "status": "SHADOW_OBSERVED",
                    "origin_exchange_id": None,
                    "task_id": getattr(task, "task_id", None),
                })
        task_created = sum(1 for item in reflected if item.get("task_id"))
        return {
            "status": "REFLECTIONS_RECORDED" if reflected else "NO_LINKED_FREE_ZONE_RESULT",
            "reflected_count": len(reflected),
            "skipped_count": skipped,
            "reflections": reflected,
            "task_created": task_created > 0,
            "task_created_count": task_created,
            "model_call": False,
            "production_runtime_mutation": False,
        }

    def _create_unlinked_feedback_task(self, source: Path, distillation: dict[str, Any]):
        if self.task_pool is None:
            return None
        experiment_id = str(distillation.get("experiment_id", "")).strip()
        stored_hash = str(distillation.get("distillation_hash", "")).strip()
        if not experiment_id or not stored_hash:
            return None
        source_ref = f"free_zone_observation:{experiment_id}:{stored_hash}"
        try:
            existing = self.task_pool.list_tasks(limit=10000, sort_by="created")
            if any(((getattr(task, "outputs", {}) or {}).get("admission", {}) or {}).get("source_ref") == source_ref for task in existing):
                return None
            feedback_dir = self.workspace_root / "08_GOVERNANCE" / "free_zone_bridge" / "feedback"
            feedback_dir.mkdir(parents=True, exist_ok=True)
            source_rel = source.relative_to(self.workspace_root).as_posix()
            payload = {
                "contract_version": "ace.free_zone_feedback.v1",
                "feedback_id": f"FEEDBACK-{experiment_id}",
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "source": {"ref": source_rel, "distillation_sha256": stored_hash},
                "observation": f"Free Zone experiment {experiment_id} produced a {distillation.get('outcome', 'UNKNOWN')} distillation without a linked ACE reality-gap exchange.",
                "epistemic_status": "UNKNOWN",
                "ace_review": {"decision": "HOLD_FOR_EVIDENCE", "reviewer": "free_zone_reflection_relay"},
                "production_integration": False,
                "automatic_model_call": False,
                "automatic_production_promotion": False,
            }
            canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            payload["feedback_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            destination = feedback_dir / f"{payload['feedback_id']}.json"
            if not destination.exists():
                temp = destination.with_suffix(f".{os.getpid()}.tmp")
                temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                try:
                    os.link(temp, destination)
                except FileExistsError:
                    pass
                finally:
                    temp.unlink(missing_ok=True)
            admission = {
                "source_type": "evidence",
                "source_ref": source_ref,
                "why_now": "自由区已产出未绑定 ACE 交换的结果，需自动回送并建立独立验证入口。",
                "evidence": [source_rel, f"08_GOVERNANCE/free_zone_bridge/feedback/{payload['feedback_id']}.json"],
                "expected_result": "确认该自由区结果是否值得形成 ACE 侧后续研究；不改变生产事实。",
                "verification_method": "复核 distillation_hash 与反馈回执 hash，并补充独立 ACE 证据。",
                "risk": "低；仅影子研究和证据核验。",
                "estimated_scope": "small",
            }
            return self.task_pool.create_task(
                title=f"回看自由区结果 {experiment_id}",
                hypothesis=f"自由区结果 {distillation.get('outcome', 'UNKNOWN')} 可能包含可复核的 ACE 研究线索。",
                creator="free_zone_reflection_relay",
                priority="low",
                tags=["free_zone", "feedback", "evidence_verification"],
                admission=admission,
                outputs={"admission": admission, "free_zone_feedback": payload},
            )
        except Exception:
            return None

    def _create_followup_task(
        self,
        source: Path,
        distillation: dict[str, Any],
        incoming: Path,
        receipt: dict[str, Any],
    ) -> Any | None:
        """Create one idempotent ACE-side verification task, never promotion.

        The stable ``source_ref`` is the deduplication key.  We inspect all
        task states (including archived history) before creating so repeated
        daemon cycles cannot manufacture a task storm.
        """
        if self.task_pool is None or receipt.get("disposition", {}).get("status") != "MAPPED_SHADOW":
            return None
        experiment_id = str(distillation.get("experiment_id", "")).strip()
        distillation_hash = str(distillation.get("distillation_hash", "")).strip()
        if not experiment_id or not distillation_hash:
            return None
        source_ref = f"free_zone_reflection:{experiment_id}:{distillation_hash}"
        try:
            existing = self.task_pool.list_tasks(limit=10000, sort_by="created")
            for task in existing:
                admission = (getattr(task, "outputs", {}) or {}).get("admission", {})
                if admission.get("source_ref") == source_ref:
                    return task
            source_rel = source.relative_to(self.workspace_root).as_posix()
            incoming_rel = incoming.relative_to(self.workspace_root).as_posix()
            bridge_id = str(receipt.get("bridge_id", ""))
            admission = {
                "source_type": "evidence",
                "source_ref": source_ref,
                "why_now": "自由区结果已回送 ACE 影子桥接，需由 ACE 独立证据验证其可重复性。",
                "evidence": [source_rel, incoming_rel, f"08_GOVERNANCE/free_zone_bridge/receipts/{bridge_id}.json"],
                "expected_result": "形成独立 ACE 侧验证结论；不得把自由区推断直接升级为生产事实。",
                "verification_method": "复核实验、入站交换回执和桥接回执哈希，并补充一条独立 ACE 证据。",
                "risk": "低；仅研究验证，不改变生产运行时或推荐权。",
                "estimated_scope": "small",
            }
            return self.task_pool.create_task(
                title=f"验证自由区影子结果 {experiment_id}",
                hypothesis=str(distillation.get("hypothesis", "")),
                creator="free_zone_reflection_relay",
                priority="medium",
                tags=["free_zone", "reflection", "evidence_verification"],
                admission=admission,
                outputs={
                    "admission": admission,
                    "free_zone_reflection": {
                        "experiment_id": experiment_id,
                        "bridge_id": bridge_id,
                        "distillation_hash": distillation_hash,
                        "production_integration": False,
                        "automatic_model_call": False,
                        "automatic_production_promotion": False,
                    },
                },
            )
        except Exception:
            # A malformed historical task file or a transient lock must not
            # suppress the shadow receipt itself.
            return None

    def _mapping(self, source: Path, distillation: dict[str, Any], incoming: Path) -> dict[str, Any]:
        experiment_id = str(distillation.get("experiment_id", "UNKNOWN"))
        outcome = str(distillation.get("outcome", "UNKNOWN"))
        relative_source = source.relative_to(self.workspace_root).as_posix()
        relative_incoming = incoming.relative_to(self.workspace_root).as_posix()
        return {
            "mapping_id": f"FREE-ZONE-REFLECTION-{experiment_id}",
            "epistemic_status": "INFERENCE",
            "observation": f"Free Zone experiment {experiment_id} returned {outcome} for a linked ACE Reality gap.",
            "learning": "The result is preserved as a shadow reflection; it is not accepted knowledge or a production fact.",
            "reality_scope": "ACE Reality research observation",
            "research_question": "What independent ACE-side evidence would confirm, refine, or reject this reflected Free Zone result?",
            "expected_result": "One hash-bound shadow receipt preserves both directional lineage without changing ACE authority.",
            "verification_method": "Verify distillation, incoming exchange, source hashes, and zero TaskPool or production mutation.",
            "constraints": [
                "shadow research receipt only",
                "no automatic acceptance",
                "TaskPool creation only through explicit admission",
                "no production runtime mutation",
            ],
            "evidence_refs": [
                {"ref": relative_source, "independence_group": "free_zone_distillation", "kind": "sandbox_distillation"},
                {"ref": relative_incoming, "independence_group": "ace_reality_gap", "kind": "incoming_exchange"},
            ],
            "ace_review": {
                "decision": "HOLD_FOR_EVIDENCE",
                "reviewer": "free_zone_reflection_relay",
                "review_basis": ["linked Free Zone distillation", "bound ACE Reality exchange receipt", "no automatic acceptance"],
            },
        }

    @staticmethod
    def _read(path: Path) -> dict[str, Any] | None:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None
