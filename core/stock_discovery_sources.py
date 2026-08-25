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
        signature = {"path": str(lexicon_path), "gaps": gaps, "updated_at": lexicon.get("updated_at")}
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
        return [self.data_health_candidates, self.advisor_status_candidates, self.lexicon_gap_candidates]
