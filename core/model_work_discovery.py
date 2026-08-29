"""Bounded coordinator for evidence-backed model-work discovery.

This is deliberately not a scheduler or a router.  It gives the existing
DiscoveryMode one backlog-independent opportunity per day and records what
happened.  Candidate creation and admission remain in the existing
DiscoveryMode -> ObservationToTaskConverter -> ModelTaskAdmission path.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set


class ModelWorkDiscovery:
    def __init__(
        self,
        discovery,
        report_path: str,
        evidence_revision_provider: Optional[Callable[[], Any]] = None,
    ):
        self.discovery = discovery
        self.report_path = Path(report_path)
        self.evidence_revision_provider = evidence_revision_provider

    @staticmethod
    def _parse_timestamp(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    def _evidence_revision(self) -> Dict[str, Optional[str]]:
        if self.evidence_revision_provider is None:
            return {"revision": None, "observed_at": None, "error": None}
        try:
            value = self.evidence_revision_provider()
        except Exception as exc:
            return {
                "revision": None,
                "observed_at": None,
                "error": type(exc).__name__,
            }
        if isinstance(value, dict):
            revision = value.get("revision")
            observed_at = value.get("observed_at")
        else:
            revision = value
            observed_at = None
        return {
            "revision": str(revision) if revision else None,
            "observed_at": str(observed_at) if observed_at else None,
            "error": None,
        }

    def _read_report(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.report_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_report(self, report: Dict[str, Any]) -> None:
        self.report_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.report_path.with_suffix(self.report_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self.report_path)

    def discover_daily(
        self,
        *,
        day: Optional[str] = None,
        allowed_priorities: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        today = day or datetime.now().date().isoformat()
        previous = self._read_report()
        evidence = self._evidence_revision()
        revision = evidence["revision"]
        previous_revision = previous.get("evidence_revision")
        rediscovery_reason = None
        if previous.get("discovery_date") == today:
            if revision and previous_revision == revision:
                outcome = "ALREADY_DISCOVERED_FOR_EVIDENCE_REVISION"
            elif revision and previous_revision and previous_revision != revision:
                rediscovery_reason = "evidence_revision_changed"
            elif revision and not previous_revision:
                observed_at = self._parse_timestamp(evidence["observed_at"])
                recorded_at = self._parse_timestamp(previous.get("recorded_at"))
                if observed_at and recorded_at and observed_at > recorded_at:
                    rediscovery_reason = "new_evidence_after_legacy_report"
                else:
                    outcome = "ALREADY_DISCOVERED_TODAY"
            else:
                # Missing or failed revision evidence must not turn the daily
                # coordinator into an every-cycle task generator.
                outcome = "ALREADY_DISCOVERED_TODAY"
            if rediscovery_reason is None:
                return {
                    "status": "not_run",
                    "outcome": outcome,
                    "discovery_date": today,
                    "evidence_revision": revision,
                    "evidence_revision_error": evidence["error"],
                    "report_path": str(self.report_path),
                    "previous_outcome": previous.get("outcome"),
                }

        result = self.discovery.discover(
            allow_existing_work=True,
            allowed_priorities=allowed_priorities,
        )
        outcome = (
            "MODEL_WORK_CANDIDATE_OBSERVED"
            if result.get("status") == "observed"
            else "NO_VALID_MODEL_WORK"
        )
        report = {
            "schema_version": 2,
            "discovery_date": today,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome,
            "evidence_revision": revision,
            "evidence_observed_at": evidence["observed_at"],
            "evidence_revision_error": evidence["error"],
            "previous_evidence_revision": previous_revision,
            "rediscovery_reason": rediscovery_reason,
            "local_backlog_is_not_a_stop_condition": True,
            # A bounded observation cap prevents recursive discovery.  It is
            # not a quota that must be filled and creates no activity target.
            "candidate_observation_cap": 1,
            "discovery": result,
            "report_path": str(self.report_path),
        }
        self._write_report(report)
        return report

    def record_admission(self, conversion: Dict[str, Any]) -> Dict[str, Any]:
        """Attach the existing converter decision to today's discovery report."""
        report = self._read_report()
        if not report:
            return {"status": "not_recorded", "reason": "discovery_report_missing"}
        funnel = {
            "candidate_count": int(conversion.get("candidate_count", 0)),
            "eligible_count": int(conversion.get("eligible_count", 0)),
            "rejected_count": int(conversion.get("rejected_count", 0)),
            "reasoning_tasks_created": int(
                conversion.get("reasoning_tasks_created", 0)
            ),
            "model_tasks_created": int(
                conversion.get("model_tasks_created", conversion.get("reasoning_tasks_created", 0))
            ),
            "task_types_created": dict(conversion.get("task_types_created", {})),
            "rejection_reasons": dict(conversion.get("rejection_reasons", {})),
        }
        if funnel["candidate_count"] == 0 and isinstance(report.get("admission_funnel"), dict):
            observation_id = report.get("discovery", {}).get("observation_id")
            # A missing identity means that discovery observed no candidate.
            # It cannot be used as a join key: legacy/local tasks commonly
            # have no source_obs_id either, and None == None would recover an
            # unrelated historical task into a zero-candidate report.
            if not observation_id:
                report["admission_funnel"] = funnel
                report["admission_recorded_at"] = datetime.now(timezone.utc).isoformat()
                self._write_report(report)
                return funnel
            previous = dict(report["admission_funnel"])
            if previous.get("candidate_count", 0) > 0:
                return previous
            for task in self.discovery.task_pool.list_tasks(limit=10000):
                outputs = task.outputs if isinstance(task.outputs, dict) else {}
                if outputs.get("source_obs_id") != observation_id:
                    continue
                decision = outputs.get("model_task_admission", {})
                task_type = str(decision.get("classification", "reasoning"))
                recovered = {
                    "candidate_count": 1,
                    "eligible_count": 1 if decision.get("eligible") is True else 0,
                    "rejected_count": 0 if decision.get("eligible") is True else 1,
                    "reasoning_tasks_created": 1 if task_type == "reasoning" else 0,
                    "model_tasks_created": 1 if decision.get("eligible") is True else 0,
                    "task_types_created": {task_type: 1} if decision.get("eligible") is True else {},
                    "rejection_reasons": {},
                    "recovered_from_task_id": task.task_id,
                }
                report["admission_funnel"] = recovered
                report["admission_recorded_at"] = datetime.now(timezone.utc).isoformat()
                self._write_report(report)
                return recovered
            return previous
        report["admission_funnel"] = funnel
        report["admission_recorded_at"] = datetime.now(timezone.utc).isoformat()
        self._write_report(report)
        return funnel
