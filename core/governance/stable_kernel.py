"""
Stable Recursive Kernel — 稳定递归治理内核

三条护栏：
  1. Drift Control    — 防止 confidence / laws / decisions 漂移
  2. State Snapshot   — 保证可回溯，append-only 历史
  3. Stability Layer — 保证同一输入产生同一输出

核心里程碑：
  OBSERVE → JUDGE → STABILIZE → EVOLVE → DRIFT CHECK

设计原则：
  - 不允许无约束进化（所有 mutation 必须经过 drift check）
  - 所有决策必须可复现（相同输入 → 相同输出）
  - 所有变化必须可回滚（任何 evolution 都不是 irreversible）

ACE 系统中的角色映射：
  - OBSERVE   → RuntimeObserver（observation.py）
  - JUDGE     → Governor（knowledge_governor.py）
  - STABILIZE → StabilityLayer（本文件）
  - EVOLVE    → KnowledgeEvolutionTracker（knowledge_evolution.py）
  - DRIFT     → DriftController（本文件）
"""

import copy
import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 1. StateSnapshot — 状态快照系统
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class StateSnapshot:
    """
    状态快照系统

    在每个决策周期开始前保存当前状态。
    Append-only，所有快照永久保留。

    可回溯：
      - rollback(steps=1) → 回退一步
      - replay()          → 回放历史
    """

    snapshots_dir: str

    def __post_init__(self):
        self.snapshots_dir = Path(self.snapshots_dir)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self.snapshots_dir / "snapshot_index.jsonl"
        self._data_dir = self.snapshots_dir / "snapshots"
        self._data_dir.mkdir(exist_ok=True)

    def save(self, snapshot_type: str, state_data: Dict[str, Any],
             metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        保存一个快照

        Returns:
            snapshot_id — 可用于后续 rollback
        """
        snapshot_id = f"{snapshot_type}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self._read_index())}"
        snapshot_record = {
            "snapshot_id": snapshot_id,
            "type": snapshot_type,
            "timestamp": datetime.now().isoformat(),
            "metadata": metadata or {},
            "state_keys": list(state_data.keys()),
        }

        data_file = self._data_dir / f"{snapshot_id}.json"
        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f, ensure_ascii=False, indent=2)

        with open(self._index_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot_record, ensure_ascii=False) + "\n")

        logger.info(f"[Snapshot] 已保存: {snapshot_id}")
        return snapshot_id

    def rollback(self, steps: int = 1) -> Optional[Dict[str, Any]]:
        """
        回退 N 步

        注意：回退不会删除快照（append-only），只是返回旧状态。
        真正"回到过去"需要调用者主动用回退状态替换当前状态。
        """
        index = self._read_index()
        if len(index) < steps:
            logger.warning(f"[Snapshot] 回退 {steps} 步，但只有 {len(index)} 个快照")
            return None

        target = index[len(index) - steps]
        data_file = self._data_dir / f"{target['snapshot_id']}.json"
        if not data_file.exists():
            logger.error(f"[Snapshot] 快照数据丢失: {target['snapshot_id']}")
            return None

        with open(data_file, "r", encoding="utf-8") as f:
            state = json.load(f)

        logger.info(f"[Snapshot] 回退到: {target['snapshot_id']} ({target['timestamp']})")
        return state

    def replay(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """回放指定快照（只读，不影响当前状态）"""
        data_file = self._data_dir / f"{snapshot_id}.json"
        if not data_file.exists():
            logger.error(f"[Snapshot] 快照不存在: {snapshot_id}")
            return None
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_latest(self) -> Optional[Dict[str, Any]]:
        """获取最新快照"""
        index = self._read_index()
        if not index:
            return None
        return self.replay(index[-1]["snapshot_id"])

    def get_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近 N 条快照记录（不含数据）"""
        index = self._read_index()
        return index[-limit:] if len(index) > limit else index

    def get_governance_summary(self) -> Dict[str, Any]:
        """获取快照系统统计"""
        index = self._read_index()
        types = {}
        for record in index:
            t = record["type"]
            types[t] = types.get(t, 0) + 1
        return {
            "total_snapshots": len(index),
            "by_type": types,
            "oldest": index[0]["timestamp"] if index else None,
            "newest": index[-1]["timestamp"] if index else None,
        }

    def _read_index(self) -> List[Dict[str, Any]]:
        if not self._index_file.exists():
            return []
        records = []
        with open(self._index_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        continue
        return records


# ═══════════════════════════════════════════════════════════════════════════
# 2. DriftController — 漂移控制层
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class DriftCheckResult:
    """漂移检查结果"""
    drift: float
    is_safe: bool
    action: str  # accept / rollback / flag
    drift_type: str  # confidence / governance / evolution
    details: Dict[str, Any] = field(default_factory=dict)


class DriftController:
    """
    漂移控制层

    监控三种漂移：
      1. Confidence Drift  — 置信度突变（单次变化超阈值）
      2. Governance Drift — 治理模式漂移（批准率/拒绝率趋势变化）
      3. Evolution Drift  — 演化模式漂移（升级/降级比率变化）

    默认 max_drift = 0.15（比老张给的 0.25 更严格）
    三源一致置信度单次变化不超过 0.15 是安全范围。
    """

    def __init__(self,
                 max_confidence_drift: float = 0.15,
                 max_governance_drift: float = 0.30,
                 max_evolution_drift: float = 0.25,
                 max_stability_deviation: float = 0.20):
        self.max_confidence_drift = max_confidence_drift
        self.max_governance_drift = max_governance_drift
        self.max_evolution_drift = max_evolution_drift
        self.max_stability_deviation = max_stability_deviation

    def check_confidence(self, before: Any, after: Any) -> DriftCheckResult:
        """
        检查置信度漂移

        Args:
            before: 之前的状态（dict 或带 confidence 属性的对象）
            after:  之后的状态
        """
        before_val = self._get_confidence(before)
        after_val = self._get_confidence(after)
        drift = abs(after_val - before_val)

        result = DriftCheckResult(
            drift=drift,
            is_safe=drift <= self.max_confidence_drift,
            action="accept" if drift <= self.max_confidence_drift else "rollback",
            drift_type="confidence",
            details={
                "before": before_val,
                "after": after_val,
                "threshold": self.max_confidence_drift,
                "change": after_val - before_val,
            }
        )

        if not result.is_safe:
            logger.warning(
                f"[Drift] Confidence 漂移检测: {before_val:.3f} → {after_val:.3f} "
                f"(drift={drift:.3f}, max={self.max_confidence_drift})"
            )

        return result

    def check_governance(self, before_stats: Dict[str, Any],
                         after_stats: Dict[str, Any]) -> DriftCheckResult:
        """
        检查治理模式漂移

        比较批准率趋势是否有突变。
        """
        before_rate = self._get_pass_rate(before_stats)
        after_rate = self._get_pass_rate(after_stats)
        drift = abs(after_rate - before_rate)

        result = DriftCheckResult(
            drift=drift,
            is_safe=drift <= self.max_governance_drift,
            action="accept" if drift <= self.max_governance_drift else "flag",
            drift_type="governance",
            details={
                "before_pass_rate": before_rate,
                "after_pass_rate": after_rate,
                "threshold": self.max_governance_drift,
            }
        )

        if not result.is_safe:
            logger.warning(
                f"[Drift] Governance 漂移检测: pass_rate {before_rate:.3f} → {after_rate:.3f} "
                f"(drift={drift:.3f})"
            )

        return result

    def check_evolution(self, before_events: List[Dict],
                        after_events: List[Dict]) -> DriftCheckResult:
        """
        检查演化模式漂移

        比较升级/降级比率是否异常。
        """
        before_ratio = self._get_upgrade_ratio(before_events)
        after_ratio = self._get_upgrade_ratio(after_events)
        drift = abs(after_ratio - before_ratio)

        result = DriftCheckResult(
            drift=drift,
            is_safe=drift <= self.max_evolution_drift,
            action="accept" if drift <= self.max_evolution_drift else "flag",
            drift_type="evolution",
            details={
                "before_upgrade_ratio": before_ratio,
                "after_upgrade_ratio": after_ratio,
                "threshold": self.max_evolution_drift,
            }
        )

        return result

    def check_stability(self, decision_history: List[Dict[str, Any]],
                        input_hash: str, new_confidence: float) -> DriftCheckResult:
        """
        检查稳定性偏差

        如果同一个 input_hash 的历史决策和新决策的 confidence 偏差过大，
        说明系统对这个输入的判断不稳定 → 强制收敛到历史值。
        """
        for record in reversed(decision_history):
            if record.get("input_hash") == input_hash:
                prev_confidence = record.get("confidence", 0.5)
                drift = abs(new_confidence - prev_confidence)

                result = DriftCheckResult(
                    drift=drift,
                    is_safe=drift <= self.max_stability_deviation,
                    action="accept" if drift <= self.max_stability_deviation else "stabilize",
                    drift_type="stability",
                    details={
                        "prev_confidence": prev_confidence,
                        "new_confidence": new_confidence,
                        "threshold": self.max_stability_deviation,
                    }
                )

                if not result.is_safe:
                    logger.warning(
                        f"[Drift] Stability 偏差: input={input_hash[:16]}... "
                        f"{prev_confidence:.3f} → {new_confidence:.3f}"
                    )

                return result

        return DriftCheckResult(
            drift=0.0, is_safe=True, action="accept",
            drift_type="stability",
            details={"reason": "first_time_evaluation"}
        )

    def check_all(self, before: Dict, after: Dict,
                  before_gov: Optional[Dict] = None,
                  after_gov: Optional[Dict] = None) -> Dict[str, DriftCheckResult]:
        """综合检查所有漂移类型"""
        results = {
            "confidence": self.check_confidence(before, after),
        }
        if before_gov and after_gov:
            results["governance"] = self.check_governance(before_gov, after_gov)
        return results

    def _get_confidence(self, state: Any) -> float:
        if isinstance(state, dict):
            return float(state.get("confidence", 0.5))
        if hasattr(state, "confidence"):
            return float(state.confidence)
        return 0.5

    def _get_pass_rate(self, stats: Dict[str, Any]) -> float:
        total = float(stats.get("total", 1))
        passed = float(stats.get("passed", 0))
        return passed / total if total > 0 else 0.0

    def _get_upgrade_ratio(self, events: List[Dict]) -> float:
        if not events:
            return 0.0
        upgrades = sum(1 for e in events if e.get("type") in ("promoted", "PROMOTED"))
        total = len(events)
        return upgrades / total


# ═══════════════════════════════════════════════════════════════════════════
# 3. StabilityLayer — 决策稳定性层
# ═══════════════════════════════════════════════════════════════════════════

class StabilityLayer:
    """
    决策稳定性层

    保证"同一输入"始终产生"同一输出"。

    原理：
      对相同的 input_hash，如果历史决策和新决策的 confidence 偏差 > 阈值，
      强制收敛到历史值，并打上 "stabilized" 标记。

    ACE 中的 input_hash：
      对于 triple_cross_validation，是 topic + 三源内容指纹的组合
      对于 Governor 决策，是 knowledge.title + 关键字段的组合
    """

    def __init__(self, cache_dir: str, deviation_threshold: float = 0.20):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._cache_file = self.cache_dir / "decision_cache.jsonl"
        self.deviation_threshold = deviation_threshold
        self._memory_cache: List[Dict[str, Any]] = []
        self._load_cache()

    def stabilize(self, input_hash: str, decision: Dict[str, Any],
                  decision_type: str = "governor") -> Dict[str, Any]:
        """
        稳定性检查 + 强制收敛

        Returns:
            decision — 可能被修改（stabilized）
            meta — 包含稳定性元数据
        """
        decision = copy.deepcopy(decision)
        meta = {
            "input_hash": input_hash,
            "decision_type": decision_type,
            "stabilized": False,
            "deviation": 0.0,
            "source": "cache" if self._find_in_cache(input_hash) else "fresh",
            "timestamp": datetime.now().isoformat(),
        }

        prev = self._find_in_cache(input_hash)
        if prev:
            prev_conf = prev.get("confidence", 0.5)
            new_conf = decision.get("confidence", 0.5)
            deviation = abs(new_conf - prev_conf)

            meta["deviation"] = deviation
            meta["prev_confidence"] = prev_conf

            if deviation > self.deviation_threshold:
                # 强制收敛到历史值
                decision["confidence"] = prev_conf
                decision["stabilized"] = True
                decision["stabilization_reason"] = f"deviation={deviation:.3f} > threshold={self.deviation_threshold}"
                meta["stabilized"] = True
                logger.info(
                    f"[Stability] 强制收敛: {input_hash[:24]}... "
                    f"{new_conf:.3f} → {prev_conf:.3f}"
                )

        self._append_to_cache({
            "input_hash": input_hash,
            "confidence": decision.get("confidence", 0.5),
            "decision": decision.get("decision", "unknown"),
            "decision_type": decision_type,
            "stabilized": meta["stabilized"],
            "timestamp": datetime.now().isoformat(),
        })

        return decision, meta

    def compute_input_hash(self, topic: str, local_summary: str = "",
                           tg_summary: str = "", external_summary: str = "") -> str:
        """
        计算输入指纹

        用于判断"相同输入"：
          同一个 topic + 相同的三源内容摘要 → 相同 hash
        """
        content = f"{topic}|{local_summary}|{tg_summary}|{external_summary}"
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:32]

    def get_stability_report(self) -> Dict[str, Any]:
        """获取稳定性报告"""
        stabilized_count = sum(1 for r in self._memory_cache if r.get("stabilized"))
        total = len(self._memory_cache)
        return {
            "total_decisions": total,
            "stabilized": stabilized_count,
            "stability_rate": (total - stabilized_count) / total if total > 0 else 1.0,
            "cache_entries": total,
        }

    def _load_cache(self):
        """从文件加载缓存到内存"""
        if not self._cache_file.exists():
            return
        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._memory_cache.append(json.loads(line))
        except Exception as e:
            logger.warning(f"[Stability] 缓存加载失败: {e}")

    def _append_to_cache(self, record: Dict[str, Any]):
        self._memory_cache.append(record)
        with open(self._cache_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _find_in_cache(self, input_hash: str) -> Optional[Dict[str, Any]]:
        for record in reversed(self._memory_cache):
            if record.get("input_hash") == input_hash:
                return record
        return None


# ═══════════════════════════════════════════════════════════════════════════
# 4. FeedbackLoop — 决策反馈闭环
# ═══════════════════════════════════════════════════════════════════════════

class FeedbackLoop:
    """
    决策反馈闭环

    让Governor的决策质量持续提升：
      决策(action) → 执行(execution) → 结果观察(observation) → 反馈(feedback) → 策略调整(adjustment)

    核心机制：
      - 追踪每个决策的后续结果（是对了还是错了）
      - 根据反馈微调confidence阈值（不是改阈值，是改对同类决策的预判）
      - 错误决策 → 降低同类决策的初始confidence
      - 正确决策 → 提高同类决策的初始confidence
      - 漂移保护：单次调整不超过 max_adjustment（防止自我强化漂移）
    """

    def __init__(self, feedback_dir: str, max_adjustment: float = 0.05,
                 history_window: int = 100):
        self.feedback_dir = Path(feedback_dir)
        self.feedback_dir.mkdir(parents=True, exist_ok=True)
        self._feedback_file = self.feedback_dir / "feedback_log.jsonl"
        self._patterns_file = self.feedback_dir / "decision_patterns.json"

        self.max_adjustment = max_adjustment
        self.history_window = history_window

        self._feedback_log: List[Dict] = []
        self._patterns: Dict[str, Dict] = {}

        self._load()

    def record_decision(self, decision_id: str, decision: Dict[str, Any],
                        decision_type: str = "governor",
                        context: Optional[Dict] = None) -> None:
        """记录一个待反馈的决策"""
        record = {
            "decision_id": decision_id,
            "decision": decision.get("decision", "unknown"),
            "confidence": decision.get("confidence", 0.5),
            "decision_type": decision_type,
            "context": context or {},
            "timestamp": datetime.now().isoformat(),
            "feedback": None,
            "resolved": False,
        }
        self._feedback_log.append(record)
        self._save_feedback()

    def record_feedback(self, decision_id: str, was_correct: bool,
                        actual_outcome: str = "", notes: str = "") -> Dict:
        """
        对一个决策给出反馈

        Args:
            decision_id: 决策ID
            was_correct: 决策是否正确（True=对了，False=错了）
            actual_outcome: 实际结果
            notes: 备注

        Returns:
            调整结果
        """
        target = None
        for record in reversed(self._feedback_log):
            if record["decision_id"] == decision_id:
                target = record
                break

        if not target:
            return {"error": "decision_not_found", "decision_id": decision_id}

        target["feedback"] = {
            "was_correct": was_correct,
            "actual_outcome": actual_outcome,
            "notes": notes,
            "feedback_time": datetime.now().isoformat(),
        }
        target["resolved"] = True

        # 更新模式
        pattern_key = self._extract_pattern_key(target)
        self._update_pattern(pattern_key, was_correct, target["confidence"])

        self._save_feedback()
        self._save_patterns()

        return {
            "decision_id": decision_id,
            "was_correct": was_correct,
            "pattern": pattern_key,
            "pattern_updated": True,
        }

    def predict_confidence(self, decision_type: str, context: Optional[Dict] = None) -> Optional[float]:
        """
        根据历史反馈预测同类决策的置信度

        用于StabilityLayer的初始值调整——如果历史上这类决策经常错，
        初始confidence就低一些；如果经常对，就高一些。
        """
        pattern_key = self._make_pattern_key(decision_type, context or {})
        pattern = self._patterns.get(pattern_key)
        if pattern and pattern.get("total", 0) >= 3:
            return pattern.get("avg_confidence", None)
        return None

    def adjust_decision(self, decision: Dict[str, Any], decision_type: str,
                        context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        根据历史反馈调整决策confidence

        Returns:
            调整后的决策 + meta信息
        """
        decision = copy.deepcopy(decision)
        meta = {
            "adjusted": False,
            "original_confidence": decision.get("confidence", 0.5),
            "adjustment": 0.0,
            "pattern": None,
        }

        pattern_key = self._make_pattern_key(decision_type, context or {})
        pattern = self._patterns.get(pattern_key)

        if pattern and pattern.get("total", 0) >= 3:
            accuracy = pattern["correct"] / pattern["total"]
            current_conf = decision.get("confidence", 0.5)

            # 准确率与置信度的偏差
            gap = accuracy - current_conf

            # 调整幅度 = gap * 0.5（保守调整，不直接跳到准确率）
            # 且不超过 max_adjustment
            adjustment = max(-self.max_adjustment, min(self.max_adjustment, gap * 0.5))

            if abs(adjustment) >= 0.01:
                decision["confidence"] = current_conf + adjustment
                decision["feedback_adjusted"] = True
                decision["feedback_adjustment_reason"] = (
                    f"pattern_accuracy={accuracy:.3f}, gap={gap:.3f}"
                )
                meta["adjusted"] = True
                meta["adjustment"] = adjustment
                meta["pattern"] = pattern_key
                meta["pattern_accuracy"] = accuracy
                meta["pattern_total"] = pattern["total"]

        return decision, meta

    def get_feedback_stats(self) -> Dict[str, Any]:
        """获取反馈统计"""
        resolved = [r for r in self._feedback_log if r.get("resolved")]
        correct = sum(1 for r in resolved if r["feedback"]["was_correct"])
        total = len(resolved)

        by_type = {}
        for record in resolved:
            t = record.get("decision_type", "unknown")
            if t not in by_type:
                by_type[t] = {"total": 0, "correct": 0, "accuracy": 0.0}
            by_type[t]["total"] += 1
            if record["feedback"]["was_correct"]:
                by_type[t]["correct"] += 1

        for t in by_type:
            by_type[t]["accuracy"] = (
                by_type[t]["correct"] / by_type[t]["total"]
                if by_type[t]["total"] > 0 else 0.0
            )

        return {
            "total_decisions": len(self._feedback_log),
            "resolved": total,
            "unresolved": len(self._feedback_log) - total,
            "correct": correct,
            "accuracy": correct / total if total > 0 else 0.0,
            "by_type": by_type,
            "patterns": len(self._patterns),
        }

    def _extract_pattern_key(self, record: Dict) -> str:
        return self._make_pattern_key(
            record.get("decision_type", "unknown"),
            record.get("context", {})
        )

    def _make_pattern_key(self, decision_type: str, context: Dict) -> str:
        """从决策类型和上下文中提取模式键"""
        # 用决策类型 + category（如果有）作为模式
        category = context.get("category", context.get("knowledge_category", "general"))
        return f"{decision_type}:{category}"

    def _update_pattern(self, pattern_key: str, was_correct: bool, confidence: float):
        """更新决策模式统计"""
        if pattern_key not in self._patterns:
            self._patterns[pattern_key] = {
                "total": 0,
                "correct": 0,
                "confidence_sum": 0.0,
                "avg_confidence": 0.0,
                "last_updated": datetime.now().isoformat(),
            }

        p = self._patterns[pattern_key]
        p["total"] += 1
        if was_correct:
            p["correct"] += 1
        p["confidence_sum"] += confidence
        p["avg_confidence"] = p["confidence_sum"] / p["total"]
        p["last_updated"] = datetime.now().isoformat()

    def _load(self):
        self._load_feedback()
        self._load_patterns()

    def _load_feedback(self):
        if not self._feedback_file.exists():
            return
        try:
            with open(self._feedback_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._feedback_log.append(json.loads(line))
            # 只保留最近 N 条
            if len(self._feedback_log) > self.history_window:
                self._feedback_log = self._feedback_log[-self.history_window:]
        except Exception as e:
            logger.warning(f"[Feedback] 反馈日志加载失败: {e}")

    def _save_feedback(self):
        try:
            with open(self._feedback_file, "w", encoding="utf-8") as f:
                for record in self._feedback_log:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[Feedback] 反馈日志保存失败: {e}")

    def _load_patterns(self):
        if not self._patterns_file.exists():
            return
        try:
            with open(self._patterns_file, "r", encoding="utf-8") as f:
                self._patterns = json.load(f)
        except Exception as e:
            logger.warning(f"[Feedback] 模式文件加载失败: {e}")

    def _save_patterns(self):
        try:
            with open(self._patterns_file, "w", encoding="utf-8") as f:
                json.dump(self._patterns, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[Feedback] 模式文件保存失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 5. StableRecursiveKernel — 核心里程碑
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class KernelCycleResult:
    """一次内核循环的结果"""
    cycle_id: str
    snapshot_id: str
    drift_check: Dict[str, Any]
    stability_meta: Dict[str, Any]
    feedback_meta: Dict[str, Any]
    action: str  # accept / rollback / stabilize
    final_state: Optional[Dict] = None
    rolled_back: bool = False
    stabilized: bool = False
    feedback_adjusted: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class StableRecursiveKernel:
    """
    稳定递归治理内核

    ACE 系统的主循环骨架：

      OBSERVE     → RuntimeObserver.observe(event, memory)
      JUDGE       → Governor.govern(knowledge)
      STABILIZE   → StabilityLayer.stabilize(input_hash, decision)
      EVOLVE      → KnowledgeEvolutionTracker + StateSnapshot.save()
      DRIFT CHECK → DriftController.check_all()

    收敛优先模式（Convergence-first Mode）：
      - 所有 mutation 必须经过 drift check
      - 漂移超限 → rollback
      - 稳定性偏差 → stabilize
      - 不允许无约束结构扩展
    """

    def __init__(
        self,
        base_dir: str,
        runtime_dir: str,
        observer=None,
        governor=None,
        evolution_tracker=None,
        triple_validator=None,
        max_drift: float = 0.15,
    ):
        from core.governance.knowledge_evolution import KnowledgeEvolutionTracker
        from core.observation import RuntimeObserver

        self.base_dir = Path(base_dir)
        self.runtime_dir = Path(runtime_dir)

        # 组件注入（不强制依赖，允许部分缺失）
        self.observer = observer
        self.governor = governor
        self.evolution_tracker = evolution_tracker
        self.triple_validator = triple_validator

        # 三条护栏 + 反馈 + 反思
        snapshot_dir = str(self.runtime_dir / "stable_kernel" / "snapshots")
        cache_dir = str(self.runtime_dir / "stable_kernel" / "stability_cache")
        feedback_dir = str(self.runtime_dir / "stable_kernel" / "feedback")
        reflection_dir = str(self.runtime_dir / "stable_kernel" / "reflection")

        self.snapshot = StateSnapshot(snapshot_dir)
        self.drift = DriftController(max_confidence_drift=max_drift)
        self.stability = StabilityLayer(cache_dir)
        self.feedback = FeedbackLoop(feedback_dir)
        self.reflector = SelfReflector(reflection_dir)

        # 运行计数
        self._cycle_count = 0

    def _judge_from_triple(self, triple_result: Dict, knowledge: Dict) -> Dict:
        """从 triple_cross_validation 结果生成决策"""
        confidence_map = {
            "high": 0.85,
            "medium": 0.55,
            "low": 0.30,
            "isolated": 0.20,
        }
        conf = confidence_map.get(triple_result.get("confidence", ""), 0.5)
        decision_map = {
            "high": "pass",
            "medium": "delay",
            "low": "reject",
            "isolated": "reject",
        }
        return {
            "decision": decision_map.get(triple_result.get("confidence", ""), "delay"),
            "confidence": conf,
            "reasons": [f"三源验证: {triple_result.get('confidence', 'unknown')}"],
            "conflict": triple_result.get("conflict", False),
            "triple_source": True,
        }

    def run_cycle(self, event: Dict[str, Any], knowledge: Optional[Dict] = None,
                  triple_result: Optional[Dict] = None) -> KernelCycleResult:
        """
        执行一次完整的内核循环

        OBSERVE → JUDGE → STABILIZE → EVOLVE → DRIFT CHECK
        """
        self._cycle_count += 1
        cycle_id = f"cycle_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._cycle_count}"

        # 0. 获取当前状态快照
        current_state = self._capture_current_state()
        snapshot_id = self.snapshot.save(
            snapshot_type="kernel_cycle",
            state_data=current_state,
            metadata={"cycle_id": cycle_id, "event_type": event.get("type", "unknown")}
        )

        # 1. OBSERVE
        perception = {}
        if self.observer:
            try:
                if hasattr(self.observer, "observe"):
                    perception = self.observer.observe(event, current_state.get("memory", {}))
                elif hasattr(self.observer, "get_observations"):
                    perception = {"observations": self.observer.get_observations()}
            except Exception as e:
                logger.warning(f"[Kernel] OBSERVE 失败: {e}")

        # 2. JUDGE（通过 TripleCrossValidation 或 Governor）
        raw_decision = {}
        if triple_result and knowledge:
            # triple_cross_validation 决策路径
            raw_decision = self._judge_from_triple(triple_result, knowledge)
        elif self.governor and knowledge:
            # Governor 决策路径
            try:
                gov_result = self.governor.govern(knowledge)
                admission = gov_result.get("admission")
                if admission is None:
                    raw_decision = {"decision": "unknown", "confidence": 0.5, "reasons": []}
                else:
                    raw_decision = {
                        "decision": admission.decision if hasattr(admission, "decision") else str(admission),
                        "confidence": admission.criteria.confidence if hasattr(admission, "criteria") and hasattr(admission.criteria, "confidence") else 0.5,
                        "reasons": admission.reasons if hasattr(admission, "reasons") else [],
                        "governor_source": True,
                    }
            except Exception as e:
                logger.warning(f"[Kernel] JUDGE 失败: {e}")

        # 3. STABILIZE
        input_hash = ""
        if triple_result:
            topic = triple_result.get("topic", "")
            input_hash = self.stability.compute_input_hash(
                topic,
                triple_result.get("local", {}).get("summary", ""),
                triple_result.get("tg", {}).get("summary", ""),
                triple_result.get("external", {}).get("summary", ""),
            )
        elif knowledge:
            input_hash = hashlib.sha256(
                knowledge.get("title", "").encode("utf-8")
            ).hexdigest()[:32]

        stable_decision, stability_meta = self.stability.stabilize(
            input_hash, raw_decision,
            decision_type="triple" if triple_result else "governor"
        )

        # 3.5 FEEDBACK ADJUST（根据历史反馈微调confidence）
        feedback_meta = {"adjusted": False, "adjustment": 0.0}
        try:
            context = knowledge or {}
            stable_decision, feedback_meta = self.feedback.adjust_decision(
                stable_decision,
                decision_type="triple" if triple_result else "governor",
                context=context,
            )
            # 记录决策到反馈系统（等待后续验证）
            self.feedback.record_decision(
                decision_id=cycle_id,
                decision=stable_decision,
                decision_type="triple" if triple_result else "governor",
                context=context,
            )
        except Exception as e:
            logger.warning(f"[Kernel] FEEDBACK ADJUST 失败: {e}")

        # 4. EVOLVE（记录到演化追踪器）
        if self.evolution_tracker:
            try:
                self.evolution_tracker.record_decision_and_event(
                    knowledge_id=knowledge.get("id", knowledge.get("title", "")) if knowledge else "",
                    decision=stable_decision.get("decision", "unknown"),
                    decision_type="kernel_cycle",
                    event_type="kernel_stabilized" if stability_meta.get("stabilized") else "kernel_accepted",
                    evidence={"cycle_id": cycle_id, "input_hash": input_hash},
                    actor_type="kernel",
                )
            except Exception as e:
                logger.warning(f"[Kernel] EVOLVE 失败: {e}")

        # 5. DRIFT CHECK
        # 比较快照前后的 confidence
        before_conf = current_state.get("avg_confidence", 0.5)
        after_conf = stable_decision.get("confidence", before_conf)
        drift_result = self.drift.check_confidence(
            {"confidence": before_conf},
            {"confidence": after_conf}
        )

        drift_check = {
            "before_confidence": before_conf,
            "after_confidence": after_conf,
            "drift": drift_result.drift,
            "is_safe": drift_result.is_safe,
            "action": drift_result.action,
        }

        # 如果漂移超限，触发 rollback
        rolled_back = False
        final_state = stable_decision
        if not drift_result.is_safe:
            logger.warning(f"[Kernel] 漂移超限，触发 rollback: {cycle_id}")
            rolled_back_state = self.snapshot.rollback(1)
            if rolled_back_state:
                final_state = rolled_back_state
                rolled_back = True
            # 触发自我反思
            try:
                self.reflector.reflect_on_failure({
                    "task_type": "kernel_cycle",
                    "error": f"confidence drift {drift_result.drift:.3f} > max {self.drift.max_confidence_drift}",
                    "input": {"cycle_id": cycle_id, "before": before_conf, "after": after_conf},
                    "decision_before": raw_decision,
                    "actual_outcome": "drift_triggered_rollback",
                })
            except Exception as e:
                logger.warning(f"[Kernel] 反思触发失败: {e}")

        return KernelCycleResult(
            cycle_id=cycle_id,
            snapshot_id=snapshot_id,
            drift_check=drift_check,
            stability_meta=stability_meta,
            feedback_meta=feedback_meta,
            action="rollback" if rolled_back else ("stabilize" if stability_meta.get("stabilized") else "accept"),
            final_state=final_state,
            rolled_back=rolled_back,
            stabilized=stability_meta.get("stabilized", False),
            feedback_adjusted=feedback_meta.get("adjusted", False),
        )

    def get_kernel_stats(self) -> Dict[str, Any]:
        """获取内核统计"""
        return {
            "total_cycles": self._cycle_count,
            "snapshot_stats": self.snapshot.get_governance_summary(),
            "stability_report": self.stability.get_stability_report(),
            "feedback_stats": self.feedback.get_feedback_stats(),
            "reflection_stats": self.reflector.get_reflection_stats(),
        }

    def _capture_current_state(self) -> Dict[str, Any]:
        """捕获当前治理状态的快照"""
        state = {
            "avg_confidence": 0.5,
            "governor_summary": {},
            "triple_stats": {},
            "timestamp": datetime.now().isoformat(),
        }

        if self.governor:
            try:
                state["governor_summary"] = self.governor.get_governance_summary()
                total = state["governor_summary"].get("total", 1)
                passed = state["governor_summary"].get("decisions", {}).get("pass", 0)
                state["avg_confidence"] = passed / total if total > 0 else 0.5
            except Exception:
                pass

        if self.triple_validator:
            try:
                if hasattr(self.triple_validator, "get_stats"):
                    state["triple_stats"] = self.triple_validator.get_stats()
            except Exception:
                pass

        return state


# ═══════════════════════════════════════════════════════════════════════════
# 6. SelfReflector — 自我反思引擎
# ═══════════════════════════════════════════════════════════════════════════

class SelfReflector:
    """
    自我反思引擎

    猎人的核心能力：从失败中学习，让每次失败都有价值。

    工作原理：
      任务失败 → 强制自检 → 提取错误模式 → 生成修正策略 → 更新约束/经验

    反思不是"骂自己"，而是"模式提取"——
    每次失败都要回答三个问题：
      1. 我哪里做错了？（错误定位）
      2. 为什么会错？（根因分析）
      3. 下次怎么避免？（策略修正）
    """

    ERROR_PATTERNS = {
        "insufficient_evidence": {
            "pattern": "证据不足时强行下结论",
            "triggers": ["confidence < 0.5", "单源孤证", "三个来源不一致"],
            "correction": "证据不足时标记为'待验证'，不进入知识层",
        },
        "premature_judgment": {
            "pattern": "过早判断，未收集足够信息就决策",
            "triggers": ["只扫描了本地就决策", "未查TG收藏夹", "未做外网验证"],
            "correction": "决策前必须走完三源验证流程",
        },
        "category_confusion": {
            "pattern": "分类错误，把概念当成协议或反过来",
            "triggers": ["category mismatch", "放置位置错误"],
            "correction": "分类前先查Lexicon，匹配失败则标记'待分类'",
        },
        "drift_detected": {
            "pattern": "置信度漂移，连续决策偏差过大",
            "triggers": ["drift > 0.15", "stabilized triggered"],
            "correction": "触发稳定性层强制收敛，暂停同类决策",
        },
        "unknown": {
            "pattern": "未知错误模式",
            "triggers": [],
            "correction": "记录错误，等待人工复盘",
        },
    }

    def __init__(self, reflection_dir: str):
        self.reflection_dir = Path(reflection_dir)
        self.reflection_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.reflection_dir / "reflection_log.jsonl"
        self._patterns_file = self.reflection_dir / "error_patterns.json"

        self._reflection_log: List[Dict] = []
        self._custom_patterns: Dict[str, Dict] = {}

        self._load()

    def reflect_on_failure(self, failure_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        对一次失败进行反思

        Args:
            failure_context: 失败上下文
                - task_type: 任务类型
                - error: 错误信息
                - input: 输入数据摘要
                - decision_before: 失败前的决策
                - actual_outcome: 实际结果

        Returns:
            反思结果
        """
        pattern = self._identify_pattern(failure_context)
        root_cause = self._analyze_root_cause(failure_context, pattern)
        correction = self._generate_correction(pattern, root_cause)

        reflection = {
            "reflection_id": f"ref_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "task_type": failure_context.get("task_type", "unknown"),
            "error_summary": failure_context.get("error", "")[:200],
            "error_pattern": pattern["pattern"],
            "pattern_key": pattern.get("key", "unknown"),
            "root_cause": root_cause,
            "correction_strategy": correction,
            "input_summary": str(failure_context.get("input", ""))[:200],
            "resolved": False,
            "verification": None,
        }

        self._reflection_log.append(reflection)
        self._save_log()

        return reflection

    def reflect_on_task_result(self, task_result: Dict[str, Any]) -> Optional[Dict]:
        """
        对任务结果进行反思（成功也可以反思）

        成功的反思：这次为什么对？能不能复制？
        失败的反思：这次为什么错？怎么避免？
        """
        success = task_result.get("success", task_result.get("status") == "success")
        if not success:
            return self.reflect_on_failure({
                "task_type": task_result.get("type", "unknown"),
                "error": task_result.get("error", str(task_result)),
                "input": task_result.get("input", {}),
                "decision_before": task_result.get("decision"),
                "actual_outcome": task_result.get("outcome", "failed"),
            })
        else:
            return self._reflect_on_success(task_result)

    def get_reflection_stats(self) -> Dict[str, Any]:
        """获取反思统计"""
        total = len(self._reflection_log)
        resolved = sum(1 for r in self._reflection_log if r.get("resolved"))
        by_pattern = {}
        for r in self._reflection_log:
            p = r.get("pattern_key", "unknown")
            by_pattern[p] = by_pattern.get(p, 0) + 1

        return {
            "total_reflections": total,
            "resolved": resolved,
            "unresolved": total - resolved,
            "by_pattern": by_pattern,
            "patterns_known": len(self.ERROR_PATTERNS) + len(self._custom_patterns),
        }

    def _identify_pattern(self, failure_context: Dict) -> Dict:
        """识别错误模式"""
        error_msg = str(failure_context.get("error", "")).lower()
        task_type = failure_context.get("task_type", "")

        for key, pattern in self.ERROR_PATTERNS.items():
            for trigger in pattern.get("triggers", []):
                if trigger.lower() in error_msg or trigger.lower() in task_type.lower():
                    return {"key": key, **pattern}

        for key, pattern in self._custom_patterns.items():
            for trigger in pattern.get("triggers", []):
                if trigger.lower() in error_msg:
                    return {"key": key, **pattern}

        return {"key": "unknown", **self.ERROR_PATTERNS["unknown"]}

    def _analyze_root_cause(self, failure_context: Dict, pattern: Dict) -> str:
        """根因分析"""
        error = failure_context.get("error", "")

        if pattern.get("key") == "insufficient_evidence":
            return "证据不足时没有遵循'待验证'流程，强行下结论导致错误"
        elif pattern.get("key") == "premature_judgment":
            return "跳过了必要的验证步骤，在信息不完整的情况下做出了决策"
        elif pattern.get("key") == "category_confusion":
            return "分类前没有查询Lexicon，凭感觉判断类别"
        elif pattern.get("key") == "drift_detected":
            return "置信度自我强化，没有经过稳定性层校验"
        else:
            return f"未知根因，需要人工复盘。错误信息: {str(error)[:100]}"

    def _generate_correction(self, pattern: Dict, root_cause: str) -> Dict:
        """生成修正策略"""
        return {
            "immediate": pattern.get("correction", "记录错误，等待人工复盘"),
            "root_cause": root_cause,
            "affected_scopes": self._identify_scopes(pattern),
            "verification_method": "下一次同类任务时验证修正是否有效",
        }

    def _identify_scopes(self, pattern: Dict) -> List[str]:
        """识别受影响的范围"""
        scope_map = {
            "insufficient_evidence": ["triple_validation", "governor"],
            "premature_judgment": ["task_pool", "researcher"],
            "category_confusion": ["lexicon", "governor"],
            "drift_detected": ["stable_kernel", "governor"],
        }
        return scope_map.get(pattern.get("key", "unknown"), ["unknown"])

    def _reflect_on_success(self, task_result: Dict) -> Dict:
        """成功反思——提取可复用的成功模式"""
        return {
            "reflection_id": f"ref_success_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "timestamp": datetime.now().isoformat(),
            "task_type": task_result.get("type", "unknown"),
            "success_pattern": "待提取",
            "reusability": "待评估",
            "outcome_summary": str(task_result.get("outcome", ""))[:200],
        }

    def _load(self):
        self._load_log()
        self._load_custom_patterns()

    def _load_log(self):
        if not self._log_file.exists():
            return
        try:
            with open(self._log_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self._reflection_log.append(json.loads(line))
        except Exception as e:
            logger.warning(f"[Reflector] 反思日志加载失败: {e}")

    def _save_log(self):
        try:
            with open(self._log_file, "a", encoding="utf-8") as f:
                if self._reflection_log:
                    f.write(json.dumps(self._reflection_log[-1], ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[Reflector] 反思日志保存失败: {e}")

    def _load_custom_patterns(self):
        if not self._patterns_file.exists():
            return
        try:
            with open(self._patterns_file, "r", encoding="utf-8") as f:
                self._custom_patterns = json.load(f)
        except Exception as e:
            logger.warning(f"[Reflector] 自定义模式加载失败: {e}")
