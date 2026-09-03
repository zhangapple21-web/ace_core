"""A durable local free-research sandbox with a one-way production boundary.

The sandbox is deliberately outside the ACE daemon lifecycle.  It can retain
experiments, failures, and speculative work without writing TaskPool, runtime,
production evidence, Advisor, Risk, Telegram, or Experience records.  Every
outcome goes straight to a local distillation record: a pass may additionally
create a signed proposal, while a failure becomes a durable counterexample.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .free_zone_realm import state_for
from .identity_constitution import FREE_ZONE_CONTEXTUAL_CONSTITUTION, IdentityConstitution


CONTRACT_VERSION = "ace.free_research_sandbox.v1"
OUTCOMES = frozenset({"PASS", "FAIL", "INCONCLUSIVE"})
POLLUTION_FLAGS = frozenset({"untrusted_source", "validation_failed", "stale_evidence", "external_injection"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class FreeResearchSandbox:
    """Own a sandbox directory; never mutate an ACE production directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.experiments = self.root / "experiments"
        self.quarantine = self.root / "quarantine"
        self.distillations = self.root / "distillations"
        self.proposals = self.root / "promotion_proposals"

    def initialize(self) -> Path:
        for path in (self.experiments, self.quarantine, self.distillations, self.proposals):
            path.mkdir(parents=True, exist_ok=True)
        manifest = self.root / "SANDBOX_MANIFEST.json"
        if manifest.exists():
            try:
                value = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                value = {}
        else:
            value = {}
        if not value:
            value = {
                "contract_version": CONTRACT_VERSION,
                "mode": "FREE_RESEARCH_ONLY",
                "created_at": _now(),
                "production_integration": False,
                "automatic_promotion": False,
                "forbidden_targets": ["TaskPool", "Runtime", "Advisor", "Risk", "Telegram", "broker", "Experience"],
            }
        changed = False
        for key, default in {
            "autonomous_discovery": True,
            "autonomous_claim": True,
            "autonomous_execution": True,
            "distill_all_outcomes": True,
            "inbound_channels": ["constitution", "inbox", "museum_observation"],
            "capabilities": {
                "text_models": "available_through_authorized_local_channels",
                "image_models": "available_through_isolated_asset_experiments",
                "video_models": ["agnes-video-2.5-flash", "agnes-video-v2.0"],
                "video_generation_mode": "FREE_ZONE_ISOLATED_EXPERIMENT",
                "video_receipt_required": True,
                "automatic_production_promotion": False,
            },
        }.items():
            if key not in value:
                value[key] = default
                changed = True
        if changed or not manifest.exists():
            self._write(manifest, value)
        return manifest

    def record_experiment(
        self,
        *,
        experiment_id: str,
        hypothesis: str,
        method: str,
        outcome: str,
        evidence: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a self-contained experiment or quarantined failure.

        Free exploration has no admission gate, but source and outcome must be
        explicit so a later distillation cannot turn untraceable prose into a
        production fact.
        """
        self.initialize()
        if not experiment_id.strip() or not hypothesis.strip() or not method.strip():
            raise ValueError("experiment_id, hypothesis, and method are required")
        if outcome not in OUTCOMES:
            raise ValueError("outcome must be PASS, FAIL, or INCONCLUSIVE")
        if not isinstance(evidence, Mapping):
            raise ValueError("evidence must be a mapping")
        details = dict(metadata or {})
        contextual_state = details.get("contextual_state_packet")
        if isinstance(contextual_state, Mapping) and self._valid_contextual_state_packet(contextual_state):
            previous = self._latest_contextual_state_packet()
            evidence_refs = self._contextual_evidence_refs(contextual_state)
            constitution = IdentityConstitution(FREE_ZONE_CONTEXTUAL_CONSTITUTION)
            details["identity_drift"] = (
                constitution.compare(previous, contextual_state, evidence_refs=evidence_refs)
                if previous is not None
                else {
                    **constitution.attest(contextual_state),
                    "status": "INITIAL_IDENTITY_ATTESTED",
                    "evidence_refs": evidence_refs,
                }
            )
        pollution = sorted(flag for flag in POLLUTION_FLAGS if details.get(flag) is True)
        source_kind = str(details.get("source_kind", "unknown"))
        record = {
            "contract_version": CONTRACT_VERSION,
            "experiment_id": experiment_id,
            "mode": "FREE_RESEARCH_ONLY",
            "hypothesis": hypothesis,
            "method": method,
            "outcome": outcome,
            "evidence": dict(evidence),
            "metadata": details,
            "pollution_flags": pollution,
            "realm_state": state_for("experiment", source_kind=source_kind, polluted=bool(pollution)),
            "recorded_at": _now(),
            "production_integration": False,
        }
        record["record_hash"] = _digest(record)
        destination = self.quarantine if pollution else self.experiments
        existing = self._find_record_path(experiment_id)
        if existing is not None:
            raise ValueError("experiment_id already exists; experiments are append-only")
        self._write(destination / f"{experiment_id}.json", record)
        return record

    def distill(self, experiment_id: str) -> dict[str, Any]:
        """Distill every experiment without treating failure as an exception.

        Distillation is an internal free-zone action, not a production
        admission gate.  Clean PASS outcomes also emit a proposal-only copy;
        FAIL and INCONCLUSIVE outcomes retain their value as counterexamples
        and open questions.  Polluted material remains visible in quarantine
        but never becomes a claim about production.
        """
        record = self._read_experiment(experiment_id)
        existing = self._read_distillation(experiment_id)
        if existing is not None:
            if existing.get("status") == "PROPOSAL_ONLY" and not (self.proposals / f"{experiment_id}.json").exists():
                return self._create_proposal(record, existing)
            return existing
        if record["pollution_flags"]:
            status, reason = "QUARANTINED", "pollution_requires_isolation"
        elif record["outcome"] == "PASS":
            status, reason = "PROPOSAL_ONLY", "clean_pass_available_for_later_review"
        elif record["outcome"] == "FAIL":
            status, reason = "COUNTEREXAMPLE_ONLY", "failed_hypothesis_retained_as_material"
        else:
            status, reason = "OPEN_QUESTION", "inconclusive_result_requires_new_observation"

        evidence = record["evidence"]
        distillation = {
            "contract_version": CONTRACT_VERSION,
            "experiment_id": experiment_id,
            "mode": "DISTILLATION_ONLY",
            "status": status,
            "reason": reason,
            "source_record_hash": record["record_hash"],
            "outcome": record["outcome"],
            "pattern": f"When {record['hypothesis']}, investigate via {record['method']}.",
            "evidence_hash": _digest(evidence),
            "created_at": _now(),
            "production_integration": False,
            "automatic_promotion": False,
            "automatic_task_creation": False,
            "automatic_delivery": False,
            "realm_state": state_for(
                "distillation",
                source_kind=str(record.get("metadata", {}).get("source_kind", "unknown")) if isinstance(record.get("metadata"), Mapping) else "unknown",
                distillation_status=status,
                polluted=bool(record["pollution_flags"]),
            ),
        }
        semantic_seed = record.get("metadata", {}).get("semantic_seed") if isinstance(record.get("metadata"), Mapping) else None
        if isinstance(semantic_seed, Mapping):
            # This carries a falsifiable question forward inside the sandbox;
            # it neither claims truth nor grants any promotion authority.
            distillation["semantic_seed"] = dict(semantic_seed)
        contextual_state = record.get("metadata", {}).get("contextual_state_packet") if isinstance(record.get("metadata"), Mapping) else None
        if isinstance(contextual_state, Mapping) and self._valid_contextual_state_packet(contextual_state):
            # Keep the hash-bound, research-only state with its distillation
            # so a later re-observation can see what evidence was still
            # missing.  It grants no additional authority to the result.
            distillation["contextual_state"] = {
                "packet_id": contextual_state["packet_id"],
                "packet_hash": contextual_state["packet_hash"],
                "learning_needs": list(contextual_state["learning_needs"]),
                "scope": contextual_state["scope"],
            }
        origin = record.get("metadata", {}).get("ace_reality_gap_origin") if isinstance(record.get("metadata"), Mapping) else None
        if isinstance(origin, Mapping):
            exchange_id = origin.get("exchange_id")
            receipt_sha256 = origin.get("receipt_sha256")
            if isinstance(exchange_id, str) and isinstance(receipt_sha256, str):
                # Lineage only: this neither accepts the learning into ACE nor
                # grants the Free Zone any control-plane authority.
                distillation["origin"] = {
                    "exchange_id": exchange_id,
                    "receipt_sha256": receipt_sha256,
                }
        distillation["distillation_hash"] = _digest(distillation)
        self._write(self.distillations / f"{experiment_id}.json", distillation)

        if status != "PROPOSAL_ONLY":
            return distillation
        if not evidence or not any(str(value).strip() for value in evidence.values()):
            distillation["status"] = "OPEN_QUESTION"
            distillation["reason"] = "pass_without_observable_evidence"
            distillation.pop("distillation_hash", None)
            distillation["distillation_hash"] = _digest(distillation)
            self._write(self.distillations / f"{experiment_id}.json", distillation)
            return distillation

        return self._create_proposal(record, distillation)

    def _create_proposal(self, record: Mapping[str, Any], distillation: Mapping[str, Any]) -> dict[str, Any]:
        experiment_id = str(record["experiment_id"])
        proposal = self._proposal(experiment_id, "PROPOSAL_ONLY", "human_and_governed_review_required", record)
        proposal.pop("proposal_hash", None)
        proposal["distillation"] = {
            "distillation_hash": distillation["distillation_hash"],
            "pattern": distillation["pattern"],
            "evidence_hash": distillation["evidence_hash"],
            "source_record_hash": record["record_hash"],
            "executable": False,
        }
        proposal["proposal_hash"] = _digest(proposal)
        self._write(self.proposals / f"{experiment_id}.json", proposal)
        return proposal

    def _read_experiment(self, experiment_id: str) -> dict[str, Any]:
        path = self._find_record_path(experiment_id)
        if path is not None:
            value = json.loads(path.read_text(encoding="utf-8"))
            if value.get("contract_version") != CONTRACT_VERSION:
                raise ValueError("unsupported sandbox record")
            return value
        raise ValueError("experiment not found")

    def _find_record_path(self, experiment_id: str) -> Path | None:
        for directory in (self.experiments, self.quarantine):
            path = directory / f"{experiment_id}.json"
            if path.exists():
                return path
        return None

    def _read_distillation(self, experiment_id: str) -> dict[str, Any] | None:
        path = self.distillations / f"{experiment_id}.json"
        if not path.exists():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if value.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("unsupported sandbox distillation")
        return value

    def _latest_contextual_state_packet(self) -> dict[str, Any] | None:
        """Return the latest prior valid packet; never infer one from prose."""
        candidates: list[tuple[str, dict[str, Any]]] = []
        for directory in (self.experiments, self.quarantine):
            if not directory.is_dir():
                continue
            for path in directory.glob("*.json"):
                try:
                    record = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                    continue
                if not isinstance(record, Mapping):
                    continue
                metadata = record.get("metadata")
                packet = metadata.get("contextual_state_packet") if isinstance(metadata, Mapping) else None
                if isinstance(packet, Mapping) and self._valid_contextual_state_packet(packet):
                    candidates.append((str(record.get("recorded_at", "")), dict(packet)))
        return max(candidates, key=lambda item: item[0])[1] if candidates else None

    @staticmethod
    def _contextual_evidence_refs(packet: Mapping[str, Any]) -> list[str]:
        refs: set[str] = set()
        for key in ("relevant_facts", "relevant_relations"):
            for item in packet.get(key, []):
                if isinstance(item, Mapping):
                    refs.update(
                        str(ref).strip()
                        for ref in item.get("evidence_refs", [])
                        if isinstance(ref, str) and ref.strip()
                    )
        return sorted(refs)

    def _proposal(self, experiment_id: str, status: str, reason: str, record: Mapping[str, Any]) -> dict[str, Any]:
        proposal = {
            "contract_version": CONTRACT_VERSION,
            "experiment_id": experiment_id,
            "mode": "PROPOSAL_ONLY",
            "status": status,
            "reason": reason,
            "created_at": _now(),
            "source_record_hash": record["record_hash"],
            "requires": ["human_confirmation", "existing_admission", "existing_validator"],
            "prohibited_actions": ["automatic_production_write", "automatic_task_creation", "automatic_delivery", "automatic_order"],
        }
        # Rejected and proposal-only outcomes are both durable artifacts.  A
        # hash on every proposal lets the court detect tampering consistently.
        proposal["proposal_hash"] = _digest(proposal)
        return proposal

    @staticmethod
    def _valid_contextual_state_packet(value: Mapping[str, Any]) -> bool:
        """Accept only a complete, self-hashing research packet as lineage."""
        required = {
            "contract_version", "packet_id", "scope", "scene_scope", "question", "entities", "constraints",
            "relevant_facts", "relevant_relations", "active_hypotheses", "retracted_hypotheses",
            "competing_hypothesis_groups", "learning_needs", "production_integration", "side_effects", "packet_hash",
            "identity_attestation",
        }
        if set(value) != required:
            return False
        if value.get("contract_version") != "ace.contextual_state_packet.v1":
            return False
        if value.get("scope") != "FREE_ZONE_RESEARCH_ONLY" or value.get("production_integration") is not False:
            return False
        side_effects = value.get("side_effects")
        if side_effects != {"task_created": False, "model_called": False, "production_runtime_mutation": False}:
            return False
        attestation = value.get("identity_attestation")
        expected_attestation = IdentityConstitution(FREE_ZONE_CONTEXTUAL_CONSTITUTION).attest(value)
        if attestation != expected_attestation or attestation.get("status") != "IDENTITY_ATTESTED":
            return False
        stored_hash = value.get("packet_hash")
        if not isinstance(stored_hash, str) or len(stored_hash) != 64:
            return False
        source = dict(value)
        source.pop("packet_hash", None)
        return _digest(source) == stored_hash

    @staticmethod
    def _write(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
