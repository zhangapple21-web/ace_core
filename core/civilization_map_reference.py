"""Minimal ACE civilization-map references and admission identity helpers.

This is not a datastore and does not replace any Memory, Task, Domain, or
Runtime authority. It gives the ACE motherplate stable references to objects
owned elsewhere and prevents source-only admission folding.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

SCHEMA_VERSION = "ace.civilization-map-reference.v1"
RELATION_TYPES = {"belongs_to", "derived_from", "depends_on", "verified_by", "routes_to", "supersedes", "projects", "copies", "mounted_on"}
STATES = {"current", "candidate", "experiment", "frozen", "archived", "unknown"}
ROLES = {"authority", "projection", "index", "cache", "recovery_copy", "runtime"}


def canonical_object_id(namespace: str, local_identity: str) -> str:
    ns = str(namespace or "").strip()
    local = str(local_identity or "").strip()
    if not ns or not local:
        raise ValueError("canonical_identity_requires_namespace_and_local_identity")
    digest = hashlib.sha256(f"{ns}\0{local}".encode("utf-8")).hexdigest()[:24]
    return f"ace:{ns}:{digest}"


def json_line(value: Mapping[str, Any]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(json_line(value).encode("utf-8")).hexdigest()


def admission_envelope(admission: Mapping[str, Any], *, title: str) -> dict[str, Any]:
    """Build identity + intent metadata; legacy omissions are marked derived."""
    source_type = str(admission.get("source_type") or "unknown").strip()
    source_ref = str(admission.get("source_ref") or "").strip()
    source_identity = str(
        admission.get("source_identity")
        or admission.get("canonical_object_id")
        or admission.get("source_fingerprint")
        or source_ref
    ).strip()
    object_id = str(admission.get("canonical_object_id") or canonical_object_id(f"source:{source_type}", source_identity))
    explicit_intent = admission.get("intent_derivation") == "explicit" or (
        "intent_derivation" not in admission and bool(admission.get("operation_intent") or admission.get("intent"))
    )
    explicit_payload = admission.get("payload_derivation") == "explicit" or (
        "payload_derivation" not in admission and (admission.get("payload") is not None or admission.get("payload_hash") is not None)
    )
    explicit_token = admission.get("token_derivation") == "explicit" or (
        "token_derivation" not in admission and bool(admission.get("idempotency_token"))
    )
    intent = str(admission.get("operation_intent") or admission.get("intent") or "admit").strip()
    payload = admission.get("payload")
    if payload is None:
        payload = {"title": str(title), "hypothesis": admission.get("hypothesis", "")}
    payload_hash = str(admission.get("payload_hash") or _stable_hash(payload))
    token = str(admission.get("idempotency_token") or "").strip()
    if not token:
        token = "derived:" + _stable_hash({"object": object_id, "intent": intent, "payload": payload_hash})[:32]
    return {
        "schema_version": SCHEMA_VERSION,
        "canonical_object_id": object_id,
        "source_identity": source_identity,
        "payload_hash": payload_hash,
        "operation_intent": intent,
        "idempotency_token": token,
        "admission_generation": int(admission.get("admission_generation") or 1),
        "identity_derivation": "explicit" if admission.get("canonical_object_id") else "derived",
        "intent_derivation": "explicit" if explicit_intent else "derived",
        "payload_derivation": "explicit" if explicit_payload else "derived",
        "token_derivation": "explicit" if explicit_token else "derived",
    }


def same_admission_intent(existing: Any, admission: Mapping[str, Any], *, title: str) -> bool:
    """Fold only identical explicit requests; preserve legacy source folding."""
    existing_outputs = getattr(existing, "outputs", {}) or {}
    existing_admission = existing_outputs.get("admission", {}) if isinstance(existing_outputs, Mapping) else {}
    existing_title = str(getattr(existing, "title", ""))
    current = admission_envelope(admission, title=title)
    prior = admission_envelope(existing_admission, title=existing_title)
    legacy = all(
        prior.get(key) == "derived" and current.get(key) == "derived"
        for key in ("intent_derivation", "payload_derivation", "token_derivation")
    )
    if legacy:
        return prior["canonical_object_id"] == current["canonical_object_id"]
    return prior == current


@dataclass(frozen=True)
class MapObjectRef:
    object_id: str
    namespace: str
    local_identity: str
    world: str
    authority: str
    role: str = "authority"
    state: str = "unknown"
    source: Optional[str] = None
    lineage: tuple[str, ...] = field(default_factory=tuple)
    capability_addresses: tuple[str, ...] = field(default_factory=tuple)
    projections: tuple[str, ...] = field(default_factory=tuple)
    copies: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.object_id or not self.namespace or not self.local_identity:
            raise ValueError("map_object_identity_required")
        if self.role not in ROLES:
            raise ValueError(f"map_object_role_invalid:{self.role}")
        if self.state not in STATES:
            raise ValueError(f"map_object_state_invalid:{self.state}")
        if not self.authority:
            raise ValueError("map_object_authority_required")

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in ("lineage", "capability_addresses", "projections", "copies"):
            value[key] = list(value[key])
        value["schema_version"] = SCHEMA_VERSION
        return value


@dataclass(frozen=True)
class MapRelation:
    from_id: str
    relation: str
    to_id: str
    source: str
    confidence: str = "observed"

    def __post_init__(self) -> None:
        if self.relation not in RELATION_TYPES:
            raise ValueError(f"map_relation_invalid:{self.relation}")
        if not self.from_id or not self.to_id or not self.source:
            raise ValueError("map_relation_ids_and_source_required")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}


def validate_projection(ref: MapObjectRef, authority_id: str) -> None:
    if ref.role in {"projection", "index", "cache", "recovery_copy"}:
        if authority_id not in ref.lineage and authority_id not in ref.projections:
            raise ValueError("projection_authority_pointer_required")
