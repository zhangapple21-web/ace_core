"""
任务生命周期岗位角色

不是人格。
是岗位。

Observer    → 发现问题、提出疑问、创建任务
Researcher  → 领取任务、寻找证据、形成报告
Validator   → 寻找反例、挑战结论
Archivist   → 归档任务、建立索引、形成知识库
Guardian    → 决定进入公理/约束/经验/废弃
"""

import re
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import Counter

from .task import Task, TaskPool
from .miner_pool.task_profiles import get_task_profile


LOCAL_ARCHAEOLOGY_TAGS = {"archaeology", "local_archaeology", "fragment", "碎片考古", "考古"}


def _model_task_type(task: Task) -> str:
    discovery = task.outputs.get("discovery", {}) if isinstance(task.outputs, dict) else {}
    if isinstance(discovery, dict):
        task_type = discovery.get("task_type", "")
        if isinstance(task_type, str) and task_type:
            return task_type.lower()
    for tag in task.tags or []:
        if isinstance(tag, str) and tag.startswith("task_type:"):
            return tag.split(":", 1)[1].lower()
    return ""


def _is_local_only_task(task: Task) -> bool:
    outputs = task.outputs if isinstance(task.outputs, dict) else {}
    admission = outputs.get("admission", {})
    model_task_admission = outputs.get("model_task_admission", {})
    source_type = admission.get("source_type", "") if isinstance(admission, dict) else ""
    tags = {tag.lower() for tag in task.tags or [] if isinstance(tag, str)}
    return (
        isinstance(model_task_admission, dict)
        and model_task_admission.get("classification") == "local_evidence_only"
    ) or source_type == "archaeology" or bool(tags & LOCAL_ARCHAEOLOGY_TAGS)


def _task_source_type(task: Task) -> str:
    outputs = task.outputs if isinstance(task.outputs, dict) else {}
    admission = outputs.get("admission", {})
    if isinstance(admission, dict) and admission.get("source_type"):
        return str(admission["source_type"])
    discovery = outputs.get("discovery", {})
    if isinstance(discovery, dict) and discovery.get("candidate_source"):
        return str(discovery["candidate_source"])
    return "unknown"


def _is_admitted_model_task(task: Task) -> bool:
    outputs = task.outputs if isinstance(task.outputs, dict) else {}
    decision = outputs.get("model_task_admission", {})
    return (
        isinstance(decision, dict)
        and decision.get("eligible") is True
        and decision.get("classification") in {"reasoning", "strategic", "execution"}
    )


def _model_result_allowed(profile: Dict[str, Any], provider: str, model: str) -> bool:
    allowed_providers = profile.get("allowed_providers", set())
    if allowed_providers and provider not in allowed_providers:
        return False
    allowed_models = profile.get("allowed_models", set())
    if allowed_models and f"{provider}:{model}" not in allowed_models:
        return False
    return True


def _quality_gate(response: Dict[str, Any], allowed: bool) -> Dict[str, Any]:
    content = response.get("content", "")
    executed = bool(response.get("success") and allowed and isinstance(content, str) and content)
    return {
        "executed": executed,
        "status": "pass" if executed else "not_run",
    }


def _record_model_execution(task: Task, role: str, llm_router, prompt: str) -> Optional[Dict[str, Any]]:
    task_type = _model_task_type(task)
    profile = get_task_profile(task_type)
    if not llm_router or not profile.get("model_enabled") or _is_local_only_task(task):
        return None
    trace = {
        "task_id": task.task_id,
        "source_type": _task_source_type(task),
        "task_type": task_type,
        "role": role,
        "profile": task_type,
        "expected_model": str(profile.get("expected_model", "")),
        "selected_model": "",
        "expected_role": role,
        "actual_role": role,
        "router_decision": {
            "eligible": True,
            "pool_task_type": task_type,
            "reason": "registered_task_profile",
        },
        "request": {
            "task_type": task_type,
            "message_count": 1,
            "max_retries": 3,
        },
        "provider": "",
        "model": "",
        "api_called": True,
        "api_result": "failed",
        "fallback": False,
        "fallback_chain": [],
        "tried_models": [],
        "usage": {},
        "cost": {},
        "latency_ms": 0,
        "attempts": [],
        "result": "failed",
        "quality_gate": {"executed": False, "status": "not_run"},
        "error": "",
        "response_sha256": "",
        "at": datetime.now().isoformat(),
    }
    try:
        response = llm_router.chat(
            task_type=task_type,
            messages=[{"role": "user", "content": prompt}],
            system_prompt="Return concise task analysis grounded in the supplied task context.",
            max_retries=3,
        )
    except Exception as error:
        response = {"success": False, "error": str(error)}
    trace["provider"] = str(response.get("provider", ""))
    trace["model"] = str(response.get("model", ""))
    trace["selected_model"] = trace["model"]
    trace["tried_models"] = list(response.get("tried_models", []))
    trace["usage"] = dict(response.get("usage", {}))
    trace["cost"] = dict(response.get("cost", {}))
    trace["latency_ms"] = response.get("latency_ms", 0)
    trace["attempts"] = list(response.get("attempts", []))
    trace["fallback_chain"] = list(trace["tried_models"])
    trace["fallback"] = len(trace["tried_models"]) > 1
    if not trace["selected_model"] and trace["tried_models"]:
        selected_provider, trace["selected_model"] = trace["tried_models"][-1].split(":", 1)
        if not trace["provider"]:
            trace["provider"] = selected_provider
    trace["error"] = str(response.get("error", ""))
    trace["api_result"] = "success" if response.get("success") else "failed"
    allowed = _model_result_allowed(profile, trace["provider"], trace["selected_model"])
    if response.get("success") and not allowed:
        trace["error"] = "selected provider/model violates task profile"
    trace["result"] = "success" if response.get("success") and allowed else "failed"
    trace["quality_gate"] = _quality_gate(response, allowed)
    content = response.get("content", "")
    if isinstance(content, str) and content:
        trace["response_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    required_trace_fields = (
        "task_id",
        "task_type",
        "role",
        "provider",
        "selected_model",
        "api_result",
        "latency_ms",
        "response_sha256",
    )
    trace["trace_complete"] = (
        trace.get("api_called") is True
        and all(trace.get(field) not in (None, "") for field in required_trace_fields)
    )
    task.outputs.setdefault("model_execution", []).append(trace)
    return response


class BaseWorker:
    """工作器基类 — 所有 Worker 的父类"""

    def __init__(self, name: str = None):
        self.name = name or self.__class__.__name__

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        raise NotImplementedError

    def can_handle(self, task: Dict[str, Any]) -> bool:
        """判断是否能处理这个任务"""
        return False


class Observer:
    """
    观察者 — 发现问题，创建任务

    不解决问题。
    只负责提出值得研究的问题。
    """

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None, daemon_state: Dict = None, experience_deposition=None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.daemon_state = daemon_state or {}
        self.experience_deposition = experience_deposition

    def observe_and_create(
        self,
        max_new: int = 3,
        allowed_priorities: Optional[set] = None,
    ) -> List[Task]:
        """观察系统状态，自动创建任务"""
        candidates = self._generate_candidates()
        if allowed_priorities is not None:
            candidates = [
                candidate for candidate in candidates
                if candidate.get("priority", "medium") in allowed_priorities
            ]
        new_tasks = []

        for cand in candidates[:max_new]:
            if not self._task_exists(cand["title"]):
                evidence = cand.get("evidence", [])
                if not evidence:
                    continue
                source_ref = cand.get("source_ref")
                if not source_ref:
                    source_ref = hashlib.sha256(
                        json.dumps(evidence, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    ).hexdigest()
                task = self.task_pool.create_task(
                    title=cand["title"],
                    hypothesis=cand.get("hypothesis", ""),
                    creator="observer",
                    priority=cand.get("priority", "medium"),
                    tags=cand.get("tags", []),
                    admission={
                        "source_type": "system_observation",
                        "source_ref": source_ref,
                        "why_now": cand.get("why_now", cand.get("hypothesis", "")),
                        "evidence": evidence,
                        "expected_result": cand.get("expected_result", cand.get("hypothesis", "")),
                        "verification_method": cand.get("verification_method", "Recheck the originating internal system state."),
                        "risk": cand.get("risk", "Internal observation may become stale before execution."),
                        "estimated_scope": cand.get("estimated_scope", "one observed system gap"),
                    },
                    outputs={"observer_candidate": dict(cand)},
                )
                new_tasks.append(task)

        return new_tasks

    def _task_exists(self, title: str) -> bool:
        title_norm = title[:30].lower()
        all_tasks = self.task_pool.list_tasks(limit=200)
        for t in all_tasks:
            if t.title[:30].lower() == title_norm:
                return True
        return False

    def _generate_candidates(self) -> List[Dict[str, Any]]:
        candidates = []
        evidence_context = {"daemon_state": self.daemon_state}

        if self.lexicon:
            stats = self.lexicon.get_stats()
            evidence_context["lexicon_stats"] = stats
            weak_cats = [
                cat for cat, count in stats.get("categories", {}).items()
                if count <= 2
            ]
            if len(weak_cats) >= 3:
                candidates.append({
                    "title": f"词库缺口补全：{len(weak_cats)}个薄弱分类",
                    "hypothesis": "薄弱分类的概念积累不足，影响系统理解能力",
                    "priority": "high" if len(weak_cats) >= 5 else "medium",
                    "tags": ["lexicon", "gap_filling"],
                })

            total_concepts = stats.get("total_concepts", 0)
            if total_concepts < 100:
                candidates.append({
                    "title": "词库概念规模不足，需要加速积累",
                    "hypothesis": "概念总量低于阈值，系统语言体系尚未成型",
                    "priority": "high",
                    "tags": ["lexicon", "growth"],
                })

        if self.memory_index:
            mem_stats = self.memory_index.get_stats()
            total_mem = mem_stats.get("total", 0)

            by_type = mem_stats.get("by_type", {})
            eco_count = by_type.get("eco_layer", 0)
            if eco_count < 50:
                candidates.append({
                    "title": "eco_layer经验索引不足",
                    "hypothesis": "285万条经验仅索引了极少部分，价值密度最高的叙事生态应优先索引",
                    "priority": "high",
                    "tags": ["eco_layer", "mining"],
                })

            research_count = sum(1 for _ in self.memory_index.search(memory_type="research_report", limit=10))
            if research_count == 0:
                candidates.append({
                    "title": "系统缺乏结构化研究报告",
                    "hypothesis": "记忆以碎片为主，缺少系统性的研究结论沉淀",
                    "priority": "medium",
                    "tags": ["research", "structure"],
                })

        mining_progress = self.daemon_state.get("mining_progress", {})
        eco_prog = mining_progress.get("eco_layer", {})
        if eco_prog:
            for layer, prog in eco_prog.items():
                mined = prog.get("offset", 0)
                total = 0
                if self.memory_index:
                    layer_name = {
                        "narrative_ecology": "叙事生态",
                        "behavioral_ecology": "行为生态",
                        "structural_ecology": "结构生态",
                        "transactional_ecology": "交易生态",
                        "free_zone": "自由区",
                    }.get(layer, layer)
                    if mined == 0 and layer == "behavioral_ecology":
                        candidates.append({
                            "title": f"行为生态层未开始挖掘（话术/对话）",
                            "hypothesis": "行为生态含2.1万条行为模板，是R1行为模式的核心沉淀",
                            "priority": "medium",
                            "tags": ["eco_layer", "behavioral"],
                        })
                        break

        if self.daemon_state.get("errors"):
            recent_errors = self.daemon_state["errors"][:5]
            error_modules = Counter(e.get("module", "") for e in recent_errors)
            top_module = error_modules.most_common(1)
            if top_module and top_module[0][1] >= 2:
                candidates.append({
                    "title": f"模块{top_module[0][0]}近期错误频发",
                    "hypothesis": "存在系统性bug或数据格式不兼容问题",
                    "priority": "medium",
                    "tags": ["bug", "stability"],
                })

        # 闭环反馈：从经验库生成任务
        if self.experience_deposition:
            exp_stats = self.experience_deposition.get_stats()
            by_type = exp_stats.get("by_type", {})

            # lesson 堆积 → 生成"避免重复失败"任务
            lesson_count = by_type.get("lesson", 0)
            if lesson_count >= 3:
                recent_lessons = self.experience_deposition.get_all("lesson", limit=3)
                lesson_titles = [e.conclusion[:40] for e in recent_lessons if e.conclusion]
                candidates.append({
                    "title": f"经验库有{lesson_count}条教训，需要复盘避免重复失败",
                    "hypothesis": f"近期教训涉及：{'；'.join(lesson_titles[:2])}",
                    "priority": "high",
                    "tags": ["experience", "lesson_review", "feedback_loop"],
                })

            # pattern 堆积 → 生成"升格为 axiom"复核任务
            pattern_count = by_type.get("pattern", 0)
            if pattern_count >= 5:
                candidates.append({
                    "title": f"经验库有{pattern_count}条模式，评估是否有可升格为公理的",
                    "hypothesis": "部分模式可能已经反复验证，可以升格为 axiom 提升系统置信度",
                    "priority": "medium",
                    "tags": ["experience", "pattern_promotion", "feedback_loop"],
                })

        for cand in candidates:
            evidence = {
                "source": "observer_internal_state",
                "title": cand["title"],
                "hypothesis": cand.get("hypothesis", ""),
                "tags": cand.get("tags", []),
                "lexicon_stats": evidence_context.get("lexicon_stats", {}),
                "daemon_state": evidence_context["daemon_state"],
            }
            cand["evidence"] = [evidence]
            cand["source_ref"] = hashlib.sha256(
                json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
        return candidates


class Researcher:
    """
    研究员 — 领取任务，寻找证据，形成报告

    不决定结论。
    只负责收集证据，呈现事实。
    """

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None, eco_parser=None, slice_clusterer=None, llm_router=None, experience_deposition=None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.eco_parser = eco_parser
        self.slice_clusterer = slice_clusterer
        self.llm_router = llm_router
        self.experience_deposition = experience_deposition

    FAIRNESS_REWORK_LIMIT = 2
    FAIRNESS_MEDIUM_AGE_LIMIT = 3

    @staticmethod
    def _admission_evidence(task: Task, limit: int = 5) -> List[Dict[str, Any]]:
        outputs = task.outputs if isinstance(task.outputs, dict) else {}
        admission = outputs.get("admission", {})
        records = admission.get("evidence", []) if isinstance(admission, dict) else []
        evidence = []
        seen = set()
        for item in records if isinstance(records, list) else []:
            if not isinstance(item, dict):
                continue
            source = item.get("source_ref") or item.get("source")
            content = item.get("content") or item.get("detail") or item.get("description")
            if not isinstance(source, str) or not source.strip() or source in seen:
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            seen.add(source)
            evidence.append({
                "content": content[:2000],
                "source": source,
                "type": "admission",
                "title": str(item.get("title", "")),
            })
            if len(evidence) >= limit:
                break
        return evidence

    def _is_rework_candidate(self, task: Task) -> bool:
        rework_streak = task.consecutive_rework_claims
        if not task.last_claimed_at:
            rework_streak = max(rework_streak, task.rework_count)
        return (
            rework_streak >= self.FAIRNESS_REWORK_LIMIT
            and task.outputs.get("last_validator_result", {}).get("outcome") == "rework_pending"
        )

    def _untouched_candidate(self, check_order: List[str], exclude_task_id: str) -> Optional[Task]:
        now = datetime.now()
        model_untouched = []
        untouched = []
        model_rework = []
        rework = []
        for priority in check_order:
            # Service the complete bounded pool, not merely the oldest page.
            # Otherwise 100 rework tasks at one priority can permanently hide
            # every untouched task behind them, including an admitted model
            # task, while the selector keeps reclaiming the same old work.
            for task in self.task_pool.list_tasks(status="pending", priority=priority, limit=10000):
                if task.task_id == exclude_task_id or task.last_claimed_at:
                    continue
                if task.retry_after:
                    try:
                        if datetime.fromisoformat(task.retry_after) > now:
                            continue
                    except ValueError:
                        continue
                if not task.last_claimed_at:
                    (model_untouched if _is_admitted_model_task(task) else untouched).append(task)
                elif (
                    self._is_rework_candidate(task)
                    or (
                        _is_admitted_model_task(task)
                        and task.outputs.get("last_validator_result", {}).get("outcome")
                        == "rework_pending"
                    )
                ):
                    (model_rework if _is_admitted_model_task(task) else rework).append(task)
        if model_untouched:
            return sorted(model_untouched, key=lambda task: task.created_at)[0]
        if untouched:
            return sorted(untouched, key=lambda task: task.created_at)[0]
        if model_rework:
            return sorted(model_rework, key=lambda task: task.created_at)[0]
        if rework:
            return sorted(rework, key=lambda task: task.created_at)[0]
        return None

    @staticmethod
    def _is_claim_eligible(task: Task, now: datetime) -> bool:
        if task.outputs.get("terminal_non_convergent"):
            return False
        if not task.retry_after:
            return True
        try:
            return datetime.fromisoformat(task.retry_after) <= now
        except ValueError:
            return False

    def _is_completion_candidate(self, task: Task) -> bool:
        last_result = task.outputs.get("last_validator_result", {})
        return (
            isinstance(last_result, dict)
            and last_result.get("outcome") == "rework_pending"
            and last_result.get("hard_objections") == []
            and bool(task.hypothesis.strip())
            and len(Validator._unique_evidence(task)) >= 3
            and task.consecutive_rework_claims < self.FAIRNESS_REWORK_LIMIT
        )

    def _first_eligible_task(self, statuses: List[str], priority: str, now: datetime) -> Optional[Task]:
        for status in statuses:
            for task in self.task_pool.list_tasks(status=status, priority=priority, limit=100):
                if self._is_claim_eligible(task, now):
                    return task
        return None

    def _aging_medium_candidate(self, priority: str) -> Optional[Task]:
        if priority != "any":
            return None
        now = datetime.now()
        if self._first_eligible_task(["pending"], "critical", now):
            return None
        if not self._first_eligible_task(["pending"], "high", now):
            return None
        # A medium task that already satisfied every hard validation gate must
        # receive a bounded second service opportunity.  Otherwise the entire
        # untouched medium backlog permanently sits ahead of it and the pool
        # can claim/research forever without ever converging to approved.
        qualified_rework = []
        for task in self.task_pool.list_tasks(
            status="pending", priority="medium", limit=10000
        ):
            if (
                self._is_claim_eligible(task, now)
                and self._is_completion_candidate(task)
            ):
                qualified_rework.append(task)
        if qualified_rework:
            return sorted(
                qualified_rework,
                key=lambda task: (task.retry_after or task.created_at, task.created_at),
            )[0]
        # Fairness must rotate through the whole untouched medium backlog.
        # The old implementation inspected only the first medium task (and
        # therefore kept aging/reselecting the same file), while the remaining
        # medium tasks never received a selection opportunity.  Keep the
        # existing age threshold semantics, but choose the oldest eligible
        # untouched candidate with the greatest observed starvation age.
        candidates = [
            task
            for task in self.task_pool.list_tasks(
                status="pending", priority="medium", limit=10000
            )
            if not task.last_claimed_at and self._is_claim_eligible(task, now)
        ]
        if candidates:
            return sorted(
                candidates,
                key=lambda task: (
                    -int(task.starvation_age or 0),
                    task.created_at,
                ),
            )[0]
        return self._first_eligible_task(["pending"], "medium", now)

    def _record_high_competition(self, medium: Optional[Task], high: Task):
        if medium is None:
            return
        medium.starvation_age += 1
        medium.record_selection(
            "researcher_claim",
            high.task_id,
            alternatives=[medium.task_id],
            reason="aging_competition",
            actor="researcher",
        )
        self.task_pool.update_task(medium)

    def _record_aging_yield(self, high: Task, medium: Task) -> None:
        high.record_selection(
            "researcher_claim",
            medium.task_id,
            alternatives=[high.task_id],
            reason="aging_yield",
            actor="researcher",
        )
        self.task_pool.update_task(high)
        medium.starvation_age = 0
        medium.record_selection(
            "researcher_claim",
            medium.task_id,
            alternatives=[high.task_id],
            reason="aging_reset",
            actor="researcher",
        )
        self.task_pool.update_task(medium)

    def pick_up_task(self, priority: str = "high") -> Optional[Task]:
        """领取最高优先级的待办任务（含卡住的active任务）"""
        priority_order = ["critical", "high", "medium", "low"]
        if priority == "any":
            check_order = priority_order
        else:
            idx = priority_order.index(priority) if priority in priority_order else 1
            check_order = priority_order[:idx + 1]

        for status in ["active", "pending"]:
            for pri in check_order:
                # The service decision must see the complete bounded priority
                # queue.  A five-item page can hide an already-claimed model
                # task behind old rework tasks indefinitely.
                tasks = self.task_pool.list_tasks(status=status, priority=pri, limit=10000)
                for task in tasks:
                    medium = (
                        self._aging_medium_candidate(priority)
                        if status == "pending" and pri == "high"
                        else None
                    )
                    untouched = (
                        self._untouched_candidate(check_order, task.task_id)
                        if self._is_rework_candidate(task)
                        else None
                    )
                    aging_yield = (
                        medium is not None
                        and (
                            medium.starvation_age >= self.FAIRNESS_MEDIUM_AGE_LIMIT
                            or self._is_completion_candidate(medium)
                        )
                    )
                    candidate = medium if aging_yield else untouched or task
                    if self._is_rework_candidate(task):
                        model_candidates = [
                            item for item in self.task_pool.list_tasks(
                                status="pending", priority=pri, limit=10000
                            )
                            if _is_admitted_model_task(item)
                            and self._is_claim_eligible(item, datetime.now())
                            and (
                                not item.last_claimed_at
                                or item.outputs.get("last_validator_result", {}).get("outcome")
                                == "rework_pending"
                            )
                        ]
                        if model_candidates:
                            candidate = sorted(model_candidates, key=lambda item: item.created_at)[0]
                    claimed = self.task_pool.claim_task(candidate.task_id, "researcher")
                    if not claimed:
                        continue
                    if aging_yield:
                        self._record_aging_yield(task, claimed)
                    elif untouched:
                        task.record_selection(
                            "researcher_claim",
                            claimed.task_id,
                            alternatives=[task.task_id],
                            reason="fairness_yield",
                            actor="researcher",
                        )
                        self.task_pool.update_task(task)
                        if (
                            status == "pending"
                            and pri == "high"
                            and claimed.priority == "high"
                        ):
                            self._record_high_competition(medium, claimed)
                    elif status == "pending" and pri == "high":
                        self._record_high_competition(medium, claimed)
                    return claimed
        return None

    def generate_candidates(self, task: Task, max_candidates: int = 3) -> List[Dict[str, Any]]:
        """
        构建假设树（ToT 风格）
        
        假设树 = 多候选假设 + 选择机制
        
        结构：
                    [根节点：任务]
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
        [假设A]      [假设B]      [假设C]
        primary    lexicon_rel   negation
        
        每个假设节点包含：
        - candidate_id: 节点标识
        - hypothesis: 假设内容
        - keywords: 关联关键词
        - confidence: 置信度 (0-1)
        - reasoning: 推导过程
        - type: 假设类型
        
        选择机制由 Validator.assess_prospect() 完成：
        - 评估每个候选的前景
        - 选择最优分支继续探索
        - 低价值分支剪枝
        
        Returns:
            [
                {
                    "candidate_id": str,
                    "hypothesis": str,
                    "keywords": [...],
                    "confidence": float,  # 0-1 初步置信度
                    "reasoning": str,    # 为什么选择这个方向
                },
                ...
            ]
        """
        candidates = []
        
        # 1. 从任务标题提取核心假设
        title_keywords = self._extract_keywords(task.title.lower())
        
        # 2. 从 hypothesis 提取辅助假设
        hypothesis_keywords = self._extract_keywords(task.hypothesis.lower()) if task.hypothesis else []
        
        # 3. 生成主假设（基于标题）
        if title_keywords:
            primary_hypothesis = " / ".join(title_keywords[:3])
            candidates.append({
                "candidate_id": "A",
                "hypothesis": f"核心假设：{primary_hypothesis}",
                "keywords": title_keywords[:5],
                "confidence": 0.8,
                "reasoning": "基于任务标题的核心概念提取",
                "type": "primary",
            })
        
        # 4. 生成备选假设（基于词库关联）
        if self.lexicon and title_keywords:
            for kw in title_keywords[:3]:
                concept = self.lexicon.get_concept(kw)
                if concept and concept.get("related"):
                    related = concept.get("related", [])[:2]
                    if related:
                        candidates.append({
                            "candidate_id": f"B_{kw}",
                            "hypothesis": f"关联假设：{kw} 与 {related[0]} 相关",
                            "keywords": [kw] + related,
                            "confidence": 0.6,
                            "reasoning": f"词库关联：{kw} 的 related 概念",
                            "type": "lexicon_related",
                        })
        
        # 5. 生成对立假设（基于反例）
        if task.counter_examples:
            candidates.append({
                "candidate_id": "C_negation",
                "hypothesis": f"对立假设：{task.title} 的反面是否成立",
                "keywords": title_keywords[:2],
                "confidence": 0.5,
                "reasoning": "基于已有反例的对立探索",
                "type": "negation",
            })
        
        # 6. 生成跨域假设（如果有 eco_layer）
        if self.eco_parser and title_keywords:
            candidates.append({
                "candidate_id": "D_cross",
                "hypothesis": f"跨域假设：{title_keywords[0]} 在 eco_layer 中的表现",
                "keywords": title_keywords[:2],
                "confidence": 0.55,
                "reasoning": "跨层探索：eco_layer 叙事生态",
                "type": "cross_layer",
            })

        # 7. 闭环反馈：从经验库生成经验驱动假设
        if self.experience_deposition and title_keywords:
            for kw in title_keywords[:2]:
                related = self.experience_deposition.find_related(kw, limit=2)
                if related:
                    top_exp = related[0]
                    candidates.append({
                        "candidate_id": f"E_exp_{kw}",
                        "hypothesis": f"经验假设：基于{top_exp.experience_type}「{top_exp.conclusion[:40]}」",
                        "keywords": [kw],
                        "confidence": 0.7,
                        "reasoning": f"历史经验 {top_exp.experience_id} 支持此方向",
                        "type": "experience_informed",
                    })
                    break

        # 去重并限制数量
        seen = set()
        unique_candidates = []
        for c in candidates:
            key = c["hypothesis"][:30]
            if key not in seen:
                seen.add(key)
                unique_candidates.append(c)
        
        return unique_candidates[:max_candidates]

    def research_task(self, task: Task, max_evidence: int = 5) -> Dict[str, Any]:
        """对任务进行研究，收集证据"""
        if task.claim_id:
            renewed = self.task_pool.renew_lease(
                task.task_id,
                "researcher",
                task.claim_id,
            )
            if renewed is None:
                raise RuntimeError("research_lease_renewal_failed")
            task = renewed
        result = {
            "task_id": task.task_id,
            "evidence_found": 0,
            "counter_found": 0,
            "research_summary": "",
            "status": "review",
        }
        admitted_evidence = self._admission_evidence(task, limit=max_evidence)
        evidence_context = "\n".join(
            f"- [{item['source']}] {item['content'][:500]}"
            for item in admitted_evidence
        )
        model_response = _record_model_execution(
            task,
            "researcher",
            self.llm_router,
            (
                f"Task: {task.title}\nHypothesis: {task.hypothesis}\n"
                "Role: analyze the supplied evidence, identify alternatives and "
                "invalidating conditions. Do not invent evidence.\n"
                f"Admitted evidence:\n{evidence_context or '(none)'}"
            ),
        )
        if isinstance(model_response, dict):
            content = model_response.get("content")
            if isinstance(content, str) and content.strip():
                task.outputs["model_research_result"] = {
                    "content": content[:4000],
                    "response_sha256": hashlib.sha256(
                        content.encode("utf-8")
                    ).hexdigest(),
                    "at": datetime.now().isoformat(),
                }

        title_lower = task.title.lower()
        hypothesis_lower = task.hypothesis.lower()
        keywords = self._extract_keywords(title_lower + " " + hypothesis_lower)

        # Admission evidence is the reason this task was allowed onto the model
        # path.  Preserve it as the first-class research basis before optional
        # broad memory/lexicon enrichment; otherwise an admitted task can lose
        # all of its real inputs and be validated against unrelated search hits.
        evidence = list(admitted_evidence)
        counter_examples = []

        if self.eco_parser and any(k in title_lower for k in ["eco", "生态", "行为", "叙事", "自由区"]):
            eco_evidence = self._research_eco(task, keywords)
            evidence.extend(eco_evidence)

        if self.memory_index:
            for kw in keywords[:5]:
                hits = self.memory_index.search(keyword=kw, limit=10)
                for hit in hits[:2]:
                    content = hit.get("content") or hit.get("summary") or ""
                    source = hit.get("source_path") or hit.get("source", "memory")
                    if not hit.get("source_path") and hit.get("id"):
                        source = f"{source}:{hit['id']}"
                    evidence.append({
                        "content": content[:300],
                        "source": source,
                        "type": "memory",
                        "title": hit.get("title", ""),
                    })

        if self.lexicon:
            for kw in keywords[:5]:
                concept = self.lexicon.get_concept(kw)
                if concept:
                    evidence.append({
                        "content": f"词库概念[{concept['name']}]：{concept.get('definition', '')}",
                        "source": "lexicon",
                        "type": "concept",
                        "concept": concept["name"],
                    })

        # 闭环反馈：从经验库检索历史经验作为证据
        if self.experience_deposition:
            for kw in keywords[:3]:
                related_exp = self.experience_deposition.find_related(kw, limit=3)
                for exp in related_exp[:2]:
                    evidence.append({
                        "content": f"[历史经验-{exp.experience_type}] {exp.conclusion[:200]}",
                        "source": f"experience:{exp.experience_id}",
                        "type": "experience",
                        "experience_id": exp.experience_id,
                    })

        # Empty search hits are not evidence.  Persisting them created the
        # illusion of a larger evidence set while Validator correctly counted
        # only meaningful independent records, causing avoidable rework loops.
        evidence = [
            ev for ev in evidence
            if isinstance(ev, dict)
            and isinstance(ev.get("content"), str)
            and ev.get("content", "").strip()
            and isinstance(ev.get("source", ""), str)
            and ev.get("source", "").strip()
        ][:max_evidence]

        for ev in evidence:
            task.add_evidence(ev.get("content", "")[:300], source=ev.get("source", ""))

        summary_parts = [f"研究了 {len(evidence)} 条证据"]
        if evidence:
            types = Counter(e.get("type", "unknown") for e in evidence)
            summary_parts.append(f"来源分布: {dict(types)}")
        result["research_summary"] = "；".join(summary_parts)

        task.add_research_note(result["research_summary"])
        
        # 生成多候选假设（ToT 风格）
        candidates = self.generate_candidates(task, max_candidates=3)
        
        task.result = {
            "evidence_count": len(evidence),
            "counter_count": len(counter_examples),
            "summary": result["research_summary"],
            "candidates": candidates,  # ToT 风格多路径探索
        }
        
        self.task_pool.update_task(task)
        self.task_pool.move_task(task.task_id, "review", actor="researcher", task=task)

        result["evidence_found"] = len(evidence)
        result["candidates_count"] = len(candidates)
        return result

    def _research_eco(self, task: Task, keywords: List[str]) -> List[Dict]:
        findings = []
        if not self.eco_parser:
            return findings

        for kw in keywords[:3]:
            hits = self.eco_parser.find_contains(kw, max_results=5)
            for hit in hits[:2]:
                findings.append({
                    "content": f"[{hit['layer_name']}] {hit.get('preview', '')[:200]}",
                    "source": f"eco_layer:{hit['layer']}",
                    "type": "eco_layer",
                })

        return findings

    def _extract_keywords(self, text: str) -> List[str]:
        stopwords = {"的", "了", "是", "在", "有", "和", "不", "一", "个", "需要", "进行", "发现", "研究", "问题", "系统", "不足", "应该", "可以", "可能", "已经", "这个", "那个", "什么", "怎么", "为什么", "因为", "所以", "但是", "如果", "包括", "包含", "相关", "对应", "提供", "实现", "执行", "处理"}
        cn_chunks = re.findall(r"[\u4e00-\u9fff]+", text)
        keywords = []
        for chunk in cn_chunks:
            found_in_chunk = False
            for length in [4, 3, 2]:
                for i in range(len(chunk) - length + 1):
                    w = chunk[i:i + length]
                    if w not in stopwords and self.lexicon and self.lexicon.get_concept(w):
                        keywords.append(w)
                        found_in_chunk = True
                        break
                if found_in_chunk:
                    break
            if not found_in_chunk and len(chunk) >= 2:
                w = chunk[:4] if len(chunk) > 4 else chunk
                if w not in stopwords:
                    keywords.append(w)
        en_words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text)
        for w in en_words:
            if w.lower() not in stopwords and w not in keywords:
                keywords.append(w)
        seen = set()
        result = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                result.append(w)
        return result[:10]


class Validator:
    """
    验证员 — 寻找反例，挑战结论

    不负责建设。
    只负责挑刺。
    至少提出一个反对意见。
    """

    MAX_UNCHANGED_REVIEWS = 4
    EVIDENCE_SIGNATURE_VERSION = 2

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None, llm_router=None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.llm_router = llm_router

    @staticmethod
    def _unique_evidence(task: Task) -> set:
        return {
            (
                item.get("source", "") if isinstance(item, dict) else "",
                item.get("content", "") if isinstance(item, dict) else str(item),
            )
            for item in task.evidence
        }

    @classmethod
    def evidence_signature(cls, task: Task) -> str:
        return hashlib.sha256(
            json.dumps(sorted(cls._unique_evidence(task)), ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def validation_signature(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def non_convergent_disposition(task: Task) -> str:
        if "permanent_dead_end" in task.tags or task.outputs.get("terminal_disposition") == "graveyard":
            return "graveyard"
        admission = task.outputs.get("admission", {})
        if "external" in task.tags or admission.get("source_type") == "external_research":
            return "observe"
        return "blocked"

    def validate_task(self, task: Task) -> Dict[str, Any]:
        """验证一个任务的研究结论，至少找一个反例或疑点"""
        evidence_signature = self.evidence_signature(task)
        previous_result = task.outputs.get("last_validator_result", {})
        if not isinstance(previous_result, dict):
            previous_result = {}
        previous_signature = task.outputs.get("last_validated_evidence_signature", "")
        previous_signature = previous_signature or previous_result.get("evidence_signature", "")
        previous_signature_version = task.outputs.get("evidence_signature_version")
        review_count = getattr(task, "review_count", 0)
        task.review_count = review_count + 1
        self.task_pool.update_task(task)

        result = {
            "task_id": task.task_id,
            "objections": [],
            "counter_examples": 0,
            "passed": False,
            "verdict": "",
            "review_count": task.review_count,
        }
        _record_model_execution(
            task,
            "validator",
            self.llm_router,
            f"Task: {task.title}\nHypothesis: {task.hypothesis}\nRole: identify counterexamples and validation risks.",
        )

        objections = []
        hard_objections = []
        advisory_objections = []

        evidence_count = len(self._unique_evidence(task))
        if evidence_count == 0:
            objection = "没有任何证据支持，研究不充分"
            objections.append(objection)
            hard_objections.append(objection)
        elif evidence_count < 3:
            objection = f"仅{evidence_count}条证据，样本量不足"
            objections.append(objection)
            hard_objections.append(objection)

        if not task.hypothesis:
            objection = "任务没有明确的假设，无法验证"
            objections.append(objection)
            hard_objections.append(objection)

        if not task.counter_examples:
            objection = "未主动寻找反例，存在确认偏误风险"
            objections.append(objection)
            advisory_objections.append(objection)

        if self.memory_index and task.evidence:
            first_ev = task.evidence[0]
            ev_content = first_ev.get("content", "") if isinstance(first_ev, dict) else str(first_ev)
            if len(ev_content) < 50:
                objection = "第一条证据内容过短，可信度存疑"
                objections.append(objection)
                # A short first item is not by itself fatal when the complete
                # evidence set meets the independent-evidence minimum.
                if evidence_count < 3:
                    hard_objections.append(objection)
                else:
                    advisory_objections.append(objection)

        keywords = re.findall(r"[\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z0-9_]{2,}", task.title)
        if self.lexicon and keywords:
            matched_concepts = sum(1 for kw in keywords[:5] if self.lexicon.get_concept(kw))
            if matched_concepts == 0 and len(keywords) >= 2:
                objection = "核心关键词在词库中无对应概念，研究背景薄弱"
                objections.append(objection)
                advisory_objections.append(objection)

        genuine_objections = [o for o in objections if "未发现明显逻辑漏洞" not in o]

        if not genuine_objections:
            genuine_objections.append("建议扩大样本量后再确认")

        for obj in genuine_objections:
            task.add_validation_note(obj, validator="validator")
            task.add_counter_example(obj, source="validator")

        result["objections"] = genuine_objections
        result["counter_examples"] = len(genuine_objections)
        result["hard_objections"] = list(hard_objections)
        result["advisory_objections"] = list(advisory_objections)

        objections_signature = self.validation_signature(sorted(genuine_objections))
        validator_outcome_signature = self.validation_signature("rework_pending")
        previous_outcome = previous_result.get("outcome", "")
        repeated_rework = not previous_outcome or previous_outcome == "rework_pending"
        legacy_rework_migration = (
            repeated_rework
            and previous_signature_version != self.EVIDENCE_SIGNATURE_VERSION
            and previous_signature != evidence_signature
        )
        previous_objections_signature = task.outputs.get("objections_signature", "")
        previous_outcome_signature = task.outputs.get("validator_outcome_signature", "")
        stable_validation = (
            previous_signature == evidence_signature
            and previous_objections_signature == objections_signature
            and previous_outcome_signature == validator_outcome_signature
        )
        legacy_format = previous_signature_version != self.EVIDENCE_SIGNATURE_VERSION
        if legacy_format and repeated_rework:
            if previous_signature == evidence_signature:
                task.unchanged_review_count = min(
                    max(task.review_count, 0),
                    self.MAX_UNCHANGED_REVIEWS,
                )
            else:
                task.unchanged_review_count = min(
                    max(task.review_count, 1),
                    self.MAX_UNCHANGED_REVIEWS - 1,
                )
        else:
            task.unchanged_review_count = (
                task.unchanged_review_count + 1 if stable_validation else 1
            )
        task.outputs["last_validated_evidence_signature"] = evidence_signature
        task.outputs["evidence_signature_version"] = self.EVIDENCE_SIGNATURE_VERSION
        task.outputs["objections_signature"] = objections_signature
        task.outputs["validator_outcome_signature"] = validator_outcome_signature
        validator_result = {
            "review_count": task.review_count,
            "evidence_signature": evidence_signature,
            "objections": list(genuine_objections),
            "hard_objections": list(hard_objections),
            "advisory_objections": list(advisory_objections),
            "validated_at": datetime.now().isoformat(),
        }

        if task.unchanged_review_count >= self.MAX_UNCHANGED_REVIEWS:
            task.retry_after = ""
            task.assignee = None
            task.outputs["terminal_non_convergent"] = True
            disposition = self.non_convergent_disposition(task)
            result["passed"] = False
            if disposition == "graveyard":
                result["verdict"] = "相同证据集重复验证达到上限，已确认永久无效"
                validator_result["outcome"] = "graveyard_non_convergent"
                task.outputs["last_validator_result"] = validator_result
                task.outputs["rework_reason"] = result["verdict"]
                self.task_pool.update_task(task)
                self.task_pool.move_task(
                    task.task_id,
                    "graveyard",
                    actor="validator",
                    reason="validator_non_convergent_permanent_dead_end",
                    task=task,
                )
            elif disposition == "observe":
                result["verdict"] = "相同证据集重复验证达到上限，等待外部新证据"
                validator_result["outcome"] = "observe_non_convergent"
                task.outputs["last_validator_result"] = validator_result
                task.outputs["rework_reason"] = result["verdict"]
                self.task_pool.update_task(task)
                self.task_pool.block_task(
                    task.task_id,
                    result["verdict"],
                    actor="validator",
                    block_type="external_condition_blocked",
                )
            else:
                result["verdict"] = "相同证据集重复验证达到上限，等待人工或外部新证据"
                validator_result["outcome"] = "blocked_non_convergent"
                task.outputs["last_validator_result"] = validator_result
                task.outputs["rework_reason"] = result["verdict"]
                self.task_pool.update_task(task)
                self.task_pool.block_task(
                    task.task_id,
                    result["verdict"],
                    actor="validator",
                    block_type="manual_gate_blocked",
                )

        elif (
            not legacy_rework_migration
            and not hard_objections
            and evidence_count >= 3
        ):
            result["passed"] = True
            result["verdict"] = "初步通过，可进入终审"
            validator_result["outcome"] = "approved"
            task.outputs["last_validator_result"] = validator_result
            self.task_pool.update_task(task)
            self.task_pool.move_task(task.task_id, "approved", actor="validator", task=task)

        else:
            result["passed"] = False
            result["verdict"] = f"需补充研究，回到pending（第{task.review_count}次重审）"
            task.add_research_note(f"验证员提出{len(genuine_objections)}个质疑，需补充研究")
            task.assignee = None
            task.rework_count += 1
            task.retry_after = (datetime.now() + timedelta(minutes=5)).isoformat()
            validator_result["outcome"] = "rework_pending"
            validator_result["retry_after"] = task.retry_after
            task.outputs["rework_reason"] = "；".join(genuine_objections)
            task.outputs["last_validator_result"] = validator_result
            self.task_pool.update_task(task)
            self.task_pool.move_task(
                task.task_id,
                "pending",
                actor="validator",
                reason="validator_rework_pending",
                task=task,
            )

        return result

    def assess_prospect(self, task: Task) -> Dict[str, Any]:
        """
        评估任务继续探索的前景（AoT 风格）
        
        基于思维算法 (Algorithm of Thoughts) 的四步框架：
        1. 分解成子问题 - 任务是否可以拆解
        2. 提议解答 - 已有多少有效解答
        3. 衡量前景 - 继续探索的价值评分
        4. 回溯决策 - 是否应该放弃当前路径
        
        Returns:
            {
                "prospect_score": float,  # 0-100，继续探索的价值
                "prospect_level": str,    # high/medium/low/dead_end
                "recommendations": [...], # 具体建议
                "prune": bool,            # 是否应该剪枝
                "branch_suggestions": [...] # 备选路径建议
            }
        """
        prospect_result = {
            "task_id": task.task_id,
            "prospect_score": 50.0,  # 默认中性
            "prospect_level": "medium",
            "recommendations": [],
            "prune": False,
            "branch_suggestions": [],
        }
        
        # === 1. 新颖性评分 ===
        novelty_score = 50.0
        if task.tags:
            # 与核心系统相关的标签权重更高
            high_value_tags = ["constraint", "protocol", "axiom", "experience", "archaeology"]
            tag_match = sum(1 for t in task.tags if any(hvt in t.lower() for hvt in high_value_tags))
            novelty_score += tag_match * 10
        
        # 考古类任务新颖性较高
        if any(t in task.tags for t in ["fragment_archaeology", "r1", "r2"]):
            novelty_score += 15
        
        # 与词库已有概念关联度高 → 新颖性下降（可能是已知知识）
        if self.lexicon and task.evidence:
            keywords = re.findall(r"[\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z0-9_]{2,}", task.title)
            matched = sum(1 for kw in keywords[:5] if self.lexicon.get_concept(kw))
            novelty_score -= matched * 5
        
        novelty_score = max(0, min(100, novelty_score))
        
        # === 2. 证据质量评分 ===
        quality_score = 50.0
        evidence_count = len(task.evidence)
        if evidence_count >= 5:
            quality_score += 20
        elif evidence_count >= 3:
            quality_score += 10
        elif evidence_count >= 1:
            quality_score += 0
        else:
            quality_score -= 30
        
        # 证据内容长度
        if task.evidence:
            avg_len = sum(
                len(e.get("content", "")) if isinstance(e, dict) else len(str(e))
                for e in task.evidence
            ) / len(task.evidence)
            if avg_len > 200:
                quality_score += 15
            elif avg_len > 100:
                quality_score += 5
        
        # 有反例 → 证据质量更高（说明认真验证过）
        if task.counter_examples and len(task.counter_examples) >= 1:
            quality_score += 10
        
        quality_score = max(0, min(100, quality_score))
        
        # === 3. 概念覆盖率评分 ===
        coverage_score = 50.0
        if self.lexicon:
            stats = self.lexicon.get_stats()
            categories = stats.get("categories", {})
            weak_categories = [cat for cat, count in categories.items() if count <= 2]
            
            # 任务是否覆盖薄弱分类
            title_lower = task.title.lower()
            for weak_cat in weak_categories[:5]:
                if weak_cat.lower() in title_lower:
                    coverage_score += 15
                    break
        
        coverage_score = max(0, min(100, coverage_score))
        
        # === 4. 综合前景评分 ===
        prospect_result["prospect_score"] = (novelty_score * 0.4 + quality_score * 0.35 + coverage_score * 0.25)
        
        # === 5. 前景等级 ===
        score = prospect_result["prospect_score"]
        if score >= 70:
            prospect_result["prospect_level"] = "high"
        elif score >= 50:
            prospect_result["prospect_level"] = "medium"
        elif score >= 30:
            prospect_result["prospect_level"] = "low"
        else:
            prospect_result["prospect_level"] = "dead_end"
        
        # === 6. 剪枝决策 ===
        # 死路或低价值任务应该剪枝
        review_count = getattr(task, "review_count", 0)
        if prospect_result["prospect_level"] == "dead_end":
            prospect_result["prune"] = True
            prospect_result["recommendations"].append("⚠️ 任务已陷入死路，建议剪枝放弃")
        elif prospect_result["prospect_level"] == "low" and review_count >= 2:
            prospect_result["prune"] = True
            prospect_result["recommendations"].append("⚠️ 任务价值低且多次重审，建议剪枝")
        elif review_count >= 5:
            # 超过 5 次重审，无论价值如何都应该给出建议
            prospect_result["recommendations"].append(f"⚠️ 已重审 {review_count} 次，建议强制通过或剪枝")
        
        # === 7. 分支建议 ===
        if prospect_result["prospect_level"] in ["low", "dead_end"] and task.tags:
            # 建议转换方向
            if "lexicon" in task.tags:
                prospect_result["branch_suggestions"].append({
                    "type": "redirect",
                    "suggestion": "词库补全方向遇阻，可尝试考古方向"
                })
            if "archaeology" in task.tags:
                prospect_result["branch_suggestions"].append({
                    "type": "redirect", 
                    "suggestion": "考古方向价值有限，可尝试补全词库或构建约束"
                })
        
        # 高价值但证据不足的任务建议继续
        if prospect_result["prospect_level"] == "high" and evidence_count < 3:
            prospect_result["recommendations"].append("✨ 高价值任务，建议继续补充证据")
        
        return prospect_result


class Archivist:
    """
    档案官 — 归档任务，建立索引，形成知识库

    不决定价值。
    只负责好好存起来，确保找得到。
    """

    def __init__(self, task_pool: TaskPool, memory_index=None, lexicon=None):
        self.task_pool = task_pool
        self.memory_index = memory_index
        self.lexicon = lexicon

    def archive_task(self, task: Task) -> bool:
        """归档已批准的任务，写入记忆索引"""
        if task.status != "approved" or task.guardian_decision not in {
            "axiom", "constraint", "experience"
        }:
            return False

        archived = self.task_pool.move_task(
            task.task_id,
            "archived",
            actor="archivist",
            task=task,
        )
        if archived is None:
            return False

        if self.memory_index:
            archive_note = self._format_task_archive(task)
            self.memory_index.add(
                title=f"[任务归档] {task.title}",
                content=archive_note,
                memory_type="task_archive",
                category="任务归档",
                source="archivist",
                tags=task.tags + ["archived", task.task_id],
            )

        return True

    def _format_task_archive(self, task: Task) -> str:
        lines = [
            f"## 任务ID: {task.task_id}",
            f"**标题**: {task.title}",
            f"**创建者**: {task.creator}",
            f"**优先级**: {task.priority}",
            f"**假设**: {task.hypothesis or '无'}",
            "",
            f"**证据数**: {len(task.evidence)}",
            f"**反例数**: {len(task.counter_examples)}",
            "",
        ]

        if task.evidence:
            lines.append("### 核心证据")
            for i, ev in enumerate(task.evidence[:5]):
                if isinstance(ev, dict):
                    lines.append(f"{i+1}. [{ev.get('source', 'unknown')}] {ev.get('content', '')[:150]}")
                else:
                    lines.append(f"{i+1}. {str(ev)[:150]}")
            lines.append("")

        if task.counter_examples:
            lines.append("### 反例/质疑")
            for i, ce in enumerate(task.counter_examples[:5]):
                if isinstance(ce, dict):
                    lines.append(f"{i+1}. {ce.get('content', '')[:150]}")
                else:
                    lines.append(f"{i+1}. {str(ce)[:150]}")
            lines.append("")

        if task.result:
            lines.append(f"### 结论")
            if isinstance(task.result, dict):
                lines.append(json.dumps(task.result, ensure_ascii=False, indent=2)[:500])
            else:
                lines.append(str(task.result)[:500])
            lines.append("")

        lines.extend([
            f"**引用次数**: {task.reference_count}",
            f"**创建时间**: {task.created_at}",
            f"**归档时间**: {datetime.now().isoformat()}",
        ])

        return "\n".join(lines)


class Guardian:
    """
    守护者 — 决定任务结论去哪里

    四个去向：
    - 进入公理（axiom）—— 已验证的基本规律
    - 进入约束（constraint）—— 系统必须遵守的规则
    - 进入经验库（experience）—— 有用但不是铁律
    - 直接废弃（discard）—— 不值得保留
    """

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None, experience_deposition=None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.experience_deposition = experience_deposition

    def judge(self, task: Task) -> Dict[str, Any]:
        """审判一个归档的任务，决定它的最终去向"""
        decision = {
            "task_id": task.task_id,
            "verdict": "experience",
            "reason": "",
            "promoted": False,
        }

        ev_count = len(task.evidence)
        ce_count = len(task.counter_examples)

        if ev_count == 0:
            decision["verdict"] = "discard"
            decision["reason"] = "无证据支撑，无保留价值"
        elif ev_count >= 5 and ce_count == 0:
            # 闭环反馈：升级为 axiom 前检查是否和已有 lesson 冲突
            conflict_found = False
            if self.experience_deposition:
                title_kw = task.title[:20].lower()
                related_lessons = self.experience_deposition.find_related(task.title[:20], limit=5)
                for exp in related_lessons:
                    if exp.experience_type == "lesson":
                        conflict_found = True
                        decision["verdict"] = "experience"
                        decision["reason"] = f"证据充分但与历史教训 {exp.experience_id} 冲突，降级为经验待复核"
                        break
            if not conflict_found:
                decision["verdict"] = "axiom"
                decision["reason"] = f"{ev_count}条证据支撑，0反例，可作为临时公理"
                decision["promoted"] = True
        elif ev_count >= 3 and task.priority in ["high", "critical"]:
            decision["verdict"] = "constraint"
            decision["reason"] = "高优先级任务，证据充分，可作为约束"
            decision["promoted"] = True
        elif ev_count >= 2:
            decision["verdict"] = "experience"
            decision["reason"] = "有一定证据，但反例或不足仍存，归入经验库"
        else:
            decision["verdict"] = "experience"
            decision["reason"] = "证据有限，暂存经验库待后续验证"

        task.guardian_decision = decision["verdict"]
        task.add_validation_note(
            f"Guardian判决: {decision['verdict']} — {decision['reason']}",
            validator="guardian",
        )
        task.touch()

        if decision["verdict"] == "discard":
            self.task_pool.update_task(task)
            self.task_pool.move_task(task.task_id, "rejected", actor="guardian", task=task)
        elif decision["promoted"] and self.lexicon:
            if decision["verdict"] == "axiom":
                cat = "核心原则"
            elif decision["verdict"] == "constraint":
                cat = "治理原则"
            else:
                cat = "经验沉淀"

            concept_name = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_]", "_", task.title[:30])
            if concept_name and not self.lexicon.get_concept(concept_name):
                self.lexicon.add_concept(
                    name=concept_name,
                    definition=f"[Guardian-{decision['verdict']}] {task.hypothesis or task.title}",
                    category=cat,
                    source=f"guardian:{task.task_id}",
                    importance=80 if decision["verdict"] == "axiom" else 65,
                )
            self.task_pool.update_task(task)
        else:
            self.task_pool.update_task(task)

        return decision
