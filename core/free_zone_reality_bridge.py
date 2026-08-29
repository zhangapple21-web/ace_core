"""Explicit, hash-bound translation from Free Zone learning into ACE reality.

The bridge lives outside both autonomous loops.  It reads exactly one named
Free Zone distillation and writes one ACE-side research receipt.  It never
creates TaskPool work, calls a model, changes the daemon, grants recommendation
authority, or treats a Free Zone outcome as a production fact.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


CONTRACT_VERSION = "ace.free_zone_reality_bridge.v1"
SOURCE_CONTRACT_VERSION = "ace.free_research_sandbox.v1"
EPISTEMIC_STATES = frozenset({"FACT", "INFERENCE", "HYPOTHESIS", "UNKNOWN"})
REVIEW_DECISIONS = frozenset({"ACCEPT_FOR_RESEARCH", "HOLD_FOR_EVIDENCE", "REJECT"})
MAPPING_FIELDS = frozenset(
    {
        "mapping_id",
        "epistemic_status",
        "observation",
        "learning",
        "reality_scope",
        "research_question",
        "expected_result",
        "verification_method",
        "constraints",
        "evidence_refs",
        "ace_review",
    }
)
EVIDENCE_FIELDS = frozenset({"ref", "independence_group", "kind"})
REVIEW_FIELDS = frozenset({"decision", "reviewer", "review_basis"})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_copy(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True))


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


class FreeZoneRealityBridge:
    """Create immutable ACE research receipts from explicitly named learning."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        sandbox_root: str | Path | None = None,
        receipt_dir: str | Path | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.sandbox_root = Path(
            sandbox_root or self.workspace_root / "07_SANDBOX" / "free_research"
        ).resolve()
        self.receipt_dir = Path(
            receipt_dir
            or self.workspace_root / "08_GOVERNANCE" / "free_zone_bridge" / "receipts"
        ).resolve()
        if not _is_within(self.sandbox_root, self.workspace_root):
            raise ValueError("sandbox_root must stay inside the workspace")
        if not _is_within(self.receipt_dir, self.workspace_root):
            raise ValueError("receipt_dir must stay inside the workspace")

    def receipt_path(self, bridge_id: str) -> Path:
        normalized = str(bridge_id).strip()
        if not normalized.startswith("BRIDGE-") or not normalized[7:].isalnum():
            raise ValueError("invalid bridge_id")
        return self.receipt_dir / f"{normalized}.json"

    def build(self, source_path: str | Path, mapping: Mapping[str, Any]) -> dict[str, Any]:
        """Map one distillation to ACE research without invoking ACE Admission."""
        normalized_mapping, review, evidence_refs = self._validate_mapping(mapping)
        source = self._validate_source(source_path)
        evidence = self._validate_evidence_refs(evidence_refs)

        decision = review["decision"]
        if decision == "ACCEPT_FOR_RESEARCH":
            if review["reviewer"] != "main_steward":
                raise ValueError("fresh main-steward review required")
            if source["pollution_flags"] or source["learning_status"] == "QUARANTINED":
                raise ValueError("polluted source cannot be accepted into ACE research")
            if evidence["independent_count"] < 2:
                raise ValueError("independent evidence groups required")
            disposition_status = "ACCEPTED_REALITY_RESEARCH"
        elif decision == "HOLD_FOR_EVIDENCE":
            disposition_status = "MAPPED_SHADOW"
        else:
            disposition_status = "REJECTED"

        identity = {
            "contract_version": CONTRACT_VERSION,
            "source": source,
            "mapping": normalized_mapping,
            "evidence": evidence,
            "ace_review": review,
            "disposition_status": disposition_status,
        }
        bridge_id = f"BRIDGE-{_digest(identity)[:24].upper()}"
        destination = self.receipt_path(bridge_id)
        existing = self._read_existing(destination)
        if existing is not None:
            return existing

        receipt = {
            "contract_version": CONTRACT_VERSION,
            "bridge_id": bridge_id,
            "created_at": _utc_now(),
            "source_realm": "FREE_ZONE",
            "destination_realm": "ACE_REALITY",
            "source": source,
            "mapping": normalized_mapping,
            "evidence": evidence,
            "ace_review": review,
            "disposition": {
                "status": disposition_status,
                "task_created": False,
                "model_call": False,
                "production_runtime_mutation": False,
                "admission_bypassed": False,
                "recommendation_authority": False,
                "next_gate": "EXISTING_ACE_ADMISSION_OR_EXPERIENCE_REVIEW",
            },
        }
        receipt["receipt_hash"] = _digest(receipt)
        self._write_once(destination, receipt)
        return self._read_existing(destination) or receipt

    def _validate_mapping(
        self, mapping: Mapping[str, Any]
    ) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, str]]]:
        if not isinstance(mapping, Mapping) or set(mapping) != MAPPING_FIELDS:
            raise ValueError("mapping has missing or unknown fields")
        for key in (
            "mapping_id",
            "observation",
            "learning",
            "reality_scope",
            "research_question",
            "expected_result",
            "verification_method",
        ):
            if not _non_empty(mapping.get(key)):
                raise ValueError(f"mapping {key} must be non-empty")
        if mapping.get("epistemic_status") not in EPISTEMIC_STATES:
            raise ValueError("invalid epistemic_status")
        constraints = mapping.get("constraints")
        if not isinstance(constraints, list) or not constraints or any(
            not _non_empty(item) for item in constraints
        ):
            raise ValueError("mapping constraints must be non-empty strings")
        refs = mapping.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise ValueError("mapping evidence_refs must be non-empty")

        review = mapping.get("ace_review")
        if not isinstance(review, Mapping) or set(review) != REVIEW_FIELDS:
            raise ValueError("ace_review has missing or unknown fields")
        if review.get("decision") not in REVIEW_DECISIONS:
            raise ValueError("invalid ace_review decision")
        if not _non_empty(review.get("reviewer")):
            raise ValueError("ace_review reviewer must be non-empty")
        basis = review.get("review_basis")
        if not isinstance(basis, list) or not basis or any(not _non_empty(item) for item in basis):
            raise ValueError("ace_review review_basis must be non-empty strings")

        normalized = {
            key: _json_copy(mapping[key])
            for key in (
                "mapping_id",
                "epistemic_status",
                "observation",
                "learning",
                "reality_scope",
                "research_question",
                "expected_result",
                "verification_method",
                "constraints",
            )
        }
        return normalized, _json_copy(dict(review)), _json_copy(refs)

    def _validate_evidence_refs(self, refs: list[dict[str, str]]) -> dict[str, Any]:
        normalized: list[dict[str, Any]] = []
        groups: set[str] = set()
        for item in refs:
            if not isinstance(item, Mapping) or set(item) != EVIDENCE_FIELDS:
                raise ValueError("evidence ref has missing or unknown fields")
            if any(not _non_empty(item.get(key)) for key in EVIDENCE_FIELDS):
                raise ValueError("evidence ref fields must be non-empty")
            path = (self.workspace_root / str(item["ref"])).resolve()
            if not _is_within(path, self.workspace_root):
                raise ValueError("evidence ref must stay inside the workspace")
            if not path.is_file():
                raise ValueError(f"evidence ref does not exist: {item['ref']}")
            group = str(item["independence_group"]).strip()
            groups.add(group)
            normalized.append(
                {
                    "ref": path.relative_to(self.workspace_root).as_posix(),
                    "independence_group": group,
                    "kind": str(item["kind"]).strip(),
                    "sha256": _file_digest(path),
                    "size_bytes": path.stat().st_size,
                }
            )
        normalized.sort(key=lambda item: (item["independence_group"], item["ref"]))
        return {
            "refs": normalized,
            "independent_groups": sorted(groups),
            "independent_count": len(groups),
        }

    def _validate_source(self, source_path: str | Path) -> dict[str, Any]:
        source = Path(source_path).resolve()
        distillations = (self.sandbox_root / "distillations").resolve()
        if not source.is_file() or source.suffix.lower() != ".json":
            raise ValueError("named distillation file required")
        if source.parent != distillations:
            raise ValueError("source must be inside the Free Zone distillations directory")
        distillation = self._read_json(source, "source distillation")
        if distillation.get("contract_version") != SOURCE_CONTRACT_VERSION:
            raise ValueError("unsupported source distillation contract")
        if distillation.get("mode") != "DISTILLATION_ONLY":
            raise ValueError("source must be a Free Zone distillation")
        if distillation.get("production_integration") is not False:
            raise ValueError("source production boundary is not closed")
        for field in ("automatic_delivery", "automatic_promotion", "automatic_task_creation"):
            if distillation.get(field) is not False:
                raise ValueError(f"source {field} must be false")
        stored_distillation_hash = distillation.get("distillation_hash")
        hash_input = dict(distillation)
        hash_input.pop("distillation_hash", None)
        if not _non_empty(stored_distillation_hash) or _digest(hash_input) != stored_distillation_hash:
            raise ValueError("source distillation hash mismatch")

        experiment_id = distillation.get("experiment_id")
        if not _non_empty(experiment_id) or source.stem != experiment_id:
            raise ValueError("source experiment identity mismatch")
        experiment_path = self.sandbox_root / "experiments" / f"{experiment_id}.json"
        if not experiment_path.is_file():
            experiment_path = self.sandbox_root / "quarantine" / f"{experiment_id}.json"
        if not experiment_path.is_file():
            raise ValueError("source experiment record is missing")
        experiment = self._read_json(experiment_path, "source experiment")
        if experiment.get("contract_version") != SOURCE_CONTRACT_VERSION:
            raise ValueError("unsupported source experiment contract")
        if experiment.get("production_integration") is not False:
            raise ValueError("source experiment production boundary is not closed")
        stored_record_hash = experiment.get("record_hash")
        record_input = dict(experiment)
        record_input.pop("record_hash", None)
        if not _non_empty(stored_record_hash) or _digest(record_input) != stored_record_hash:
            raise ValueError("source experiment hash mismatch")
        if distillation.get("source_record_hash") != stored_record_hash:
            raise ValueError("distillation does not bind the source experiment")

        pollution_flags = experiment.get("pollution_flags")
        if not isinstance(pollution_flags, list):
            raise ValueError("source pollution flags are malformed")
        return {
            "artifact_ref": source.relative_to(self.workspace_root).as_posix(),
            "artifact_sha256": _file_digest(source),
            "experiment_ref": experiment_path.resolve().relative_to(self.workspace_root).as_posix(),
            "experiment_sha256": _file_digest(experiment_path),
            "experiment_id": experiment_id,
            "source_record_hash": stored_record_hash,
            "distillation_hash": stored_distillation_hash,
            "learning_status": distillation.get("status"),
            "source_outcome": distillation.get("outcome"),
            "pollution_flags": _json_copy(pollution_flags),
        }

    @staticmethod
    def _read_json(path: Path, label: str) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError(f"{label} is unreadable") from error
        if not isinstance(value, dict):
            raise ValueError(f"{label} must be a JSON object")
        return value

    @staticmethod
    def _read_existing(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        value = FreeZoneRealityBridge._read_json(path, "bridge receipt")
        stored_hash = value.get("receipt_hash")
        hash_input = dict(value)
        hash_input.pop("receipt_hash", None)
        if not _non_empty(stored_hash) or _digest(hash_input) != stored_hash:
            raise ValueError("existing bridge receipt hash mismatch")
        return value

    @staticmethod
    def _write_once(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        finally:
            temporary.unlink(missing_ok=True)
