import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .observation import RuntimeObserver
from .task import TaskPool


@dataclass(frozen=True)
class DiscoveryCandidate:
    fingerprint: str
    title: str
    description: str
    reason: str
    objective: str
    completion_criteria: str
    verification_method: str
    priority: str = "high"
    task_type: str = "reasoning"
    severity: str = "high"
    candidate_source: str = "repository_gap"
    metadata: Optional[Dict[str, Any]] = None

    def to_metadata(self, route: Dict[str, Any]) -> Dict[str, Any]:
        metadata = {
            "candidate_source": self.candidate_source,
            "fingerprint": self.fingerprint,
            "title": self.title,
            "reason": self.reason,
            "objective": self.objective,
            "completion_criteria": self.completion_criteria,
            "verification_method": self.verification_method,
            "priority": self.priority,
            "task_type": self.task_type,
            "route": route,
            "autonomous_maintenance": {
                "why_now": self.reason,
                "evidence": [{
                    "source": self.candidate_source,
                    "detail": self.description,
                    "fingerprint": self.fingerprint,
                }],
                "priority": self.priority,
                "expected_result": self.completion_criteria,
                "verification_method": self.verification_method,
                "risk": "Bounded internal maintenance task; no external action is authorized.",
                "source": self.candidate_source,
                "estimated_scope": self.objective,
            },
        }
        if self.metadata:
            metadata.update(self.metadata)
        return metadata


class DiscoveryMode:
    def __init__(
        self,
        task_pool: TaskPool,
        observer: RuntimeObserver,
        base_dir: str,
        model_router=None,
        candidate_sources: Optional[List[Callable[[], List[DiscoveryCandidate]]]] = None,
        include_repository_gap: Optional[bool] = None,
    ):
        self.task_pool = task_pool
        self.observer = observer
        self.base_dir = Path(base_dir)
        self.model_router = model_router
        if include_repository_gap is None:
            include_repository_gap = candidate_sources is None
        self.candidate_sources = ([] if not include_repository_gap else [self._repository_gap_candidates]) + (candidate_sources or [])

    def _fingerprint_exists(self, fingerprint: str) -> bool:
        for observation in self.observer.get_recent(limit=200):
            discovery = observation.system_state.get("discovery", {})
            if isinstance(discovery, dict) and discovery.get("fingerprint") == fingerprint:
                return True
        for task in self.task_pool.list_tasks(limit=1000):
            discovery = task.outputs.get("discovery", {})
            if isinstance(discovery, dict) and discovery.get("fingerprint") == fingerprint:
                return True
        return False

    def _has_viable_work(self) -> bool:
        for status in ("pending", "active", "blocked", "review", "approved"):
            if self.task_pool.list_tasks(status=status, limit=1):
                return True
        return False

    def _route(self, task_type: str) -> Dict[str, Any]:
        if not self.model_router:
            return {"boundary": "ModelRouter", "selected_model": None, "mode": "local_evidence_only"}
        selected = self.model_router.select_model(task_type)
        return {
            "boundary": "ModelRouter",
            "task_type": task_type,
            "selected_model": selected.full_id if selected else None,
            "mode": "model_selected" if selected else "local_evidence_only",
        }

    def _repository_gap_candidates(self) -> List[DiscoveryCandidate]:
        daemon_path = self.base_dir / "ace_daemon.py"
        if not daemon_path.exists():
            return []
        source = daemon_path.read_text(encoding="utf-8")
        if "def _run_autonomous_loop" not in source or "create_worker(" not in source:
            return []
        signature = hashlib.sha256(
            "autonomous_loop_direct_worker_dispatch_v1".encode("utf-8")
        ).hexdigest()
        return [
            DiscoveryCandidate(
                fingerprint=signature,
                title="收敛自治执行的模型路由边界",
                description="自主循环包含直接 Worker 工厂分派，未经过模型任务画像路由。",
                reason="当前自治执行路径与 MinerPool 的任务画像、提供商健康和降级路由未收敛。",
                objective="确认直接分派路径的调用面，并提出保留现有角色生命周期的最小路由收敛方案。",
                completion_criteria="列出调用面、目标路由边界、迁移限制和可验证的后续改动范围。",
                verification_method="静态检查自治循环不再直接选择 Worker 类型，并由隔离生命周期测试记录 ModelRouter 决策。",
            )
        ]

    def discover(
        self,
        allow_existing_work: bool = False,
        allowed_priorities: Optional[set] = None,
    ) -> Dict[str, Any]:
        result = {
            "status": "no_action",
            "reason": "",
            "candidate": None,
            "observation_id": None,
        }
        if not allow_existing_work and self._has_viable_work():
            result["reason"] = "viable_task_exists"
            return result
        for source in self.candidate_sources:
            for candidate in source():
                if (
                    allowed_priorities is not None
                    and candidate.priority not in allowed_priorities
                ):
                    continue
                if self._fingerprint_exists(candidate.fingerprint):
                    continue
                route = self._route(candidate.task_type)
                observation = self.observer.record(
                    description=candidate.description,
                    system_state={
                        "discovery": candidate.to_metadata(route),
                        "task_pool_empty": not self._has_viable_work(),
                    },
                    severity=candidate.severity,
                    source="discovery_mode",
                    category="improvement",
                    auto_generated=True,
                )
                result.update({
                    "status": "observed",
                    "reason": "evidence_backed_candidate",
                    "candidate": candidate.title,
                    "observation_id": observation.obs_id,
                })
                return result
        result["reason"] = "no_evidence_backed_candidate"
        return result
