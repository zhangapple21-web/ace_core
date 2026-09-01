"""Product-facing daily shift ledger built from existing production evidence."""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from core.finance_shift_contract import build_evaluation_slots, build_postmortem_status
from core.paper_evaluation_journal import PaperEvaluationJournal


FINANCE_WINDOW_ORDER = (
    "morning_observation",
    "open_validation",
    "midday_review",
    "close_review",
    "next_day_watchlist",
)


class DailyShift:
    def __init__(self, task_pool, data_dir: str):
        self.task_pool = task_pool
        self.data_dir = Path(data_dir)
        self.json_path = self.data_dir / "daily_shift_latest.json"
        self.md_path = self.data_dir / "daily_shift_latest.md"

    @staticmethod
    def _read(path: Path) -> Dict[str, Any]:
        # The daemon writes state atomically.  On Windows an immediate reader
        # can still encounter a short sharing violation during replacement;
        # retry once so a Daily Shift does not silently erase live identity.
        for attempt in range(2):
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
                return value if isinstance(value, dict) else {}
            except (OSError, json.JSONDecodeError):
                if attempt == 0:
                    time.sleep(0.01)
        return {}

    def _daily_learning_summary(self, daily_learning: Dict[str, Any]) -> Dict[str, Any]:
        """Show the retained daily-learning snapshot alongside live task state.

        The daily result is immutable evidence of what the learner observed at
        that time.  Its ``queued_research`` value must not be presented as the
        current lifecycle once the existing TaskPool has subsequently consumed
        or archived that task.
        """
        summary = {
            key: daily_learning.get(key)
            for key in (
                "mode",
                "outcome",
                "reason",
                "candidate",
                "task_id",
                "execution_deferred_by",
                "lifecycle_stage",
                "external_learning",
            )
            if key in daily_learning
        }
        task_id = str(daily_learning.get("task_id", "")).strip()
        task = None
        if task_id:
            try:
                task = self.task_pool.load_task(task_id)
            except (OSError, ValueError):
                task = None
        summary["task_runtime"] = {
            "task_id": task_id or None,
            "status": task.status if task is not None else ("NOT_FOUND" if task_id else "NOT_RECORDED"),
            "updated_at": task.updated_at if task is not None else None,
            "recorded_snapshot_outcome": daily_learning.get("outcome"),
        }
        return summary

    def _free_zone_model_shift_summary(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Report persisted research evidence without converting it to runtime proof."""
        workspace_root = self.data_dir.parents[3]
        persisted = self._read(workspace_root / "07_SANDBOX" / "free_research" / "model_shift_state.json")
        last_shift = persisted.get("last_shift") if isinstance(persisted.get("last_shift"), dict) else {}
        daemon_last = state.get("free_zone_model_shift_last") if isinstance(state.get("free_zone_model_shift_last"), dict) else {}
        if last_shift:
            absence = {"status": "NOT_ABSENT"}
        elif daemon_last:
            absence = {
                "status": "DAEMON_SHIFT_HAS_NO_PERSISTED_RECEIPT",
                "reason": "inspect_daemon_lifecycle_status_before_inferring_a_provider_failure",
            }
        else:
            absence = {
                "status": "NO_RESEARCH_RECEIPT_OR_DAEMON_SHIFT_OBSERVATION",
                "reason": "unknown_until_the_existing_daemon_adopts_the_shift_and_records_its_first_lifecycle_result",
            }
        return {
            "persisted_receipt": {
                key: last_shift.get(key)
                for key in ("outcome", "dual_source_status", "model_execution_realm", "provider", "seed_hash", "record_hash", "recorded_at", "invitation", "raw_content_retained", "production_integration")
                if key in last_shift
            },
            "daemon_lifecycle_observation": {
                key: daemon_last.get(key)
                for key in ("status", "at")
                if key in daemon_last
            },
            "runtime_adoption_status": "DAEMON_LIFECYCLE_RECORDED" if daemon_last else "DAEMON_NOT_YET_OBSERVED",
            "absence_explanation": absence,
            "semantics": "A persisted receipt proves a bounded research turn only. Daemon adoption requires a matching daemon lifecycle observation; neither promotes research or alters production gates.",
        }

    @staticmethod
    def _finance_window_coverage(window: Dict[str, Any]) -> Dict[str, Any]:
        """Expose retained same-day windows without scheduling or observing anew."""
        daily_windows = window.get("daily_windows")
        daily_windows = daily_windows if isinstance(daily_windows, dict) else {}
        observed = [name for name in FINANCE_WINDOW_ORDER if isinstance(daily_windows.get(name), dict)]
        missing = [name for name in FINANCE_WINDOW_ORDER if name not in observed]
        return {
            "observed_windows": observed,
            "missing_windows": missing,
            "records": {
                name: {
                    key: daily_windows[name].get(key)
                    for key in ("observed_at", "window_status", "finance_status", "task_created", "model_call")
                    if key in daily_windows[name]
                }
                for name in observed
            },
            "source": "finance_work_windows_latest.daily_windows",
            "observation_authority": False,
        }

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        """Persist a shift atomically so readers never observe a partial ledger."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def build(self, date: Optional[str] = None, *, daemon_state_path: Optional[str] = None) -> Dict[str, Any]:
        day = date or datetime.now(timezone.utc).date().isoformat()
        state = self._read(Path(daemon_state_path)) if daemon_state_path else {}
        growth = self._read(self.data_dir / "daily_growth_latest.json")
        daily_learning_record = self._read(
            self.data_dir / "memory" / "daily_learning" / "daily_results" / f"{day}.json"
        )
        daily_learning = self._daily_learning_summary(daily_learning_record)
        window = self._read(self.data_dir / "finance_work_windows_latest.json")
        sentiment = self._read(self.data_dir / "public_sentiment_latest.json")
        market_context = self._read(self.data_dir / "market_context_latest.json")
        research_brief = self._read(self.data_dir / "daily_research_brief_latest.json")
        continuity = self._read(self.data_dir / "continuity" / "continuity_latest.json")
        free_zone_model_shift = self._free_zone_model_shift_summary(state)
        paper_evaluation = PaperEvaluationJournal(str(self.data_dir)).summary()
        refresh = window.get("data_refresh") if isinstance(window.get("data_refresh"), dict) else {}
        if refresh.get("status") == "already_attempted_for_window":
            initial = refresh.get("initial_result")
            refresh_evidence = initial if isinstance(initial, dict) else refresh
        else:
            refresh_evidence = refresh
        counts = {}
        transitions = {key: 0 for key in ("claim", "research", "validation", "approved", "archived")}
        for task in self.task_pool.list_tasks(limit=10000):
            counts[task.status] = counts.get(task.status, 0) + 1
            for event in task.audit_log or []:
                if not isinstance(event, dict):
                    continue
                if event.get("event") != "transition":
                    continue
                if not str(event.get("at", "")).startswith(day):
                    continue
                pair = (event.get("from"), event.get("to"), event.get("reason"))
                if pair == ("pending", "active", "lease_claimed"):
                    transitions["claim"] += 1
                elif event.get("to") == "review":
                    transitions["research"] += 1
                if event.get("from") == "review" and event.get("actor") == "validator":
                    transitions["validation"] += 1
                if event.get("to") == "approved":
                    transitions["approved"] += 1
                if event.get("to") == "archived":
                    transitions["archived"] += 1
        report = {
            "schema_version": 1,
            "date": day,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "daemon": {
                "pid": state.get("pid"),
                "run_id": state.get("run_id"),
                "cycle_status": state.get("cycle_progress", {}).get("cycle_status"),
                "stop_reason": state.get("cycle_progress", {}).get("stop_reason"),
            },
            "windows": window,
            "finance_live_refresh": {
                key: refresh_evidence.get(key)
                for key in ("status", "completed_at", "sources", "operations", "refreshed_probe_count")
                if key in refresh_evidence
            },
            "hourly_service": self._read(self.data_dir / "hourly_task_service_latest.json"),
            "completed_work": {
                "outcome": growth.get("outcome"),
                "archived_task_count": growth.get("archived_task_count", 0),
                "today_cumulative_archived_task_count": growth.get("archived_task_count", 0),
                "archived_model_task_count": growth.get("archived_model_task_count", 0),
                "verified_outcome_count": growth.get("verified_outcome_count", 0),
                "verified_outcomes": growth.get("verified_outcomes", []),
                "attempted_production_model_call_count": growth.get("attempted_production_model_call_count", 0),
                "successful_production_model_call_count": growth.get("successful_production_model_call_count", growth.get("production_model_call_count", 0)),
                "production_model_call_count": growth.get("production_model_call_count", 0),
                "production_model_call_semantics": growth.get("production_model_call_semantics", {}),
                "experience_deposition": growth.get("verified_outcome_count", 0) > 0,
                "archive_semantics": "all archives and model calls are lifecycle telemetry; only a verified outcome receipt can support a growth or reusable-result claim",
            },
            "daily_learning": daily_learning,
            "model_performance": growth.get("model_performance_ledger", {}),
            "taskpool": {
                "status_counts": counts,
                "current_status_counts": counts,
                "lifecycle_transitions": transitions,
                "today_lifecycle_transitions": transitions,
                "current_snapshot_semantics": "statuses at Daily Shift build time; not daily totals",
                "daily_transition_semantics": "transitions observed for this date across retained task audit logs",
            },
            "finance_window_coverage": self._finance_window_coverage(window),
            "finance_status": growth.get("finance_status", window.get("finance_status", "UNKNOWN")),
            "public_sentiment": {
                key: sentiment.get(key)
                for key in ("status", "window", "independent_content_source_count", "admission_ready", "reason")
                if key in sentiment
            },
            "market_context": {
                key: market_context.get(key)
                for key in ("research_status", "recommendation_authority", "market_data_admission_changed", "cross_validation_questions")
                if key in market_context
            },
            "market_review": {
                key: window.get(key)
                for key in ("market_state", "counter_evidence", "invalidating_conditions", "next_validation")
                if key in window
            },
            # These are read-only reporting slots.  Candidate producers must
            # meet the complete contract; a zero count is an expected honest
            # result, not a signal to create a task or call a model.
            "finance_evaluation": build_evaluation_slots(
                research_brief.get("candidate_cards", [])
                if isinstance(research_brief.get("candidate_cards"), list)
                else []
            ),
            "paper_evaluation_journal": paper_evaluation,
            "continuity_audit": {
                key: continuity.get(key)
                for key in ("recorded_at", "continuity_status", "claim_level", "reason_codes", "migration")
                if key in continuity
            },
            "free_zone_model_shift": free_zone_model_shift,
            "finance_postmortem": {
                "status": paper_evaluation["postmortem_status"],
                "eligible_record_count": paper_evaluation["outcome_receipt_count"],
                "rule": "only_explicit_evidence_backed_outcome_receipts_may_be_reviewed",
            },
            "advisor_status": "BLOCKED",
            "risk_status": "NOT_READY",
            "owner_tg": "OFF",
            "next_observation": window.get("next_action"),
            "no_synthetic_work": True,
        }
        self._atomic_write_text(
            self.json_path,
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        )
        self._atomic_write_text(
            self.md_path,
            "\n".join([
                f"# ACE DAILY SHIFT — {day}", "",
                f"- Daemon: PID `{report['daemon']['pid']}`, run `{report['daemon']['run_id']}`",
                f"- Cycle: `{report['daemon']['cycle_status']}` / `{report['daemon']['stop_reason']}`",
                f"- Finance: `{report['finance_status']}`; window `{window.get('window_status', 'UNKNOWN')}`",
                f"- Finance windows observed today: `{report['finance_window_coverage']['observed_windows']}`; missing `{report['finance_window_coverage']['missing_windows']}`; source `{report['finance_window_coverage']['source']}`",
                f"- Public sentiment: `{report['public_sentiment'].get('status', 'NOT_OBSERVED')}`; independent content sources `{report['public_sentiment'].get('independent_content_source_count', 0)}`; admission-ready `{report['public_sentiment'].get('admission_ready', False)}`",
                f"- Market context: `{report['market_context'].get('research_status', 'NOT_RECORDED')}`; recommendation authority `{report['market_context'].get('recommendation_authority', False)}`; pending cross-validation `{len(report['market_context'].get('cross_validation_questions', []))}`",
                f"- Market review: `{report['market_review'].get('market_state', 'NOT_RECORDED')}`; counter-evidence `{len(report['market_review'].get('counter_evidence', []))}` items; invalidating conditions `{len(report['market_review'].get('invalidating_conditions', []))}`; next validation recorded",
                f"- Evaluation slots: target `{report['finance_evaluation']['evaluation_pick_target']}`, eligible `{report['finance_evaluation']['evaluation_pick_count']}`, status `{report['finance_evaluation']['status']}`; publication authority `{report['finance_evaluation']['publication_authority']}`",
                f"- Finance post-mortem: `{report['finance_postmortem']['status']}`; eligible prior records `{report['finance_postmortem']['eligible_record_count']}`",
                f"- Live data refresh: `{report['finance_live_refresh'].get('status', 'NOT_RUN')}`; operations `{report['finance_live_refresh'].get('operations', [])}`; sources `{report['finance_live_refresh'].get('sources', [])}`",
                f"- Execution and outcomes: `{report['completed_work']['today_cumulative_archived_task_count']}` archived records, `{report['completed_work']['archived_model_task_count']}` admitted model-task records; `{report['completed_work']['attempted_production_model_call_count']}` attempted / `{report['completed_work']['successful_production_model_call_count']}` successful production model calls; independently verified outcomes `{report['completed_work']['verified_outcome_count']}`",
                f"- Model performance: `{report['model_performance'].get('group_count', 0)}` groups, shadow-only `{report['model_performance'].get('shadow_only', True)}`",
                f"- Daily learning: recorded `{report['daily_learning'].get('outcome', 'NOT_RECORDED')}`; task `{report['daily_learning'].get('task_runtime', {}).get('task_id', 'NOT_RECORDED')}` currently `{report['daily_learning'].get('task_runtime', {}).get('status', 'NOT_RECORDED')}`; external `{report['daily_learning'].get('external_learning', {}).get('status', 'NOT_RECORDED')}`",
                f"- TaskPool current snapshot: `{counts}` (not daily totals)",
                f"- TaskPool transitions today: `{transitions}`",
                f"- Continuity audit: `{report['continuity_audit'].get('continuity_status', 'NOT_RECORDED')}` / `{report['continuity_audit'].get('claim_level', 'NOT_RECORDED')}`; reasons `{report['continuity_audit'].get('reason_codes', [])}`",
                f"- Free Zone local/cloud research: `{report['free_zone_model_shift']['persisted_receipt'].get('dual_source_status', 'NOT_RECORDED')}`; daemon lifecycle observation `{report['free_zone_model_shift']['daemon_lifecycle_observation'].get('status', 'NOT_RECORDED')}`; no production promotion",
                "- Advisor: `BLOCKED`; Risk: `NOT_READY`; Owner TG: `OFF`",
                f"- Next observation: `{report['next_observation']}`",
                "- Synthetic work: `NO`",
                "",
            ]),
        )
        return report
