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
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass

from .observation import RuntimeObserver, Observation
from .task import TaskPool


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
    severity_min: str  # low / medium / high / critical
    condition_fn: Optional[Callable[[Observation], bool]] = None

    task_title: str = ""
    task_priority: str = "medium"
    task_tags: List[str] = None
    task_hypothesis: str = ""

    def matches(self, obs: Observation) -> bool:
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
        # 替换模板变量
        title = self.task_title.format(
            obs_id=obs.obs_id,
            description=obs.description[:50],
        )
        hypothesis = self.task_hypothesis.format(
            obs_id=obs.obs_id,
            description=obs.description,
            state=json.dumps(obs.system_state, ensure_ascii=False),
        )
        tags = [f"from_obs:{obs.obs_id}"] + (self.task_tags or [])
        return {
            "title": title,
            "hypothesis": hypothesis,
            "priority": self.task_priority,
            "tags": tags,
            "creator": "observation_to_task",
            "source_obs_id": obs.obs_id,
        }


# ============================================================
# 内置规则集
# ============================================================

def _review_bottleneck(obs: Observation) -> bool:
    """review 队列积压是系统瓶颈"""
    state = obs.system_state
    review_count = state.get("review", 0)
    pending_count = state.get("pending", 0)
    active_count = state.get("active", 0)
    # 积压超过 5 个，或者 review + pending = 0 但 review > 0
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


# 规则列表（按优先级从高到低排序）
BUILTIN_RULES: List[ConversionRule] = [
    # === 瓶颈类 (bottleneck) ===
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
    # === 缺口类 (gap) ===
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
    # === 异常类 (anomaly) ===
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
    # === 改进类 (improvement) ===
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
    # === 健康类 (health) ===
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
        self._triggered_cache = self._load_triggered_cache()

    def _load_triggered_cache(self) -> set:
        """加载已触发的 Observation ID 集合"""
        cache_file = self.observer.data_dir / "triggered_obs.json"
        if cache_file.exists():
            try:
                return set(json.load(open(cache_file, "r", encoding="utf-8")))
            except Exception:
                return set()
        return set()

    def _save_triggered_cache(self):
        cache_file = self.observer.data_dir / "triggered_obs.json"
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(list(self._triggered_cache), f, ensure_ascii=False)
        except Exception:
            pass

    def convert(self) -> Dict[str, Any]:
        """
        执行 Observation → Task 转换

        Returns:
          {
            "observations_checked": int,
            "rules_matched": int,
            "tasks_created": int,
            "skipped": int,
            "details": [...]
          }
        """
        result = {
            "observations_checked": 0,
            "rules_matched": 0,
            "tasks_created": 0,
            "skipped": 0,
            "details": [],
        }

        # 获取所有未处理的 Observation
        unprocessed = self.observer.get_unprocessed(limit=100)
        result["observations_checked"] = len(unprocessed)

        for obs in unprocessed:
            # 检查是否已触发过
            if obs.obs_id in self._triggered_cache:
                result["skipped"] += 1
                continue

            # 尝试匹配规则
            for rule in self.rules:
                if not rule.matches(obs):
                    continue

                # 生成 Task 参数
                task_params = rule.generate_task_from(obs)

                # 补充动态参数
                state = obs.system_state
                gap_categories = state.get("gap_categories", [])
                task_params["hypothesis"] = task_params["hypothesis"].format(
                    review=state.get("review", 0),
                    pending=state.get("pending", 0),
                    active=state.get("active", 0),
                    pending_scan=state.get("pending_scan", 0),
                    total_concepts=state.get("total_concepts", 0),
                    uncategorized=state.get("uncategorized", 0),
                    gap_count=len(gap_categories),
                    gap_categories=", ".join(gap_categories[:5]),
                    last_mine_seed_scan=state.get("last_mine_seed_scan", "never"),
                    recent_error_count=state.get("recent_error_count", 0),
                    error_samples=", ".join(state.get("error_samples", [])[:3]),
                    disk_free_pct=state.get("disk_free_pct", 0),
                    disk_free_gb=state.get("disk_free_gb", 0),
                    task_never_run=state.get("task_never_run", False),
                )

                # 创建 Task
                try:
                    task = self.task_pool.create_task(
                        title=task_params["title"],
                        hypothesis=task_params["hypothesis"],
                        creator=task_params["creator"],
                        priority=task_params["priority"],
                        tags=task_params["tags"],
                    )

                    # 记录 source_obs_id
                    task.outputs["source_obs_id"] = task_params["source_obs_id"]
                    task.outputs["source_obs_description"] = obs.description
                    self.task_pool.update_task(task)

                    # 标记 Observation 已处理
                    self.observer.mark_consumed(obs.obs_id, task.task_id)
                    self._triggered_cache.add(obs.obs_id)

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

                break  # 一个 Observation 只匹配一条规则

        self._save_triggered_cache()
        return result
