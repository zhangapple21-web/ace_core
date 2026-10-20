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
from .knowledge_reuse import JOIN_SOURCE_PREFIX
from .execution_discipline import (
    add_evidence_ledger_entry,
    ensure_execution_discipline,
    execution_gate,
    record_checkpoint,
    record_event,
)
from .delivery_protocols import ensure_task_protocols, protocol_errors, validate_release_receipt
from .miner_pool.task_profiles import get_task_profile
from .execution_contract import build_execution_system_prompt, summarize_execution_feedback
from .neuro_symbolic_claims import (
    audit_symbolic_claims,
    claims_from_audit,
    combine_symbolic_claim_sets,
)
from .cognitive_think_gate import COGNITIVE_HUB, LOOP_BLOCKED, evaluate_cognitive_think_gate


def _invalid_symbolic_audit(reason: str, side_effect_scope: str) -> dict[str, Any]:
    """Represent a bounded symbolic-audit failure without stopping the role."""
    audit = audit_symbolic_claims("INVALID", side_effect_scope=side_effect_scope)
    audit["issues"] = [{"claim_id": None, "code": reason, "field": "evidence_context"}]
    return audit


def _symbolic_evidence_snapshot(evidence_items: Any) -> list[dict[str, str]]:
    """Bound and normalize evidence identity/content used by the audit digest.

    Task records can legitimately contain the same evidence more than once: the
    Validator's convergence logic already treats exact duplicates as one record.
    Keep the raw input and per-item limits fail-closed, but do not spend the
    aggregate digest budget repeatedly on an identical item.
    """
    if not isinstance(evidence_items, list) or len(evidence_items) > 512:
        raise ValueError("symbolic evidence context exceeds the bounded list size")
    snapshot: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    source_chars = 0
    content_chars = 0
    for item in evidence_items:
        if isinstance(item, dict):
            source = item.get("source") or item.get("source_ref") or ""
            kind = item.get("kind") or item.get("type") or item.get("evidence_type") or ""
            if not kind and item.get("source_ref"):
                kind = "admission"
            content = item.get("content") or item.get("detail") or ""
        else:
            source, kind, content = item, "", ""
        source = source.strip() if isinstance(source, str) else ""
        kind = kind.strip() if isinstance(kind, str) else ""
        if not kind and isinstance(item, dict) and item.get("source_ref"):
            kind = "admission"
        content = content.strip() if isinstance(content, str) else ""
        if len(source) > 512 or len(content) > 32768:
            raise ValueError("symbolic evidence item exceeds the bounded field size")
        if not source:
            continue
        normalized_kind = kind.lower()
        identity = (source, normalized_kind, content)
        if identity in seen:
            continue
        seen.add(identity)
        source_chars += len(source)
        content_chars += len(content)
        if source_chars > 32768 or content_chars > 32768:
            raise ValueError("symbolic evidence context exceeds aggregate budgets")
        snapshot.append({"source": source, "kind": normalized_kind, "content": content})
    return snapshot


LOCAL_ARCHAEOLOGY_TAGS = {"archaeology", "local_archaeology", "fragment", "碎片考古", "考古"}

# Evidence written by the Archivist. An `archivist:<id>` record whose body is a
# task card - it opens with this header - is the system quoting its own ledger
# back at itself, not an observation of anything outside it.
ARCHIVIST_SOURCE_PREFIX = "archivist:"
_TASK_CARD_HEADER = "## 任务ID: RQ-"


def _is_reuse_pointer(item: Any) -> bool:
    """True for entries that point at archived knowledge instead of observing
    the world. Governance must not count them as corroboration.

    Two shapes reach this predicate, and the second was previously invisible.

    `knowledge_join:` is the declared reuse pointer. The `archivist:` shape is an
    archived task card rendered back as evidence. On 2026-10-13 the
    free-zone reflection relay filed 59 of these, and each cited the other two:
    a task whose evidence is two other task cards is not two independent
    observations, it is a closed ring of the system reading its own backlog.
    Validator scored the pair as corroboration, could not converge, and the ring
    parked 59 tasks in `blocked` with the reason "相同证据集重复验证达到上限" -
    the correct verdict, reached for the wrong reason, and unrecoverable because
    no amount of re-validation could break a ring.

    Both shapes are the same claim: this points at what we already wrote, not at
    the world.
    """
    if not isinstance(item, dict):
        return False
    source = str(item.get("source") or "")
    if source.startswith(JOIN_SOURCE_PREFIX):
        return True
    if source.startswith(ARCHIVIST_SOURCE_PREFIX):
        return str(item.get("content") or "").lstrip().startswith(_TASK_CARD_HEADER)
    return False


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


def _declares_delivery(task: Task) -> bool:
    outputs = task.outputs if isinstance(task.outputs, dict) else {}
    delivery = outputs.get("delivery")
    return isinstance(delivery, dict) and bool(str(delivery.get("required_path") or "").strip())


def _has_verified_delivery(task: Task) -> bool:
    """True when the delivery gate has verified the declared artifact on disk."""
    outputs = task.outputs if isinstance(task.outputs, dict) else {}
    delivery = outputs.get("delivery")
    if not isinstance(delivery, dict):
        return False
    verification = delivery.get("verification")
    return isinstance(verification, dict) and verification.get("satisfied") is True


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
    if not response.get("success"):
        reason = "model_call_failed"
    elif not allowed:
        reason = "task_profile_mismatch"
    elif not isinstance(content, str) or not content.strip():
        reason = "empty_model_content"
    else:
        reason = ""
    executed = not reason
    return {
        "executed": executed,
        "status": "pass" if executed else "not_run",
        "reason": reason,
    }


_MODEL_OUTPUT_CONTRACT_FIELDS = (
    "facts",
    "evidence",
    "inference",
    "unknowns",
    "objections",
    "next_verification",
    "stop_condition",
)
_VALIDATOR_FINDING_FIELDS = (
    "hard_objections",
    "advisory_objections",
    "counter_examples",
)


def _has_nonempty_contract_value(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple)):
        return any(_has_nonempty_contract_value(item) for item in value)
    if isinstance(value, dict):
        return any(_has_nonempty_contract_value(item) for item in value.values())
    return False


def _output_contract_gate(
    response: Dict[str, Any], role: str, quality_passed: bool
) -> Dict[str, Any]:
    """Require role-relevant structured output after route/content eligibility.

    Researcher may return a partial structured result from its declared fields.
    Validator must additionally provide all three review arrays (empty arrays
    are valid), so downstream objection parsing cannot silently substitute
    omitted or malformed findings with empty lists.
    """
    role_fields = list(_MODEL_OUTPUT_CONTRACT_FIELDS)
    if role == "validator":
        role_fields.extend(_VALIDATOR_FINDING_FIELDS)
    result = {
        "executed": False,
        "status": "not_run",
        "reason": "model_response_not_eligible",
        "contract": "json_object_with_role_fields",
        "fields_present": [],
        "missing_fields": list(role_fields),
        "invalid_fields": [],
    }
    if not quality_passed:
        return result
    if role not in {"researcher", "validator"}:
        result["reason"] = "unsupported_role_contract"
        return result
    try:
        payload = json.loads(response.get("content", ""))
    except (TypeError, ValueError):
        result.update(
            executed=True,
            status="fail",
            reason="response_not_json",
            missing_fields=list(role_fields),
        )
        return result
    if not isinstance(payload, dict):
        result.update(executed=True, status="fail", reason="response_not_json_object")
        return result

    present = [field for field in _MODEL_OUTPUT_CONTRACT_FIELDS if field in payload]
    missing = [field for field in role_fields if field not in payload]
    invalid_fields = [
        field for field in _MODEL_OUTPUT_CONTRACT_FIELDS
        if field in payload and not _has_nonempty_contract_value(payload[field])
    ]
    reason = ""
    if role == "validator":
        present.extend(field for field in _VALIDATOR_FINDING_FIELDS if field in payload)
        invalid_fields.extend(
            field for field in _VALIDATOR_FINDING_FIELDS
            if field in payload
            and (
                not isinstance(payload[field], list)
                or any(not isinstance(value, str) for value in payload[field])
            )
        )
        missing_findings = [field for field in _VALIDATOR_FINDING_FIELDS if field not in payload]
        has_review_context = bool(
            set(present).intersection(_MODEL_OUTPUT_CONTRACT_FIELDS)
        )
        passed = has_review_context and not missing_findings and not invalid_fields
        if invalid_fields:
            reason = "invalid_validator_finding_types"
        elif missing_findings:
            reason = "missing_validator_finding_fields"
        elif not has_review_context:
            reason = "no_known_role_contract_fields"
    else:
        passed = bool(present) and not invalid_fields
        if invalid_fields:
            reason = "empty_research_contract_fields"
        elif not passed:
            reason = "no_known_role_contract_fields"

    result.update(
        executed=True,
        status="pass" if passed else "fail",
        reason="" if passed else reason,
        contract=("researcher_json" if role == "researcher" else "validator_json"),
        fields_present=present,
        missing_fields=missing,
        invalid_fields=invalid_fields,
    )
    return result


def _record_model_execution(
    task: Task,
    role: str,
    llm_router,
    prompt: str,
    ace_local_run_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
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
    if isinstance(ace_local_run_id, str) and ace_local_run_id.strip():
        # This is deliberately ACE-local correlation only: never a provider
        # request/response/billing identifier and never backfilled on history.
        trace["ace_local_run_id"] = ace_local_run_id.strip()
    try:
        envelope = task.outputs.get("execution_discipline", {}) if isinstance(task.outputs, dict) else {}
        routing_context = {
            "task_id": task.task_id,
            "title": task.title,
            "priority": task.priority,
            "tags": list(task.tags or []),
            "complexity": envelope.get("complexity") if isinstance(envelope, dict) else None,
            "execution_discipline": envelope if isinstance(envelope, dict) else {},
            "depends_on": list(task.depends_on or []),
        }
        prior_traces = task.outputs.get("model_execution", []) if isinstance(task.outputs, dict) else []
        if not isinstance(prior_traces, list):
            prior_traces = []
        prior_feedback = None
        if prior_traces:
            prior_feedback = prior_traces[-1].get("execution_feedback") if isinstance(prior_traces[-1], dict) else None
            if isinstance(prior_feedback, dict):
                # This is a bounded routing hint from the previous attempt,
                # not a claim about the truth of the model's content.
                routing_context["execution_feedback"] = dict(prior_feedback)
        think_gate = evaluate_cognitive_think_gate(
            actor_role=COGNITIVE_HUB,
            # Only attempts that actually reached a model consume think
            # budget. A trace with api_called but no tried model never left
            # the router: the gate opened, selection found nothing, and no
            # thinking happened. Counting those sealed RQ-20261008-022 shut
            # even after the router-failure fix, because its two old traces
            # show api_called with empty tried_models.
            think_rounds=sum(
                1 for trace in prior_traces
                if isinstance(trace, dict)
                and trace.get("api_called") is True
                and (
                    bool(trace.get("tried_models"))
                    or bool(trace.get("selected_model"))
                )
            ),
            new_evidence_since_last_think=(
                isinstance(prior_feedback, dict)
                and prior_feedback.get("status") == "TEXT_UNSTRUCTURED"
            ),
            execution_requested=False,
            existing_execution_authorized=False,
            complexity=str((envelope.get("complexity") if isinstance(envelope, dict) else None) or "medium"),
        )
        trace["cognitive_think"] = think_gate
        if think_gate.get("status") == LOOP_BLOCKED or think_gate.get("thinking_permitted") is not True:
            trace["api_called"] = False
            trace["api_result"] = "blocked"
            trace["result"] = "blocked"
            trace["error"] = "THINK_LOOP_BLOCKED"
            trace["execution_feedback"] = summarize_execution_feedback("")
            trace["trace_complete"] = False
            task.outputs.setdefault("model_execution", []).append(trace)
            return None
        response = llm_router.chat(
            task_type=task_type,
            messages=[{"role": "user", "content": prompt}],
            system_prompt=build_execution_system_prompt(
                role=role,
                task_type=task_type,
                task_id=task.task_id,
                role_instruction="Return concise task analysis grounded in the supplied task context.",
            ),
            # Provider fallback is owned by the gateway; ACE gets one bounded
            # task attempt so a failed request cannot multiply upstream spend.
            max_retries=1,
            task_context=routing_context,
            data_boundary={"data_class": getattr(task, "data_class", "PRIVATE")},
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
    if isinstance(response.get("routing"), dict):
        trace["router_decision"] = dict(response["routing"])
    trace["capability"] = str(response.get("capability", ""))
    trace["routing_complexity"] = str(response.get("complexity", ""))
    trace["fallback_chain"] = list(trace["tried_models"])
    trace["fallback"] = len(trace["tried_models"]) > 1
    if not trace["selected_model"] and trace["tried_models"]:
        selected_provider, trace["selected_model"] = trace["tried_models"][-1].split(":", 1)
        if not trace["provider"]:
            trace["provider"] = selected_provider
    trace["error"] = str(response.get("error", ""))
    trace["api_result"] = "success" if response.get("success") else "failed"
    content = response.get("content", "")
    allowed = _model_result_allowed(profile, trace["provider"], trace["selected_model"])
    trace["quality_gate"] = _quality_gate(response, allowed)
    usable = trace["quality_gate"]["executed"]
    if response.get("success") and not allowed:
        trace["error"] = "selected provider/model violates task profile"
    elif response.get("success") and not usable:
        trace["error"] = trace["quality_gate"].get("reason") or "model response has no usable content"
    trace["execution_feedback"] = summarize_execution_feedback(content if usable else "")
    trace["output_contract_gate"] = _output_contract_gate(
        response, role, quality_passed=usable
    )
    output_eligible = (
        usable
        and role in {"researcher", "validator"}
        and trace["output_contract_gate"].get("status") == "pass"
    )
    trace["result"] = "success" if output_eligible else "failed"
    if usable and not output_eligible:
        contract_reason = trace["output_contract_gate"].get("reason") or "role_contract_rejected"
        trace["error"] = "model output contract failed: " + str(contract_reason)
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
    # The execution receipt may preserve an off-profile or empty response for
    # diagnostics, but only a response that passed both the route and content
    # gates is a model result.  Downstream roles must not consume the raw reply.
    return response if output_eligible else None


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

        # 自主缺口发现（后台自发现，不走窗口对话）：
        # 以下检查均为确定性、 bounded、无模型调用；标题保持稳定以借 _task_exists 去重，
        # 同一缺口只建一次，归档后不再重建——复发需新证据另起任务。
        try:
            blocked_all = self.task_pool.list_tasks(status="blocked", limit=200)
            missing_fuse = sum(
                1 for t in blocked_all
                if isinstance(getattr(t, "outputs", None), dict)
                and "ruin_fuse" not in (t.outputs or {})
            )
            if missing_fuse > 0:
                candidates.append({
                    "title": "存量非收敛任务缺熔断方向待补",
                    "hypothesis": f"blocked中{missing_fuse}个任务无ruin_fuse熔断方向（接线前存量），需批量补方向或确认外部证据已到",
                    "priority": "high" if missing_fuse >= 10 else "medium",
                    "tags": ["gap", "ruin-smelter", "backfill"],
                })
        except Exception:
            pass
        try:
            pend_all = self.task_pool.list_tasks(status="pending", limit=200)
            low_flood = sum(1 for t in pend_all if getattr(t, "priority", "") == "low")
            if low_flood >= 15:
                candidates.append({
                    "title": "低优先级碎沫堆积需批量分诊",
                    "hypothesis": f"pending中{low_flood}个low任务（多为EXTREVIEW碎沫），需批量去重/归并而非逐个领取",
                    "priority": "medium",
                    "tags": ["gap", "triage", "low-flood"],
                })
        except Exception:
            pass
        try:
            arch_all = self.task_pool.list_tasks(status="archived", limit=20)
            with_lineage = sum(
                1 for t in arch_all
                if isinstance(getattr(t, "outputs", None), dict)
                and isinstance((t.outputs or {}).get("state_lineage"), list)
            )
            if arch_all and with_lineage == 0:
                candidates.append({
                    "title": "状态谱系缺TURIYA闭环验证待补",
                    "hypothesis": "近20个归档任务无state_lineage，接线后新任务应带A-U-M谱系，需验证闭环是否真实流转",
                    "priority": "medium",
                    "tags": ["gap", "state-machine", "lineage"],
                })
        except Exception:
            pass
        try:
            deaths = self.daemon_state.get("death_count", 0)
            misses = self.daemon_state.get("consecutive_misses", 0)
            if isinstance(deaths, int) and deaths >= 100:
                candidates.append({
                    "title": "daemon死亡计数过百需根因复盘",
                    "hypothesis": f"death_count={deaths}，consecutive_misses={misses}，需从healing_log提炼约束而非只拉起",
                    "priority": "high" if misses else "medium",
                    "tags": ["gap", "resilience", "daemon"],
                })
        except Exception:
            pass

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

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None, eco_parser=None, slice_clusterer=None, llm_router=None, experience_deposition=None, run_id_supplier=None, policy_card_store=None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.eco_parser = eco_parser
        self.slice_clusterer = slice_clusterer
        self.llm_router = llm_router
        self.experience_deposition = experience_deposition
        self.run_id_supplier = run_id_supplier
        self.policy_card_store = policy_card_store

    def _ace_local_run_id(self) -> Optional[str]:
        if not callable(self.run_id_supplier):
            return None
        value = self.run_id_supplier()
        return value.strip() if isinstance(value, str) and value.strip() else None

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
            # Historical system-observation tasks recorded the observation ID
            # but not a generic source field.  The ID is still a durable,
            # auditable local evidence reference; recover it without claiming
            # an independent external source or changing any validation gate.
            if not source and isinstance(item.get("observation_id"), str):
                source = f"runtime_observation:{item['observation_id']}"
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
                if task.task_id == exclude_task_id:
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

    @staticmethod
    def _delivery_first(tasks: List[Task]) -> List[Task]:
        """Order ties so tasks promising a physical artifact are researched first.

        Priority ordering is untouched; this only breaks ties inside one
        priority level. Without it the researcher's bounded per-cycle budget is
        consumed by internal rework loops that can never deliver anything, and a
        waiting external will never reaches the review queue where the delivery
        gate can verify it.
        """
        return sorted(
            tasks,
            key=lambda task: 0 if _declares_delivery(task) else 1,
        )

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
                tasks = self._delivery_first(
                    self.task_pool.list_tasks(status=status, priority=pri, limit=10000)
                )
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
                related = self.experience_deposition.find_related(
                    kw, limit=2, actor="researcher")
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
        
        if self.policy_card_store:
            unique_candidates = self.policy_card_store.rank_candidates(task, unique_candidates)
        return unique_candidates[:max_candidates]

    def research_task(self, task: Task, max_evidence: int = 5) -> Dict[str, Any]:
        """对任务进行研究，收集证据"""
        ensure_execution_discipline(task)
        ready, reason = execution_gate(task, allow_backfill=False)
        if not ready:
            record_event(task, "stop", actor="execution_discipline", reason=reason)
            raise RuntimeError(reason)
        record_event(task, "clarified", actor="execution_discipline")
        record_event(task, "planned", actor="execution_discipline")
        record_event(task, "routed", actor="execution_discipline")
        record_checkpoint(
            task,
            "pre_execution_gate",
            actor="execution_discipline",
            complexity=task.outputs.get("execution_discipline", {}).get("complexity"),
            route=task.outputs.get("execution_discipline", {}).get("constraints", {}).get("route"),
        )
        record_event(task, "started", actor="researcher")
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
        symbolic_evidence_context = list(admitted_evidence)
        audit_task_evidence = _symbolic_evidence_snapshot(list(task.evidence or []))
        evidence_candidates_for_audit: list[dict[str, Any]] = []
        symbolic_audit = audit_symbolic_claims(None)
        model_response = _record_model_execution(
            task,
            "researcher",
            self.llm_router,
            (
                f"Task: {task.title}\nHypothesis: {task.hypothesis}\n"
                "Role: analyze the supplied evidence, identify alternatives and "
                "invalidating conditions. Do not invent evidence. Return JSON with "
                "facts, evidence, inference, unknowns, objections, "
                "next_verification, stop_condition, and symbolic_claims. Each "
                "symbolic_claim must be an object with claim_id, subject, predicate, "
                "object, polarity (SUPPORTS/REFUTES/UNKNOWN), epistemic_status "
                "(FACT/INFERENCE/HYPOTHESIS/UNKNOWN), evidence_refs (exact source "
                "ids from the supplied evidence), premise_ids, and falsifiable_if. "
                "Use claim-level UNKNOWN when unsupported; citations prove traceability "
                "only, never entailment. This is a candidate format, not verified truth.\n"
                f"Admitted evidence:\n{evidence_context or '(none)'}"
            ),
            ace_local_run_id=self._ace_local_run_id(),
        )
        research_output_contract = {}
        if isinstance(model_response, dict) and task.outputs.get("model_execution"):
            last_trace = task.outputs["model_execution"][-1]
            research_output_contract = (
                last_trace.get("output_contract_gate", {})
                if isinstance(last_trace, dict) else {}
            )
            if research_output_contract.get("status") == "pass":
                task.outputs.pop("neuro_symbolic_audit", None)
                task.outputs.pop("neuro_symbolic_audit_task_id", None)
                task.outputs.pop("neuro_symbolic_audit_model_sha256", None)
                task.outputs.pop("research_model_execution_receipt", None)
                content = model_response.get("content")
                response_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
                try:
                    model_payload = json.loads(content)
                    model_claims = (
                        model_payload.get("symbolic_claims")
                        if isinstance(model_payload, dict) else None
                    )
                    audit_claims = model_claims if isinstance(model_claims, list) else None
                    if isinstance(audit_claims, list):
                        audit_claims = [
                            {
                                **claim,
                                "premise_ids": [
                                    premise for premise in claim.get("premise_ids", [])
                                    if not (
                                        isinstance(premise, str)
                                        and premise.startswith(("researcher:", "validator:"))
                                    )
                                ],
                            }
                            if isinstance(claim, dict)
                            and isinstance(claim.get("premise_ids"), list)
                            else claim
                            for claim in audit_claims
                        ]
                    audit_claims_digest = hashlib.sha256(
                        json.dumps(
                            {"symbolic_claims": audit_claims},
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()
                    research_task_evidence = _symbolic_evidence_snapshot(
                        audit_task_evidence
                        + [
                            {
                                "source": ev.get("source", ""),
                                "kind": "research",
                                "content": ev.get("content", "")[:300],
                            }
                            for ev in evidence_candidates_for_audit
                            if isinstance(ev, dict)
                        ]
                    )
                    research_evidence_snapshot = _symbolic_evidence_snapshot(
                        symbolic_evidence_context + research_task_evidence
                    )
                    research_evidence_digest = hashlib.sha256(
                        json.dumps(
                            research_evidence_snapshot,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    ).hexdigest()
                    task.outputs["model_research_result"] = {
                        "content": content[:4000],
                        "response_sha256": response_sha256,
                        "audit_claims": audit_claims,
                        "audit_claims_sha256": audit_claims_digest,
                        "audit_evidence": research_evidence_snapshot,
                        "audit_task_evidence": research_task_evidence,
                        "audit_evidence_sha256": research_evidence_digest,
                        "at": datetime.now().isoformat(),
                    }
                    symbolic_audit = audit_symbolic_claims(
                        model_claims,
                        research_evidence_snapshot,
                        side_effect_scope="researcher_audit_persisted_as_task_metadata",
                    )
                except (TypeError, ValueError):
                    # The output contract already parsed the content, but keep
                    # the symbolic shadow fail-closed if the payload changes.
                    task.outputs.pop("model_research_result", None)
                    symbolic_audit = audit_symbolic_claims("INVALID")
                task.outputs["neuro_symbolic_audit"] = symbolic_audit
                task.outputs["neuro_symbolic_audit_task_id"] = task.task_id
                task.outputs["neuro_symbolic_audit_model_sha256"] = task.outputs[
                    "model_research_result"
                ]["response_sha256"]
            else:
                task.outputs.pop("model_research_result", None)
                task.outputs.pop("neuro_symbolic_audit", None)
                task.outputs.pop("neuro_symbolic_audit_task_id", None)
                task.outputs.pop("neuro_symbolic_audit_model_sha256", None)
                model_response = None
        else:
            # Never let a stale symbolic audit or prior model response stand in
            # for the current research attempt.
            task.outputs.pop("neuro_symbolic_audit", None)
            task.outputs.pop("neuro_symbolic_audit_task_id", None)
            task.outputs.pop("neuro_symbolic_audit_model_sha256", None)
            if task.outputs.get("model_research_result"):
                task.outputs.pop("model_research_result", None)

        # A blocked or failed model call is not a research result.  Without this
        # the failure was invisible: the flow continued into the keyword path,
        # whose candidates are built from title tokens, and the task was then
        # validated on the evidence count and archived with an outcome receipt.
        # Measured on 2026-10-18: 228 archived tension_question tasks, none with
        # a model_execution trace and none with a model_research_result, every
        # one carrying the same "core hypothesis: 验证系统 / 来源 / obs" and the
        # same three memory hits.  The questions were never read.
        #
        # The cause was a correct decision by a different component: those tasks
        # are data_class=PRIVATE, so the data boundary refused egress with
        # DATA_BOUNDARY_BLOCKED:sensitive_data_cannot_egress.  Refusing to send
        # the data was right.  Turning that refusal into a signed "researched"
        # outcome was not, and it made the TaskPool's completion counts report
        # work that never happened.
        #
        # So: record why the model contributed nothing, and refuse to present a
        # keyword-only candidate set as a completed research step.  The task
        # still closes its lifecycle - closing is honest here - but the result
        # now carries the reason instead of a fabricated hypothesis.
        model_attempted = False
        model_engaged = False
        model_block_reason = ""
        if isinstance(model_response, dict):
            model_attempted = True
            model_engaged = True
            if research_output_contract.get("status") != "pass":
                task.outputs.pop("neuro_symbolic_audit", None)
                task.outputs.pop("neuro_symbolic_audit_task_id", None)
                task.outputs.pop("neuro_symbolic_audit_model_sha256", None)
                model_block_reason = str(
                    research_output_contract.get("reason") or "model_output_contract_failed"
                )[:200]
        elif task.outputs.get("model_execution"):
            task.outputs.pop("neuro_symbolic_audit", None)
            task.outputs.pop("neuro_symbolic_audit_task_id", None)
            task.outputs.pop("neuro_symbolic_audit_model_sha256", None)
            task.outputs.pop("model_research_result", None)
            model_attempted = True
            traces = task.outputs.get("model_execution")
            last = traces[-1] if isinstance(traces, list) and traces else {}
            if isinstance(last, dict):
                model_block_reason = str(
                    last.get("error") or last.get("api_result") or "model_returned_no_content"
                )[:200]

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
                    # Per-cycle daemon summaries are operational telemetry, not
                    # independent evidence for an arbitrary research question.
                    # Promoting them inflated evidence counts and repeatedly
                    # injected the same generic runtime text into rework tasks.
                    if hit.get("type") in {"daily_summary", "cycle_summary"}:
                        continue
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
                related_exp = self.experience_deposition.find_related(
                    kw, limit=3, actor="researcher")
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
        evidence_candidates_for_audit = list(evidence)
        candidates = [
            ev for ev in evidence
            if isinstance(ev, dict)
            and isinstance(ev.get("content"), str)
            and ev.get("content", "").strip()
            and isinstance(ev.get("source", ""), str)
            and ev.get("source", "").strip()
        ]

        # Duplicate records are not corroboration.  The enrichment above iterates
        # keywords and can reach the same memory record through several of them,
        # and research_task re-runs on every rework cycle, so the identical
        # {source, content} was appended over and over.  Measured on
        # RQ-20261004-044: 25 stored items collapsing to 2 unique, repeated over 4
        # rework cycles until MAX_UNCHANGED_REVIEWS declared it non-convergent.
        # The Validator signature is computed over the deduplicated set, so it never
        # moved.  Researching the task harder guaranteed non-convergence: a
        # fail-closed guard defeated by the input path that feeds it.
        #
        # Deduplicate before truncating, otherwise max_evidence buys repeats of the
        # first record instead of distinct ones.  Records already carried by the
        # task are skipped too, so a re-research that finds nothing new stores
        # nothing rather than inflating the count.
        already_present = {
            (item.get("source", ""), item.get("content", ""))
            for item in (task.evidence or [])
            if isinstance(item, dict)
        }
        evidence = []
        seen_in_batch = set()
        for ev in candidates:
            key = (ev.get("source", ""), ev.get("content", "")[:300])
            if key in seen_in_batch or key in already_present:
                continue
            seen_in_batch.add(key)
            evidence.append(ev)
            if len(evidence) >= max_evidence:
                break

        for ev in evidence:
            task.add_evidence(ev.get("content", "")[:300], source=ev.get("source", ""))
            audit_task_evidence.append({
                "source": ev.get("source", ""),
                "kind": "research",
                "content": ev.get("content", "")[:300],
            })
            add_evidence_ledger_entry(
                task,
                "source",
                {"source": ev.get("source", ""), "type": ev.get("type", "unknown")},
            )

        summary_parts = [f"研究了 {len(evidence)} 条证据"]
        if evidence:
            types = Counter(e.get("type", "unknown") for e in evidence)
            summary_parts.append(f"来源分布: {dict(types)}")
        result["research_summary"] = "；".join(summary_parts)
        result["neuro_symbolic_audit"] = symbolic_audit

        task.add_research_note(result["research_summary"])
        
        # 生成多候选假设（ToT 风格）
        candidates = self.generate_candidates(task, max_candidates=3)

        # A candidate set derived only from title tokens is not a hypothesis
        # about the task's question.  Marking it keeps the honesty of the record
        # without discarding the evidence gathering that did happen, and without
        # inventing a second failure path for work that legitimately only needed
        # local evidence.
        keyword_only = bool(candidates) and not model_engaged
        task.result = {
            "evidence_count": len(evidence),
            "counter_count": len(counter_examples),
            "summary": result["research_summary"],
            "candidates": candidates,  # ToT 风格多路径探索
            "model_engaged": model_engaged,
            "model_attempted": model_attempted,
            "model_block_reason": model_block_reason,
            "candidate_basis": "title_keywords_only" if keyword_only else "evidence_or_model",
        }
        
        self.task_pool.update_task(task)
        record_event(task, "researched", actor="researcher", evidence_count=len(evidence))
        record_checkpoint(
            task,
            "research_complete",
            actor="researcher",
            evidence_count=len(evidence),
            counter_example_count=len(counter_examples),
        )
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

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None, llm_router=None, run_id_supplier=None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.llm_router = llm_router
        self.run_id_supplier = run_id_supplier

    def _ace_local_run_id(self) -> Optional[str]:
        if not callable(self.run_id_supplier):
            return None
        value = self.run_id_supplier()
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _unique_evidence(task: Task) -> set:
        # A knowledge_join entry is a pointer at what the archive already knows,
        # not an independent observation of the world. Counting it would let
        # ACE's own memory stand in for corroboration, and it would also move
        # the evidence signature, which can re-open a settled rework loop.
        return {
            (
                item.get("source", "") if isinstance(item, dict) else "",
                item.get("content", "") if isinstance(item, dict) else str(item),
            )
            for item in task.evidence
            if not _is_reuse_pointer(item)
        }

    @staticmethod
    def _unique_counter_examples(task: Task) -> set:
        """Distinct counter-example texts.

        The validator re-deposits its standard objections on every review pass,
        so ``len(task.counter_examples)`` grows by the same handful of texts on
        each round. Measured over all 67 non-convergent blocked tasks (2026-10-11)
        the stored list held 14.4 entries for 3.7 distinct ones - a record that
        reads like fourteen objections and is really four. This mirrors
        ``_unique_evidence``: the stored list stays untouched, and the reader is
        given the count that actually means something.
        """
        return {
            str(item.get("content", "")) if isinstance(item, dict) else str(item)
            for item in task.counter_examples
            if str(item.get("content", "") if isinstance(item, dict) else item).strip()
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

    @staticmethod
    def _model_objections(response: Any) -> Dict[str, List[str]]:
        if not isinstance(response, dict) or not response.get("success"):
            return {"hard_objections": [], "advisory_objections": [], "counter_examples": []}
        content = response.get("content", "")
        if not isinstance(content, str) or not content.strip():
            return {"hard_objections": [], "advisory_objections": [], "counter_examples": []}
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            return {"hard_objections": [], "advisory_objections": [], "counter_examples": []}
        if not isinstance(payload, dict):
            return {"hard_objections": [], "advisory_objections": [], "counter_examples": []}
        parsed = {}
        for field in ("hard_objections", "advisory_objections", "counter_examples"):
            values = payload.get(field, [])
            if not isinstance(values, list):
                values = []
            unique = []
            for value in values[:5]:
                if isinstance(value, str):
                    value = value.strip()
                    if value and len(value) <= 500 and value not in unique:
                        unique.append(value)
            parsed[field] = unique
        return parsed

    def validate_task(self, task: Task) -> Dict[str, Any]:
        """验证一个任务的研究结论，至少找一个反例或疑点"""
        ensure_execution_discipline(task)
        ready, reason = execution_gate(task, allow_backfill=False)
        if not ready:
            record_event(task, "stop", actor="execution_discipline", reason=reason)
            self.task_pool.update_task(task)
            raise RuntimeError(reason)
        protocols = ensure_task_protocols(task, refresh_evidence=True)
        # At the Validator boundary, a structurally valid but UNKNOWN or
        # incomplete packet is still a gate failure.  Ordinary TaskPool work
        # may carry such a packet while evidence is being collected.
        protocol_failures = protocol_errors(protocols, require_evidence=True)
        if protocols.get("active"):
            task.outputs["delivery_protocol_checks"] = {
                "checked_by": "validator",
                "at": datetime.now().isoformat(),
                "errors": protocol_failures,
                "active": True,
            }
        record_event(task, "reviewed", actor="validator")
        record_checkpoint(task, "validation_start", actor="validator")
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
        model_response = _record_model_execution(
            task,
            "validator",
            self.llm_router,
            (
                f"Task: {task.title}\nHypothesis: {task.hypothesis}\n"
                "Role: identify counterexamples and validation risks. Return only a JSON object "
                "with facts, evidence, inference, unknowns, objections, next_verification, "
                "stop_condition, and hard_objections, advisory_objections, "
                "counter_examples arrays of concise strings. Use empty arrays when none. "
                "Optionally emit symbolic_claims with typed subject/predicate/object, "
                "polarity (SUPPORTS/REFUTES/UNKNOWN), epistemic_status "
                "(FACT/INFERENCE/HYPOTHESIS/UNKNOWN), exact evidence_refs, premise_ids, "
                "and falsifiable_if. Distinguish source traceability from entailment; "
                "keep unsupported claims UNKNOWN and conflicts unresolved."
            ),
            ace_local_run_id=self._ace_local_run_id(),
        )
        model_objections = self._model_objections(model_response)
        execution_feedback = {}
        output_contract = {}
        execution_traces = task.outputs.get("model_execution", [])
        latest_trace = {}
        current_validator_trace = (
            execution_traces[-1]
            if isinstance(execution_traces, list) and execution_traces
            and isinstance(execution_traces[-1], dict)
            and execution_traces[-1].get("role") == "validator"
            and execution_traces[-1].get("task_id") == task.task_id
            else None
        )
        if isinstance(execution_traces, list) and execution_traces:
            latest_trace = execution_traces[-1]
            if isinstance(latest_trace, dict):
                execution_feedback = latest_trace.get("execution_feedback", {})
                output_contract = latest_trace.get("output_contract_gate", {})

        admission_records = (
            task.outputs.get("admission", {}).get("evidence", [])
            if isinstance(task.outputs, dict)
            and isinstance(task.outputs.get("admission"), dict) else []
        )
        symbolic_evidence_context = list(admission_records) + list(task.evidence or [])
        researcher_audit = task.outputs.get("neuro_symbolic_audit")
        research_result = task.outputs.get("model_research_result")
        stored_validator_audit = task.outputs.get("validator_neuro_symbolic_audit")
        stored_validator_audit_task_id = task.outputs.get("validator_neuro_symbolic_audit_task_id")
        stored_validator_audit_digest = task.outputs.get("validator_neuro_symbolic_audit_model_sha256")
        validator_audit_metadata_present = any(
            key in task.outputs
            for key in (
                "validator_neuro_symbolic_audit",
                "validator_neuro_symbolic_audit_task_id",
                "validator_neuro_symbolic_audit_model_sha256",
            )
        )
        validator_shadow_present = validator_audit_metadata_present and not (
            isinstance(stored_validator_audit, dict)
            and stored_validator_audit.get("status") == "ABSENT"
        )
        validator_shadow_binding_valid = (
            validator_shadow_present
            and isinstance(stored_validator_audit, dict)
            and stored_validator_audit.get("contract_version") == "ace.neuro_symbolic_claims.v1"
            and stored_validator_audit_task_id == task.task_id
            and isinstance(stored_validator_audit_digest, str)
            and bool(stored_validator_audit_digest)
            and isinstance(stored_validator_audit.get("claims"), list)
            and stored_validator_audit.get("claim_count") == len(stored_validator_audit["claims"])
            and isinstance(stored_validator_audit.get("issues"), list)
        )
        researcher_trace = next(
            (
                trace for trace in reversed(execution_traces)
                if isinstance(trace, dict)
                and trace.get("task_id") == task.task_id
                and trace.get("role") == "researcher"
            ),
            None,
        ) if isinstance(execution_traces, list) else None
        research_content = (
            research_result.get("content") if isinstance(research_result, dict) else None
        )
        research_digest = (
            research_result.get("response_sha256") if isinstance(research_result, dict) else None
        )
        research_claim_payload = (
            research_result.get("audit_claims") if isinstance(research_result, dict) else None
        )
        if isinstance(research_claim_payload, list):
            research_claim_payload = [
                {
                    **claim,
                    "premise_ids": [
                        premise for premise in claim.get("premise_ids", [])
                        if not (
                            isinstance(premise, str)
                            and premise.startswith(("researcher:", "validator:"))
                        )
                    ],
                }
                if isinstance(claim, dict) and isinstance(claim.get("premise_ids"), list)
                else claim
                for claim in research_claim_payload
            ]
        try:
            saved_research_task_evidence = (
                research_result.get("audit_task_evidence")
                if isinstance(research_result, dict) else None
            )
            current_research_evidence = (
                list(admission_records) + saved_research_task_evidence
                if isinstance(saved_research_task_evidence, list)
                else symbolic_evidence_context
            )
            research_evidence_snapshot = _symbolic_evidence_snapshot(current_research_evidence)
        except (TypeError, ValueError):
            research_evidence_snapshot = []
        research_evidence_digest = hashlib.sha256(
            json.dumps(
                research_evidence_snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        try:
            research_claims_reaudited = audit_symbolic_claims(
                research_claim_payload if isinstance(research_claim_payload, list) else None,
                research_evidence_snapshot,
                side_effect_scope="researcher_audit_persisted_as_task_metadata",
            )
        except (TypeError, ValueError):
            research_claims_reaudited = audit_symbolic_claims("INVALID")
        research_response_hash_valid = (
            isinstance(research_content, str)
            and isinstance(research_digest, str)
            and bool(research_digest)
            and hashlib.sha256(research_content.encode("utf-8")).hexdigest() == research_digest
            and isinstance(research_claim_payload, list)
            and hashlib.sha256(
                json.dumps(
                    {"symbolic_claims": research_claim_payload},
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest() == research_result.get("audit_claims_sha256")
        )
        research_reaudit = research_claims_reaudited
        research_binding_valid = (
            isinstance(researcher_audit, dict)
            and researcher_audit.get("contract_version") == "ace.neuro_symbolic_claims.v1"
            and task.outputs.get("neuro_symbolic_audit_task_id") == task.task_id
            and research_response_hash_valid
            and isinstance(researcher_trace, dict)
            and researcher_trace.get("task_id") == task.task_id
            and researcher_trace.get("role") == "researcher"
            and researcher_trace.get("result") == "success"
            and researcher_trace.get("response_sha256") == research_digest
            and isinstance(research_claim_payload, list)
            and researcher_audit.get("claim_count") == len(research_claim_payload)
            and (
                hashlib.sha256(
                    json.dumps(
                        claims_from_audit(researcher_audit),
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                == hashlib.sha256(
                    json.dumps(
                        research_claim_payload,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                ).hexdigest()
                if researcher_audit.get("status") in {"TRACEABLE_UNVERIFIED", "NEEDS_REVIEW"}
                else True
            )
            and task.outputs.get("neuro_symbolic_audit_model_sha256") == research_digest
            and research_result.get("audit_evidence_sha256") == research_evidence_digest
            and researcher_audit == research_reaudit
        )
        research_reaudit = research_claims_reaudited
        researcher_claims_for_validator = (
            claims_from_audit(researcher_audit) if research_binding_valid else None
        )
        if research_binding_valid:
            researcher_claims_for_validator = audit_symbolic_claims(
                research_claim_payload,
                research_evidence_snapshot,
                namespace="researcher",
                side_effect_scope="researcher_audit_recomputed_in_validator",
            )
            researcher_claims_for_validator = claims_from_audit(researcher_claims_for_validator)
        validator_evidence_context = symbolic_evidence_context + [
            {"source": reference}
            for claim in (researcher_claims_for_validator or [])
            if isinstance(claim, dict)
            for reference in claim.get("evidence_refs", [])
            if isinstance(reference, str)
        ]
        validator_evidence_snapshot_error = False
        try:
            validator_evidence_snapshot = _symbolic_evidence_snapshot(validator_evidence_context)
        except (TypeError, ValueError):
            # Keep the optional shadow fail-closed, but do not let oversized
            # evidence prevent the established Validator gates from running.
            validator_evidence_snapshot = []
            validator_evidence_snapshot_error = True
        validator_claims = None
        validator_symbolic_audit = (
            _invalid_symbolic_audit(
                "EVIDENCE_SNAPSHOT_BUDGET_EXCEEDED",
                "pure_validator_audit_in_task_lifecycle",
            )
            if validator_evidence_snapshot_error else audit_symbolic_claims(None)
        )
        validator_binding_valid = False
        if isinstance(model_response, dict):
            try:
                validator_payload = json.loads(model_response.get("content", ""))
                validator_claims = (
                    validator_payload.get("symbolic_claims")
                    if isinstance(validator_payload, dict) else None
                )
                validator_binding_valid = (
                    isinstance(current_validator_trace, dict)
                    and current_validator_trace.get("api_result") == "success"
                    and current_validator_trace.get("result") == "success"
                    and current_validator_trace.get("output_contract_gate", {}).get("status") == "pass"
                    and isinstance(current_validator_trace.get("response_sha256"), str)
                    and bool(current_validator_trace.get("response_sha256"))
                    and hashlib.sha256(
                        str(model_response.get("content", "")).encode("utf-8")
                    ).hexdigest() == current_validator_trace.get("response_sha256")
                )
                validator_symbolic_audit = (
                    _invalid_symbolic_audit(
                        "EVIDENCE_SNAPSHOT_BUDGET_EXCEEDED",
                        "pure_validator_audit_in_task_lifecycle",
                    )
                    if validator_evidence_snapshot_error else audit_symbolic_claims(
                        validator_claims if validator_binding_valid else None,
                        validator_evidence_snapshot,
                        namespace="validator",
                        side_effect_scope="pure_validator_audit_in_task_lifecycle",
                    )
                )
            except (TypeError, ValueError):
                validator_claims = "INVALID"
                validator_symbolic_audit = audit_symbolic_claims(validator_claims)
        if (
            validator_binding_valid
            and isinstance(validator_claims, list)
            and research_binding_valid
            and not validator_evidence_snapshot_error
        ):
            validator_symbolic_audit = audit_symbolic_claims(
                validator_claims,
                validator_evidence_snapshot,
                namespace="validator",
                external_premise_ids=(
                    [claim["claim_id"] for claim in researcher_claims_for_validator]
                    if research_binding_valid and isinstance(researcher_claims_for_validator, list)
                    else []
                ),
                side_effect_scope="pure_validator_audit_in_task_lifecycle",
            )
        validator_audit_binding_valid = (
            validator_binding_valid
            and stored_validator_audit_task_id == task.task_id
            and isinstance(current_validator_trace, dict)
            and stored_validator_audit_digest == current_validator_trace.get("response_sha256")
            and stored_validator_audit == validator_symbolic_audit
        )
        if (
            not validator_audit_metadata_present
            and validator_binding_valid
        ) or (
            validator_shadow_binding_valid
            and validator_binding_valid
            and stored_validator_audit_digest == current_validator_trace.get("response_sha256")
            and stored_validator_audit == validator_symbolic_audit
        ):
            # This is the first audit of this Validator response: the inputs are
            # bound directly to its live execution trace, so no prior persisted
            # audit can be compared yet. The next validation pass will verify the
            # persisted task-id, response digest, and full audit before reuse.
            validator_audit_binding_valid = True
        if not validator_binding_valid:
            validator_claims = None
            if not validator_evidence_snapshot_error:
                validator_symbolic_audit = audit_symbolic_claims(None)
            validator_audit_binding_valid = False
        task.outputs["validator_neuro_symbolic_audit"] = validator_symbolic_audit
        task.outputs["validator_neuro_symbolic_audit_task_id"] = task.task_id
        task.outputs["validator_neuro_symbolic_audit_model_sha256"] = (
            current_validator_trace.get("response_sha256")
            if isinstance(current_validator_trace, dict) else None
        )

        # Combine only the current research audit (bound to this task and the
        # stored model-response digest) with this Validator attempt.  Namespaced
        # IDs preserve each role's local premise graph.  The existing evidence
        # catalogue and review authority remain the sole source of acceptance.
        researcher_claims = researcher_claims_for_validator
        combined_claims = combine_symbolic_claim_sets({
            "researcher": researcher_claims,
            "validator": validator_claims,
        })
        combined_ids = {
            claim.get("claim_id")
            for claim in combined_claims if isinstance(claim, dict)
        }
        combined_claims = [
            {
                **claim,
                "premise_ids": [
                    premise for premise in claim.get("premise_ids", [])
                    if not (
                        isinstance(premise, str)
                        and premise.startswith("validator:")
                        and premise not in combined_ids
                    )
                ],
            }
            if isinstance(claim, dict)
            and claim.get("claim_id", "").startswith("researcher:")
            and isinstance(claim.get("premise_ids"), list)
            else claim
            for claim in combined_claims
        ]
        symbolic_audit = (
            _invalid_symbolic_audit(
                "EVIDENCE_SNAPSHOT_BUDGET_EXCEEDED",
                "combined_advisory_metadata_in_task_lifecycle",
            )
            if validator_evidence_snapshot_error else audit_symbolic_claims(
                combined_claims if combined_claims else None,
                validator_evidence_context,
                max_claims=64,
                side_effect_scope="combined_advisory_metadata_in_task_lifecycle",
            )
        )
        if (
            not validator_evidence_snapshot_error
            and (
                len(combined_claims) > 64
                or len(combined_claims) > 32 and researcher_claims and validator_claims
            )
        ):
            combined_audit_claims = combined_claims[:64]
            symbolic_audit = audit_symbolic_claims(
                combined_audit_claims,
                validator_evidence_context,
                max_claims=64,
                side_effect_scope="combined_advisory_metadata_in_task_lifecycle",
            )
            symbolic_audit["warnings"].append({
                "claim_id": None,
                "code": "COMBINED_CLAIM_SET_BUDGETED",
                "field": "symbolic_claims",
            })
        symbolic_audit["role_audits"] = {
            "researcher": {
                "binding_valid": research_binding_valid,
                "status": (
                    researcher_audit.get("status")
                    if research_binding_valid else "ABSENT_OR_STALE"
                ),
                "issues": (
                    list(researcher_audit.get("issues", []))
                    if research_binding_valid else []
                ),
            },
            "validator": {
                "binding_valid": validator_audit_binding_valid,
                "status": validator_symbolic_audit.get("status"),
                "issues": list(validator_symbolic_audit.get("issues", [])),
            },
        }
        prior_invalid = [
            role for role, role_audit in symbolic_audit["role_audits"].items()
            if role_audit.get("status") == "INVALID"
            and role_audit.get("binding_valid")
        ]
        unbound_validator_audit = validator_shadow_present and not validator_audit_binding_valid
        invalid_roles = list(prior_invalid)
        if unbound_validator_audit and "validator" not in invalid_roles:
            invalid_roles.append("validator")
        if invalid_roles:
            symbolic_audit["status"] = "INVALID"
            symbolic_audit["issues"] = list(symbolic_audit.get("issues", [])) + [
                {"claim_id": None, "code": "ROLE_AUDIT_INVALID", "field": role}
                for role in invalid_roles
            ]

        objections = []
        hard_objections = []
        advisory_objections = []
        for objection in model_objections["hard_objections"]:
            objections.append(objection)
            hard_objections.append(objection)
        for objection in model_objections["advisory_objections"]:
            objections.append(objection)
            advisory_objections.append(objection)
        for counter_example in model_objections["counter_examples"]:
            objections.append(counter_example)
            advisory_objections.append(counter_example)

        # A successful validator call is not sufficient for approval.  If the
        # model answered without the contract's verifiable structure, route the
        # task back to research so the next attempt must produce facts,
        # unknowns, objections and a minimal verification step.  No model call
        # or no configured model keeps the existing local validation behavior.
        latest_trace = (
            execution_traces[-1]
            if isinstance(execution_traces, list) and execution_traces
            else {}
        )
        rejected_successful_contract = (
            isinstance(latest_trace, dict)
            and latest_trace.get("api_result") == "success"
            and isinstance(latest_trace.get("quality_gate"), dict)
            and latest_trace["quality_gate"].get("executed") is True
            and isinstance(output_contract, dict)
            and output_contract.get("status") == "fail"
        )
        if rejected_successful_contract or (
            isinstance(model_response, dict)
            and model_response.get("success") is True
            and (
                not isinstance(execution_feedback, dict)
                or execution_feedback.get("status") != "STRUCTURED"
                or output_contract.get("status") != "pass"
            )
        ):
            missing_fields = output_contract.get("missing_fields", [])
            detail = "缺少字段: " + ", ".join(missing_fields) if missing_fields else "结构不符合岗位契约"
            objection = "模型验证结果缺少结构化事实/未知/反例/下一步验证，不能直接批准（" + detail + "）"
            objections.append(objection)
            hard_objections.append(objection)

        evidence_count = len(self._unique_evidence(task))
        if protocols.get("active"):
            packet = protocols.get("evidence_packet", {})
            packet_items = packet.get("items", []) if isinstance(packet, dict) else []
            evidence_count = len({
                (item.get("source", ""), item.get("content", ""))
                for item in packet_items
                if isinstance(item, dict) and item.get("source") and item.get("content")
            } - {
                (item.get("source", ""), item.get("content", ""))
                for item in packet_items
                if isinstance(item, dict) and _is_reuse_pointer(item)
            })
        # A verified physical artifact is first-hand evidence about the world,
        # and a strictly stronger acceptance test than counting memory excerpts.
        # When the task's declared success_metric has been decided on disk, the
        # evidence-volume heuristics below have nothing left to say about it.
        delivery_verified = _has_verified_delivery(task)
        if evidence_count == 0 and not delivery_verified:
            objection = "没有任何证据支持，研究不充分"
            objections.append(objection)
            hard_objections.append(objection)
        elif evidence_count < 3 and not delivery_verified:
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

        if protocols.get("active") and protocol_failures:
            objection = "交付协议不完整: " + "; ".join(protocol_failures)
            objections.append(objection)
            hard_objections.append(objection)

        if self.memory_index and task.evidence and not delivery_verified:
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

        # Questions and advisory warnings are useful review notes, but are not
        # concrete counterexamples. Preserve the existing response shape while
        # keeping the epistemic record from inventing counterexamples.
        if not genuine_objections:
            genuine_objections.append("建议扩大样本量后再确认")
            advisory_objections.append(genuine_objections[-1])

        # Distinguish concrete falsifying observations from blocking obligations.
        # Hard blockers (sample-count, protocol, or response-contract failures)
        # stop approval, but do not become epistemic counterexamples merely
        # because they are hard. Only explicit model counterexamples enter the
        # counterexample ledger.
        concrete_counter_examples = []
        existing_counter_examples = self._unique_counter_examples(task)
        for counter_example in model_objections["counter_examples"]:
            if counter_example not in existing_counter_examples and counter_example not in concrete_counter_examples:
                concrete_counter_examples.append(counter_example)
        for obj in genuine_objections:
            task.add_validation_note(obj, validator="validator")
        for counter_example in concrete_counter_examples:
            if counter_example not in self._unique_counter_examples(task):
                task.add_counter_example(counter_example, source="validator")

        result["objections"] = genuine_objections
        result["counter_examples"] = len(concrete_counter_examples)
        result["hard_objections"] = list(hard_objections)
        result["advisory_objections"] = list(advisory_objections)

        objections_signature = self.validation_signature(sorted(genuine_objections))
        validator_outcome_signature = self.validation_signature("rework_pending")
        previous_outcome = previous_result.get("outcome", "")
        # A task with no prior validator outcome is a new review, not a
        # legacy rework record.  Treating the empty outcome as rework made
        # every evidence-qualified task fail its first review even when all
        # objections were advisory-only.
        repeated_rework = previous_outcome == "rework_pending" or (
            not previous_outcome
            and review_count > 0
            and bool(previous_signature)
        )
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
        stored_evidence_count = len(task.evidence or [])
        distinct_evidence_count = len(self._unique_evidence(task))
        stored_counter_example_count = len(task.counter_examples or [])
        distinct_counter_example_count = len(self._unique_counter_examples(task))
        validator_result = {
            "review_count": task.review_count,
            "evidence_signature": evidence_signature,
            # `len(task.evidence)` is what a reader sees, but it is not what this
            # verdict was computed over. On RQ-20261004-044 the stored list held 25
            # items while the signature covered 2 distinct records, and nothing in the
            # record said so. Publishing both counts turns "the evidence set is
            # duplicated" from a hidden condition into a measurable one.
            "stored_evidence_count": stored_evidence_count,
            "distinct_evidence_count": distinct_evidence_count,
            "evidence_inflation_ratio": (
                round(stored_evidence_count / distinct_evidence_count, 2)
                if distinct_evidence_count
                else None
            ),
            # Same treatment for counter-examples: ``len(task.counter_examples)``
            # is what a reader sees, and it is re-deposited on every review pass.
            # Without both counts, "14 objections" is indistinguishable from
            # "4 objections heard four times", which is how a one-objection
            # review could present itself as three rounds of deliberation.
            "stored_counter_example_count": stored_counter_example_count,
            "distinct_counter_example_count": distinct_counter_example_count,
            "counter_example_inflation_ratio": (
                round(stored_counter_example_count / distinct_counter_example_count, 2)
                if distinct_counter_example_count
                else None
            ),
            "objections": list(genuine_objections),
            "hard_objections": list(hard_objections),
            "advisory_objections": list(advisory_objections),
            "neuro_symbolic_claims": claims_from_audit(symbolic_audit),
            "neuro_symbolic_audit": symbolic_audit,
            "validated_at": datetime.now().isoformat(),
        }

        if task.unchanged_review_count >= self.MAX_UNCHANGED_REVIEWS:
            task.retry_after = ""
            task.assignee = None
            task.outputs["terminal_non_convergent"] = True
            try:
                from core.ruin_smelter import fuse as _ruin_fuse
                _fuse = _ruin_fuse(task)
                task.outputs["ruin_fuse"] = {
                    "action": _fuse.get("action", ""),
                    "reason": _fuse.get("reason", "")[:300],
                    "repair_direction": _fuse.get("repair_direction", _fuse.get("next_verify", ""))[:300],
                    "need_judge": bool(_fuse.get("need_judge", False)),
                    "class": (_fuse.get("class", {}) or {}).get("class", "") if isinstance(_fuse.get("class"), dict) else "",
                    "at": _fuse.get("at", ""),
                    "state_lineage": [
                        {"state": "A", "reason": "observe"},
                        {"state": "U", "reason": "research"},
                        {"state": "M", "reason": "smelt_non_convergent"},
                    ],
                }
            except Exception:
                pass
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
            # Three independent evidence items, or one artifact whose declared
            # success_metric the delivery gate already decided by inspecting the
            # filesystem. The artifact is not a self-reported claim.
            and (evidence_count >= 3 or delivery_verified)
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

        persisted_task = self.task_pool.load_task(task.task_id) or task
        add_evidence_ledger_entry(
            persisted_task,
            "review",
            {
                "outcome": validator_result.get("outcome", "unknown"),
                "objection_count": len(genuine_objections),
                "review_count": task.review_count,
            },
        )
        record_event(
            persisted_task,
            "validated",
            actor="validator",
            outcome=validator_result.get("outcome", "unknown"),
            objection_count=len(genuine_objections),
        )
        record_checkpoint(
            persisted_task,
            "validation_complete",
            actor="validator",
            outcome=validator_result.get("outcome", "unknown"),
            verdict=result.get("verdict", ""),
        )
        self.task_pool.update_task(persisted_task)
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
        scored_evidence = [e for e in task.evidence if not _is_reuse_pointer(e)]
        evidence_count = len(scored_evidence)
        if evidence_count >= 5:
            quality_score += 20
        elif evidence_count >= 3:
            quality_score += 10
        elif evidence_count >= 1:
            quality_score += 0
        else:
            quality_score -= 30
        
        # 证据内容长度
        if scored_evidence:
            avg_len = sum(
                len(e.get("content", "")) if isinstance(e, dict) else len(str(e))
                for e in scored_evidence
            ) / len(scored_evidence)
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
        ensure_execution_discipline(task)
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
        record_event(task, "archived", actor="archivist")
        self.task_pool.update_task(task)

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
        ensure_execution_discipline(task)
        protocols = ensure_task_protocols(task, refresh_evidence=True)
        record_event(task, "guardian_reviewed", actor="guardian")
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
                related_lessons = self.experience_deposition.find_related(
                    task.title[:20], limit=5, actor="guardian")
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
        elif ev_count >= 3 and task.priority in ["high", "critical"] and ce_count == 0:
            decision["verdict"] = "constraint"
            decision["reason"] = "高优先级任务，证据充分且无已记录反例，可作为约束"
            decision["promoted"] = True
        elif ev_count >= 2:
            decision["verdict"] = "experience"
            decision["reason"] = "有一定证据，但已记录反例或其他不足，归入经验库"
        else:
            decision["verdict"] = "experience"
            decision["reason"] = "证据有限，暂存经验库待后续验证"

        # Only a proposed long-term rule activates the gate for an otherwise
        # ordinary task.  Exploration and daily observation remain untouched.
        if decision["verdict"] in {"axiom", "constraint"} and not protocols.get("active"):
            protocols = ensure_task_protocols(task, refresh_evidence=True, force=True)
        if protocols.get("active"):
            # Guardian is the final consumer before a long-term promotion;
            # require a source-backed, complete packet at this boundary too.
            scope = protocols.get("scope", {})
            protocol_failures = protocol_errors(
                protocols,
                require_evidence=True,
                # Long-term rules and explicit delivery are the responsibility
                # boundary; ordinary research remains able to accumulate
                # evidence without inventing a learning return.
                require_responsibility=(
                    decision["verdict"] in {"axiom", "constraint"}
                    or scope.get("purpose") == "long_term_rule"
                    or scope.get("delivery_required") is True
                ),
            )
            if scope.get("delivery_required"):
                receipt = task.outputs.get("release_receipt", {}) if isinstance(task.outputs, dict) else {}
                receipt_check = validate_release_receipt(
                    receipt,
                    task.task_id,
                    require_verified=True,
                )
                protocol_failures.extend(
                    f"release_receipt:{error}" for error in receipt_check.get("errors", [])
                )
            task.outputs["delivery_protocol_checks"] = {
                "checked_by": "guardian",
                "at": datetime.now().isoformat(),
                "errors": list(dict.fromkeys(protocol_failures)),
                "active": True,
            }
            if protocol_failures and decision["verdict"] in {"axiom", "constraint"}:
                decision["verdict"] = "experience"
                decision["promoted"] = False
                decision["reason"] = "关键节点协议未通过，暂不升格为长期规则: " + "; ".join(protocol_failures)

        task.guardian_decision = decision["verdict"]
        add_evidence_ledger_entry(
            task,
            "review",
            {
                "actor": "guardian",
                "decision": decision["verdict"],
                "promoted": decision["promoted"],
            },
        )
        record_checkpoint(
            task,
            "guardian_decision",
            actor="guardian",
            decision=decision["verdict"],
            promoted=decision["promoted"],
        )
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
