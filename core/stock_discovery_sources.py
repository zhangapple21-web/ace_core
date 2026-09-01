import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .discovery import DiscoveryCandidate
from .stock_data_reliability import load_latest_health


class StockDiscoverySources:
    def __init__(self, observer, base_dir: str, advisor_workspace: Optional[str] = None, evidence_dir: Optional[str] = None):
        self.observer = observer
        self.base_dir = Path(base_dir)
        self.advisor_workspace = Path(advisor_workspace) if advisor_workspace else self._find_workspace()
        self.evidence_dir = Path(evidence_dir) if evidence_dir else self.base_dir / "06_RUNTIME" / "ace" / "data" / "stock_data_evidence"
        self.incident_state_path = self.base_dir / "06_RUNTIME" / "ace" / "data" / "stock_discovery_incidents.json"

    @staticmethod
    def _fingerprint(kind: str, payload: Dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(f"{kind}:{encoded}".encode("utf-8")).hexdigest()

    @staticmethod
    def _read_json(path: Path) -> Dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def _enabled(name: str) -> bool:
        return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _timestamp(value: Any) -> Optional[datetime]:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return None

    def evidence_revision(self) -> Dict[str, Optional[str]]:
        """Return a stable revision for the evidence read by candidate sources.

        Content hashes are used instead of mtimes so copying an unchanged
        artifact cannot reopen discovery.  ``observed_at`` exists only for
        migrating a same-day legacy report that predates newer evidence.
        """
        paths = {
            "benchmark": self.evidence_dir / "stock_data_benchmark_latest.json",
            "lexicon": self.base_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json",
            "public_sentiment": self.base_dir / "06_RUNTIME" / "ace" / "data" / "public_sentiment_latest.json",
        }
        if self.advisor_workspace:
            paths.update({
                "advisor_status": self.advisor_workspace / "05_TOOLS" / "mine_output" / "advisor" / "runner_status.json",
                "advisor_delivery": self.advisor_workspace / "02_MEMORY" / "advisor_delivery.json",
            })

        inputs: Dict[str, Any] = {
            "flags": {
                "auto_run": self._enabled("ACE_STOCK_ADVISOR_AUTO_RUN"),
                "auto_push": self._enabled("ACE_STOCK_ADVISOR_AUTO_PUSH"),
            },
            "artifacts": {},
        }
        observed_times = []
        timestamp_fields = (
            "completed_at",
            "generated_at",
            "updated_at",
            "last_run_time",
            "recorded_at",
        )
        for name, path in paths.items():
            try:
                raw = path.read_bytes()
            except OSError:
                continue
            payload = self._read_json(path)
            inputs["artifacts"][name] = hashlib.sha256(raw).hexdigest()
            for field in timestamp_fields:
                parsed = self._timestamp(payload.get(field))
                if parsed:
                    observed_times.append(parsed)
            summary = payload.get("summary")
            if isinstance(summary, dict):
                parsed = self._timestamp(summary.get("generated_at"))
                if parsed:
                    observed_times.append(parsed)

        if not inputs["artifacts"]:
            return {"revision": None, "observed_at": None}
        revision_payload = json.dumps(inputs, ensure_ascii=False, sort_keys=True)
        observed_at = max(observed_times).isoformat() if observed_times else None
        return {
            "revision": hashlib.sha256(revision_payload.encode("utf-8")).hexdigest(),
            "observed_at": observed_at,
        }

    def _find_workspace(self) -> Optional[Path]:
        configured = os.environ.get("ACE_ADVISOR_WORKSPACE", "").strip()
        candidates = [Path(configured)] if configured else []
        candidates.append(self.base_dir.parent / "mine-seed")
        candidates.append(Path.home() / "ace_workspace" / "mine-seed")
        for candidate in candidates:
            if (candidate / "05_TOOLS" / "advisor" / "daily_runner.py").exists():
                return candidate
        return None

    def _record(self, description: str, state: Dict[str, Any], severity: str, category: str) -> None:
        self.observer.record(
            description=description,
            system_state=state,
            severity=severity,
            source="stock_discovery",
            category=category,
            auto_generated=True,
        )

    def _incidents(self) -> Dict[str, Any]:
        return self._read_json(self.incident_state_path).get("incidents", {})

    def _write_incidents(self, incidents: Dict[str, Any]) -> None:
        self.incident_state_path.parent.mkdir(parents=True, exist_ok=True)
        self.incident_state_path.write_text(json.dumps({"incidents": incidents}, ensure_ascii=False, indent=2), encoding="utf-8")

    def _candidate_for_incident(self, source: str, signature: Dict[str, Any], factory):
        incidents = self._incidents()
        encoded = json.dumps(signature, ensure_ascii=False, sort_keys=True, default=str)
        existing = incidents.get(source, {})
        if existing.get("signature") == encoded and existing.get("open"):
            return []
        recovery_count = int(existing.get("recovery_count", 0)) if existing else 0
        incidents[source] = {
            "open": True,
            "signature": encoded,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "recovery_count": recovery_count,
        }
        self._write_incidents(incidents)
        return [factory(recovery_count)]

    def _resolve_incident(self, source: str) -> None:
        incidents = self._incidents()
        existing = incidents.get(source)
        if not existing or not existing.get("open"):
            return
        existing["open"] = False
        existing["recovered_at"] = datetime.now(timezone.utc).isoformat()
        existing["recovery_count"] = int(existing.get("recovery_count", 0)) + 1
        incidents[source] = existing
        self._write_incidents(incidents)

    def data_health_candidates(self) -> List[DiscoveryCandidate]:
        health = load_latest_health(str(self.evidence_dir))
        if not health.get("available"):
            self._record("A股数据源基准证据尚未生成。", {"stock_data_health": health}, "low", "health")
            return []
        sources = health.get("summary", {}).get("sources", {})
        degraded = {
            name: metrics for name, metrics in sources.items()
            if metrics.get("availability", 0) < 0.8
            or metrics.get("field_completeness", 0) < 0.8
            or metrics.get("consistency", 0) < 0.7
            or metrics.get("coverage", 0) < 0.8
        }
        self._record(
            "A股数据源健康检查已完成。" if not degraded else "A股数据源健康检查发现退化或冲突。",
            {"stock_data_health": health, "degraded_sources": degraded},
            "high" if degraded else "low",
            "health",
        )
        if not degraded:
            self._resolve_incident("stock_data_health")
            return []
        signature = {name: {field: metrics.get(field) for field in ("availability", "field_completeness", "coverage", "consistency")} for name, metrics in degraded.items()}
        evidence = [{
            "source": name,
            "source_ref": f"{health.get('path', 'stock_data_benchmark_latest')}#{name}",
            "content": json.dumps(metrics, ensure_ascii=False, sort_keys=True),
            "confidence": 0.95,
            "author": "stock_data_benchmark",
            "source_location": health.get("path", "stock_data_benchmark_latest"),
            "metadata": {
                "upstream_identity": name,
                "retrieval_method": "runtime_benchmark",
            },
        } for name, metrics in sorted(degraded.items())]
        return self._candidate_for_incident("stock_data_health", signature, lambda recovery_count: DiscoveryCandidate(
            fingerprint=self._fingerprint("stock_data_health", {"signature": signature, "recovery_count": recovery_count}),
            title="核查A股数据源退化与字段冲突",
            description="A股数据源基准发现可用性、完整性、覆盖率或一致性低于生产阈值。",
            reason="关键行情字段不能以低质量回填，需依据原始测量证据确认适用范围与失效条件。",
            objective="复核退化源的端点、血缘、字段缺口和连续稳定性，并更新生产角色建议，不修改荐股策略。",
            completion_criteria="形成字段级失效条件、可用角色和离线降级验证结果。",
            verification_method="复跑固定股票池多轮基准并对比证据哈希、失败原因与健康指标。",
            priority="high",
            task_type="reasoning",
            severity="high",
            candidate_source="stock_data_health",
            metadata={"autonomous_maintenance": {
                "why_now": "Measured source degradation remains after the latest production benchmark.",
                "evidence": evidence,
                "priority": "high",
                "expected_result": "A bounded production-role recommendation for each degraded source.",
                "verification_method": "Compare the latest benchmark probes, lineage, failures, and operation-quality thresholds.",
                "risk": "Research only; do not change Data Health thresholds or publish recommendations.",
                "source": "stock_data_benchmark",
                "estimated_scope": "Reason across the recorded degraded-source evidence only.",
            }},
        ))

    def financial_cross_validation_candidates(self) -> List[DiscoveryCandidate]:
        """Discover one strategic financial cross-check only from fresh evidence.

        This is a research workload, not a recommendation generator.  The
        strategic admission contract deliberately retains the existing three
        independent-reference gate required for a 5.6 route.
        """
        health = load_latest_health(str(self.evidence_dir))
        if not health.get("available"):
            return []
        completed_at = str(health.get("completed_at", ""))
        if not completed_at.startswith(datetime.now(timezone.utc).date().isoformat()):
            return []
        sources = health.get("summary", {}).get("sources", {})
        invalid_lineage = {"", "UNVERIFIED", "UNVERIFIED_AGGREGATE"}
        eligible = []
        seen_groups = set()
        for name, metrics in sorted(sources.items()):
            if not isinstance(metrics, dict):
                continue
            upstream = str(metrics.get("upstream_identity", "")).strip()
            group = str(metrics.get("independence_group", "")).strip()
            if (
                metrics.get("lineage_observable") is not True
                or float(metrics.get("availability", 0) or 0) <= 0
                or upstream in invalid_lineage
                or group in invalid_lineage
                or group in seen_groups
            ):
                continue
            seen_groups.add(group)
            eligible.append((name, metrics))
        if len(eligible) < 3:
            return []
        evidence = [{
            "source": name,
            "source_ref": f"{health.get('path', 'stock_data_benchmark_latest')}#summary.sources.{name}",
            "content": json.dumps(metrics, ensure_ascii=False, sort_keys=True),
            "confidence": 0.8,
            "author": "stock_data_benchmark",
            "source_location": health.get("path", "stock_data_benchmark_latest"),
            "metadata": {
                "upstream_identity": metrics["upstream_identity"],
                "independence_group": metrics["independence_group"],
                "lineage_observable": True,
            },
        } for name, metrics in eligible[:3]]
        # A new calendar date or a refreshed JSON timestamp is not new
        # research material.  Re-open this incident only when the observable
        # lineage roster or one of its admission-relevant health states
        # changes.  Otherwise the same three sources would buy a strategic
        # model turn every morning without a new falsifiable question.
        def health_band(value: Any, threshold: float = 0.8) -> str:
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                return "UNKNOWN"
            if numeric <= 0:
                return "UNAVAILABLE"
            return "AT_OR_ABOVE_THRESHOLD" if numeric >= threshold else "BELOW_THRESHOLD"

        signature = {
            "sources": [
                {
                    "name": name,
                    "upstream_identity": str(metrics.get("upstream_identity", "")),
                    "independence_group": str(metrics.get("independence_group", "")),
                    "lineage_observable": metrics.get("lineage_observable") is True,
                    "availability_band": health_band(metrics.get("availability")),
                    "coverage_band": health_band(metrics.get("coverage")),
                    "consistency_band": health_band(metrics.get("consistency"), 0.7),
                    "field_completeness_band": health_band(metrics.get("field_completeness")),
                }
                for name, metrics in eligible[:3]
            ]
        }
        return self._candidate_for_incident("financial_cross_validation", signature, lambda recovery_count: DiscoveryCandidate(
            fingerprint=self._fingerprint("financial_cross_validation", {"signature": signature, "recovery_count": recovery_count}),
            title="金融状态与技术特征交叉验证",
            description="基于当日多源行情基准证据，交叉验证市场状态、技术特征和失效条件；不输出交易建议。",
            reason="真实 benchmark 已提供至少三个可观察血缘来源，值得由战略模型进行独立反证与研究复核。",
            objective="比较多源市场状态是否一致，识别技术特征假设的支持证据、反证和下一交易日验证条件。",
            completion_criteria="形成市场状态结论、反证、失效条件和下一验证窗口，不生成 BUY/SELL。",
            verification_method="对照三条独立来源证据、技术特征快照和下一观察窗口结果，由 Validator 复核。",
            priority="medium",
            task_type="strategic",
            severity="medium",
            candidate_source="financial_research",
            metadata={
                "model_work_contract": {
                    "value_level": "L2_STRATEGIC",
                    "alternatives": ["sources agree", "sources diverge"],
                    "impact_scope": "financial research workload only",
                    "counter_evidence": "Any freshness, coverage, or cross-source inconsistency invalidates the hypothesis.",
                    "decision_verification": "Recheck at the next observation window against the same lineage refs.",
                },
                "autonomous_maintenance": {
                    "why_now": "Fresh benchmark evidence contains three independently identified lineage groups.",
                    "evidence": evidence,
                    "priority": "medium",
                    "expected_result": "A market-state comparison with counter-evidence and invalidating conditions.",
                    "verification_method": "Validator compares the three source refs and next observation window.",
                    "risk": "Research only; no recommendation, risk approval, or Telegram delivery.",
                    "source": "stock_data_benchmark",
                    "estimated_scope": "One bounded cross-validation study.",
                },
            },
        ))

    def public_sentiment_candidates(self) -> List[DiscoveryCandidate]:
        """Admit public-sentiment research only from retained independent snapshots.

        The collector itself may run in any existing finance window.  This
        source never turns an unavailable or thin landing page into a task;
        it merely makes sufficiently evidenced public observations available
        to the existing strategic-admission contract.
        """
        report_path = self.base_dir / "06_RUNTIME" / "ace" / "data" / "public_sentiment_latest.json"
        report = self._read_json(report_path)
        if report.get("date") != datetime.now().date().isoformat() or report.get("admission_ready") is not True:
            return []
        evidence = []
        groups = set()
        for item in report.get("sources", []):
            if not isinstance(item, dict):
                continue
            group = str(item.get("independence_group", "")).strip()
            source_ref = item.get("source_ref")
            snapshot_path = Path(str(item.get("snapshot_path", "")))
            content_hash = str(item.get("content_hash", ""))
            try:
                snapshot_hash = hashlib.sha256(snapshot_path.read_bytes()).hexdigest()
            except OSError:
                snapshot_hash = ""
            if (
                item.get("status") != "observed"
                or item.get("lineage_observable") is not True
                or item.get("headline_count", 0) < 3
                or item.get("source_timestamp_observable") is not True
                or not group
                or group in groups
                or not isinstance(source_ref, str)
                or not source_ref
                or not content_hash
                or snapshot_hash != content_hash
                or source_ref != f"{snapshot_path}#sha256={content_hash}"
            ):
                continue
            groups.add(group)
            evidence.append({
                "source": item.get("name"),
                "source_ref": source_ref,
                "content": json.dumps({
                    "title": item.get("title"),
                    "description": item.get("description"),
                    "headlines": item.get("headlines", []),
                    "retrieved_at": item.get("retrieved_at"),
                    "source_timestamp_observable": True,
                    "content_hash": item.get("content_hash"),
                    "source_timestamp_observable": True,
                }, ensure_ascii=False, sort_keys=True),
                "confidence": 0.65,
                "author": item.get("upstream_identity"),
                "source_location": item.get("url"),
                "metadata": {
                    "upstream_identity": item.get("upstream_identity"),
                    "independence_group": group,
                    "lineage_observable": True,
                    "retrieved_at": item.get("retrieved_at"),
                    "content_hash": item.get("content_hash"),
                },
            })
        if len(evidence) < 3:
            return []
        signature = {"date": report["date"], "window": report.get("window"), "refs": [item["source_ref"] for item in evidence]}
        return self._candidate_for_incident("public_finance_sentiment", signature, lambda recovery_count: DiscoveryCandidate(
            fingerprint=self._fingerprint("public_finance_sentiment", {"signature": signature, "recovery_count": recovery_count}),
            title="公开金融舆情的跨来源研究复核",
            description="以三条独立、可复核的公开内容快照比较市场叙事的一致与分歧；不输出个股推荐或交易指令。",
            reason="当前观察窗口保留了三条独立上游的可追溯公开内容，值得进行有限的叙事与反证研究。",
            objective="识别来源间共同主题、分歧、证据缺口和下一观察窗口应验证的问题。",
            completion_criteria="形成带来源引用的研究摘要、反证、失效条件和下一次验证问题；不生成 BUY/SELL。",
            verification_method="Validator 对照每条本地快照的哈希、抓取时间和原始内容，检查结论是否超出证据范围。",
            priority="medium",
            task_type="strategic",
            severity="medium",
            candidate_source="public_finance_sentiment",
            metadata={"model_work_contract": {
                "value_level": "L2_STRATEGIC",
                "alternatives": ["sources converge on a bounded theme", "sources diverge or content is insufficient"],
                "impact_scope": "financial research workload only; no advice, delivery, or data-admission change",
                "counter_evidence": "A missing snapshot, content hash mismatch, stale capture, or claim absent from the cited snapshot invalidates the conclusion.",
                "decision_verification": "At the next finance observation window, compare the retained source refs and record whether the stated theme persisted or diverged.",
            }, "autonomous_maintenance": {
                "why_now": "Three independent public-source snapshots contain observable content in the current finance window.",
                "evidence": evidence,
                "priority": "medium",
                "expected_result": "A bounded, source-cited market-narrative research brief with counter-evidence.",
                "verification_method": "Validator checks snapshot hashes, timestamps, source boundaries, and claim-to-text grounding.",
                "risk": "Research only; no recommendation, risk approval, or Telegram delivery.",
                "source": "public_sentiment_observation",
                "estimated_scope": "One cross-source public-content comparison.",
            }},
        ))

    def advisor_status_candidates(self) -> List[DiscoveryCandidate]:
        if not self.advisor_workspace:
            self._record("荐股工作区未被发现，未执行生产检查。", {"advisor_workspace": "missing"}, "low", "health")
            return []
        output = self.advisor_workspace / "05_TOOLS" / "mine_output" / "advisor"
        status = self._read_json(output / "runner_status.json")
        ledger = self._read_json(self.advisor_workspace / "02_MEMORY" / "advisor_delivery.json")
        auto_run = self._enabled("ACE_STOCK_ADVISOR_AUTO_RUN")
        auto_push = self._enabled("ACE_STOCK_ADVISOR_AUTO_PUSH")
        state = {
            "workspace": str(self.advisor_workspace),
            "auto_run_enabled": auto_run,
            "auto_push_enabled": auto_push,
            "runner_status_present": bool(status),
            "last_run_success": status.get("last_run_success"),
            "steps": status.get("steps", {}),
            "error_message": status.get("error_message", ""),
            "delivery_reports": len(ledger.get("reports", {})) if isinstance(ledger.get("reports", {}), dict) else 0,
        }
        blocked = auto_run and status and not status.get("last_run_success", False)
        failed_steps = [name for name, value in state["steps"].items() if str(value).lower() in {"failed", "error", "blocked"}]
        state["failed_steps"] = failed_steps
        anomaly = auto_run and (blocked or bool(failed_steps))
        self._record(
            "荐股生产自动开关关闭，状态仅记录不派单。" if not auto_run else ("荐股链路状态检查发现阻断。" if anomaly else "荐股链路状态检查正常。"),
            state,
            "high" if anomaly else "low",
            "health",
        )
        if not anomaly:
            self._resolve_incident("advisor_system_status")
            return []
        signature = {"last_run": status.get("last_run_time"), "error": status.get("error_message"), "steps": failed_steps}
        return self._candidate_for_incident("advisor_system_status", signature, lambda recovery_count: DiscoveryCandidate(
            fingerprint=self._fingerprint("advisor_status", {"signature": signature, "recovery_count": recovery_count}),
            title="处理荐股链路阻断或恢复失败",
            description="candidate、analysis、risk、report、TG、delivery ledger 或 retry/recovery 阶段存在失败证据。",
            reason="自动链路在显式启用后出现失败或阻断，恢复状态需要由既有任务生命周期核验。",
            objective="定位阻断阶段，保留自动开关和发布边界，提出可验证的恢复方案。",
            completion_criteria="明确失败阶段、账本证据、恢复条件和不发布约束。",
            verification_method="离线检查 runner status、delivery ledger 与 retry/recovery 记录，不触发荐股或推送。",
            priority="critical",
            task_type="reasoning",
            severity="critical",
            candidate_source="advisor_system_status",
        ))

    def lexicon_gap_candidates(self) -> List[DiscoveryCandidate]:
        lexicon_path = self.base_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
        lexicon = self._read_json(lexicon_path)
        if not lexicon:
            self._record("词库文件不存在，尚无真实覆盖率证据。", {"lexicon_path": str(lexicon_path), "coverage_evidence": "missing"}, "low", "gap")
            return []
        categories = lexicon.get("categories", {})
        required = ("stock", "industry", "concept", "risk_event", "new_term")
        gaps = [name for name in required if not categories.get(name)]
        state = {"lexicon_path": str(lexicon_path), "concept_count": lexicon.get("concept_count", 0), "gap_categories": gaps}
        self._record("词库覆盖检查完成。" if not gaps else "词库发现真实分类覆盖缺口。", state, "medium" if gaps else "low", "gap")
        if not gaps:
            self._resolve_incident("stock_lexicon_gap")
            return []
        # The incident identity is the actual missing A-share category set.
        # ``updated_at`` changes for unrelated lexicon writes and must not
        # reopen the same unresolved gap as a fresh discovery candidate.
        signature = {"path": str(lexicon_path), "gaps": gaps}
        return self._candidate_for_incident("stock_lexicon_gap", signature, lambda recovery_count: DiscoveryCandidate(
            fingerprint=self._fingerprint("stock_lexicon_gap", {"signature": signature, "recovery_count": recovery_count}),
            title="补齐A股词库真实覆盖缺口",
            description="股票、行业、概念、风险事件或新词分类缺少已记录概念。",
            reason="词库覆盖缺口由实际词库快照证明，需补充或研究而非生成固定巡检任务。",
            objective="核实缺失分类和外部事实边界，补齐可追溯概念，不改变荐股策略。",
            completion_criteria="为每个缺口建立来源、定义、分类和去重关系。",
            verification_method="复查词库快照、分类计数与新增概念血缘。",
            priority="medium",
            task_type="reasoning",
            severity="medium",
            candidate_source="stock_lexicon_gap",
        ))

    def candidate_sources(self) -> List:
        return [
            self.financial_cross_validation_candidates,
            self.public_sentiment_candidates,
            self.data_health_candidates,
            self.advisor_status_candidates,
            self.lexicon_gap_candidates,
        ]
