"""Bounded roles for the free-research sandbox.

These roles are persistent contracts, not permanently running model personas.
The free zone itself may discover, claim and execute experiments without prior
approval. Curator and court operate after execution: they preserve meaning and
guard only the one-way edge into production.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .free_research_sandbox import CONTRACT_VERSION, FreeResearchSandbox, _digest
from .free_zone_factories import FreeZoneFactoryLine
from .lazy_cat_audit import LazyCatAudit


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SandboxSociety:
    """Free-zone, curator, court and teacher-review roles in one bounded turn."""

    def __init__(self, root: str | Path) -> None:
        self.sandbox = FreeResearchSandbox(root)
        self.root = self.sandbox.root
        self.reports = self.root / "reports"
        self.factories = FreeZoneFactoryLine(self.root)
        self.lazy_cat = LazyCatAudit(self.root)

    def run_turn(self) -> dict[str, Any]:
        """Distill completed work; never approve or promote it to production."""
        self.sandbox.initialize()
        self.factories.initialize()
        self.lazy_cat.initialize()
        clean = self._records(self.sandbox.experiments)
        quarantined = self._records(self.sandbox.quarantine)
        distillations_before = self._distillation_ids()
        proposals_before = self._proposal_ids()
        new_distillations = []
        new_proposals = []
        new_smelter_receipts = []
        for record in [*clean, *quarantined]:
            experiment_id = record["experiment_id"]
            if experiment_id in distillations_before:
                continue
            result = self.sandbox.distill(experiment_id)
            new_distillations.append({"experiment_id": experiment_id, "status": result["status"]})
            smelter = self.factories.smelt(record=record, distillation=result)
            new_smelter_receipts.append(smelter["receipt_id"])
            if result["status"] == "PROPOSAL_ONLY" and experiment_id not in proposals_before:
                new_proposals.append(experiment_id)
        all_records = [*clean, *quarantined]
        lazy_cat = self.lazy_cat.audit_all(
            records=all_records,
            distillations=self._distillation_records(),
        )
        lazy_cat["challenge_reconciliation"] = self.lazy_cat.reconcile_challenge_probes(records=all_records)
        # Reconciliation may settle legacy challenge probes.  Report the
        # post-reconciliation count, not the earlier pre-backfill snapshot.
        lazy_cat["pending_challenge_count"] = lazy_cat["challenge_reconciliation"]["pending_challenge_count"]
        court = self._court_audit()
        queue = self._teacher_queue(self.lazy_cat.verdict_by_experiment())
        report = {
            "contract_version": CONTRACT_VERSION,
            "mode": "SANDBOX_SOCIETY_TURN",
            "at": _now(),
            "roles": {
                "free_zone": {"clean_experiment_count": len(clean), "quarantine_count": len(quarantined)},
                "curator": {
                    "new_distillations": new_distillations,
                    "new_proposal_ids": new_proposals,
                    "new_smelter_receipt_ids": new_smelter_receipts,
                    "action": "distill_all_outcomes" if new_distillations else "NO_NEW_SANDBOX_WORK",
                },
                "court": court,
                "lazy_cat": lazy_cat,
                "teacher": {**queue, "may_approve": False},
            },
            "design_seed": self._design_seed_summary(),
            "factories": self.factories.snapshot(),
            "production_integration": False,
            "automatic_promotion": False,
            "automatic_model_call": False,
            "automatic_external_fetch": False,
        }
        self._write_report(report)
        return report

    def _design_seed_summary(self) -> dict[str, Any]:
        """Expose which parts of the R1 seed are observable in today's turn.

        This is intentionally a read-only map.  A path being present is not
        treated as proof that it is a live daemon consumer; the distinction is
        recorded explicitly so the free zone cannot accidentally promote old
        code merely because it still exists.
        """
        path = self.root / "constitution" / "R1_ECOLOGY_CONSTITUTION_v1.json"
        if not path.exists():
            return {"status": "NOT_OBSERVED", "reason": "constitution_missing", "route": [], "invariants": []}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {"status": "INVALID", "reason": "constitution_unreadable", "route": [], "invariants": []}
        if not isinstance(value, dict):
            return {"status": "INVALID", "reason": "constitution_not_mapping", "route": [], "invariants": []}
        route = [str(item) for item in value.get("route", []) if str(item).strip()]
        invariants = [str(item.get("id")) for item in value.get("invariants", []) if isinstance(item, dict) and item.get("id")]
        mapping = value.get("reinstantiation_mapping", {})
        return {
            "status": "DESIGN_SEED_OBSERVED",
            "contract_version": value.get("contract_version"),
            "route": route,
            "invariants": invariants,
            "mapping_keys": sorted(str(key) for key in mapping) if isinstance(mapping, dict) else [],
            "consumption_mode": "sandbox_report_only",
            "production_integration": False,
        }

    def _court_audit(self) -> dict[str, Any]:
        invalid = []
        for record in [*self._records(self.sandbox.experiments), *self._records(self.sandbox.quarantine)]:
            expected = record.get("record_hash", "")
            unsigned = dict(record)
            unsigned.pop("record_hash", None)
            if not expected or _digest(unsigned) != expected:
                invalid.append(record.get("experiment_id", "unknown"))
        records = {
            item["experiment_id"]: item
            for item in [*self._records(self.sandbox.experiments), *self._records(self.sandbox.quarantine)]
        }
        distillation_mismatch = []
        distillation_integrity_failures = []
        for distillation in self._distillation_records():
            experiment_id = distillation.get("experiment_id", "")
            record = records.get(experiment_id)
            if not record or distillation.get("source_record_hash") != record.get("record_hash"):
                distillation_mismatch.append(experiment_id or "unknown")
            expected = distillation.get("distillation_hash", "")
            unsigned = dict(distillation)
            unsigned.pop("distillation_hash", None)
            if not expected or _digest(unsigned) != expected:
                distillation_integrity_failures.append(experiment_id or "unknown")

        proposal_mismatch = []
        proposal_integrity_failures = []
        for proposal in self._proposal_records():
            experiment_id = proposal.get("experiment_id", "")
            record = records.get(experiment_id)
            if not record or proposal.get("source_record_hash") != record.get("record_hash"):
                proposal_mismatch.append(experiment_id or "unknown")
            expected = proposal.get("proposal_hash", "")
            unsigned = dict(proposal)
            unsigned.pop("proposal_hash", None)
            if not expected or _digest(unsigned) != expected:
                proposal_integrity_failures.append(experiment_id or "unknown")
        factory_integrity_failures = []
        for directory, hash_field, identity_field in (
            (self.factories.threads, "thread_hash", "thread_id"),
            (self.factories.marks, "mark_hash", "mark_id"),
            (self.factories.worlds, "world_hash", "world_id"),
            (self.factories.processing, "receipt_hash", "receipt_id"),
            (self.factories.courier, "receipt_hash", "receipt_id"),
            (self.factories.smelter, "receipt_hash", "receipt_id"),
        ):
            for path in sorted(directory.glob("*.json")):
                try:
                    receipt = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    factory_integrity_failures.append(f"{directory.name}:{path.stem}")
                    continue
                if not isinstance(receipt, dict):
                    factory_integrity_failures.append(f"{directory.name}:{path.stem}")
                    continue
                expected = receipt.get(hash_field, "")
                unsigned = dict(receipt)
                unsigned.pop(hash_field, None)
                if not expected or _digest(unsigned) != expected:
                    identity = str(receipt.get(identity_field, path.stem))
                    factory_integrity_failures.append(f"{directory.name}:{identity}")
        return {
            "status": "VALID" if not invalid and not distillation_mismatch and not distillation_integrity_failures and not proposal_mismatch and not proposal_integrity_failures and not factory_integrity_failures else "INVALID",
            "invalid_record_ids": sorted(invalid),
            "distillation_source_mismatches": sorted(distillation_mismatch),
            "distillation_integrity_failures": sorted(distillation_integrity_failures),
            "proposal_source_mismatches": sorted(proposal_mismatch),
            "proposal_integrity_failures": sorted(proposal_integrity_failures),
            "factory_integrity_failures": sorted(factory_integrity_failures),
            "enforcement": "report_only_no_promotion_authority",
        }

    def _teacher_queue(self, lazy_cat_verdicts: Mapping[str, Mapping[str, Any]] | None = None) -> dict[str, list[dict[str, str]]]:
        """Expose post-execution material; neither queue is an entry gate."""
        verdicts = lazy_cat_verdicts or {}
        proposal_queue = []
        audit_queue = []
        for item in self._proposal_records():
            experiment_id = str(item.get("experiment_id", ""))
            audit = verdicts.get(experiment_id, {})
            verdict = str(audit.get("verdict", "NOT_AUDITED")) if isinstance(audit, Mapping) else "NOT_AUDITED"
            row = {
                "experiment_id": experiment_id,
                "status": str(item.get("status", "PROPOSAL_ONLY")),
                "reason": "human_and_governed_review_required",
            }
            if verdict == "FIT_FOR_TEACHER_REVIEW":
                proposal_queue.append(row)
            else:
                audit_queue.append({
                    "experiment_id": experiment_id,
                    "verdict": verdict,
                    "missing_dimensions": list(audit.get("missing_dimensions", [])) if isinstance(audit, Mapping) else [],
                })
        return {
            "review_queue": proposal_queue,
            "counterexample_queue": [
                {"experiment_id": item["experiment_id"], "status": item["status"], "reason": item["reason"]}
                for item in self._distillation_records()
                if item.get("status") in {"COUNTEREXAMPLE_ONLY", "OPEN_QUESTION", "QUARANTINED"}
            ],
            "lazy_cat_queue": audit_queue,
        }

    def _proposal_ids(self) -> set[str]:
        return {item.get("experiment_id", "") for item in self._proposal_records()}

    def _distillation_ids(self) -> set[str]:
        return {item.get("experiment_id", "") for item in self._distillation_records()}

    @staticmethod
    def _records(directory: Path) -> list[dict[str, Any]]:
        if not directory.exists():
            return []
        records = []
        for path in sorted(directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                if value.get("contract_version") == CONTRACT_VERSION:
                    records.append(value)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return records

    def _proposal_records(self) -> list[dict[str, Any]]:
        return self._records(self.sandbox.proposals)

    def _distillation_records(self) -> list[dict[str, Any]]:
        return self._records(self.sandbox.distillations)

    def _write_report(self, report: dict[str, Any]) -> None:
        self.reports.mkdir(parents=True, exist_ok=True)
        target = self.reports / "sandbox_society_latest.json"
        temporary = target.with_suffix(".json.tmp")
        encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
