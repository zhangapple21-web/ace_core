"""Autonomous foraging and execution inside the ACE free zone.

This module deliberately has no production import.  It is the living part of
the free zone: it discovers available local food, decides which item is worth
trying next, claims exactly one item, and executes an isolated experiment.  A
claim never waits for a teacher, court, TaskPool, or production admission.

The output is an append-only sandbox experiment.  ``SandboxSociety`` then
distills every outcome.  Court validation therefore protects the outbound edge
to production rather than becoming an entrance examination for exploration.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .free_research_sandbox import FreeResearchSandbox
from .free_zone_factories import FreeZoneFactoryLine
from .lazy_cat_audit import LazyCatAudit
from .counterexample_executor import StructuralCounterexampleExecutor
from .free_zone_semantic_exploration import SemanticSliceExplorer
from .open_source_learning import CATALOG
from .semantic_seed import SemanticSeedError, normalize_semantic_seed
from .free_zone_realm import state_for
from .contextual_state_packet import ContextualStatePacket


CONTRACT_VERSION = "ace.free_zone_autonomy.v1"
MAX_REPOSITORY_FILE_BYTES = 24 * 1024


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class FreeZoneAutonomy:
    """One bounded autonomous ecology turn rooted entirely in the sandbox."""

    def __init__(
        self,
        root: str | Path,
        *,
        external_fetcher: Callable[[str], Mapping[str, Any]] | None = None,
        git_observer: Callable[[], Mapping[str, Any]] | None = None,
        selection_seed_factory: Callable[[], int] | None = None,
    ) -> None:
        self.sandbox = FreeResearchSandbox(root)
        self.root = self.sandbox.root
        self.factories = FreeZoneFactoryLine(self.root)
        self.lazy_cat = LazyCatAudit(self.root)
        self.counterexample_executor = StructuralCounterexampleExecutor(self.root)
        self.inbox = self.root / "inbox"
        self.reports = self.root / "reports"
        self.state_path = self.root / "autonomy_state.json"
        self.external_fetcher = external_fetcher or self._fetch_json
        self.git_observer = git_observer or self._local_git_observation
        # Entropy is confined to sandbox resource allocation.  The drawn seed
        # is recorded with every turn, making the resulting pseudo-random
        # sequence replayable from the same candidate snapshot.
        self.selection_seed_factory = selection_seed_factory or (lambda: secrets.randbits(64))

    def run_turn(
        self,
        *,
        max_experiments: int = 1,
        allow_external: bool = False,
        execution_context: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Discover, judge, claim, and execute a bounded local batch.

        The per-turn bound is a resource limit, not a pre-approval queue.  It
        protects the machine while still allowing the free zone to create and
        execute its own work every time new food arrives.
        """
        if max_experiments < 1:
            raise ValueError("max_experiments must be positive")
        execution_evidence = self._execution_evidence(execution_context)
        self.sandbox.initialize()
        self.factories.initialize()
        self.inbox.mkdir(parents=True, exist_ok=True)
        state = self._read_state()
        candidates = self._discover_candidates(state, allow_external=allow_external)
        prepared = self.factories.prepare(candidates)
        allocation = self._choose_many(candidates, max_experiments, state)
        selected = allocation["selected"]
        if not selected:
            report = self._report(
                event="NO_NEW_FREE_ZONE_WORK",
                candidates=[],
                claim=None,
                execution=None,
                factories=self.factories.snapshot(),
                resource_selection=allocation["resource_selection"],
                execution_evidence=execution_evidence,
            )
            self._write_report(report)
            return report

        claims = []
        executions = []
        for selected_item in selected:
            factory_material = prepared.get(str(selected_item["fingerprint"]), {})
            factory_thread = factory_material.get("thread") if isinstance(factory_material.get("thread"), Mapping) else {}
            factory_worlds = factory_material.get("worlds") if isinstance(factory_material.get("worlds"), list) else []
            selected_stance = "COUNTEREXAMPLE_SEARCH" if selected_item["source_kind"] == "lazy_cat_challenge" else "DIRECT_OBSERVATION"
            factory_world = next(
                (
                    item for item in factory_worlds
                    if isinstance(item, Mapping) and item.get("stance") == selected_stance
                ),
                {},
            )
            claim = self._claim(state, selected_item)
            execution = self._execute(selected_item, state, factory_material=factory_material)
            inherited_context = selected_item.get("parent_contextual_state")
            contextual_state = (
                dict(inherited_context)
                if selected_item["source_kind"] == "contextual_learning_need" and isinstance(inherited_context, Mapping)
                else ContextualStatePacket().from_research_candidate(selected_item)
            )
            # A source fingerprint can contain a colon and multiple
            # constitution items share a textual prefix. Use a filesystem-safe
            # digest plus microseconds so automatic claims never collide.
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
            experiment_id = f"EXP-{stamp}-FREEZONE-{_digest(selected_item['fingerprint'])[:12].upper()}"
            record = self.sandbox.record_experiment(
                experiment_id=experiment_id,
                hypothesis=selected_item["hypothesis"],
                method=selected_item["method"],
                outcome=execution["outcome"],
                evidence=execution["evidence"],
                metadata={
                    "source_kind": selected_item["source_kind"],
                    "source_ref": selected_item["source_ref"],
                    "source_fingerprint": selected_item["fingerprint"],
                    "automatic_discovery": True,
                    "automatic_claim": True,
                    "automatic_execution": True,
                    "execution_evidence": execution_evidence,
                    "free_zone_only": True,
                    "production_integration": False,
                    "factory_thread_id": factory_thread.get("thread_id"),
                    "factory_world_id": factory_world.get("world_id"),
                    "semantic_slice": selected_item.get("semantic_slice", {}),
                    "allocation": selected_item.get("allocation", {}),
                    "semantic_seed": selected_item.get("semantic_seed"),
                    # The packet is an explicit research context, not a model
                    # prompt or production memory.  Its missing learning
                    # needs make the next observation condition visible.
                    "contextual_state_packet": contextual_state,
                    "ace_reality_gap_origin": (
                        selected_item.get("payload", {}).get("origin")
                        if selected_item.get("source_kind") == "ace_reality_gap"
                        and isinstance(selected_item.get("payload"), Mapping)
                        else None
                    ),
                    "realm_state": state_for("experiment", source_kind=str(selected_item["source_kind"])),
                },
            )
            processing = self.factories.process(
                candidate=selected_item,
                prepared=factory_material,
                experiment_id=experiment_id,
                outcome=record["outcome"],
                record_hash=record["record_hash"],
                selected_stance=selected_stance,
            )
            challenge_probe = None
            if selected_item["source_kind"] == "lazy_cat_challenge":
                challenge_probe = self.lazy_cat.record_challenge_probe(
                    challenge=selected_item["challenge"],
                    experiment_id=experiment_id,
                    experiment_outcome=record["outcome"],
                    evidence=record["evidence"],
                    processing_receipt=processing,
                )
            state.setdefault("claims", {})[selected_item["fingerprint"]].update({
                "status": "EXECUTED",
                "experiment_id": experiment_id,
                "outcome": record["outcome"],
                "executed_at": record["recorded_at"],
            })
            self._write_state(state)
            claims.append(claim)
            executions.append({
                "experiment_id": experiment_id,
                "outcome": record["outcome"],
                "record_hash": record["record_hash"],
                "factory_thread_id": processing.get("thread_id"),
                "factory_world_id": processing.get("world_id"),
                "challenge_probe_id": challenge_probe.get("probe_id") if challenge_probe else None,
            })
        report = self._report(
            event="FREE_ZONE_EXPERIMENT_EXECUTED",
            candidates=candidates,
            claim=claims[0],
            execution=executions[0],
            claims=claims,
            executions=executions,
            factories=self.factories.snapshot(),
            resource_selection=allocation["resource_selection"],
            execution_evidence=execution_evidence,
        )
        self._write_report(report)
        return report

    def _discover_candidates(self, state: Mapping[str, Any], *, allow_external: bool) -> list[dict[str, Any]]:
        claimed = state.get("claims", {}) if isinstance(state.get("claims"), Mapping) else {}
        candidates = self._constitution_candidates(claimed)
        candidates.extend(self._distillation_candidates(claimed))
        candidates.extend(self._inbox_candidates(claimed))
        candidates.extend(self._local_git_candidates(claimed))
        candidates.extend(self._lazy_cat_candidates(claimed))
        # A contextual gap is real learning food only after all ordinary
        # observed sources are exhausted.  This prevents missing-evidence
        # records from becoming a hidden daily-work quota.
        if not candidates:
            candidates.extend(self._contextual_learning_candidates(claimed))
        if not candidates and allow_external:
            candidates.extend(self._external_catalog_candidates(claimed))
        return [
            {**candidate, "realm_state": state_for("inbound", source_kind=str(candidate.get("source_kind", "unknown")))}
            for candidate in candidates
        ]

    def _lazy_cat_candidates(self, claimed: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Turn post-hoc audit deficiencies into food, never into an entrance gate."""
        candidates = []
        for challenge in self.lazy_cat.pending_challenges():
            challenge_id = str(challenge.get("challenge_id", ""))
            if not challenge_id:
                continue
            attempt = self.lazy_cat.next_challenge_attempt(challenge_id)
            fingerprint = f"lazy_cat_challenge:{challenge_id}:attempt:{attempt}"
            if fingerprint in claimed:
                continue
            candidates.append({
                "fingerprint": fingerprint,
                "source_kind": "lazy_cat_challenge",
                "source_ref": str(self.lazy_cat.challenges / f"{challenge_id}.json"),
                "priority": 0,
                "challenge": challenge,
                "challenge_attempt": attempt,
                "hypothesis": str(challenge.get("question", "")),
                "method": str(challenge.get("method", "")),
            })
        return candidates

    def _local_git_candidates(self, claimed: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Offer a path-redacted local change observation as food, never a fact."""
        observation = dict(self.git_observer())
        if observation.get("status") != "OBSERVED" or not observation.get("safe_paths"):
            return []
        fingerprint = f"local_git:{observation.get('fingerprint', '')}"
        if not observation.get("fingerprint") or fingerprint in claimed:
            return []
        return [{
            "fingerprint": fingerprint,
            "source_kind": "local_git",
            "source_ref": str(observation.get("repository", "local_git")),
            "priority": 12,
            "observation": observation,
            "hypothesis": "A changed local implementation surface may contain one bounded, independently testable research question.",
            "method": "Observe a path-redacted Git delta only, retain a digest and counts, and ask for later dedicated verification rather than trusting the diff.",
        }]

    def _distillation_candidates(self, claimed: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Let failures and open questions feed the next observation cycle.

        This is the ecological link that a simple queue lacks: a failure is not
        merely retained for a later human to notice; it becomes food for an
        automatic re-observation experiment in the same free zone.
        """
        candidates = []
        for distillation in self._records(self.sandbox.distillations):
            status = str(distillation.get("status", ""))
            if status not in {"COUNTEREXAMPLE_ONLY", "OPEN_QUESTION"}:
                continue
            experiment_id = str(distillation.get("experiment_id", ""))
            if not experiment_id:
                continue
            experiment = self._read_json(self.sandbox.experiments / f"{experiment_id}.json")
            metadata = experiment.get("metadata") if isinstance(experiment, Mapping) else None
            # A contextual learning-need turn deliberately records absence
            # without asserting a new fact.  It is still distilled for audit,
            # but must not re-enter the generic re-observation chain: doing so
            # would turn one named missing observation into an endless loop.
            if isinstance(metadata, Mapping) and metadata.get("source_kind") == "contextual_learning_need":
                continue
            fingerprint = f"distillation:{status}:{experiment_id}"
            if fingerprint in claimed:
                continue
            label = "counterexample" if status == "COUNTEREXAMPLE_ONLY" else "open question"
            candidates.append({
                "fingerprint": fingerprint,
                "source_kind": "distillation",
                "source_ref": str(self.sandbox.distillations / f"{experiment_id}.json"),
                "priority": 15,
                "parent_experiment_id": experiment_id,
                "parent_status": status,
                "hypothesis": f"The {label} {experiment_id} can be turned into a distinct next observation without overwriting its original result.",
                "method": "Preserve the parent distillation, formulate an explicit re-observation question, and record the new experiment separately.",
            })
        return candidates

    def _contextual_learning_candidates(self, claimed: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Re-observe one recorded missing fact without creating a self-loop.

        Only a full packet from its original experiment is reused.  The new
        record keeps that same packet rather than generating a new missing
        fact, and its fingerprint is claimed after one turn.  Thus a gap stays
        visible but cannot manufacture endlessly nested research work.
        """
        candidates: list[dict[str, Any]] = []
        for distillation in self._records(self.sandbox.distillations):
            context = distillation.get("contextual_state")
            if not isinstance(context, Mapping):
                continue
            experiment_id = str(distillation.get("experiment_id", "")).strip()
            packet_hash = str(context.get("packet_hash", "")).strip()
            if not experiment_id or not packet_hash:
                continue
            experiment = self._read_json(self.sandbox.experiments / f"{experiment_id}.json")
            metadata = experiment.get("metadata") if isinstance(experiment, Mapping) else None
            packet = metadata.get("contextual_state_packet") if isinstance(metadata, Mapping) else None
            if not isinstance(packet, Mapping) or packet.get("packet_hash") != packet_hash:
                continue
            needs = context.get("learning_needs")
            if not isinstance(needs, list):
                continue
            for need in needs:
                if not isinstance(need, Mapping):
                    continue
                fact_id = str(need.get("fact_id", "")).strip()
                if not fact_id:
                    continue
                fingerprint = f"contextual_learning_need:{packet_hash}:{fact_id}"
                if fingerprint in claimed:
                    continue
                candidates.append(
                    {
                        "fingerprint": fingerprint,
                        "source_kind": "contextual_learning_need",
                        "source_ref": str(self.sandbox.distillations / f"{experiment_id}.json"),
                        "priority": 30,
                        "parent_experiment_id": experiment_id,
                        "parent_packet_hash": packet_hash,
                        "learning_need": dict(need),
                        "parent_contextual_state": dict(packet),
                        "hypothesis": f"The missing observable {fact_id} remains unresolved until independently observed.",
                        "method": "Preserve the source packet and record the named missing observation without treating absence as proof.",
                    }
                )
        return candidates

    def _constitution_candidates(self, claimed: Mapping[str, Any]) -> list[dict[str, Any]]:
        path = self.root / "constitution" / "R1_ECOLOGY_CONSTITUTION_v1.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return []
        if not isinstance(value, Mapping):
            return []
        result = []
        for invariant in value.get("invariants", []):
            if not isinstance(invariant, Mapping) or not str(invariant.get("id", "")).strip():
                continue
            invariant_id = str(invariant["id"])
            fingerprint = f"constitution:{invariant_id}"
            if fingerprint in claimed:
                continue
            result.append({
                "fingerprint": fingerprint,
                "source_kind": "constitution",
                "source_ref": str(path),
                "priority": 10,
                "invariant_id": invariant_id,
                "hypothesis": str(invariant.get("rule", invariant_id)),
                "method": f"Run the local {invariant_id} ecological probe and retain its observed outcome.",
            })
        return result

    def _inbox_candidates(self, claimed: Mapping[str, Any]) -> list[dict[str, Any]]:
        candidates = []
        for path in sorted(self.inbox.glob("*.json")):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                # Invalid food is still a valid free-zone observation.  It is
                # converted to a failed local experiment rather than rejected
                # at the doorway.
                value = {"malformed": True}
            fingerprint = f"inbox:{_digest({'path': path.name, 'content': value})}"
            if fingerprint in claimed:
                continue
            hypothesis = str(value.get("hypothesis") or value.get("question") or f"Inspect free-zone input {path.name}") if isinstance(value, Mapping) else f"Inspect free-zone input {path.name}"
            method = str(value.get("method") or "Run an isolated local probe over the preserved inbox payload.") if isinstance(value, Mapping) else "Run an isolated local probe over the preserved inbox payload."
            food_kind = str(value.get("food_kind", "")) if isinstance(value, Mapping) else ""
            semantic_seed = None
            if food_kind == "semantic_seed":
                try:
                    semantic_seed = normalize_semantic_seed(value)
                    source_kind = "semantic_seed"
                    hypothesis = semantic_seed["transfer_hypothesis"]
                    method = semantic_seed["next_verification"]
                except SemanticSeedError as error:
                    # The free zone has an open intake.  An incomplete idea is
                    # still worth preserving as a pending observation; only the
                    # outbound production edge needs a complete contract.
                    source_kind = "semantic_seed_unstructured"
                    value = {"food_kind": "semantic_seed", "validation_error": str(error), "payload_hash": _digest(value)}
            else:
                source_kind = {
                    "museum_history": "museum_history",
                    "ace_reality_gap": "ace_reality_gap",
                }.get(food_kind, "inbox")
            candidates.append({
                "fingerprint": fingerprint,
                "source_kind": source_kind,
                "source_ref": str(path),
                "priority": 25 if source_kind == "museum_history" else 20,
                "payload": value,
                "semantic_seed": semantic_seed,
                "hypothesis": hypothesis,
                "method": method,
            })
        return candidates

    def _external_catalog_candidates(self, claimed: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Fetch one bounded public repository artifact after local food is exhausted.

        The first contact is repository metadata. A later independent turn may
        read exactly one README response from that same public repository, but
        stores only its digest and shape. It never follows links, clones,
        installs, executes, or treats README prose as authority.
        """
        for item in CATALOG:
            identifier = str(item["id"])
            metadata_fingerprint = f"external_catalog:{identifier}:v1"
            repository = str(item["repository"])
            if metadata_fingerprint not in claimed:
                endpoint = self._github_metadata_url(repository)
                try:
                    payload = dict(self.external_fetcher(endpoint))
                    fetch = {"status": "OBSERVED", "endpoint": endpoint, "payload": payload}
                except Exception as error:
                    fetch = {"status": "UNAVAILABLE", "endpoint": endpoint, "error": f"{type(error).__name__}: {error}"}
                return [{
                    "fingerprint": metadata_fingerprint,
                    "source_kind": "external_catalog",
                    "source_ref": repository,
                    "priority": 5,
                    "catalog_item": dict(item),
                    "fetch": fetch,
                    "hypothesis": f"The public repository {identifier} may provide a reusable research design without installation or production integration.",
                    "method": "Read one public repository metadata record, preserve provenance, and form a separate free-zone question rather than a production claim.",
                }]

            readme_fingerprint = f"external_catalog:{identifier}:readme:v1"
            if readme_fingerprint in claimed:
                continue
            endpoint = self._github_readme_url(repository)
            try:
                payload = dict(self.external_fetcher(endpoint))
                fetch = {"status": "OBSERVED", "endpoint": endpoint, "payload": payload}
            except Exception as error:
                fetch = {"status": "UNAVAILABLE", "endpoint": endpoint, "error": f"{type(error).__name__}: {error}"}
            return [{
                "fingerprint": readme_fingerprint,
                "source_kind": "external_repository_file",
                "source_ref": repository,
                "priority": 5,
                "catalog_item": dict(item),
                "fetch": fetch,
                "hypothesis": f"The public README of {identifier} may expose a research design that warrants a later ACE compatibility probe.",
                "method": "Read one public README response, retain only a bounded digest and structural summary, and create no installation, execution, or production claim.",
            }]
        return []

    def _choose_many(self, candidates: list[dict[str, Any]], limit: int, state: dict[str, Any]) -> dict[str, Any]:
        """Allocate capacity fairly, then explore descriptive semantic slices.

        The selector deliberately does not receive prior outcomes, market data,
        recommendation status, or a quality score.  It only receives structural
        candidate fields, historical *allocation counts*, and a recorded seed.
        Lazy Cat remains the post-execution evaluator.
        """
        return SemanticSliceExplorer.allocate(
            candidates,
            limit=limit,
            state=state,
            selection_seed=int(self.selection_seed_factory()),
        )

    def _claim(self, state: dict[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
        claim = {
            "status": "CLAIMED",
            "claimed_at": _now(),
            "source_kind": candidate["source_kind"],
            "source_ref": candidate["source_ref"],
            "semantic_slice": candidate.get("semantic_slice", {}),
            "allocation": candidate.get("allocation", {}),
            "realm_state": candidate.get("realm_state", state_for("inbound", source_kind=str(candidate["source_kind"]))),
        }
        state.setdefault("claims", {})[str(candidate["fingerprint"])] = claim
        self._write_state(state)
        return {"fingerprint": candidate["fingerprint"], **claim}

    def _execute(self, candidate: Mapping[str, Any], state: Mapping[str, Any], *, factory_material: Mapping[str, Any] | None = None) -> dict[str, Any]:
        if candidate["source_kind"] == "museum_history":
            payload = candidate.get("payload")
            if not isinstance(payload, Mapping):
                return {"outcome": "FAIL", "evidence": {"source": candidate["source_ref"], "reason": "museum_food_not_mapping"}}
            inventory_path = Path(str(payload.get("inventory_report", "")))
            inventory = self._read_json(inventory_path)
            expected_hash = str(payload.get("inventory_sha256", ""))
            observed_hash = str(inventory.get("inventory_sha256", ""))
            report_count = inventory.get("summary", {}).get("historical_daily_report_count", 0)
            non_actions = payload.get("non_actions")
            valid = (
                bool(expected_hash)
                and observed_hash == expected_hash
                and isinstance(report_count, int)
                and report_count >= 7
                and isinstance(non_actions, list)
                and bool(non_actions)
            )
            return {
                "outcome": "PASS" if valid else "FAIL",
                "evidence": {
                    "source": candidate["source_ref"],
                    "inventory_report": str(inventory_path),
                    "expected_inventory_sha256": expected_hash,
                    "observed_inventory_sha256": observed_hash,
                    "historical_daily_report_count": report_count,
                    "non_actions_preserved": bool(non_actions),
                    "condition": "museum_food_is_rechecked_after_autonomous_claim",
                },
            }

        if candidate["source_kind"] == "local_git":
            observation = candidate.get("observation")
            if not isinstance(observation, Mapping) or observation.get("status") != "OBSERVED":
                return {"outcome": "FAIL", "evidence": {"source": candidate["source_ref"], "reason": "local_git_observation_invalid"}}
            return {
                "outcome": "INCONCLUSIVE",
                "evidence": {
                    "repository": candidate["source_ref"],
                    "head": observation.get("head"),
                    "safe_path_count": observation.get("safe_path_count", 0),
                    "redacted_path_count": observation.get("redacted_path_count", 0),
                    "paths_sha256": observation.get("paths_sha256"),
                    "content_retained": False,
                    "next_question": "Which one of these local changes has a dedicated testable hypothesis and isolated verification method?",
                },
            }

        if candidate["source_kind"] == "lazy_cat_challenge":
            challenge = candidate.get("challenge")
            if not isinstance(challenge, Mapping):
                return {"outcome": "FAIL", "evidence": {"source": candidate["source_ref"], "reason": "lazy_cat_challenge_not_mapping"}}
            worlds = factory_material.get("worlds", []) if isinstance(factory_material, Mapping) else []
            mapped_worlds = [item for item in worlds if isinstance(item, Mapping)] if isinstance(worlds, list) else []
            return self.counterexample_executor.execute(challenge=challenge, factory_worlds=mapped_worlds)

        if candidate["source_kind"] == "inbox":
            payload = candidate.get("payload")
            if not isinstance(payload, Mapping):
                return {"outcome": "FAIL", "evidence": {"source": candidate["source_ref"], "reason": "inbox_payload_not_mapping"}}
            return {
                "outcome": "INCONCLUSIVE",
                "evidence": {
                    "source": candidate["source_ref"],
                    "payload_hash": _digest(payload),
                    "reason": "inbox_food_preserved_for_a_future_specialized_probe",
                },
            }

        if candidate["source_kind"] == "ace_reality_gap":
            payload = candidate.get("payload")
            if not isinstance(payload, Mapping) or not isinstance(payload.get("origin"), Mapping):
                return {"outcome": "FAIL", "evidence": {"source": candidate["source_ref"], "reason": "reality_gap_food_missing_origin"}}
            return {
                "outcome": "INCONCLUSIVE",
                "evidence": {
                    "source": candidate["source_ref"],
                    "origin_exchange_id": payload["origin"].get("exchange_id"),
                    "origin_receipt_sha256": payload["origin"].get("receipt_sha256"),
                    "payload_hash": _digest(payload),
                    "expected_result": payload.get("expected_result"),
                    "reason": "ace_reality_gap_preserved_for_a_future_specialized_probe",
                },
            }

        if candidate["source_kind"] == "semantic_seed":
            seed = candidate.get("semantic_seed")
            if not isinstance(seed, Mapping):
                return {"outcome": "FAIL", "evidence": {"source": candidate["source_ref"], "reason": "semantic_seed_missing_after_validation"}}
            return {
                "outcome": "INCONCLUSIVE",
                "evidence": {
                    "source": candidate["source_ref"],
                    "source_ref": seed["source_ref"],
                    "source_snapshot_hash": seed["source_snapshot_hash"],
                    "semantic_seed_hash": seed["seed_hash"],
                    "status": "PENDING",
                    "requires_independent_evidence": True,
                    "local_evidence_refs": list(seed["local_evidence_refs"]),
                    "external_evidence_refs": list(seed["external_evidence_refs"]),
                    "next_verification": seed["next_verification"],
                },
            }

        if candidate["source_kind"] == "semantic_seed_unstructured":
            payload = candidate.get("payload")
            return {
                "outcome": "INCONCLUSIVE",
                "evidence": {
                    "source": candidate["source_ref"],
                    "status": "PENDING",
                    "normalization_error": payload.get("validation_error", "semantic_seed_unstructured") if isinstance(payload, Mapping) else "semantic_seed_unstructured",
                    "payload_hash": payload.get("payload_hash") if isinstance(payload, Mapping) else None,
                    "next_question": "What additional context would turn this raw observation into a falsifiable semantic seed?",
                },
            }

        if candidate["source_kind"] == "distillation":
            parent_id = str(candidate.get("parent_experiment_id", ""))
            parent = self._read_json(self.sandbox.distillations / f"{parent_id}.json")
            valid_parent = bool(parent) and parent.get("status") == candidate.get("parent_status")
            return {
                "outcome": "PASS" if valid_parent else "FAIL",
                "evidence": {
                    "parent_experiment_id": parent_id,
                    "parent_distillation_hash": parent.get("distillation_hash"),
                    "parent_status": candidate.get("parent_status"),
                    "re_observation_question": f"What new evidence would change or refine the result of {parent_id}?",
                    "parent_preserved": valid_parent,
                },
            }

        if candidate["source_kind"] == "contextual_learning_need":
            need = candidate.get("learning_need")
            if not isinstance(need, Mapping):
                return {"outcome": "FAIL", "evidence": {"source": candidate["source_ref"], "reason": "contextual_learning_need_malformed"}}
            return {
                "outcome": "INCONCLUSIVE",
                "evidence": {
                    "source": candidate["source_ref"],
                    "parent_experiment_id": candidate.get("parent_experiment_id"),
                    "parent_packet_hash": candidate.get("parent_packet_hash"),
                    "fact_id": need.get("fact_id"),
                    "required_by_hypotheses": need.get("required_by_hypotheses", []),
                    "status": "MISSING_INDEPENDENT_OBSERVATION",
                    "reason": "named_learning_need_retained_without_inventing_evidence",
                },
            }

        if candidate["source_kind"] == "external_catalog":
            fetch = candidate.get("fetch", {})
            if not isinstance(fetch, Mapping) or fetch.get("status") != "OBSERVED":
                return {
                    "outcome": "FAIL",
                    "evidence": {
                        "repository": candidate["source_ref"],
                        "fetch_status": fetch.get("status") if isinstance(fetch, Mapping) else "INVALID",
                        "fetch_error": fetch.get("error") if isinstance(fetch, Mapping) else "invalid_fetch_record",
                    },
                }
            payload = fetch.get("payload", {})
            return {
                "outcome": "INCONCLUSIVE",
                "evidence": {
                    "repository": candidate["source_ref"],
                    "metadata_endpoint": fetch.get("endpoint"),
                    "metadata_hash": _digest(payload),
                    "repository_name": payload.get("full_name") if isinstance(payload, Mapping) else None,
                    "updated_at": payload.get("updated_at") if isinstance(payload, Mapping) else None,
                    "next_question": "Which design element survives a local ACE compatibility and counterexample probe?",
                },
            }

        if candidate["source_kind"] == "external_repository_file":
            fetch = candidate.get("fetch", {})
            if not isinstance(fetch, Mapping) or fetch.get("status") != "OBSERVED":
                return {
                    "outcome": "FAIL",
                    "evidence": {
                        "repository": candidate["source_ref"],
                        "fetch_status": fetch.get("status") if isinstance(fetch, Mapping) else "INVALID",
                        "fetch_error": fetch.get("error") if isinstance(fetch, Mapping) else "invalid_fetch_record",
                    },
                }
            payload = fetch.get("payload", {})
            summary = self._repository_file_summary(payload)
            if summary.get("status") != "OBSERVED":
                return {
                    "outcome": "FAIL",
                    "evidence": {
                        "repository": candidate["source_ref"],
                        "readme_endpoint": fetch.get("endpoint"),
                        **summary,
                    },
                }
            return {
                "outcome": "INCONCLUSIVE",
                "evidence": {
                    "repository": candidate["source_ref"],
                    "readme_endpoint": fetch.get("endpoint"),
                    "catalog_id": candidate.get("catalog_item", {}).get("id"),
                    **summary,
                    "next_question": "Which stated design element is independently compatible with ACE under a dedicated sandbox probe?",
                },
            }

        invariant_id = str(candidate.get("invariant_id", ""))
        manifest = self._read_json(self.root / "SANDBOX_MANIFEST.json")
        records = self._records(self.sandbox.experiments)
        distillations = self._records(self.sandbox.distillations)
        proposals = self._records(self.sandbox.proposals)
        common = {
            "invariant_id": invariant_id,
            "manifest_hash": _digest(manifest),
            "experiment_count_before": len(records),
            "distillation_count_before": len(distillations),
            "proposal_count_before": len(proposals),
        }
        if invariant_id == "ECO-01":
            condition = manifest.get("production_integration") is False and manifest.get("automatic_promotion") is False
            return {"outcome": "PASS" if condition else "FAIL", "evidence": {**common, "condition": "continuity_boundary_present", "observed": condition}}
        if invariant_id == "ECO-02":
            condition = all(name in manifest.get("forbidden_targets", []) for name in ("TaskPool", "Runtime", "Advisor", "Risk", "Telegram", "broker", "Experience"))
            return {"outcome": "PASS" if condition else "FAIL", "evidence": {**common, "condition": "freedom_isolated_from_production", "observed": condition}}
        if invariant_id == "ECO-03":
            prior_failures = [item["experiment_id"] for item in records if item.get("outcome") == "FAIL"]
            return {
                "outcome": "PASS" if prior_failures else "FAIL",
                "evidence": {**common, "condition": "prior_failure_retained", "prior_failure_ids": prior_failures},
            }
        if invariant_id == "ECO-04":
            complete = bool(distillations) and all(item.get("source_record_hash") for item in distillations)
            return {"outcome": "PASS" if complete else "INCONCLUSIVE", "evidence": {**common, "condition": "portable_distillation_exists", "observed": complete}}
        if invariant_id == "ECO-05":
            role_separation = all(item.get("production_integration") is False for item in distillations)
            return {"outcome": "PASS" if role_separation else "FAIL", "evidence": {**common, "condition": "no_distillation_has_production_authority", "observed": role_separation}}
        if invariant_id == "ECO-06":
            claims = state.get("claims", {}) if isinstance(state.get("claims"), Mapping) else {}
            return {"outcome": "PASS", "evidence": {**common, "condition": "one_claimed_item_per_turn_without_activity_quota", "claim_count": len(claims)}}
        return {"outcome": "INCONCLUSIVE", "evidence": {**common, "reason": "unknown_invariant"}}

    def _read_state(self) -> dict[str, Any]:
        value = self._read_json(self.state_path)
        if value.get("contract_version") != CONTRACT_VERSION:
            return {"contract_version": CONTRACT_VERSION, "claims": {}, "created_at": _now()}
        value.setdefault("claims", {})
        return value

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _records(directory: Path) -> list[dict[str, Any]]:
        records = []
        for path in sorted(directory.glob("*.json")):
            value = FreeZoneAutonomy._read_json(path)
            if value:
                records.append(value)
        return records

    @staticmethod
    def _github_metadata_url(repository: str) -> str:
        parsed = urlparse(repository)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc.lower() != "github.com" or len(parts) < 2:
            raise ValueError("only GitHub repository URLs are supported for automatic external food")
        return f"https://api.github.com/repos/{parts[0]}/{parts[1]}"

    @staticmethod
    def _github_readme_url(repository: str) -> str:
        parsed = urlparse(repository)
        parts = [part for part in parsed.path.split("/") if part]
        if parsed.netloc.lower() != "github.com" or len(parts) < 2:
            raise ValueError("only GitHub repository URLs are supported for automatic external food")
        return f"https://api.github.com/repos/{parts[0]}/{parts[1]}/readme"

    @staticmethod
    def _repository_file_summary(payload: Any) -> dict[str, Any]:
        """Return a bounded, non-executable summary of a GitHub Contents response."""
        if not isinstance(payload, Mapping):
            return {"status": "INVALID", "reason": "repository_file_response_not_mapping"}
        encoded = payload.get("content")
        if not isinstance(encoded, str) or not encoded.strip():
            return {"status": "INVALID", "reason": "repository_file_missing_base64"}
        try:
            raw = base64.b64decode(encoded.encode("ascii"), validate=False)
        except (UnicodeEncodeError, ValueError):
            return {"status": "INVALID", "reason": "repository_file_invalid_base64"}
        bounded = raw[:MAX_REPOSITORY_FILE_BYTES]
        return {
            "status": "OBSERVED",
            "file_name": str(payload.get("name", "README")),
            "file_path": str(payload.get("path", "README")),
            "upstream_sha": str(payload.get("sha", "")) or None,
            "observed_bytes": len(bounded),
            "truncated": len(raw) > MAX_REPOSITORY_FILE_BYTES,
            "content_sha256": hashlib.sha256(bounded).hexdigest(),
            "content_line_count": bounded.count(b"\n") + (1 if bounded else 0),
            "content_retained": False,
        }

    def _local_git_observation(self) -> Mapping[str, Any]:
        """Read only Git names/statuses, excluding credential-like paths and file bodies."""
        try:
            top = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "--show-toplevel"],
                capture_output=True, text=True, check=True, timeout=4,
            ).stdout.strip()
            head = subprocess.run(
                ["git", "-C", top, "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True, timeout=4,
            ).stdout.strip()
            status = subprocess.run(
                ["git", "-C", top, "status", "--porcelain=v1"],
                capture_output=True, text=True, check=True, timeout=4,
            ).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            return {"status": "UNAVAILABLE"}

        paths = []
        redacted = 0
        for line in status:
            raw = line[3:].strip() if len(line) >= 4 else ""
            path = raw.split(" -> ")[-1].strip()
            if not path:
                continue
            if self._is_sensitive_path(path):
                redacted += 1
            else:
                paths.append(path.replace("\\", "/"))
        paths = sorted(set(paths))[:24]
        if not paths:
            return {"status": "NO_SAFE_GIT_FOOD", "redacted_path_count": redacted}
        fingerprint_payload = {"head": head, "paths": paths, "redacted_path_count": redacted}
        return {
            "status": "OBSERVED",
            "repository": top,
            "head": head,
            "safe_paths": paths,
            "safe_path_count": len(paths),
            "redacted_path_count": redacted,
            "paths_sha256": _digest(paths),
            "fingerprint": _digest(fingerprint_payload),
            "content_retained": False,
        }

    @staticmethod
    def _is_sensitive_path(path: str) -> bool:
        normalized = path.lower().replace("\\", "/")
        name = normalized.rsplit("/", 1)[-1]
        return (
            name.startswith(".env")
            or any(token in name for token in ("credential", "secret", "token", "apikey", "api_key", "private_key"))
            or name in {"ace_config.json", "config.toml"}
        )

    @staticmethod
    def _fetch_json(url: str) -> Mapping[str, Any]:
        request = Request(
            url,
            headers={"User-Agent": "ACE-FreeZone/1.0", "Accept": "application/vnd.github+json"},
        )
        with urlopen(request, timeout=8) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, Mapping):
            raise ValueError("external response is not a mapping")
        return value

    @staticmethod
    def _execution_evidence(execution_context: Mapping[str, Any] | None) -> dict[str, Any]:
        context = dict(execution_context or {})
        trigger_kind = str(context.get("trigger_kind", "")).strip()
        runner = str(context.get("runner", "")).strip()
        pid = context.get("pid")
        shift_kind = str(context.get("shift_kind", "UNSPECIFIED")).strip()
        if shift_kind not in {"AD_HOC", "OFF_DUTY"}:
            shift_kind = "UNSPECIFIED"
        check_in_at = str(context.get("check_in_at", "")).strip() or None
        if trigger_kind and runner and isinstance(pid, int) and pid > 0:
            return {
                "status": "EXPLICIT_TRIGGER_RECORDED",
                "runtime_proof": False,
                "natural_daemon_cycle": "NO" if trigger_kind == "MANUAL_CLI" else "UNKNOWN",
                "trigger": {"kind": trigger_kind, "runner": runner, "pid": pid},
                "shift": {"kind": shift_kind, "check_in_at": check_in_at},
                "semantics": "an explicit sandbox trigger proves attribution only; it grants no ACE reality or production authority",
            }
        return {
            "status": "UNATTRIBUTED_LOCAL_CALL",
            "runtime_proof": False,
            "natural_daemon_cycle": "UNKNOWN",
            "trigger": None,
            "shift": {"kind": "UNSPECIFIED", "check_in_at": None},
            "semantics": "a sandbox report alone does not prove who triggered the turn or a natural daemon cycle",
        }

    def _report(self, *, event: str, candidates: list[dict[str, Any]], claim: Mapping[str, Any] | None, execution: Mapping[str, Any] | None, claims: list[Mapping[str, Any]] | None = None, executions: list[Mapping[str, Any]] | None = None, factories: Mapping[str, Any] | None = None, resource_selection: Mapping[str, Any] | None = None, execution_evidence: Mapping[str, Any] | None = None) -> dict[str, Any]:
        completed_at = _now()
        evidence = dict(execution_evidence or self._execution_evidence(None))
        if evidence.get("shift", {}).get("kind") == "OFF_DUTY":
            evidence["check_out_at"] = completed_at
        return {
            "contract_version": CONTRACT_VERSION,
            "mode": "FREE_ZONE_AUTONOMY_TURN",
            "at": completed_at,
            "event": event,
            "discovery": {"candidate_count": len(candidates), "source_kinds": sorted({item["source_kind"] for item in candidates})},
            "judgment": {
                "selected_fingerprint": claim.get("fingerprint") if claim else None,
                "approval_required": False,
                "quality_decision_performed": False,
                "selection_semantics": "resource_allocation_only",
            },
            "resource_selection": dict(resource_selection or {
                "policy": "source_fair_round_robin_then_semantic_slice_probability",
                "quality_decision_performed": False,
                "outcome_used": False,
                "production_value_used": False,
            }),
            "claim": dict(claim) if claim else None,
            "execution": dict(execution) if execution else None,
            "claims": [dict(item) for item in (claims or [])],
            "executions": [dict(item) for item in (executions or [])],
            "execution_evidence": evidence,
            "food_chain": ["inbound_food", "free_zone_discovery", "autonomous_claim", "isolated_execution", "distillation", "counterexample_re_observation", "court_at_production_edge"],
            "factories": dict(factories or self.factories.snapshot()),
            "production_integration": False,
            "automatic_production_promotion": False,
            "automatic_model_call": False,
            "available_capabilities": {
                "video_models": ["agnes-video-2.5-flash", "agnes-video-v2.0"],
                "video_generation_mode": "FREE_ZONE_ISOLATED_EXPERIMENT",
                "video_receipt_required": True,
                "production_promotion": "EXPLICIT_HASH_BOUND_ADMISSION_ONLY",
            },
            "automatic_external_fetch": any(
                item["source_kind"] in {"external_catalog", "external_repository_file"}
                for item in candidates
            ),
        }

    def _write_state(self, value: Mapping[str, Any]) -> None:
        self._atomic_write(self.state_path, value)

    def _write_report(self, value: Mapping[str, Any]) -> None:
        self._atomic_write(self.reports / "free_zone_autonomy_latest.json", value)

    @staticmethod
    def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
