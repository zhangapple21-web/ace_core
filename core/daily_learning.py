import json
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Dict, List, Optional, Tuple

from .discovery import DiscoveryCandidate
from .experience_deposition import ExperienceDeposition
from .task_roles import Archivist, Guardian
from .triple_cross_validation import CrossValidator
from .governance.knowledge_governor import AdmissionDecision
from .governance.knowledge_lifecycle import LifecycleStage


DAILY_LEARNING_OBSERVATION_LIMIT = 200


class DailyLearningLoop:
    source_tiers = [
        "official",
        "technical_primary",
        "documentation",
        "community",
        "open_web",
    ]
    required_contract_fields = {
        "why_learn",
        "learning_objective",
        "required_evidence",
        "mastery_criteria",
    }
    blocking_priorities = {"critical", "high"}
    # Only work that can consume execution/review capacity should defer the
    # learning execution window. Externally blocked work and already-approved
    # work are not runnable and must not silence discovery for the whole day.
    blocking_statuses = {"pending", "active", "review"}

    def __init__(
        self,
        data_dir: str,
        discovery,
        converter,
        task_pool,
        evidence_registry,
        knowledge_governor,
        lifecycle_manager,
        internal_candidate_sources: List[Callable[[], List[Tuple[Any, List[Dict[str, Any]]]]]],
        external_discoverer: Optional[Callable[[str, List[str]], List[Tuple[Any, List[Dict[str, Any]]]]]] = None,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir = self.data_dir / "daily_results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.discovery = discovery
        self.converter = converter
        self.task_pool = task_pool
        self.evidence_registry = evidence_registry
        self.knowledge_governor = knowledge_governor
        self.lifecycle_manager = lifecycle_manager
        self.internal_candidate_sources = internal_candidate_sources
        self.external_discoverer = external_discoverer
        Path(self.lifecycle_manager.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.archivist = Archivist(task_pool=self.task_pool)
        self.guardian = Guardian(task_pool=self.task_pool)
        self.deposition = ExperienceDeposition(str(self.data_dir / "knowledge"))

    def run(self, run_date: str) -> Dict[str, Any]:
        existing = self._load_result(run_date)
        legacy_blocked_result = self._is_legacy_blocked_result(existing)
        if existing is not None and not legacy_blocked_result:
            return existing

        blocking_task = self._blocking_task()
        # Discovery and assessment are independent from execution capacity.
        # A high-priority pending task may delay service, but it must not erase
        # a real learning candidate or prevent it entering the existing
        # admission/lifecycle path.  TaskPool fairness remains responsible
        # for when the candidate is actually claimed.
        mode, selection = self._choose_candidate(allow_external=True)

        if selection is None:
            result = {
                "date": run_date,
                "mode": "none",
                "outcome": "NO_VALID_LEARNING_TARGET",
                "reason": "no_evidence_backed_internal_candidate_or_external_candidate",
                "no_side_effects": True,
            }
            self._record_daily_result(run_date, result)
            return result

        candidate, evidence_items = selection
        contract = self._learning_contract(candidate)
        if not self._valid_contract(contract):
            result = {
                "date": run_date,
                "mode": mode,
                "outcome": "NO_VALID_LEARNING_TARGET",
                "reason": "learning_contract_incomplete",
                "candidate": candidate.title,
                "no_side_effects": True,
            }
            self._record_daily_result(run_date, result)
            return result

        task = self._create_task(candidate, evidence_items)
        if task is None:
            result = {
                "date": run_date,
                "mode": mode,
                "outcome": "NO_VALID_LEARNING_TARGET",
                "reason": "discovery_to_task_conversion_failed",
                "candidate": candidate.title,
                "no_side_effects": True,
            }
            self._record_daily_result(run_date, result)
            return result

        evidence_ids = self._register_evidence(evidence_items)
        independence = self._source_independence(evidence_items)
        cross_validation = self._cross_validate(candidate, evidence_items)
        lifecycle = self.lifecycle_manager.create(candidate.fingerprint)
        self.lifecycle_manager.transition(candidate.fingerprint, LifecycleStage.RESEARCH, "evidence_registered", "daily_learning")
        self.lifecycle_manager.transition(candidate.fingerprint, LifecycleStage.VALIDATION, "source_independence_checked", "daily_learning")

        confidence = self._confidence(evidence_items)
        governor_record = self.knowledge_governor.evaluate({
            "id": candidate.fingerprint,
            "title": candidate.title,
            "status": "FACT" if independence["independent_count"] >= 2 else "EVIDENCE",
            "source": candidate.candidate_source,
            "content": contract["learning_objective"],
            "evidence": evidence_ids,
            "references": evidence_ids,
            "confidence": confidence,
        })
        outcome, reason = self._outcome(candidate, independence, governor_record.decision)
        task.evidence = list(evidence_items)
        task.result = {
            "learning_contract": contract,
            "evidence_ids": evidence_ids,
            "source_independence": independence,
            "cross_validation": cross_validation,
            "governor_decision": governor_record.decision,
            "outcome": outcome,
            "reason": reason,
            "governance_boundary": "Validator and Guardian task decisions do not equal knowledge adoption.",
            "no_side_effects": False,
        }
        task.outputs["daily_learning"] = task.result
        self.task_pool.update_task(task)

        if outcome == "adopt":
            active = self.task_pool.claim_task(task.task_id, "daily_learning")
            if not active:
                outcome = "observe"
                reason = "daily_learning_claim_not_acquired"
            else:
                self.lifecycle_manager.transition(candidate.fingerprint, LifecycleStage.CONTRACT, "governor_pass", "daily_learning")
                self.lifecycle_manager.transition(candidate.fingerprint, LifecycleStage.REPOSITORY_CANDIDATE, "adoption_candidate", "daily_learning")
                self.lifecycle_manager.transition(candidate.fingerprint, LifecycleStage.PUBLISHED, "adopted_learning_asset", "daily_learning")
                review = self.task_pool.move_task(task.task_id, "review", actor="daily_learning", reason="cross_validation_completed", task=active)
                approved = self.task_pool.move_task(task.task_id, "approved", actor="daily_learning", reason="knowledge_governor_pass", task=review)
                decision = self.guardian.judge(approved) if approved else {"verdict": "discard"}
                judged_task = self.task_pool.load_task(task.task_id)
                if decision["verdict"] == "discard" or not judged_task or not self.archivist.archive_task(judged_task):
                    outcome = "observe"
                    reason = "task_archive_not_completed"
                else:
                    self.lifecycle_manager.transition(candidate.fingerprint, LifecycleStage.ARCHIVED, "archived_after_adoption", "daily_learning")
                    self.deposition.deposit(
                        judged_task,
                        experience_type="observation",
                        conclusion=contract["learning_objective"],
                        related_concepts=[candidate.candidate_source],
                    )
        else:
            self.lifecycle_manager.transition(candidate.fingerprint, LifecycleStage.GRAVEYARD, reason, "daily_learning")
            self.task_pool.move_task(task.task_id, "rejected", actor="daily_learning", reason=reason, task=task)

        result = {
            "date": run_date,
            "mode": mode,
            "outcome": outcome,
            "reason": reason,
            "candidate": candidate.title,
            "task_id": task.task_id,
            "execution_deferred_by": blocking_task.task_id if blocking_task else None,
            "evidence_ids": evidence_ids,
            "source_independence": independence,
            "cross_validation": cross_validation,
            "governor_decision": governor_record.decision,
            "lifecycle_stage": self.lifecycle_manager.get(candidate.fingerprint).current_stage.value,
            "no_side_effects": False,
        }
        self._record_daily_result(run_date, result)
        return result

    @staticmethod
    def _is_legacy_blocked_result(existing: Any) -> bool:
        if not isinstance(existing, dict):
            return False
        if (
            existing.get("outcome") == "NO_VALID_LEARNING_TARGET"
            and existing.get("reason")
            == "no_evidence_backed_internal_candidate_or_external_candidate"
            and existing.get("candidate_scan_limit") != DAILY_LEARNING_OBSERVATION_LIMIT
        ):
            return True
        if existing.get("reason") != "learning_blocked_by_priority_task":
            return False
        if existing.get("task_id"):
            return False
        return existing.get("outcome") in {
            "NO_VALID_LEARNING_TARGET",
            "LEARNING_CANDIDATE_DEFERRED",
        }

    def _blocking_task(self) -> Optional[Any]:
        for status in self.blocking_statuses:
            for priority in self.blocking_priorities:
                tasks = self.task_pool.list_tasks(
                    status=status,
                    priority=priority,
                    limit=100,
                )
                for task in tasks:
                    admission = task.outputs.get("admission", {})
                    if isinstance(admission, dict) and admission.get("source_type") == "learning":
                        continue
                    return task
        return None

    def _choose_candidate(
        self,
        allow_external: bool = True,
    ) -> Tuple[str, Optional[Tuple[Any, List[Dict[str, Any]]]]]:
        for source in self.internal_candidate_sources:
            candidates = source() or []
            if candidates:
                return "internal", candidates[0]
        if not allow_external or self.external_discoverer is None:
            return "none", None
        objective = "Find a currently evidence-backed ACE learning objective not satisfied by internal assets."
        candidates = self.external_discoverer(objective, list(self.source_tiers)) or []
        if candidates:
            return "external", candidates[0]
        return "none", None

    def _create_task(self, candidate, evidence_items: List[Dict[str, Any]]) -> Optional[Any]:
        for task in self.task_pool.list_tasks(limit=10000):
            discovery = task.outputs.get("discovery", {})
            if discovery.get("fingerprint") == candidate.fingerprint:
                return task
        learning_candidate = self._candidate_with_evidence(candidate, evidence_items)
        original_sources = self.discovery.candidate_sources
        self.discovery.candidate_sources = [lambda: [learning_candidate]]
        try:
            discovered = self.discovery.discover(allow_existing_work=True)
        finally:
            self.discovery.candidate_sources = original_sources
        observation_id = discovered.get("observation_id")
        if discovered.get("status") != "observed" or not observation_id:
            return None
        converted = self.converter.convert()
        for detail in converted["details"]:
            if detail.get("obs_id") == observation_id and detail.get("task_id"):
                return self.task_pool.load_task(detail["task_id"])
        return None

    def _candidate_with_evidence(
        self,
        candidate: DiscoveryCandidate,
        evidence_items: List[Dict[str, Any]],
    ) -> DiscoveryCandidate:
        metadata = dict(candidate.metadata or {})
        metadata["autonomous_maintenance"] = {
            "why_now": candidate.reason,
            "evidence": list(evidence_items),
            "priority": candidate.priority,
            "expected_result": candidate.completion_criteria,
            "verification_method": candidate.verification_method,
            "risk": "Bounded evidence-backed learning task; no external action is authorized.",
            "source": candidate.candidate_source,
            "estimated_scope": candidate.objective,
        }
        return DiscoveryCandidate(
            fingerprint=candidate.fingerprint,
            title=candidate.title,
            description=candidate.description,
            reason=candidate.reason,
            objective=candidate.objective,
            completion_criteria=candidate.completion_criteria,
            verification_method=candidate.verification_method,
            priority=candidate.priority,
            task_type=candidate.task_type,
            severity=candidate.severity,
            candidate_source=candidate.candidate_source,
            metadata=metadata,
        )

    def _learning_contract(self, candidate) -> Dict[str, Any]:
        metadata = candidate.metadata or {}
        contract = metadata.get("learning", {})
        return dict(contract) if isinstance(contract, dict) else {}

    def _valid_contract(self, contract: Dict[str, Any]) -> bool:
        if not self.required_contract_fields.issubset(contract):
            return False
        for field in self.required_contract_fields:
            value = contract[field]
            if isinstance(value, str) and value.strip():
                continue
            if isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value):
                continue
            return False
        return True

    def _register_evidence(self, items: List[Dict[str, Any]]) -> List[str]:
        evidence_ids = []
        for item in items:
            registered = self.evidence_registry.register(
                source=item.get("source", "unknown"),
                content=item.get("content", ""),
                confidence=item.get("confidence", 0.0),
                author=item.get("author", ""),
                source_location=item.get("source_location", ""),
                metadata=item.get("metadata", {}),
            )
            evidence_ids.append(registered.id)
        return evidence_ids

    def _source_independence(self, items: List[Dict[str, Any]]) -> Dict[str, Any]:
        qualifying = []
        groups = set()
        for item in items:
            metadata = item.get("metadata", {})
            directness = metadata.get("directness", "derived")
            if (
                directness in {"repost", "search_result"}
                or metadata.get("lineage_observable") is False
            ):
                continue
            group = metadata.get("independence_group") or metadata.get("upstream_identity")
            if group and group not in {"UNVERIFIED", "UNVERIFIED_AGGREGATE"}:
                groups.add(group)
                qualifying.append(group)
        return {
            "independent_count": len(groups),
            "independence_groups": sorted(groups),
            "qualifying_evidence_count": len(qualifying),
            "excluded_lineage": [
                item.get("metadata", {}).get("independence_group", "UNVERIFIED")
                for item in items
                if (
                    item.get("metadata", {}).get("lineage_observable") is False
                    or item.get("metadata", {}).get("independence_group")
                    in {"UNVERIFIED", "UNVERIFIED_AGGREGATE"}
                )
            ],
            "excluded_directness": [
                item.get("metadata", {}).get("directness", "derived")
                for item in items
                if item.get("metadata", {}).get("directness", "derived") in {"repost", "search_result"}
            ],
        }

    def _cross_validate(self, candidate, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources = {"local": [], "tg": [], "external": []}
        for item in items:
            metadata = item.get("metadata", {})
            source = metadata.get("cross_validation_source", "external")
            if source not in sources:
                source = "external"
            content = item.get("content", "")
            sources[source].append({
                "topics": [candidate.fingerprint],
                "content": content,
                "summary": content[:200],
                "path": item.get("source_location", ""),
                "mtime": item.get("metadata", {}).get("retrieved_at", ""),
            })
        return CrossValidator(sources).validate_all()

    def _confidence(self, items: List[Dict[str, Any]]) -> float:
        values = [float(item.get("confidence", 0.0)) for item in items]
        return mean(values) if values else 0.0

    def _outcome(self, candidate, independence: Dict[str, Any], governor_decision: str) -> Tuple[str, str]:
        if self._has_adopted_title(candidate.title):
            return "observe", "duplicate_learning_asset"
        if independence["independent_count"] < 2:
            return "observe", "insufficient_independent_evidence"
        if governor_decision == AdmissionDecision.PASS:
            return "adopt", "knowledge_governor_pass"
        if governor_decision == AdmissionDecision.REJECT:
            return "reject", "knowledge_governor_reject"
        return "observe", f"knowledge_governor_{governor_decision}"

    def _has_adopted_title(self, title: str) -> bool:
        for result_file in self.results_dir.glob("*.json"):
            try:
                result = json.loads(result_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if result.get("outcome") == "adopt" and result.get("candidate") == title:
                return True
        return False

    def _load_result(self, run_date: str) -> Optional[Dict[str, Any]]:
        path = self.results_dir / f"{run_date}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def _record_daily_result(self, run_date: str, result: Dict[str, Any]) -> None:
        path = self.results_dir / f"{run_date}.json"
        result.setdefault("candidate_scan_limit", DAILY_LEARNING_OBSERVATION_LIMIT)
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
