"""A provenance-preserving, sandbox-only semantic learning seed.

The contract captures an observed transferable mechanism without treating the
source as a production authority. A seed may be created from one source, but
stays ``PENDING`` until later independent evidence is supplied through the
existing governed path. It owns no scheduler, task, model, or promotion right.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


CONTRACT_VERSION = "ace.semantic_seed.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_TEXT_FIELDS = (
    "source_ref", "source_snapshot_hash", "source_kind", "extracted_mechanism",
    "ace_symptom", "transfer_hypothesis", "counterexample_question", "next_verification",
)


class SemanticSeedError(ValueError):
    """The provided sandbox seed is not structurally usable."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Mapping[str, Any], field: str) -> str:
    result = value.get(field)
    if not isinstance(result, str) or not result.strip():
        raise SemanticSeedError(f"{field} is required")
    return result.strip()


def _refs(value: Mapping[str, Any], field: str) -> list[str]:
    raw = value.get(field, [])
    if not isinstance(raw, list) or not all(isinstance(item, str) and item.strip() for item in raw):
        raise SemanticSeedError(f"{field} must be a list of non-empty strings")
    return list(dict.fromkeys(item.strip() for item in raw))


def normalize_semantic_seed(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize a seed without fetching its source or taking action."""
    if not isinstance(value, Mapping):
        raise SemanticSeedError("semantic seed must be a mapping")
    if value.get("contract_version") != CONTRACT_VERSION:
        raise SemanticSeedError("unsupported semantic seed contract_version")
    snapshot_hash = _text(value, "source_snapshot_hash")
    if not _SHA256.fullmatch(snapshot_hash):
        raise SemanticSeedError("source_snapshot_hash must be a lowercase sha256 digest")
    normalized = {
        "contract_version": CONTRACT_VERSION,
        **{field: _text(value, field) for field in _TEXT_FIELDS},
        "local_evidence_refs": _refs(value, "local_evidence_refs"),
        "external_evidence_refs": _refs(value, "external_evidence_refs"),
        "lineage": _refs(value, "lineage"),
        "status": "PENDING",
        "consumption_mode": "sandbox_report_only",
        "source_evidence_weight": "UNASSESSED",
        # Reference groups preserve provenance only. Their count cannot prove
        # independence; the existing governed admission path must determine it.
        "independent_evidence_status": "NOT_ASSESSED",
        "production_integration": False,
        "taskpool_authority": False,
        "automatic_model_call": False,
        "automatic_promotion": False,
    }
    normalized["seed_hash"] = _digest(normalized)
    return normalized
