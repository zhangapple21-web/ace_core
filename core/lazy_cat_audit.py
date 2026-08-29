"""Post-execution fitness audit for the ACE free-zone ecology.

The free zone is a productive cat: it creates and runs bounded experiments.
Lazy Cat is deliberately post-hoc: it does not approve intake, select a
candidate, or alter an experiment.  It rates the *research shape* after
distillation and returns weak shapes as new, traceable challenges.

Fitness is not a claim that an experiment is true, profitable, or ready for
production.  It only answers whether the sandbox artifact is complete enough
to be worth a teacher's separate review.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


CONTRACT_VERSION = "ace.lazy_cat_audit.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class LazyCatAudit:
    """Judge completed sandbox shapes and return deficiencies as food."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.audit_root = self.root / "lazy_cat"
        self.verdicts = self.audit_root / "verdicts"
        self.challenges = self.audit_root / "challenges"
        self.challenge_probes = self.audit_root / "challenge_probes"

    def initialize(self) -> None:
        self.verdicts.mkdir(parents=True, exist_ok=True)
        self.challenges.mkdir(parents=True, exist_ok=True)
        self.challenge_probes.mkdir(parents=True, exist_ok=True)

    def audit_all(
        self,
        *,
        records: list[Mapping[str, Any]],
        distillations: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        """Audit all complete material; never affects free-zone intake."""
        self.initialize()
        record_map = {str(item.get("experiment_id", "")): item for item in records if item.get("experiment_id")}
        new_verdict_ids: list[str] = []
        new_challenge_ids: list[str] = []
        for distillation in distillations:
            experiment_id = str(distillation.get("experiment_id", ""))
            if not experiment_id or experiment_id not in record_map:
                continue
            path = self.verdicts / f"{experiment_id}.json"
            if path.exists():
                continue
            verdict, challenge = self._assess(record_map[experiment_id], distillation)
            self._append(path, verdict)
            new_verdict_ids.append(verdict["verdict_id"])
            if challenge is not None:
                self._append(self.challenges / f"{challenge['challenge_id']}.json", challenge)
                new_challenge_ids.append(challenge["challenge_id"])
        all_verdicts = self._records(self.verdicts)
        return {
            "contract_version": CONTRACT_VERSION,
            "mode": "POST_EXECUTION_FITNESS_AUDIT",
            "new_verdict_ids": new_verdict_ids,
            "new_challenge_ids": new_challenge_ids,
            "fit_for_teacher_review_count": sum(item.get("verdict") == "FIT_FOR_TEACHER_REVIEW" for item in all_verdicts),
            "return_to_free_zone_count": sum(item.get("verdict") == "RETURN_TO_FREE_ZONE" for item in all_verdicts),
            "total_verdict_count": len(all_verdicts),
            "pending_challenge_count": len(self.pending_challenges()),
            "production_integration": False,
            "may_block_free_zone": False,
            "may_approve_production": False,
        }

    def verdict_by_experiment(self) -> dict[str, dict[str, Any]]:
        self.initialize()
        return {
            str(item["experiment_id"]): item
            for item in self._records(self.verdicts)
            if item.get("experiment_id")
        }

    def pending_challenges(self) -> list[dict[str, Any]]:
        self.initialize()
        latest = self._latest_probe_by_challenge()
        pending = []
        for challenge in self._records(self.challenges):
            challenge_id = str(challenge.get("challenge_id", ""))
            probe = latest.get(challenge_id, {})
            probe_state = str(probe.get("state", ""))
            if probe_state in {"PROBE_COMPLETED_WITHIN_SCOPE", "COUNTEREXAMPLE_OBSERVED"}:
                continue
            # Do not annotate this signed record with runtime state.  The
            # challenge hash covers every field except ``challenge_hash``;
            # callers need an untouched mapping for integrity verification.
            pending.append(dict(challenge))
        return pending

    def next_challenge_attempt(self, challenge_id: str) -> int:
        """Return an allocation label without changing the signed challenge."""
        self.initialize()
        probe = self._latest_probe_by_challenge().get(str(challenge_id), {})
        return int(probe.get("attempt", 0)) + 1 if probe else 1

    def record_challenge_probe(
        self,
        *,
        challenge: Mapping[str, Any],
        experiment_id: str,
        experiment_outcome: str,
        evidence: Mapping[str, Any],
        processing_receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Append the post-execution state of a challenge without deleting it.

        A completion receipt is not a quality verdict and cannot close the
        free-zone entrance.  It merely distinguishes completed, explicitly
        bounded probes from inputs that still need another experiment.  The
        original challenge stays immutable and can be re-opened by a later
        audit with a new challenge id.
        """
        self.initialize()
        challenge_id = str(challenge.get("challenge_id", ""))
        if not challenge_id or not experiment_id:
            raise ValueError("challenge_id and experiment_id are required")
        witness = evidence.get("counterexample_witness") if isinstance(evidence.get("counterexample_witness"), Mapping) else {}
        witness_outcome = str(witness.get("outcome", ""))
        if witness_outcome == "FALSIFIED":
            state = "COUNTEREXAMPLE_OBSERVED"
        elif witness_outcome == "NOT_FALSIFIED_WITHIN_SCOPE":
            state = "PROBE_COMPLETED_WITHIN_SCOPE"
        else:
            state = "NEEDS_ANOTHER_PROBE"
        prior = self._latest_probe_by_challenge().get(challenge_id, {})
        attempt = int(prior.get("attempt", 0)) + 1 if prior else 1
        record = {
            "contract_version": CONTRACT_VERSION,
            "probe_id": f"LAZY-CAT-PROBE-{challenge_id}-{experiment_id}",
            "recorded_at": _now(),
            "role": "lazy_cat_post_execution_tracker",
            "challenge_id": challenge_id,
            "source_experiment_id": challenge.get("source_experiment_id"),
            "probe_experiment_id": experiment_id,
            "attempt": attempt,
            "state": state,
            "experiment_outcome": experiment_outcome,
            "witness_outcome": witness_outcome or None,
            "source_record_hash": evidence.get("source_record_hash_valid"),
            "processing_receipt_id": processing_receipt.get("receipt_id"),
            "processing_receipt_hash": processing_receipt.get("receipt_hash"),
            "production_integration": False,
            "probe_hash": "",
        }
        record["probe_hash"] = _digest({key: value for key, value in record.items() if key != "probe_hash"})
        return self._append(self.challenge_probes / f"{record['probe_id']}.json", record)

    def reconcile_challenge_probes(self, *, records: list[Mapping[str, Any]]) -> dict[str, Any]:
        """Backfill only status receipts for legacy completed challenge probes.

        The historical experiment records are not rewritten.  A legacy probe
        without a CounterexampleWitness/v1 stays open rather than being
        silently treated as complete.
        """
        self.initialize()
        existing_probe_experiments = {
            str(item.get("probe_experiment_id", ""))
            for item in self._records(self.challenge_probes)
            if item.get("probe_experiment_id")
        }
        created = []
        for record in records:
            metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
            evidence = record.get("evidence") if isinstance(record.get("evidence"), Mapping) else {}
            if metadata.get("source_kind") != "lazy_cat_challenge":
                continue
            experiment_id = str(record.get("experiment_id", ""))
            if not experiment_id or experiment_id in existing_probe_experiments:
                continue
            challenge_id = str(evidence.get("challenge_id", ""))
            if not challenge_id:
                continue
            challenge = {"challenge_id": challenge_id, "source_experiment_id": evidence.get("source_experiment_id")}
            process = self._read_processing_receipt(experiment_id)
            probe = self.record_challenge_probe(
                challenge=challenge,
                experiment_id=experiment_id,
                experiment_outcome=str(record.get("outcome", "INCONCLUSIVE")),
                evidence=evidence,
                processing_receipt=process,
            )
            created.append(probe["probe_id"])
        return {
            "legacy_probe_receipts_created": created,
            "pending_challenge_count": len(self.pending_challenges()),
            "production_integration": False,
        }

    def _assess(self, record: Mapping[str, Any], distillation: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any] | None]:
        experiment_id = str(record["experiment_id"])
        metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
        evidence = record.get("evidence") if isinstance(record.get("evidence"), Mapping) else {}
        source_kind = str(metadata.get("source_kind", ""))
        checks = {
            "lineage": bool(record.get("record_hash")) and distillation.get("source_record_hash") == record.get("record_hash"),
            "bounded_method": bool(str(record.get("method", "")).strip()),
            "observable_evidence": bool(evidence),
            "boundary_intact": metadata.get("production_integration") is False,
            "dissent_blueprint": bool(metadata.get("factory_thread_id")) and bool(metadata.get("factory_world_id")),
        }
        if source_kind == "lazy_cat_challenge":
            witness = evidence.get("counterexample_witness") if isinstance(evidence.get("counterexample_witness"), Mapping) else {}
            checks["counterexample_scope"] = (
                evidence.get("scope") == "STRUCTURAL_COUNTEREXAMPLE_ONLY"
                and evidence.get("claim_truth_assessed") is False
                and evidence.get("market_or_production_assessed") is False
            )
            checks["counterexample_witness"] = (
                witness.get("contract_version") == "ace.counterexample_witness.v1"
                and witness.get("outcome") in {"FALSIFIED", "NOT_FALSIFIED_WITHIN_SCOPE", "INCONCLUSIVE"}
                and bool(witness.get("challenged_property"))
                and isinstance(witness.get("adversarial_case"), Mapping)
                and isinstance(witness.get("expected_rule"), Mapping)
                and isinstance(witness.get("observed_result"), Mapping)
                and isinstance(witness.get("receipt_refs"), Mapping)
                and isinstance(witness.get("replay_recipe"), Mapping)
                and bool(witness.get("scope_limits"))
                and witness.get("production_integration") is False
            )
        missing = sorted(name for name, passed in checks.items() if not passed)
        if not missing:
            verdict_name = "FIT_FOR_TEACHER_REVIEW"
        elif source_kind == "lazy_cat_challenge":
            verdict_name = "OPEN_CHALLENGE_RETAINED"
        else:
            verdict_name = "RETURN_TO_FREE_ZONE"
        verdict = {
            "contract_version": CONTRACT_VERSION,
            "verdict_id": f"LAZY-CAT-{experiment_id}",
            "recorded_at": _now(),
            "role": "lazy_cat_post_execution_auditor",
            "experiment_id": experiment_id,
            "distillation_status": distillation.get("status"),
            "checks": checks,
            "missing_dimensions": missing,
            "verdict": verdict_name,
            "meaning": (
                "research_shape_fit_for_teacher_review_not_production_approval"
                if verdict_name == "FIT_FOR_TEACHER_REVIEW"
                else (
                    "open_challenge_retained_until_a_specialized_resolution_probe_exists"
                    if verdict_name == "OPEN_CHALLENGE_RETAINED"
                    else "return_deficient_research_shape_to_free_zone_without_erasing_it"
                )
            ),
            "production_integration": False,
            "verdict_hash": "",
        }
        verdict["verdict_hash"] = _digest({key: value for key, value in verdict.items() if key != "verdict_hash"})
        if verdict_name != "RETURN_TO_FREE_ZONE":
            return verdict, None
        challenge = {
            "contract_version": CONTRACT_VERSION,
            "challenge_id": f"CHALLENGE-{experiment_id}",
            "created_at": _now(),
            "source_experiment_id": experiment_id,
            "source_verdict_id": verdict["verdict_id"],
            "missing_dimensions": missing,
            "question": f"What bounded free-zone probe can repair or explicitly delimit the missing dimensions of {experiment_id}: {', '.join(missing)}?",
            "method": "Preserve the original artifact, address only the named missing dimensions, and record a separate result without changing production state.",
            "production_integration": False,
            "challenge_hash": "",
        }
        challenge["challenge_hash"] = _digest({key: value for key, value in challenge.items() if key != "challenge_hash"})
        return verdict, challenge

    @staticmethod
    def _records(directory: Path) -> list[dict[str, Any]]:
        if not directory.exists():
            return []
        values = []
        for path in sorted(directory.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                values.append(value)
        return values

    def _latest_probe_by_challenge(self) -> dict[str, dict[str, Any]]:
        latest: dict[str, dict[str, Any]] = {}
        for probe in self._records(self.challenge_probes):
            challenge_id = str(probe.get("challenge_id", ""))
            if not challenge_id:
                continue
            prior = latest.get(challenge_id)
            if prior is None or (int(probe.get("attempt", 0)), str(probe.get("recorded_at", ""))) > (int(prior.get("attempt", 0)), str(prior.get("recorded_at", ""))):
                latest[challenge_id] = probe
        return latest

    def _read_processing_receipt(self, experiment_id: str) -> dict[str, Any]:
        path = self.root / "factories" / "processing" / f"{experiment_id}.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _append(path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
        record = dict(value)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                return existing
            raise ValueError(f"lazy cat record is not a mapping: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        encoded = json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return record
