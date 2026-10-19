"""Durable diagnosis and recovery routing for data-admission blockers.

This module neither relaxes Phase Two nor performs network work.  It turns a
current capability matrix into a bounded, source-specific recovery contract
so a recurring ``NOT_ADMITTED`` state is not mistaken for progress.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


REQUIRED_OPERATIONS = ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index")

# ``RECOVERY_VERIFICATION_DUE`` saturates at three unchanged observations, so a
# blocker that never moves is indistinguishable from one that just appeared:
# by 2026-10-15 the same fingerprint had repeated 5,421 times while every window
# still routed the identical research action.  A stall band makes "no progress
# for a long time" a distinct, actionable fact instead of more of the same.
STALL_THRESHOLD = 96
"""Unchanged observations before a stuck blocker is treated as stalled.

Chosen above the observation cadence of one trading day (~96 windows/day across
the daily windows) so ordinary intraday repetition stays ``VERIFICATION_DUE``
and only a genuinely non-moving blocker escalates.
"""

STALL_ACTION = "escalate_stalled_blocker_to_admission_and_experience_review"
"""Action taken once a blocker is stalled: stop repeating the dead research path."""
RESEARCH_CANDIDATE_SOURCES = {
    "quote": ("sina_direct", "tencent_direct"),
    "daily_kline": ("tencent_direct", "baostock"),
    "minute_kline_1m": ("sina_direct", "tencent_direct"),
    "minute_kline_5m": ("tencent_direct", "baostock"),
    "index": ("sina_direct", "tencent_direct"),
}


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


class DataAdmissionRecovery:
    """Single-writer, evidence-only recovery ledger under the existing data dir."""

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.path = self.data_dir / "stock_data_evidence" / "data_admission_recovery_latest.json"

    @staticmethod
    def _read(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _write(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def escalate(self, report: Mapping[str, Any], task_pool: Any) -> dict[str, Any]:
        """Route a stalled blocker into the existing review path, idempotently.

        A stalled blocker must stop replaying the research action that already
        failed.  This admits one review task through the existing TaskPool and
        admission-duplicate gate, keyed on the blocker fingerprint, so repeated
        calls inside one stall cycle cannot create more than one task.  It never
        opens the admission gate and never calls a provider.
        """
        outcome: dict[str, Any] = {
            "attempted": False,
            "created": False,
            "task_id": "",
            "reason": "",
        }
        if not report.get("stalled"):
            outcome["reason"] = "not_stalled"
            return outcome
        if task_pool is None:
            outcome["reason"] = "no_task_pool_available"
            return outcome
        escaped = [str(name) for name in report.get("unresolved_operations", [])]
        if not escaped:
            outcome["reason"] = "nothing_unresolved"
            return outcome

        fingerprint = str(report.get("blocker_fingerprint") or "")
        outcome["attempted"] = True

        def _spent_same_cycle(task: Any) -> bool:
            """A review of this fingerprint that already circuit-broke."""
            outputs = getattr(task, "outputs", {}) or {}
            record = outputs.get("admission", {}) if isinstance(outputs, Mapping) else {}
            if fingerprint not in json.dumps(record, ensure_ascii=False, default=str):
                return False
            return bool(outputs.get("terminal_non_convergent"))

        # A spent review is left in ``blocked``, which ``create_task`` does not
        # deduplicate, so it would otherwise be returned as the "duplicate" of
        # every later escalation and the corrected review could never run.
        try:
            spent = sum(
                1 for task in task_pool.list_tasks(limit=10000) if _spent_same_cycle(task)
            )
        except Exception:
            spent = 0
        generation = spent + 1

        # The generation is a diagnostic, not an identity.
        #
        # This used to be spliced into operation_intent, which participates in
        # create_task's duplicate detection - and so guaranteed the opposite of
        # what this module exists to do. Measured on 2026-10-19: one blocker,
        # one fingerprint, thirty-five tasks, gen1 through gen35, created every
        # thirty minutes since 2026-10-16, all sitting in blocked waiting for a
        # repair that each one had already failed to produce. The circuit breaker
        # detected the stall by building a task that stalls identically.
        #
        # The fix is not to weaken the gate: a genuinely new stall cycle has a
        # new fingerprint and still admits its own review. It is to stop making
        # the retry distinguishable from the attempt it is retrying.
        operation_intent = "review_stalled_data_admission_blocker"

        # source_ref is the fingerprint: a new fingerprint is a genuinely new
        # stall cycle and may admit a new review; the same one folds into the
        # existing task through create_task's admission duplicate gate.
        admission = {
            "source_type": "system_observation",
            "source_ref": f"data-admission-stall:{fingerprint}",
            "source_identity": fingerprint,
            "operation_intent": operation_intent,
            "why_now": (
                f"{report.get('consecutive_unchanged_observations')} consecutive observations "
                f"left the same blocker unresolved, so repeating the research action is not working."
            ),
            "evidence": [{
                "blocker_fingerprint": fingerprint,
                "consecutive_unchanged_observations": report.get("consecutive_unchanged_observations"),
                "unresolved_operations": escaped,
                # How many reviews of this fingerprint have already circuit-broken.
                # Kept as evidence, deliberately outside operation_intent: the
                # count is what a reader needs, and putting it in the intent is
                # what turned this into a 35-generation retry loop.
                "prior_circuit_broken_reviews": spent,
                "prior_action": "research_candidate_source_evidence_without_changing_the_existing_refresh_or_admission",
                # Concrete external targets so the researcher has something to
                # actually measure, rather than re-reading this same record.
                "research_candidate_sources": {
                    name: list((report.get("operations") or {}).get(name, {}).get("research_candidate_sources") or [])
                    for name in escaped
                },
            }],
            "expected_result": (
                "Per unresolved operation, either a named candidate source with isolated probe "
                "evidence and an independent cross-validation partner, or the exact external "
                "condition that is missing (unreachable endpoint, absent credential, no "
                "independent second lineage) with the trigger that would allow a retry."
            ),
            # Verification must name an object outside this task.  Measured over
            # 1,510 pool tasks, review whose verification re-reads its own
            # admission evidence terminates non-convergent 43.2% of the time
            # versus 10.0% when it rechecks an external artifact, because a
            # self-referential check can only ever rediscover the evidence the
            # task was born with.  Point at the probe benchmark instead.
            "verification_method": (
                "Re-run the read-only probe benchmark and compare per-source results "
                "against stock_data_benchmark_latest.json, then check each affected "
                "endpoint directly; the evidence must come from outside this task record."
            ),
            "external_evidence_ref": str(
                self.data_dir / "stock_data_evidence" / "stock_data_benchmark_latest.json"
            ),
            "risk": "Research-only. Must not open the admission gate, fabricate a source, or produce a recommendation.",
            "estimated_scope": "one stalled blocker cycle",
        }
        try:
            existing = [
                task for task in task_pool.list_tasks(limit=10000)
                if task.status not in {"archived", "graveyard", "rejected"}
                and "data-admission-stall" in json.dumps(
                    (getattr(task, "outputs", {}) or {}).get("admission", {}), ensure_ascii=False, default=str
                )
            ]
            before = {
                task.task_id for task in existing
                if fingerprint in json.dumps(
                    (getattr(task, "outputs", {}) or {}).get("admission", {}), ensure_ascii=False, default=str
                )
                and not _spent_same_cycle(task)
            }
            # Every id present before the call, spent or not. The created flag
            # has to be answerable from the pool, not inferred from which subset
            # of it happened to be unspent.
            ids_before_call = {task.task_id for task in task_pool.list_tasks(limit=10000)}
            task = task_pool.create_task(
                title=f"停滞根因复核: 数据准入 {len(escaped)} 项无进展",
                hypothesis=(
                    "该阻塞已长期不变，研究动作本身可能无效；需要复核候选来源、独立交叉验证与生产供给链的缺失条件。"
                ),
                creator="data_admission_stall_escalation",
                priority="high",
                # ``task_type:`` is not decoration: ``_model_task_type`` reads it
                # to pick the task profile, and an untagged task resolves to an
                # empty profile with no ``model_enabled``, so
                # ``_record_model_execution`` returns None before any model is
                # called.  RQ-20261016-001 and -007 carried no task_type tag and
                # the researcher ran with no model route and no local artifact,
                # reporting "0 evidence" on every cycle.  ``reasoning`` is the
                # profile whose route resolves to a provider that answers on
                # this host (verified: opencode_cli returned PROBE-OK in 8.8s).
                tags=["data-admission", "stalled", "blocker-review", "task_type:reasoning"],
                admission=admission,
                outputs={"stall_fingerprint": fingerprint},
            )
        except Exception as error:  # never let escalation break the observation path
            outcome["reason"] = f"escalation_failed:{type(error).__name__}"
            return outcome

        outcome["task_id"] = str(getattr(task, "task_id", "") or "")
        # Answer "did this call create anything" from the pool, not from which
        # subset of it was unspent. The old flag was derived from a `before` set
        # that deliberately excluded spent reviews, so once a review had
        # circuit-broken every later escalation reported created=True while
        # create_task returned the *same* id and the pool stayed at one record.
        # Nothing was escalated; only the report said otherwise - which is how 35
        # identical generations accumulated unnoticed.
        outcome["created"] = outcome["task_id"] not in ids_before_call
        if outcome["created"]:
            outcome["reason"] = "admitted"
        else:
            outcome["reason"] = "already_admitted_same_fingerprint"
            outcome["folded_into_existing"] = True
            outcome["prior_circuit_broken_reviews"] = spent
        return outcome

    def build(self, matrix: Mapping[str, Any], *, observed_at: str | None = None) -> dict[str, Any]:
        admission = matrix.get("phase_two_admission", {}) if isinstance(matrix, Mapping) else {}
        operations = admission.get("core_operations", {}) if isinstance(admission, Mapping) else {}
        operation_rows: dict[str, Any] = {}
        unresolved: list[str] = []
        for operation in REQUIRED_OPERATIONS:
            detail = operations.get(operation, {}) if isinstance(operations, Mapping) else {}
            detail = detail if isinstance(detail, Mapping) else {}
            sources = sorted(str(item) for item in detail.get("production_sources", []) if str(item))
            groups = sorted(set(str(item) for item in detail.get("independence_groups", []) if str(item)))
            cross_validated = detail.get("has_independent_cross_validation") is True
            blockers: list[str] = []
            if not sources:
                blockers.append("NO_QUALIFIED_PRODUCTION_SOURCE")
            if len(groups) < 2 or not cross_validated:
                blockers.append("INDEPENDENT_CROSS_VALIDATION_MISSING")
            status = "READY" if not blockers else "BLOCKED"
            if blockers:
                unresolved.append(operation)
            operation_rows[operation] = {
                "status": status,
                "blockers": blockers,
                "qualified_sources": sources,
                "independence_groups": groups,
                "research_candidate_sources": list(RESEARCH_CANDIDATE_SOURCES[operation]),
                "verification": "a candidate source needs isolated evidence and a fresh admission review before it can enter the existing open-validation refresh",
            }
        blocker_fingerprint = _digest({name: row["blockers"] for name, row in operation_rows.items()})
        prior = self._read(self.path)
        repeated = prior.get("blocker_fingerprint") == blocker_fingerprint
        consecutive = int(prior.get("consecutive_unchanged_observations", 0)) + 1 if repeated else 1
        if unresolved and consecutive >= STALL_THRESHOLD:
            state = "STALLED_NO_PROGRESS"
        elif unresolved and consecutive >= 3:
            state = "RECOVERY_VERIFICATION_DUE"
        elif unresolved:
            state = "RECOVERY_IN_PROGRESS"
        else:
            state = "ADMISSION_READY"
        stalled = state == "STALLED_NO_PROGRESS"
        if not unresolved:
            next_action = "keep_existing_admission_gate_and_revalidate_candidates"
        elif stalled:
            # The repeated research action is proven ineffective for this
            # fingerprint; escalate instead of re-running it every window.
            next_action = STALL_ACTION
        else:
            next_action = "research_candidate_source_evidence_without_changing_the_existing_refresh_or_admission"
        report = {
            "contract_version": "ace.data_admission_recovery.v1",
            "recorded_at": observed_at or datetime.now(timezone.utc).isoformat(),
            "phase_two_status": admission.get("status", "NOT_RECORDED") if isinstance(admission, Mapping) else "NOT_RECORDED",
            "recovery_status": state,
            "unresolved_operations": unresolved,
            "operations": operation_rows,
            "blocker_fingerprint": blocker_fingerprint,
            "consecutive_unchanged_observations": consecutive,
            "stall_threshold": STALL_THRESHOLD,
            "stalled": stalled,
            "next_action": next_action,
            "side_effects": {"network_called": False, "taskpool_mutated": False, "admission_changed": False, "recommendation_created": False},
            "semantics": "This ledger explains and routes evidence repair; it never treats a planned probe or recovery status as data admission.",
        }
        self._write(self.path, report)
        return report
