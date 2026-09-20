"""ACE 闭环引擎 v1：观察、拆解、验证、复盘、晋升或回滚。

这个模块是 ACE 的通用认知闭环，不绑定视频、股票、模型或某个常驻进程。
它只负责把一次改进变成可审计的生命周期：

    observe -> decompose -> baseline -> change -> evaluate -> painful review
             -> promote / reject / rollback -> next observation

执行资源由调用方提供；本模块不把模型输出当成事实，也不直接改生产配置。
只有带基线、可比较指标和完整痛苦复盘的结果，才允许写入能力增长账本。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional


CONTRACT_VERSION = "ace.closed_loop_engine.v1"
DECISIONS = {
    "PROMOTED_TO_CAPABILITY_GROWTH",
    "REJECTED_NO_MEASURABLE_GAIN",
    "REJECTED_MISSING_PAINFUL_REVIEW",
    "REJECTED_REVIEW_DECLINED",
    "ROLLBACK_REQUIRED",
    "BLOCKED_MISSING_BASELINE",
    "BLOCKED_MISSING_EVALUATION",
}
PAINFUL_REVIEW_FIELDS = (
    "cost",
    "counterfactual",
    "recurrence_risk",
    "reusable_lesson",
)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hash(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class WorkNode:
    """一个有边界、可回放的子任务。"""

    node_id: str
    objective: str
    acceptance: str
    depends_on: List[str] = field(default_factory=list)
    risk: str = "low"
    status: str = "PLANNED"


@dataclass
class CycleReceipt:
    cycle_id: str
    contract_version: str
    created_at: str
    observation: Dict[str, Any]
    objective: str
    decomposition: List[Dict[str, Any]]
    baseline: Dict[str, Any]
    change: Dict[str, Any]
    evaluation: Dict[str, Any]
    painful_review: Dict[str, Any]
    decision: str
    next_observation: Dict[str, Any]
    receipt_hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["receipt_hash"] = ""
        payload["receipt_hash"] = _hash(payload)
        return payload


class ClosedLoopEngine:
    """ACE 的通用、可回滚、自我反馈闭环。

    ``run_cycle`` 接收执行节点已经产生的 change metrics；这保证“执行”和
    “认知收敛”分离，避免引擎为了自我证明而把未经验证的结果晋升。
    """

    MAX_NODES = 8
    MAX_DEPTH = 3

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir).resolve()
        self.runtime_dir = self.base_dir / "06_RUNTIME" / "ace" / "data" / "closed_loop"
        self.knowledge_dir = self.base_dir / "09_KNOWLEDGE" / "closed_loop"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.knowledge_dir / "cycle_receipts.jsonl"
        self.failure_path = self.knowledge_dir / "failure_replay.jsonl"
        self.growth_path = self.knowledge_dir / "capability_growth.jsonl"
        self.state_path = self.runtime_dir / "state.json"

    def decompose(
        self,
        observation: Mapping[str, Any],
        objective: str,
        work_items: Optional[Iterable[Mapping[str, Any]]] = None,
    ) -> List[WorkNode]:
        """把目标拆成有限、有依赖、有验收条件的子任务。

        调用方可以提供领域专属 work_items；没有提供时只生成通用的三段式
        骨架（复现基线、实施单变量改动、评估与复盘），不猜测业务细节。
        """
        objective = str(objective or "").strip()
        if not objective:
            raise ValueError("objective_required")
        raw = list(work_items or [])
        if not raw:
            raw = [
                {"objective": f"为“{objective}”复现并记录当前基线", "acceptance": "baseline 已带来源且可重跑", "risk": "low"},
                {"objective": f"对“{objective}”实施一个可回滚的最小改动", "acceptance": "change 有明确 diff、范围和回滚点", "risk": "medium"},
                {"objective": f"比较改动前后结果并完成痛苦复盘", "acceptance": "evaluation、painful_review 和决策齐全", "risk": "low"},
            ]
        if len(raw) > self.MAX_NODES:
            raise ValueError(f"decomposition_too_wide:{len(raw)}>{self.MAX_NODES}")
        nodes: List[WorkNode] = []
        for index, item in enumerate(raw, start=1):
            if not isinstance(item, Mapping):
                raise ValueError("work_item_must_be_mapping")
            text = str(item.get("objective", "")).strip()
            acceptance = str(item.get("acceptance", "")).strip()
            if not text or not acceptance:
                raise ValueError(f"work_item_incomplete:{index}")
            node_id = str(item.get("node_id") or f"N{index:02d}")
            deps = [str(value) for value in item.get("depends_on", (index > 1 and [f"N{index - 1:02d}"]) or [])]
            nodes.append(WorkNode(node_id, text, acceptance, deps, str(item.get("risk", "low")), "PLANNED"))
        node_ids = {node.node_id for node in nodes}
        for node in nodes:
            if any(dep not in node_ids for dep in node.depends_on):
                raise ValueError(f"unknown_dependency:{node.node_id}")
            if node.node_id in node.depends_on:
                raise ValueError(f"self_dependency:{node.node_id}")
        # 依赖图必须可拓扑排序；否则所谓“拆解”会把死循环传给执行层。
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError(f"cyclic_dependency:{node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            node = next(item for item in nodes if item.node_id == node_id)
            for dependency in node.depends_on:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node in nodes:
            visit(node.node_id)
        return nodes

    def evaluate(
        self,
        baseline: Mapping[str, Any],
        changed: Mapping[str, Any],
        directions: Optional[Mapping[str, str]] = None,
        tolerance: float = 0.0,
    ) -> Dict[str, Any]:
        """只比较可数值化指标；缺失或不可比较时保持 UNKNOWN。"""
        if not baseline or not changed:
            return {"status": "BLOCKED_MISSING_EVALUATION", "measurable_gain": False, "regression": False, "metrics": {}}
        directions = directions or {}
        metrics: Dict[str, Any] = {}
        regression = False
        gain = False
        for key in sorted(set(baseline) | set(changed)):
            before, after = baseline.get(key), changed.get(key)
            row = {"before": before, "after": after, "direction": directions.get(key, "higher")}
            if not isinstance(before, (int, float)) or not isinstance(after, (int, float)):
                row["status"] = "UNKNOWN_NON_NUMERIC"
                metrics[key] = row
                continue
            delta = float(after) - float(before)
            row["delta"] = delta
            direction = directions.get(key, "higher")
            if direction not in {"higher", "lower"}:
                raise ValueError(f"invalid_metric_direction:{key}")
            improvement = delta >= -tolerance if direction == "higher" else delta <= tolerance
            strict_gain = delta > tolerance if direction == "higher" else delta < -tolerance
            if not improvement:
                regression = True
                row["status"] = "REGRESSED"
            elif strict_gain:
                gain = True
                row["status"] = "IMPROVED"
            else:
                row["status"] = "UNCHANGED"
            metrics[key] = row
        if regression:
            status = "REGRESSION"
        elif gain:
            status = "IMPROVED"
        else:
            status = "NO_MEASURABLE_GAIN"
        return {"status": status, "measurable_gain": gain, "regression": regression, "metrics": metrics}

    def decide(self, evaluation: Mapping[str, Any], painful_review: Mapping[str, Any]) -> str:
        missing = [field for field in PAINFUL_REVIEW_FIELDS if not str(painful_review.get(field, "")).strip()]
        if evaluation.get("status") == "BLOCKED_MISSING_EVALUATION":
            return "BLOCKED_MISSING_EVALUATION"
        if missing or "retain" not in painful_review:
            return "REJECTED_MISSING_PAINFUL_REVIEW"
        if evaluation.get("regression"):
            return "ROLLBACK_REQUIRED"
        if not evaluation.get("measurable_gain"):
            return "REJECTED_NO_MEASURABLE_GAIN"
        if painful_review.get("retain") is not True:
            return "REJECTED_REVIEW_DECLINED"
        return "PROMOTED_TO_CAPABILITY_GROWTH"

    def run_cycle(
        self,
        observation: Mapping[str, Any],
        objective: str,
        baseline: Mapping[str, Any],
        changed: Mapping[str, Any],
        painful_review: Mapping[str, Any],
        *,
        work_items: Optional[Iterable[Mapping[str, Any]]] = None,
        directions: Optional[Mapping[str, str]] = None,
        change: Optional[Mapping[str, Any]] = None,
        tolerance: float = 0.0,
    ) -> Dict[str, Any]:
        nodes = self.decompose(observation, objective, work_items)
        evaluation = self.evaluate(baseline, changed, directions, tolerance)
        decision = self.decide(evaluation, painful_review)
        created_at = _now()
        cycle_id = f"CLC-{datetime.now().strftime('%Y%m%d%H%M%S')}-{_hash({'objective': objective, 'observation': observation})}"
        next_observation = self._next_observation(cycle_id, objective, decision, evaluation, painful_review)
        receipt = CycleReceipt(
            cycle_id=cycle_id,
            contract_version=CONTRACT_VERSION,
            created_at=created_at,
            observation=dict(observation),
            objective=objective,
            decomposition=[asdict(node) for node in nodes],
            baseline=dict(baseline),
            change=dict(change or {"metrics": dict(changed)}),
            evaluation=evaluation,
            painful_review=dict(painful_review),
            decision=decision,
            next_observation=next_observation,
        )
        payload = receipt.to_dict()
        self._append(self.ledger_path, payload)
        if decision == "PROMOTED_TO_CAPABILITY_GROWTH":
            self._append(self.growth_path, {"cycle_id": cycle_id, "objective": objective, "decision": decision, "evaluation": evaluation, "lesson": painful_review.get("reusable_lesson"), "recorded_at": created_at})
        else:
            self._append(self.failure_path, {"cycle_id": cycle_id, "objective": objective, "decision": decision, "evaluation": evaluation, "painful_review": dict(painful_review), "recorded_at": created_at})
        self._write_state({"last_cycle_id": cycle_id, "last_decision": decision, "next_observation": next_observation, "updated_at": created_at})
        return payload

    @staticmethod
    def _next_observation(cycle_id: str, objective: str, decision: str, evaluation: Mapping[str, Any], review: Mapping[str, Any]) -> Dict[str, Any]:
        if decision == "PROMOTED_TO_CAPABILITY_GROWTH":
            action = "在下一个相似场景复测，确认能力没有回归"
        elif decision == "ROLLBACK_REQUIRED":
            action = "执行回滚并复现失败，禁止把本次改动当作经验"
        else:
            action = "保留为失败/未知样本，等待新证据，不重复盲改"
        return {
            "source_cycle": cycle_id,
            "subject": objective,
            "trigger": decision,
            "action": action,
            "evaluation_status": evaluation.get("status", "UNKNOWN"),
            "lesson": review.get("reusable_lesson", ""),
        }

    @staticmethod
    def _append(path: Path, payload: Mapping[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(payload), ensure_ascii=False, sort_keys=True) + "\n")

    def _write_state(self, payload: Mapping[str, Any]) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(dict(payload), ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)


__all__ = ["ClosedLoopEngine", "CycleReceipt", "WorkNode", "CONTRACT_VERSION", "DECISIONS"]
