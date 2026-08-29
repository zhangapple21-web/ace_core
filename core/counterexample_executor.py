"""Specialized structural counterexample executor for Lazy Cat challenges.

This executor is intentionally narrow.  It does not prove a strategy, market
claim, or recommendation correct.  It tests whether a challenged sandbox
artifact can demonstrate the *missing structural dimensions* named by Lazy
Cat: lineage, bounded method, observable evidence, current boundary witness,
and a real counterexample-world blueprint.

The design borrows the discipline of property/metamorphic testing: name the
property, construct an adversarial check, and preserve the counterexample when
the property fails.  It is sandbox-only and has no production imports.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


CONTRACT_VERSION = "ace.counterexample_executor.v1"
WITNESS_CONTRACT_VERSION = "ace.counterexample_witness.v1"
_BOUNDARY_TARGETS = {"TaskPool", "Runtime", "Advisor", "Risk", "Telegram", "broker", "Experience"}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class StructuralCounterexampleExecutor:
    """Run a bounded, evidence-preserving response to a Lazy Cat challenge."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def execute(
        self,
        *,
        challenge: Mapping[str, Any],
        factory_worlds: list[Mapping[str, Any]],
    ) -> dict[str, Any]:
        challenge_valid = self._valid_challenge(challenge)
        source_id = str(challenge.get("source_experiment_id", ""))
        source = self._source_record(source_id)
        source_hash_valid = self._valid_record(source)
        distillation_link_valid = self._valid_distillation_link(source_id, source)
        manifest = self._read(self.root / "SANDBOX_MANIFEST.json")
        counter_world = next(
            (
                world for world in factory_worlds
                if isinstance(world, Mapping) and world.get("stance") == "COUNTEREXAMPLE_SEARCH"
            ),
            {},
        )
        missing = [str(item) for item in challenge.get("missing_dimensions", []) if str(item).strip()]
        evidence = source.get("evidence") if isinstance(source.get("evidence"), Mapping) else {}
        source_metadata = source.get("metadata") if isinstance(source.get("metadata"), Mapping) else {}
        dimension_proofs = {
            "lineage": source_hash_valid and distillation_link_valid,
            "bounded_method": bool(str(source.get("method", "")).strip()),
            "observable_evidence": bool(evidence),
            # A challenge never edits historical metadata.  It proves the
            # fresh counterexample experiment remains inside the current,
            # explicit sandbox boundary.
            "boundary_intact": (
                manifest.get("production_integration") is False
                and manifest.get("automatic_promotion") is False
                and _BOUNDARY_TARGETS.issubset(set(manifest.get("forbidden_targets", [])))
            ),
            "dissent_blueprint": bool(counter_world.get("world_id")) and counter_world.get("execution_state") == "BLUEPRINT_ONLY",
        }
        requested = {dimension: dimension_proofs.get(dimension, False) for dimension in missing}
        unresolved = sorted(dimension for dimension, proved in requested.items() if not proved)
        preconditions = challenge_valid and bool(source) and source_hash_valid and distillation_link_valid
        if not preconditions:
            outcome = "FAIL"
        elif unresolved:
            outcome = "INCONCLUSIVE"
        else:
            outcome = "PASS"
        # The executor can complete a *structural* adversarial check, but it
        # never observes a market outcome or a claim-level counterexample.
        # Therefore a passing structural turn means only that the named
        # structural rule was not falsified within this explicit scope.
        witness_outcome = "NOT_FALSIFIED_WITHIN_SCOPE" if outcome == "PASS" else "INCONCLUSIVE"
        return {
            "outcome": outcome,
            "evidence": {
                "contract_version": CONTRACT_VERSION,
                "challenge_id": challenge.get("challenge_id"),
                "source_experiment_id": source_id,
                "challenge_hash_valid": challenge_valid,
                "source_record_hash_valid": source_hash_valid,
                "source_distillation_link_valid": distillation_link_valid,
                "requested_dimensions": sorted(requested),
                "dimension_proofs": requested,
                "unresolved_dimensions": unresolved,
                "counterexample_world_id": counter_world.get("world_id"),
                "counterexample_world_state": counter_world.get("execution_state"),
                "source_metadata_present": bool(source_metadata),
                "scope": "STRUCTURAL_COUNTEREXAMPLE_ONLY",
                "claim_truth_assessed": False,
                "market_or_production_assessed": False,
                "source_payload_retained": False,
                "counterexample_witness": {
                    "contract_version": WITNESS_CONTRACT_VERSION,
                    "challenged_property": "named_sandbox_research_dimensions_are_observable_and_bounded",
                    "adversarial_case": {
                        "challenge_hash": challenge.get("challenge_hash"),
                        "requested_dimensions": sorted(requested),
                        "counterexample_world_id": counter_world.get("world_id"),
                    },
                    "expected_rule": {
                        "source_record_and_distillation_integrity": True,
                        "all_requested_dimensions_proved": True,
                        "selected_world_stance": "COUNTEREXAMPLE_SEARCH",
                    },
                    "observed_result": {
                        "preconditions_satisfied": preconditions,
                        "dimension_proofs": requested,
                        "unresolved_dimensions": unresolved,
                    },
                    "outcome": witness_outcome,
                    "receipt_refs": {
                        "challenge_id": challenge.get("challenge_id"),
                        "source_experiment_id": source_id,
                        "source_record_hash": source.get("record_hash"),
                        "source_distillation_hash": self._distillation_hash(source_id),
                    },
                    "replay_recipe": {
                        "executor_contract_version": CONTRACT_VERSION,
                        "replay_inputs": ["signed_challenge", "signed_source_record", "linked_distillation", "counterexample_world_blueprint"],
                        "selected_world_stance": "COUNTEREXAMPLE_SEARCH",
                    },
                    "scope_limits": [
                        "structural_sandbox_artifact_only",
                        "no_claim_truth_assessment",
                        "no_market_or_production_assessment",
                    ],
                    "production_integration": False,
                },
            },
        }

    def _source_record(self, experiment_id: str) -> dict[str, Any]:
        for directory in (self.root / "experiments", self.root / "quarantine"):
            value = self._read(directory / f"{experiment_id}.json")
            if value:
                return value
        return {}

    def _valid_distillation_link(self, experiment_id: str, record: Mapping[str, Any]) -> bool:
        value = self._read(self.root / "distillations" / f"{experiment_id}.json")
        return bool(value) and value.get("source_record_hash") == record.get("record_hash")

    def _distillation_hash(self, experiment_id: str) -> str | None:
        value = self._read(self.root / "distillations" / f"{experiment_id}.json")
        digest = value.get("distillation_hash") if value else None
        return str(digest) if digest else None

    @staticmethod
    def _valid_challenge(value: Mapping[str, Any]) -> bool:
        expected = str(value.get("challenge_hash", ""))
        unsigned = {key: item for key, item in value.items() if key != "challenge_hash"}
        return bool(expected) and _digest(unsigned) == expected

    @staticmethod
    def _valid_record(value: Mapping[str, Any]) -> bool:
        if not value:
            return False
        expected = str(value.get("record_hash", ""))
        unsigned = {key: item for key, item in value.items() if key != "record_hash"}
        return bool(expected) and _digest(unsigned) == expected

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return dict(value) if isinstance(value, Mapping) else {}
