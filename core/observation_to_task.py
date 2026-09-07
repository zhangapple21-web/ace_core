"""
Observation → Task 自动转换规则引擎

核心职责：
  - 检查所有未处理的 Observation
  - 根据规则，将 Observation 转换为 Task
  - 防止重复触发（同一个 Observation 只生成一次 Task）

设计原则：
  - 规则是声明式的，易于扩展
  - 瓶颈类 Observation → 高优先级 Task
  - 同一个 Observation 只触发一次
  - 不处理已生成 Task 的 Observation

规则分类：
  bottleneck  → review积压、active=0等 → P0-P1
  gap         → 词库缺口、知识空白     → P1-P2
  anomaly     → 错误、异常值          → P1-P2
  improvement → 优化机会              → P2-P3
  health      → 健康指标异常          → P2-P3
"""

import json
import hashlib
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from .observation import RuntimeObserver, Observation
from .task import TaskPool
from .model_task_admission import ModelTaskAdmission


@dataclass
class ConversionRule:
    """
    单条转换规则

    触发条件：
      - category: Observation 类别（bottleneck/gap/anomaly/improvement/health）
      - severity_min: 最小严重程度（>= 此严重程度才触发）
      - condition_fn: 额外的自定义条件函数

    生成结果：
      - task_title: 生成的 Task 标题模板
      - task_priority: 优先级（critical/high/medium/low）
      - task_tags: 标签列表
      - task_hypothesis: 假设描述
    """
    name: str
    category: str
    severity_min: str
    condition_fn: Optional[Callable[[Observation], bool]] = None

    task_title: str = ""
    task_priority: str = "medium"
    task_tags: List[str] = None
    task_hypothesis: str = ""

    def matches(self, obs: Observation) -> bool:
        if not isinstance(obs.system_state, dict):
            return False
        if obs.category != self.category:
            return False

        severity_rank = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        obs_rank = severity_rank.get(obs.severity, 0)
        min_rank = severity_rank.get(self.severity_min, 0)
        if obs_rank < min_rank:
            return False

        if self.condition_fn:
            return self.condition_fn(obs)
        return True

    def generate_task_from(self, obs: Observation) -> Dict[str, Any]:
        """从 Observation 生成 Task 参数字典"""
        title = self.task_title.format(
            obs_id=obs.obs_id,
            description=obs.description[:50],
        )
        hypothesis = self.task_hypothesis
        tags = [f"from_obs:{obs.obs_id}"] + (self.task_tags or [])
        return {
            "title": title,
            "hypothesis": hypothesis,
            "priority": self.task_priority,
            "tags": tags,
            "creator": "observation_to_task",
            "source_obs_id": obs.obs_id,
        }


def _review_bottleneck(obs: Observation) -> bool:
    """review 队列积压是系统瓶颈"""
    state = obs.system_state
    review_count = state.get("review", 0)
    pending_count = state.get("pending", 0)
    active_count = state.get("active", 0)
    if review_count >= 5:
        return True
    if review_count > 0 and active_count == 0 and pending_count == 0:
        return True
    return False


def _lexicon_gap(obs: Observation) -> bool:
    """词库缺口：某分类概念数 < 5"""
    state = obs.system_state
    if "gap_categories" in state:
        gaps = state["gap_categories"]
        if isinstance(gaps, list) and len(gaps) >= 3:
            return True
    return False


def _fragment_backlog(obs: Observation) -> bool:
    """碎片积压：未考古数量 > 500"""
    state = obs.system_state
    return state.get("pending_scan", 0) > 500


def _cross_agent_idle(obs: Observation) -> bool:
    """跨智能体学习长期未启动"""
    state = obs.system_state
    last_scan = state.get("last_mine_seed_scan", "never")
    if last_scan == "never":
        return True
    return False


def _discovery_candidate(obs: Observation) -> bool:
    discovery = obs.system_state.get("discovery", {})
    required = {
        "fingerprint",
        "title",
        "reason",
        "objective",
        "completion_criteria",
        "verification_method",
        "priority",
        "route",
    }
    return obs.source == "discovery_mode" and isinstance(discovery, dict) and required.issubset(discovery)


def _valid_learning_contract(contract: Any) -> bool:
    required = {"why_learn", "learning_objective", "required_evidence", "mastery_criteria"}
    if not isinstance(contract, dict) or not required.issubset(contract):
        return False
    for field in required:
        value = contract[field]
        if isinstance(value, str) and value.strip():
            continue
        if isinstance(value, list) and any(isinstance(item, str) and item.strip() for item in value):
            continue
        return False
    return True


def _valid_autonomous_maintenance_contract(contract: Any) -> bool:
    required = {
        "why_now",
        "evidence",
        "priority",
        "expected_result",
        "verification_method",
        "risk",
        "source",
        "estimated_scope",
    }
    if not isinstance(contract, dict) or not required.issubset(contract):
        return False
    if contract["priority"] not in {"critical", "high", "medium", "low"}:
        return False
    evidence = contract["evidence"]
    # Candidate Work may record an unresolved question before supporting
    # evidence has formed.  Admission, not candidate parsing, decides whether
    # the evidence is sufficient to create a production Task.
    if not isinstance(evidence, list):
        return False
    for field in required - {"evidence", "priority"}:
        if not isinstance(contract[field], str) or not contract[field].strip():
            return False
    return True


BUILTIN_RULES: List[ConversionRule] = [
    ConversionRule(
        name="discovery_candidate",
        category="improvement",
        severity_min="medium",
        condition_fn=_discovery_candidate,
    ),
    ConversionRule(
        name="review_queue_bottleneck",
        category="bottleneck",
        severity_min="medium",
        condition_fn=_review_bottleneck,
        task_title="疏通 review 队列积压 — {obs_id}",
        task_priority="critical",
        task_tags=["governance", "runtime疏通", "P0"],
        task_hypothesis="Review 队列积压 {review} 个任务，Runtime 流水线已在 Validator 阶段阻塞。"
                        "系统当前 pending={pending}, active={active}。"
                        "需要快速清理 review 队列，恢复任务流动。"
                        "来源：{obs_id}",
    ),
    ConversionRule(
        name="lexicon_category_gap",
        category="gap",
        severity_min="medium",
        condition_fn=_lexicon_gap,
        task_title="补齐词库分类缺口 — {obs_id}",
        task_priority="high",
        task_tags=["knowledge", "词库治理"],
        task_hypothesis="词库存在 {gap_categories} 共 {gap_count} 个稀缺分类（< 5 个概念）。"
                        "概念总数 {total_concepts}，其中 {uncategorized} 个待分类。"
                        "需要整理分类体系，将待分类概念归位，补充稀缺分类。"
                        "来源：{obs_id}",
    ),
    ConversionRule(
        name="fragment_backlog",
        category="gap",
        severity_min="medium",
        condition_fn=_fragment_backlog,
        task_title="启动碎片考古 — {obs_id}",
        task_priority="medium",
        task_tags=["archaeology", "碎片考古"],
        task_hypothesis="碎片索引积压 {pending_scan} 个未考古文件。"
                        "需要按优先级批量处理考古任务，提取有价值材料。"
                        "来源：{obs_id}",
    ),
    ConversionRule(
        name="cross_agent_idle",
        category="gap",
        severity_min="medium",
        condition_fn=_cross_agent_idle,
        task_title="激活跨智能体学习 — {obs_id}",
        task_priority="high",
        task_tags=["cross_agent", "mine_seed", "外部学习"],
        task_hypothesis="mine-seed 扫描器从未执行（last_scan=never）。"
                        "系统失去了向外学习的机会。"
                        "需要配置 mine-seed 路径并激活扫描循环。"
                        "来源：{obs_id}",
    ),
    ConversionRule(
        name="recent_errors",
        category="anomaly",
        severity_min="medium",
        condition_fn=lambda obs: obs.system_state.get("recent_error_count", 0) > 3,
        task_title="处理系统异常错误 — {obs_id}",
        task_priority="high",
        task_tags=["error_handling", "系统修复"],
        task_hypothesis="近24小时出现 {recent_error_count} 个错误。"
                        "错误类型：{error_samples}。"
                        "需要逐一分析根因，修复或降级处理。"
                        "来源：{obs_id}",
    ),
    ConversionRule(
        name="scheduled_task_inactive",
        category="improvement",
        severity_min="medium",
        condition_fn=lambda obs: obs.system_state.get("task_never_run", False),
        task_title="激活自动化计划任务 — {obs_id}",
        task_priority="medium",
        task_tags=["ops", "automation"],
        task_hypothesis="计划任务已安装但从未执行。"
                        "系统失去了自动巡检和恢复能力。"
                        "来源：{obs_id}",
    ),
    ConversionRule(
        name="disk_space_low",
        category="health",
        severity_min="high",
        condition_fn=lambda obs: obs.system_state.get("disk_free_pct", 100) < 20,
        task_title="清理磁盘空间 — {obs_id}",
        task_priority="high",
        task_tags=["ops", "infrastructure"],
        task_hypothesis="磁盘剩余空间 {disk_free_pct}%，{disk_free_gb}GB。"
                        "空间不足会影响系统运行。"
                        "来源：{obs_id}",
    ),
]


class ObservationToTaskConverter:
    """
    Observation → Task 转换器

    工作流程：
      1. 获取所有未处理的 Observation
      2. 遍历规则，找到匹配的 Observation
      3. 检查是否已为该 Observation 生成过 Task（防抖）
      4. 生成 Task 并标记 Observation 已处理
      5. 返回转换结果

    触发时机：
      - 主循环每次迭代结束时
      - 巡检任务完成后
      - 手动触发（ops/auto_convert.py）
    """

    def __init__(
        self,
        observer: RuntimeObserver,
        task_pool: TaskPool,
        rules: List[ConversionRule] = None,
    ):
        self.observer = observer
        self.task_pool = task_pool
        self.rules = rules or BUILTIN_RULES
        self.model_task_admission = ModelTaskAdmission()
        self._triggered_timestamps: Dict[str, str] = {}
        self._triggered_cache = self._load_triggered_cache()
        self._semantic_incidents = self._load_semantic_incidents()

    # These rules describe a continuing condition, rather than a sequence of
    # independent work items.  Their canonical task survives mechanical
    # archival until a later observation proves recovery.
    _PERSISTENT_INCIDENT_RULES = {"fragment_backlog", "cross_agent_idle"}
    # Runtime caches are idempotency aids, not an append-only event log.
    _CACHE_SCHEMA_VERSION = 1
    _TRIGGERED_CACHE_MAX_ENTRIES = 512
    _TRIGGERED_CACHE_MAX_AGE_DAYS = 7
    _INCIDENT_CACHE_MAX_ENTRIES = 128
    _INCIDENT_CACHE_MAX_AGE_DAYS = 30

    def _load_triggered_cache(self) -> set:
        """Load a bounded observation-id cache (migrating the legacy list)."""
        cache_file = self.observer.data_dir / "triggered_obs.json"
        if cache_file.exists():
            try:
                data = json.load(open(cache_file, "r", encoding="utf-8"))
                if isinstance(data, dict):
                    entries = data.get("entries", {})
                    if isinstance(entries, dict):
                        cutoff = datetime.now() - timedelta(days=self._TRIGGERED_CACHE_MAX_AGE_DAYS)
                        retained = {
                            str(key): value for key, value in entries.items()
                            if isinstance(value, dict) and self._parse_cache_time(value.get("last_seen_at"), cutoff)
                        }
                        self._triggered_timestamps = {key: str(value.get("last_seen_at")) for key, value in retained.items()}
                        return set(sorted(retained, key=lambda key: retained[key].get("last_seen_at", ""))[-self._TRIGGERED_CACHE_MAX_ENTRIES:])
                if isinstance(data, list):
                    now = datetime.now().isoformat()
                    self._triggered_timestamps = {str(item): now for item in data[-self._TRIGGERED_CACHE_MAX_ENTRIES:]}
                    return set(self._triggered_timestamps)
            except Exception:
                return set()
        return set()

    @staticmethod
    def _parse_cache_time(value: Any, cutoff: datetime) -> bool:
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None) >= cutoff
        except (TypeError, ValueError):
            return False

    def _mark_triggered(self, obs_id: str):
        self._triggered_cache.add(obs_id)
        self._triggered_timestamps[obs_id] = datetime.now().isoformat()
        if len(self._triggered_cache) > self._TRIGGERED_CACHE_MAX_ENTRIES:
            keep = sorted(self._triggered_cache, key=lambda key: self._triggered_timestamps.get(key, ""))[-self._TRIGGERED_CACHE_MAX_ENTRIES:]
            self._triggered_cache = set(keep)
            self._triggered_timestamps = {key: self._triggered_timestamps[key] for key in keep}

    def _save_triggered_cache(self):
        cache_file = self.observer.data_dir / "triggered_obs.json"
        try:
            entries = {obs_id: {"last_seen_at": self._triggered_timestamps.get(obs_id, datetime.now().isoformat())} for obs_id in sorted(self._triggered_cache)}
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump({"schema_version": self._CACHE_SCHEMA_VERSION, "entries": entries}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _load_semantic_incidents(self) -> Dict[str, Dict[str, str]]:
        cache_file = self.observer.data_dir / "semantic_incidents.json"
        if cache_file.exists():
            try:
                data = json.load(open(cache_file, "r", encoding="utf-8"))
                if not isinstance(data, dict):
                    return {}
                cutoff = datetime.now() - timedelta(days=self._INCIDENT_CACHE_MAX_AGE_DAYS)
                retained = {
                    str(key): value for key, value in data.items()
                    if isinstance(value, dict) and self._parse_cache_time(value.get("last_observed_at"), cutoff)
                }
                return dict(sorted(retained.items(), key=lambda item: item[1].get("last_observed_at", ""))[-self._INCIDENT_CACHE_MAX_ENTRIES:])
            except Exception:
                return {}
        return {}

    def _save_semantic_incidents(self):
        cache_file = self.observer.data_dir / "semantic_incidents.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(self._semantic_incidents, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _record_persistent_incident(self, rule: ConversionRule, state: Dict[str, Any], task_id: str):
        if rule.name not in self._PERSISTENT_INCIDENT_RULES:
            return
        signature = self._semantic_signature(rule, state)
        if signature:
            self._semantic_incidents[rule.name] = {
                "schema_version": self._CACHE_SCHEMA_VERSION,
                "signature": signature,
                "task_id": task_id,
                "last_observed_at": datetime.now().isoformat(),
                "reason": "persistent_semantic_incident",
            }
            self._semantic_incidents = dict(sorted(self._semantic_incidents.items(), key=lambda item: item[1].get("last_observed_at", ""))[-self._INCIDENT_CACHE_MAX_ENTRIES:])
            self._save_semantic_incidents()

    def _reconcile_persistent_incidents(self, obs: Observation):
        """Forget an incident only after explicit recovery evidence.

        An unrelated gap observation must not imply recovery.  The relevant
        state field has to be present and its persistent rule must be false.
        This preserves generic terminal-task reuse while allowing a recovered
        incident to reopen when it genuinely returns.
        """
        state = obs.system_state if isinstance(obs.system_state, dict) else {}
        for rule in self.rules:
            if rule.name not in self._PERSISTENT_INCIDENT_RULES or rule.category != obs.category:
                continue
            required_key = "pending_scan" if rule.name == "fragment_backlog" else "last_mine_seed_scan"
            if required_key not in state or not rule.condition_fn or rule.condition_fn(obs):
                continue
            if rule.name in self._semantic_incidents:
                self._semantic_incidents.pop(rule.name, None)
                self._save_semantic_incidents()

    @staticmethod
    def _lexicon_gap_signature(state: Dict[str, Any]) -> tuple:
        """Return the stable problem identity, excluding per-cycle counters."""
        gaps = state.get("gap_categories", [])
        if not isinstance(gaps, list):
            return ()
        return tuple(sorted({str(gap).strip() for gap in gaps if str(gap).strip()}))

    @staticmethod
    def _normal_text(value: Any) -> str:
        """Normalize a diagnostic token without erasing its identity."""
        return re.sub(r"\s+", " ", str(value or "").strip().lower())

    @classmethod
    def _semantic_signature(cls, rule: ConversionRule, state: Dict[str, Any]) -> str:
        """Return the stable identity of a recurring observation.

        Observation IDs and rolling counters are deliberately excluded.  The
        identity changes only when the underlying incident changes, so a
        persistent error is serviced by one task instead of creating one task
        per daemon cycle.  This is a deduplication aid, not a quality or
        admission decision.
        """
        name = rule.name
        payload: Dict[str, Any]
        if name == "lexicon_category_gap":
            payload = {"gaps": list(cls._lexicon_gap_signature(state))}
        elif name == "recent_errors":
            samples = state.get("error_samples", [])
            normalized = {
                cls._normal_text(item)
                for item in samples
                if cls._normal_text(item)
            } if isinstance(samples, list) else set()
            payload = {"errors": sorted(normalized)}
        elif name == "cross_agent_idle":
            payload = {"last_mine_seed_scan": cls._normal_text(state.get("last_mine_seed_scan", "never"))}
        elif name == "review_queue_bottleneck":
            review = int(state.get("review", 0) or 0)
            pending = int(state.get("pending", 0) or 0)
            active = int(state.get("active", 0) or 0)
            mode = "review_backlog" if review >= 5 else "review_starvation" if review > 0 and active == 0 and pending == 0 else ""
            payload = {"mode": mode}
        elif name == "fragment_backlog":
            payload = {"condition": bool((state.get("pending_scan", 0) or 0) > 500)}
        elif name == "scheduled_task_inactive":
            payload = {"condition": bool(state.get("task_never_run", False))}
        elif name == "disk_space_low":
            try:
                free_pct = float(state.get("disk_free_pct", 0) or 0)
            except (TypeError, ValueError):
                free_pct = 0.0
            # A five-point bucket allows a materially changed disk condition
            # to reopen while ignoring harmless telemetry jitter.
            payload = {"free_pct_bucket": math.floor(free_pct / 5)}
        else:
            return ""
        if not payload or payload == {"mode": ""}:
            return ""
        canonical = {"rule": name, **payload}
        return hashlib.sha256(
            json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @classmethod
    def _task_semantic_signature(cls, task: Any, rule: ConversionRule) -> str:
        outputs = task.outputs if isinstance(getattr(task, "outputs", None), dict) else {}
        stored = outputs.get("semantic_signature")
        if stored:
            return str(stored)
        admission = outputs.get("admission", {})
        evidence = admission.get("evidence", []) if isinstance(admission, dict) else []
        state = evidence[0].get("system_state", {}) if evidence and isinstance(evidence[0], dict) else {}
        return cls._semantic_signature(rule, state if isinstance(state, dict) else {})

    def _open_semantic_duplicate(self, rule: ConversionRule, state: Dict[str, Any]):
        """Find a still-open task for a recurring invariant observation.

        Runtime observations have unique IDs on every cycle. For a persistent
        lexicon gap that does not mean new work was discovered: the work is
        the same until its gap-category set materially changes or the earlier
        task closes.
        """
        if rule.name not in {
            "lexicon_category_gap",
            "recent_errors",
            "cross_agent_idle",
            "review_queue_bottleneck",
            "fragment_backlog",
            "scheduled_task_inactive",
            "disk_space_low",
        }:
            return None
        signature = self._semantic_signature(rule, state)
        if not signature:
            return None
        # A blocked non-convergent task is still the canonical open incident.
        # Counting it here prevents the next observation from recreating the
        # same task while it waits for genuinely new evidence.
        for status in ("pending", "active", "review", "approved", "blocked"):
            for task in self.task_pool.list_tasks(status=status, limit=10000):
                outputs = task.outputs if isinstance(task.outputs, dict) else {}
                if outputs.get("conversion_rule") != rule.name:
                    continue
                if self._task_semantic_signature(task, rule) == signature:
                    self._record_persistent_incident(rule, state, task.task_id)
                    return task
        if rule.name in self._PERSISTENT_INCIDENT_RULES:
            incident = self._semantic_incidents.get(rule.name, {})
            if incident.get("signature") == signature and incident.get("task_id"):
                task = self.task_pool.load_task(str(incident["task_id"]))
                if task is not None:
                    return task
                self._semantic_incidents.pop(rule.name, None)
                self._save_semantic_incidents()
        return None

    def _convert_discovery_candidate(
        self,
        obs: Observation,
        allowed_priorities: Optional[set] = None,
    ) -> Dict[str, Any]:
        discovery = obs.system_state["discovery"]
        if (
            allowed_priorities is not None
            and discovery.get("priority", "medium") not in allowed_priorities
        ):
            raise ValueError("priority_suppressed")
        contract = discovery.get("autonomous_maintenance")
        if not _valid_autonomous_maintenance_contract(contract):
            raise ValueError("invalid_autonomous_maintenance_contract")
        learning = discovery.get("learning")
        if learning is not None and not _valid_learning_contract(learning):
            raise ValueError("invalid_learning_contract")
        task_type = discovery.get("task_type", "reasoning")
        if task_type not in {"reasoning", "strategic", "execution"}:
            return {
                "obs_id": obs.obs_id,
                "rule": "discovery_candidate",
                "status": "rejected",
                "reasons": ["discovery_task_type_not_allowed"],
            }
        tags = [
            f"from_obs:{obs.obs_id}",
            "discovery",
            discovery.get("candidate_source", "repository_gap"),
            f"task_type:{task_type}",
        ]
        if learning is not None:
            tags.append("learning")
        source_type = "learning" if learning is not None else "maintenance"
        if discovery.get("candidate_source") == "archaeology":
            source_type = "archaeology"
        source_ref = str(discovery["fingerprint"])
        admission = {
            "source_type": source_type,
            "source_ref": source_ref,
            "why_now": contract["why_now"],
            "evidence": list(contract["evidence"]),
            "expected_result": contract["expected_result"],
            "verification_method": contract["verification_method"],
            "risk": contract["risk"],
            "estimated_scope": contract["estimated_scope"],
            **(
                {"model_work_contract": dict(discovery["model_work_contract"])}
                if isinstance(discovery.get("model_work_contract"), dict)
                else {}
            ),
        }
        if learning is not None:
            admission["learning_contract"] = dict(learning)
        model_task_candidate = {
            "source_type": source_type,
            "source_ref": source_ref,
            "evidence": admission["evidence"],
            "research_question": discovery["objective"],
            "expected_result": contract["expected_result"],
            "verification_method": contract["verification_method"],
            "tags": tags,
            "local_evidence_only": discovery.get("local_evidence_only") is True,
            "task_type": task_type,
            "model_work_contract": discovery.get("model_work_contract"),
        }
        decision = self.model_task_admission.evaluate(model_task_candidate)
        if not decision["eligible"] or decision["classification"] != task_type:
            return {
                "obs_id": obs.obs_id,
                "rule": "discovery_candidate",
                "status": "rejected",
                "reasons": decision["reasons"],
                "model_task_admission": decision,
            }
        task = self.task_pool.create_task(
            title=discovery["title"],
            hypothesis=discovery["objective"],
            creator="discovery_mode",
            priority=discovery["priority"],
            tags=tags,
            admission=admission,
            outputs={
                "source_obs_id": obs.obs_id,
                "source_obs_description": obs.description,
                "discovery": dict(discovery),
                "autonomous_maintenance": dict(contract),
                "model_task_admission": decision,
                **({"learning": dict(learning)} if learning is not None else {}),
            },
        )
        self.observer.mark_consumed(obs.obs_id, task.task_id)
        self._mark_triggered(obs.obs_id)
        return {
            "obs_id": obs.obs_id,
            "rule": "discovery_candidate",
            "task_id": task.task_id,
            "task_title": task.title,
            "task_priority": task.priority,
            "status": "created",
            "task_type": task_type,
            "model_task_admission": decision,
        }

    def convert(self, allowed_priorities: Optional[set] = None) -> Dict[str, Any]:
        result = {
            "observations_checked": 0,
            "rules_matched": 0,
            "tasks_created": 0,
            "candidate_count": 0,
            "eligible_count": 0,
            "rejected_count": 0,
            "reasoning_tasks_created": 0,
            "model_tasks_created": 0,
            "task_types_created": {},
            "rejection_reasons": {},
            "skipped": 0,
            "semantic_duplicates": 0,
            "details": [],
        }

        unprocessed = self.observer.get_unprocessed(limit=100)
        result["observations_checked"] = len(unprocessed)

        for obs in unprocessed:
            self._reconcile_persistent_incidents(obs)
            if obs.obs_id in self._triggered_cache:
                result["skipped"] += 1
                continue

            for rule in self.rules:
                if not rule.matches(obs):
                    continue

                if rule.name == "discovery_candidate":
                    try:
                        detail = self._convert_discovery_candidate(obs, allowed_priorities)
                        result["candidate_count"] += 1
                        result["rules_matched"] += 1
                        if detail["status"] == "created":
                            result["eligible_count"] += 1
                            result["tasks_created"] += 1
                            result["model_tasks_created"] += 1
                            created_type = detail.get("task_type", "reasoning")
                            result["task_types_created"][created_type] = (
                                result["task_types_created"].get(created_type, 0) + 1
                            )
                            if created_type == "reasoning":
                                result["reasoning_tasks_created"] += 1
                        else:
                            result["rejected_count"] += 1
                            for reason in detail["reasons"]:
                                reasons = result["rejection_reasons"]
                                reasons[reason] = reasons.get(reason, 0) + 1
                        result["details"].append(detail)
                    except ValueError as error:
                        result["details"].append({
                            "obs_id": obs.obs_id,
                            "rule": rule.name,
                            "reason": str(error),
                        })
                    except Exception as error:
                        result["details"].append({
                            "obs_id": obs.obs_id,
                            "rule": rule.name,
                            "error": str(error),
                        })
                    break

                task_params = rule.generate_task_from(obs)
                if (
                    allowed_priorities is not None
                    and task_params["priority"] not in allowed_priorities
                ):
                    result["skipped"] += 1
                    break
                state = obs.system_state if isinstance(obs.system_state, dict) else {}
                duplicate = self._open_semantic_duplicate(rule, state)
                if duplicate is not None:
                    self.observer.mark_consumed(obs.obs_id, duplicate.task_id)
                    self._mark_triggered(obs.obs_id)
                    result["skipped"] += 1
                    result["semantic_duplicates"] += 1
                    result["details"].append({
                        "obs_id": obs.obs_id,
                        "rule": rule.name,
                        "status": "semantic_duplicate",
                        "existing_task_id": duplicate.task_id,
                    })
                    break
                gap_categories_raw = state.get("gap_categories")
                gap_categories = gap_categories_raw if isinstance(gap_categories_raw, list) else []
                format_args = {
                    "obs_id": obs.obs_id,
                    "description": obs.description,
                    "state": json.dumps(state, ensure_ascii=False),
                    "review": state.get("review", 0),
                    "pending": state.get("pending", 0),
                    "active": state.get("active", 0),
                    "pending_scan": state.get("pending_scan", 0),
                    "total_concepts": state.get("total_concepts", 0),
                    "uncategorized": state.get("uncategorized", 0),
                    "gap_count": len(gap_categories),
                    "gap_categories": ", ".join(gap_categories[:5]) if gap_categories else "无",
                    "last_mine_seed_scan": state.get("last_mine_seed_scan", "never"),
                    "recent_error_count": state.get("recent_error_count", 0),
                    "error_samples": ", ".join(str(e) for e in state.get("error_samples", [])[:3]),
                    "disk_free_pct": state.get("disk_free_pct", 0),
                    "disk_free_gb": state.get("disk_free_gb", 0),
                    "task_never_run": state.get("task_never_run", False),
                }
                task_params["hypothesis"] = task_params["hypothesis"].format(**format_args)
                admission = {
                    "source_type": "system_observation",
                    "source_ref": obs.obs_id,
                    "why_now": (
                        f"Observation {obs.obs_id} matched rule {rule.name} at "
                        f"{obs.severity} severity."
                    ),
                    "evidence": [{
                        "observation_id": obs.obs_id,
                        "source_ref": f"runtime_observation:{obs.obs_id}",
                        "category": obs.category,
                        "severity": obs.severity,
                        "description": obs.description,
                        "system_state": state,
                        "rule": rule.name,
                    }],
                    "expected_result": task_params["hypothesis"],
                    "verification_method": (
                        f"Re-observe the runtime condition for rule {rule.name}."
                    ),
                    "risk": "Internal observation-driven maintenance only.",
                    "estimated_scope": "one observation and one conversion rule",
                }

                try:
                    task = self.task_pool.create_task(
                        title=task_params["title"],
                        hypothesis=task_params["hypothesis"],
                        creator=task_params["creator"],
                        priority=task_params["priority"],
                        tags=task_params["tags"],
                        admission=admission,
                        outputs={
                            "source_obs_id": task_params["source_obs_id"],
                            "source_obs_description": obs.description,
                            "conversion_rule": rule.name,
                            "semantic_signature": self._semantic_signature(rule, state),
                        },
                    )
                    self.observer.mark_consumed(obs.obs_id, task.task_id)
                    self._record_persistent_incident(rule, state, task.task_id)
                    self._mark_triggered(obs.obs_id)
                    result["rules_matched"] += 1
                    result["tasks_created"] += 1
                    result["details"].append({
                        "obs_id": obs.obs_id,
                        "rule": rule.name,
                        "task_id": task.task_id,
                        "task_title": task.title,
                        "task_priority": task.priority,
                    })
                except Exception as e:
                    result["details"].append({
                        "obs_id": obs.obs_id,
                        "rule": rule.name,
                        "error": str(e),
                    })

                break

        self._save_triggered_cache()
        if result["candidate_count"] and not result["eligible_count"]:
            result["outcome"] = "NO_VALID_MODEL_TASK_TARGET"
        return result
