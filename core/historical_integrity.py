"""Report-only registry for known historical integrity anomalies.

An entry in this registry labels an old artifact for archaeology; it never
turns a failed hash check into a valid record and never grants promotion or
production authority.  The registry is deliberately separate from the
append-only sandbox artifacts so a repair cannot rewrite history.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.historical_integrity_registry.v1"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def build_declaration(
    *,
    anomaly_id: str,
    artifact_path: str,
    artifact_id: str,
    stored_hash: str,
    recomputed_hash: str,
    observed_at: str,
    reason: str,
    source_record_hash: str,
    evidence_refs: Sequence[str],
) -> dict[str, Any]:
    """Build a hash-bound, non-suppressing historical anomaly declaration."""

    text_fields = {
        "anomaly_id": anomaly_id,
        "artifact_path": artifact_path,
        "artifact_id": artifact_id,
        "observed_at": observed_at,
        "reason": reason,
        "source_record_hash": source_record_hash,
    }
    for field, value in text_fields.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field}_required")
    if not isinstance(stored_hash, str) or not _SHA256.fullmatch(stored_hash):
        raise ValueError("stored_hash_must_be_sha256")
    if not isinstance(recomputed_hash, str) or not _SHA256.fullmatch(recomputed_hash):
        raise ValueError("recomputed_hash_must_be_sha256")
    if stored_hash == recomputed_hash:
        raise ValueError("declaration_requires_hash_mismatch")
    if not isinstance(evidence_refs, (list, tuple)) or not evidence_refs or any(not isinstance(item, str) or not item.strip() for item in evidence_refs):
        raise ValueError("evidence_refs_required")
    if len(set(evidence_refs)) != len(evidence_refs):
        raise ValueError("evidence_refs_must_be_unique")

    declaration = {
        "contract_version": CONTRACT_VERSION,
        "mode": "HISTORICAL_ARCHAEOLOGY_ONLY",
        "anomaly_id": anomaly_id.strip(),
        "artifact_path": artifact_path.strip(),
        "artifact_id": artifact_id.strip(),
        "classification": "ARCHIVED_INVALID_HERITAGE",
        "stored_hash": stored_hash,
        "recomputed_hash": recomputed_hash,
        "observed_at": observed_at.strip(),
        "reason": reason.strip(),
        "source_record_hash": source_record_hash.strip(),
        "evidence_refs": list(evidence_refs),
        "court_policy": "continue_reporting_invalid; do_not_suppress_hash_failure",
        "skip_court_validation": False,
        "promotion_eligible": False,
        "production_integration": False,
        "append_only": True,
    }
    declaration["declaration_hash"] = digest(declaration)
    return declaration


def validate_declaration(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a declaration and return a plain copy."""

    if not isinstance(value, Mapping) or value.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("unsupported_historical_integrity_declaration")
    required = ("anomaly_id", "artifact_path", "artifact_id", "classification", "stored_hash", "recomputed_hash", "observed_at", "reason", "source_record_hash", "evidence_refs", "declaration_hash")
    if any(not value.get(key) for key in required):
        raise ValueError("incomplete_historical_integrity_declaration")
    if value.get("classification") != "ARCHIVED_INVALID_HERITAGE":
        raise ValueError("invalid_historical_classification")
    if value.get("skip_court_validation") is not False or value.get("promotion_eligible") is not False or value.get("production_integration") is not False:
        raise ValueError("historical_declaration_must_not_grant_authority")
    for key in ("stored_hash", "recomputed_hash", "source_record_hash"):
        if not isinstance(value.get(key), str) or not _SHA256.fullmatch(value[key]):
            raise ValueError(f"{key}_must_be_sha256")
    if value["stored_hash"] == value["recomputed_hash"]:
        raise ValueError("declaration_requires_hash_mismatch")
    if not isinstance(value.get("evidence_refs"), list) or not value["evidence_refs"]:
        raise ValueError("evidence_refs_required")
    unsigned = dict(value)
    expected = unsigned.pop("declaration_hash", None)
    if expected != digest(unsigned):
        raise ValueError("historical_declaration_hash_mismatch")
    return dict(value)


def load_declarations(directory: str | Path) -> list[dict[str, Any]]:
    """Load valid declarations; malformed entries remain visible as errors."""

    directory = Path(directory)
    result = []
    for path in sorted(directory.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        result.append(validate_declaration(value))
    return result

