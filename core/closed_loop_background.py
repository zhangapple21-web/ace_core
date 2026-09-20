"""把闭环引擎接入 ACE daemon 与 MinerPool 的受治理后台桥。

模型在这里仅提供候选拆解和测量方案；候选必须经过本地契约校验，随后进入
TaskPool，由现有 Researcher/Validator/Guardian 继续处理。模型没有生产写权。
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .closed_loop_engine import ClosedLoopEngine


class ClosedLoopBackgroundRunner:
    MAX_MODELS = 3

    def __init__(self, engine: ClosedLoopEngine, miner_pool=None, task_pool=None):
        self.engine = engine
        self.miner_pool = miner_pool
        self.task_pool = task_pool
        self.state_path = engine.runtime_dir / "background_state.json"
        self.plan_path = engine.knowledge_dir / "plans.jsonl"
        self.state = self._load_state()

    def run_once(self, self_evolution_result: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
        proposal = self_evolution_result.get("proposal") if isinstance(self_evolution_result, dict) else None
        if not isinstance(proposal, dict) or self_evolution_result.get("status") not in {"OBSERVED", "ALREADY_ACTIVE"}:
            return {"status": "NO_ACTION", "reason": "no_new_observed_proposal", "provider_calls": 0}
        fingerprint = str(proposal.get("fingerprint", "")).strip()
        if not fingerprint:
            return {"status": "BLOCKED", "reason": "proposal_fingerprint_missing", "provider_calls": 0}
        if fingerprint == self.state.get("last_fingerprint"):
            return {"status": "ALREADY_PLANNED", "fingerprint": fingerprint, "provider_calls": 0}
        if dry_run:
            return {"status": "DRY_RUN", "fingerprint": fingerprint, "provider_calls": 0}
        if self.miner_pool is None:
            return {"status": "BLOCKED", "reason": "miner_pool_unavailable", "fingerprint": fingerprint, "provider_calls": 0}

        prompt = self._prompt(proposal)
        model_count = min(self.MAX_MODELS, max(1, len(getattr(self.miner_pool, "available_providers", []) or [])))
        try:
            responses = self.miner_pool.multi_chat(
                task_type="reasoning",
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "你是 ACE 的闭环规划器。只输出 JSON，不执行修改，不虚构指标。"
                    "必须区分 UNKNOWN 与已知证据。"
                ),
                model_count=model_count,
                diverse=True,
            )
        except Exception as error:
            return {"status": "BLOCKED", "reason": f"miner_pool_error:{error}", "fingerprint": fingerprint, "provider_calls": 0}

        candidates: List[Dict[str, Any]] = []
        invalid = 0
        for response in responses:
            parsed = self._parse_json(response.get("content", "") if isinstance(response, dict) else "")
            if not parsed:
                invalid += 1
                continue
            try:
                work_items = parsed.get("work_items")
                if not isinstance(work_items, list) or not work_items:
                    invalid += 1
                    continue
                nodes = self.engine.decompose(
                    proposal,
                    str(proposal.get("objective", "")),
                    work_items,
                )
            except (TypeError, ValueError):
                invalid += 1
                continue
            metrics = parsed.get("baseline_metrics")
            if not isinstance(metrics, list) or not metrics:
                invalid += 1
                continue
            candidates.append({
                "model": response.get("model", "") if isinstance(response, dict) else "",
                "provider": response.get("provider", "") if isinstance(response, dict) else "",
                "nodes": [node.__dict__ for node in nodes],
                "baseline_metrics": metrics[:16],
                "change_boundary": str(parsed.get("change_boundary", ""))[:500],
                "unknowns": parsed.get("unknowns", [])[:16] if isinstance(parsed.get("unknowns", []), list) else [],
            })

        status = "PLANS_READY_FOR_TASK_POOL_REVIEW" if candidates else "BLOCKED_NO_VALID_PLAN"
        plan_id = f"CLP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{fingerprint[:10]}"
        record = {
            "plan_id": plan_id,
            "fingerprint": fingerprint,
            "proposal_id": proposal.get("proposal_id"),
            "status": status,
            "candidates": candidates,
            "invalid_candidates": invalid,
            "provider_calls": len(responses),
            "recorded_at": datetime.now().isoformat(),
            "governance": "models_propose_only_task_pool_validates_and_executes",
        }
        self._append(self.plan_path, record)
        task_id = None
        if candidates and self.task_pool is not None:
            task = self.task_pool.create_task(
                title=f"闭环计划审议：{proposal.get('title', proposal.get('objective', '未命名'))[:100]}",
                hypothesis=str(proposal.get("objective", "")),
                creator="closed_loop_background",
                priority=str(proposal.get("priority", "medium")),
                tags=["closed_loop", "miner_pool_plan", "requires_baseline"],
                admission={
                    "source_type": "closed_loop_background",
                    "source_ref": f"closed_loop_plan:{plan_id}",
                    "why_now": proposal.get("reason", ""),
                    "evidence": proposal.get("evidence", [])[:8],
                    "expected_result": "形成带基线、改动、评估和痛苦复盘的可回放闭环",
                    "verification_method": "由 TaskPool 的 Researcher/Validator/Guardian 继续验证",
                    "risk": "模型输出仅为候选规划，未直接修改生产配置",
                    "estimated_scope": "single governed closed-loop plan",
                },
                outputs={"closed_loop_plan": record},
            )
            task_id = task.task_id
        self.state.update({"last_fingerprint": fingerprint, "last_plan_id": plan_id, "last_task_id": task_id, "updated_at": datetime.now().isoformat()})
        self._save_state()
        return {"status": status, "plan_id": plan_id, "task_id": task_id, "fingerprint": fingerprint, "provider_calls": len(responses), "valid_candidates": len(candidates), "invalid_candidates": invalid}

    @staticmethod
    def _prompt(proposal: Dict[str, Any]) -> str:
        return json.dumps({
            "objective": proposal.get("objective", ""),
            "reason": proposal.get("reason", ""),
            "evidence": proposal.get("evidence", [])[:8],
            "required_output": {
                "work_items": [{"objective": "", "acceptance": "", "risk": "low|medium|high"}],
                "baseline_metrics": [{"name": "", "direction": "higher|lower", "measurement": ""}],
                "change_boundary": "只允许一个可回滚最小改动",
                "unknowns": ["证据不足的地方"],
            },
        }, ensure_ascii=False, indent=2)

    @staticmethod
    def _parse_json(content: str) -> Optional[Dict[str, Any]]:
        text = str(content or "").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
        try:
            value = json.loads(text)
        except (TypeError, json.JSONDecodeError):
            return None
        return value if isinstance(value, dict) else None

    @staticmethod
    def _append(path: Path, payload: Dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")

    def _load_state(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)


__all__ = ["ClosedLoopBackgroundRunner"]
