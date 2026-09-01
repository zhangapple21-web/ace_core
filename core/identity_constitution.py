"""Portable identity constitutions with explicit, evidence-bound variation.

The contract is deliberately smaller than a personality system.  It separates
non-negotiable identity boundaries from fields that may evolve when a source
is recorded.  The result is an attestation/report, never a permission grant.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


FREE_ZONE_CONTEXTUAL_CONSTITUTION = {
    "contract_version": "ace.identity_constitution.v1",
    "identity_id": "ACE_FREE_ZONE_CONTEXTUAL_RESEARCH",
    "scope": "FREE_ZONE_RESEARCH_ONLY",
    "invariants": {
        "scope": "FREE_ZONE_RESEARCH_ONLY",
        "production_integration": False,
        "side_effects": {
            "task_created": False,
            "model_called": False,
            "production_runtime_mutation": False,
        },
    },
    "allowed_variant_fields": [
        "question",
        "active_hypotheses",
        "retracted_hypotheses",
        "learning_needs",
        "relevant_facts",
        "relevant_relations",
    ],
    "forbidden_change_meaning": {
        "scope": "A research packet cannot silently become an ACE Reality packet.",
        "production_integration": "Research cannot grant production authority.",
        "side_effects": "Context assembly cannot create work, call a model, or mutate runtime.",
    },
}


class IdentityConstitution:
    """Validate stable identity separately from allowed contextual evolution."""

    def __init__(self, definition: Mapping[str, Any]) -> None:
        if not isinstance(definition, Mapping):
            raise ValueError("constitution must be a mapping")
        required = {"contract_version", "identity_id", "scope", "invariants", "allowed_variant_fields", "forbidden_change_meaning"}
        if set(definition) != required:
            raise ValueError("constitution has missing or unknown fields")
        if definition.get("contract_version") != "ace.identity_constitution.v1":
            raise ValueError("unsupported constitution contract")
        if not isinstance(definition.get("identity_id"), str) or not definition["identity_id"].strip():
            raise ValueError("identity_id is required")
        if not isinstance(definition.get("invariants"), Mapping) or not definition["invariants"]:
            raise ValueError("invariants are required")
        variants = definition.get("allowed_variant_fields")
        if not isinstance(variants, list) or not variants or not all(isinstance(item, str) and item.strip() for item in variants):
            raise ValueError("allowed_variant_fields are required")
        self.definition = json.loads(json.dumps(definition, ensure_ascii=False, sort_keys=True))
        self.constitution_hash = _digest(self.definition)

    def attest(self, subject: Mapping[str, Any]) -> dict[str, Any]:
        violations = self._invariant_violations(subject)
        return {
            "contract_version": "ace.identity_attestation.v1",
            "identity_id": self.definition["identity_id"],
            "constitution_hash": self.constitution_hash,
            "status": "IDENTITY_ATTESTED" if not violations else "IDENTITY_DRIFT_BLOCKED",
            "invariant_violations": violations,
            "allowed_variant_fields": list(self.definition["allowed_variant_fields"]),
            "production_authority": False,
        }

    def compare(
        self,
        baseline: Mapping[str, Any],
        candidate: Mapping[str, Any],
        *,
        evidence_refs: list[str],
    ) -> dict[str, Any]:
        baseline_attestation = self.attest(baseline)
        candidate_attestation = self.attest(candidate)
        violations = sorted(set(baseline_attestation["invariant_violations"]) | set(candidate_attestation["invariant_violations"]))
        allowed = set(self.definition["allowed_variant_fields"])
        changed = sorted(
            key for key in allowed
            if baseline.get(key) != candidate.get(key)
        )
        refs = sorted({item.strip() for item in evidence_refs if isinstance(item, str) and item.strip()})
        if violations:
            status = "IDENTITY_DRIFT_BLOCKED"
        elif changed and not refs:
            status = "VARIANT_UNATTESTED"
        elif changed:
            status = "ALLOWED_VARIANT"
        else:
            status = "IDENTITY_STABLE"
        return {
            "contract_version": "ace.identity_drift_report.v1",
            "identity_id": self.definition["identity_id"],
            "constitution_hash": self.constitution_hash,
            "status": status,
            "invariant_violations": violations,
            "changed_variant_fields": changed,
            "evidence_refs": refs,
            "production_authority": False,
        }

    def _invariant_violations(self, subject: Mapping[str, Any]) -> list[str]:
        if not isinstance(subject, Mapping):
            return sorted(self.definition["invariants"])
        return sorted(
            key for key, expected in self.definition["invariants"].items()
            if subject.get(key) != expected
        )
