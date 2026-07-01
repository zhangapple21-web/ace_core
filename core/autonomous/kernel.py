"""
Autonomous Kernel — 系统神经节 v1

不是再造系统，是把已有系统点火成自驱闭环。

现有系统：
  思考层（脑）：HypothesisTree / Assumptions / Researcher
  实验层（手）：TripleCrossValidation / SurvivalLoopEngine
  判断层（审稿人）：Validator / RejectionEngine / SimilarityEngine
  记忆层（历史）：StateSnapshot / Archivist / Lineage
  修正层（自愈）：SelfHealing / KnowledgeEvolution

缺的：自动把它们串起来的"触发器 + 编排器 + 决策回写器"

本文件就是这个神经节。

结构：
  scan_triggers() → detect_signal() → run_experiment() → critique() → writeback() → snapshot()

v1 原则：
  - 薄，非常薄
  - 不发明新能力，只编排已有能力
  - 所有动作可回放（StateSnapshot）
  - 不修改 SurvivalLoopEngine 执行逻辑
"""

import json
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field


TRIGGER_TYPES = [
    "provider_failure",
    "contradiction",
    "low_confidence",
    "drift",
]


@dataclass
class TriggerSignal:
    """触发信号"""
    type: str
    source: str
    description: str
    severity: str = "low"  # low / medium / high / critical
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            "type": self.type,
            "source": self.source,
            "description": self.description,
            "severity": self.severity,
            "data": self.data,
            "timestamp": self.timestamp,
        }


class AutonomousKernel:
    """
    自主内核 v1 — 系统神经节

    职责：
      1. 监听触发信号（失败 / 矛盾 / 低置信 / 漂移）
      2. 编排对照实验（多 provider 跑同一输入）
      3. 批判对比（一致性 / 冲突 / 置信度）
      4. 高置信结论写回（配置 / 规则 / 假设）
      5. 全程快照可回放

    不做的事：
      - 不替代现有模块
      - 不修改 SurvivalLoopEngine 执行逻辑
      - 不发明新的治理规则
    """

    def __init__(
        self,
        llm_engine=None,
        data_dir: Optional[str] = None,
        ace_daemon=None,
    ):
        self.llm_engine = llm_engine
        self.ace_daemon = ace_daemon
        self._ready = False

        if data_dir:
            self.data_dir = Path(data_dir)
        elif ace_daemon and hasattr(ace_daemon, 'base_dir'):
            self.data_dir = Path(ace_daemon.base_dir) / "06_RUNTIME" / "ace" / "data" / "autonomous"
        else:
            self.data_dir = Path(__file__).parent.parent / "06_RUNTIME" / "ace" / "data" / "autonomous"

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.data_dir / "kernel_log.jsonl"
        self.experiments_dir = self.data_dir / "experiments"
        self.experiments_dir.mkdir(exist_ok=True)

        self._trigger_history: List[TriggerSignal] = []
        self._experiment_count = 0
        self._writeback_count = 0

    @property
    def is_ready(self) -> bool:
        return self._ready

    def initialize(self) -> bool:
        """初始化：接入现有系统"""
        try:
            if self.llm_engine and hasattr(self.llm_engine, 'initialize'):
                self.llm_engine.initialize()
            self._ready = True
            self._log_event("init", {"status": "ok"})
            return True
        except Exception as e:
            self._log_event("init", {"status": "failed", "error": str(e)})
            return False

    # ─── ① Trigger Listener ────────────────────────────────────────

    def scan_triggers(self) -> List[TriggerSignal]:
        """
        扫描触发信号。

        来源：
          1. provider failure logs — LLM 调用失败
          2. contradictions — 知识/假设之间的冲突
          3. low confidence — 低置信输出
          4. drift — 决策漂移

        v1 先实现最容易的：provider failure。
        其他的从现有系统里取数据。
        """
        signals: List[TriggerSignal] = []

        # 1. Provider Failures（从 LLM 引擎日志里扫）
        signals.extend(self._scan_provider_failures())

        # 2. Contradictions（从 RejectionEngine / SimilarityEngine 取）
        signals.extend(self._scan_contradictions())

        # 3. Low Confidence（从最近的验证结果里取）
        signals.extend(self._scan_low_confidence())

        # 4. Drift（从 StableKernel / DriftController 取）
        signals.extend(self._scan_drift())

        for sig in signals:
            self._trigger_history.append(sig)

        if signals:
            self._log_event("triggers_detected", {"count": len(signals), "types": [s.type for s in signals]})

        return signals

    def _scan_provider_failures(self) -> List[TriggerSignal]:
        """扫描 provider 失败日志"""
        signals = []
        if not self.llm_engine:
            return signals

        try:
            logs = []
            if hasattr(self.llm_engine, 'get_logs'):
                logs = self.llm_engine.get_logs(limit=100)
            elif hasattr(self.llm_engine, '_logs'):
                logs = list(self.llm_engine._logs[-100:])

            fail_logs = [l for l in logs if l.get("status") == "fail"]

            if len(fail_logs) >= 3:
                by_provider: Dict[str, int] = {}
                for l in fail_logs:
                    p = l.get("provider", "unknown")
                    by_provider[p] = by_provider.get(p, 0) + 1

                for provider, count in by_provider.items():
                    if count >= 2:
                        severity = "high" if count >= 5 else "medium"
                        signals.append(TriggerSignal(
                            type="provider_failure",
                            source=f"llm_engine.{provider}",
                            description=f"Provider {provider} 连续失败 {count} 次",
                            severity=severity,
                            data={"provider": provider, "failure_count": count},
                        ))

            # 单次严重失败也触发
            critical_errors = ["HTTP 401", "HTTP 403", "DNS", "SSL", "Connection refused"]
            for l in fail_logs[-5:]:
                err = l.get("error", "")
                for crit in critical_errors:
                    if crit.lower() in err.lower():
                        signals.append(TriggerSignal(
                            type="provider_failure",
                            source=f"llm_engine.{l.get('provider','unknown')}",
                            description=f"严重错误: {err[:100]}",
                            severity="high",
                            data={"provider": l.get("provider"), "error": err},
                        ))
                        break
        except Exception:
            pass

        return signals

    def _scan_contradictions(self) -> List[TriggerSignal]:
        """扫描矛盾（v1：从 rejection engine 取，没有就跳过）"""
        signals = []
        try:
            if self.ace_daemon and hasattr(self.ace_daemon, 'governor'):
                gov = self.ace_daemon.governor
                if hasattr(gov, 'rejection_engine'):
                    re = gov.rejection_engine
                    if hasattr(re, 'rejected_today') and re.rejected_today > 0:
                        signals.append(TriggerSignal(
                            type="contradiction",
                            source="rejection_engine",
                            description=f"今日拒绝 {re.rejected_today} 项，可能存在冲突",
                            severity="low",
                            data={"rejected_count": re.rejected_today},
                        ))
        except Exception:
            pass
        return signals

    def _scan_low_confidence(self) -> List[TriggerSignal]:
        """扫描低置信输出"""
        signals = []
        try:
            if self.ace_daemon and hasattr(self.ace_daemon, 'validator'):
                val = self.ace_daemon.validator
                if hasattr(val, 'recent_validations'):
                    low_conf = [v for v in val.recent_validations[-20:] if v.get("confidence", 1) < 0.3]
                    if len(low_conf) >= 2:
                        signals.append(TriggerSignal(
                            type="low_confidence",
                            source="validator",
                            description=f"近期 {len(low_conf)} 项验证置信度低于 0.3",
                            severity="medium",
                            data={"low_confidence_count": len(low_conf)},
                        ))
        except Exception:
            pass
        return signals

    def _scan_drift(self) -> List[TriggerSignal]:
        """扫描漂移（v1：从 stable_kernel 取，没有就跳过）"""
        signals = []
        try:
            if self.ace_daemon and hasattr(self.ace_daemon, 'stable_kernel'):
                sk = self.ace_daemon.stable_kernel
                if hasattr(sk, 'drift_controller'):
                    dc = sk.drift_controller
                    if hasattr(dc, 'recent_drifts') and dc.recent_drifts:
                        signals.append(TriggerSignal(
                            type="drift",
                            source="stable_kernel.drift_controller",
                            description=f"检测到 {len(dc.recent_drifts)} 次漂移事件",
                            severity="medium",
                            data={"drift_count": len(dc.recent_drifts)},
                        ))
        except Exception:
            pass
        return signals

    # ─── ② Experiment Orchestrator ─────────────────────────────────

    def run_experiment(
        self,
        prompt: str,
        system_prompt: str = "你是严谨的助手，请准确回答问题。",
        providers: Optional[List[str]] = None,
        experiment_id: Optional[str] = None,
        max_tokens: int = 500,
    ) -> Dict[str, Any]:
        """
        对照实验：同一输入跑所有（或指定）provider，收集输出做对比。

        注意：这不是顺序 fallback，是故意每个都跑一遍做对比。
        即使第一个成功了，后面的也要跑，因为目的是对照，不是快速返回。
        """
        if not experiment_id:
            experiment_id = f"exp_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{self._experiment_count}"
        self._experiment_count += 1

        results: Dict[str, Dict] = {}

        if not self.llm_engine:
            return {"experiment_id": experiment_id, "results": {}, "error": "no llm_engine"}

        available = self.llm_engine.available_providers if hasattr(self.llm_engine, 'available_providers') else []
        target_providers = providers or available

        for provider_name in target_providers:
            if provider_name not in available:
                continue
            try:
                result = self.llm_engine.chat(
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=system_prompt,
                    model=self._provider_model(provider_name),
                    max_tokens=max_tokens,
                )
                results[provider_name] = {
                    "success": result.get("success", False),
                    "content": result.get("content", ""),
                    "model": result.get("model", ""),
                    "latency_ms": result.get("latency_ms", 0),
                    "error": result.get("error", ""),
                }
            except Exception as e:
                results[provider_name] = {
                    "success": False,
                    "content": "",
                    "model": "",
                    "latency_ms": 0,
                    "error": str(e),
                }

        experiment = {
            "experiment_id": experiment_id,
            "timestamp": datetime.now().isoformat(),
            "prompt": prompt,
            "system_prompt": system_prompt,
            "providers": target_providers,
            "results": results,
        }

        self._save_experiment(experiment)
        self._log_event("experiment", {"id": experiment_id, "providers": len(results)})

        return experiment

    def _provider_model(self, provider_name: str) -> str:
        """provider 的默认模型"""
        defaults = {
            "glm": "glm-4-flash",
            "openrouter": "anthropic/claude-3.5-sonnet",
            "nim": "deepseek-ai/deepseek-v4-flash",
            "apiyi": "gemini-pro",
            "sambanova": "Meta-Llama-3.1-405B-Instruct",
            "oneapi": "gpt-4o",
            "github_models": "gpt-4o",
            "modelscope": "qwen-plus",
            "huggingface": "meta-llama/Meta-Llama-3-8B-Instruct",
            "ace_proxy": "gpt-4o",
        }
        return defaults.get(provider_name, "")

    def _save_experiment(self, experiment: Dict):
        """保存实验结果（可回放）"""
        try:
            exp_file = self.experiments_dir / f"{experiment['experiment_id']}.json"
            with open(exp_file, "w", encoding="utf-8") as f:
                json.dump(experiment, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ─── ③ Critic / Comparator ────────────────────────────────────

    def critique(self, experiment: Dict[str, Any]) -> Dict[str, Any]:
        """
        批判对比：分析多 provider 输出的一致性、冲突、置信度。

        指标：
          - consensus_score: 0-1，多少 provider 给出了一致答案
          - contradictions: 明显矛盾的点
          - confidence: 综合置信度评估
          - agreed: 一致同意的结论
          - disputed: 有争议的点
        """
        results = experiment.get("results", {})
        successful = {k: v for k, v in results.items() if v.get("success") and v.get("content")}

        if len(successful) < 2:
            return {
                "experiment_id": experiment.get("experiment_id"),
                "consensus_score": 0.0,
                "confidence": 0.0,
                "agreed": [],
                "disputed": [],
                "contradictions": [],
                "note": "成功 provider 不足 2 个，无法对比",
                "successful_count": len(successful),
            }

        contents = [v["content"] for v in successful.values()]

        # 简单相似度：比较前几句的关键词重叠度
        consensus = self._calc_consensus(contents)

        # 找矛盾点（简单版：否定词出现差异）
        contradictions = self._find_contradictions(successful)

        # 置信度 = 共识度 × (成功数 / 总数)
        success_ratio = len(successful) / max(len(results), 1)
        confidence = consensus * success_ratio

        agreed = []
        disputed = []
        if consensus >= 0.7:
            agreed.append(f"majority_consensus_{int(consensus*100)}pct")
        else:
            disputed.append("low_consensus")

        critique = {
            "experiment_id": experiment.get("experiment_id"),
            "timestamp": datetime.now().isoformat(),
            "consensus_score": round(consensus, 4),
            "confidence": round(confidence, 4),
            "successful_count": len(successful),
            "total_count": len(results),
            "agreed": agreed,
            "disputed": disputed,
            "contradictions": contradictions,
            "providers": list(successful.keys()),
        }

        self._log_event("critique", {
            "experiment_id": experiment.get("experiment_id"),
            "consensus": critique["consensus_score"],
            "confidence": critique["confidence"],
        })

        return critique

    def _calc_consensus(self, contents: List[str]) -> float:
        """计算多个文本之间的共识度（简单版：关键词 Jaccard 相似度均值）"""
        if len(contents) < 2:
            return 0.0

        def keywords(text: str) -> set:
            words = re.findall(r'[\w\u4e00-\u9fa5]+', text.lower())
            return set(w for w in words if len(w) >= 2)

        sets = [keywords(c[:1000]) for c in contents]

        # 计算两两 Jaccard 的平均
        total = 0
        pairs = 0
        for i in range(len(sets)):
            for j in range(i + 1, len(sets)):
                a, b = sets[i], sets[j]
                if a or b:
                    jaccard = len(a & b) / len(a | b)
                    total += jaccard
                    pairs += 1

        return total / max(pairs, 1)

    def _find_contradictions(self, results: Dict[str, Dict]) -> List[Dict]:
        """找矛盾点（v1 简单版：检测肯定/否定词差异）"""
        contradictions = []
        negations = ["不", "不是", "没有", "无法", "不能", "不会", "no", "not", "never", "cannot"]

        contents = [(k, v["content"]) for k, v in results.items()]

        for i in range(len(contents)):
            for j in range(i + 1, len(contents)):
                p1, c1 = contents[i]
                p2, c2 = contents[j]

                c1_neg = sum(1 for n in negations if n in c1[:200])
                c2_neg = sum(1 for n in negations if n in c2[:200])

                if abs(c1_neg - c2_neg) >= 2:
                    contradictions.append({
                        "type": "negation_difference",
                        "providers": [p1, p2],
                        "detail": f"{p1} 否定词 {c1_neg} 个, {p2} 否定词 {c2_neg} 个",
                    })

        return contradictions

    # ─── ④ Writeback Gate ─────────────────────────────────────────

    def writeback(
        self,
        critique: Dict[str, Any],
        experiment: Dict[str, Any],
        trigger: Optional[TriggerSignal] = None,
    ) -> Dict[str, Any]:
        """
        写回门：高置信结论才写回系统。

        写回目标（v1 从易到难）：
          1. 写入 assumptions（假说系统）— 总是可以
          2. 写入经验（experience deposition）— 中等置信
          3. 修改配置（provider 优先级 / 超时等）— 高置信 + 可回滚
          4. 其他更深层的 — v1 不做

        所有写回前先 snapshot（可回滚）。
        """
        result = {
            "experiment_id": critique.get("experiment_id"),
            "timestamp": datetime.now().isoformat(),
            "confidence": critique.get("confidence", 0),
            "actions": [],
            "snapshot_id": None,
            "error": None,
        }

        confidence = critique.get("confidence", 0)

        # 先快照（任何写回前都留底）
        snapshot_id = self._snapshot_before_writeback(experiment, critique)
        result["snapshot_id"] = snapshot_id

        # 1. 低置信 → 只记录，不写回
        if confidence < 0.3:
            result["actions"].append({"type": "log_only", "reason": "confidence_too_low"})
            self._log_event("writeback", {"action": "log_only", "confidence": confidence})
            return result

        # 2. 中等置信 → 写入 assumptions
        if confidence >= 0.3 and confidence < 0.7:
            self._write_assumption(critique, experiment, trigger)
            result["actions"].append({"type": "add_assumption"})
            self._writeback_count += 1
            self._log_event("writeback", {"action": "add_assumption", "confidence": confidence})

        # 3. 高置信 → 写入 assumptions + 经验
        if confidence >= 0.7:
            self._write_assumption(critique, experiment, trigger)
            self._write_experience(critique, experiment)
            result["actions"].append({"type": "add_assumption"})
            result["actions"].append({"type": "add_experience"})
            self._writeback_count += 2
            self._log_event("writeback", {"action": "add_assumption_and_experience", "confidence": confidence})

        return result

    def _snapshot_before_writeback(self, experiment: Dict, critique: Dict) -> Optional[str]:
        """写回前快照（用 StableKernel 的 StateSnapshot，如果有的话）"""
        try:
            if self.ace_daemon and hasattr(self.ace_daemon, 'stable_kernel'):
                sk = self.ace_daemon.stable_kernel
                if hasattr(sk, 'state_snapshot'):
                    return sk.state_snapshot.save(
                        snapshot_type="autonomous_writeback",
                        state_data={"experiment": experiment, "critique": critique},
                    )
        except Exception:
            pass
        return None

    def _write_assumption(self, critique: Dict, experiment: Dict, trigger: Optional[TriggerSignal]):
        """写入假说系统（v1 简单版：存到 assumptions 目录）"""
        try:
            assumptions_dir = self.data_dir.parent.parent / "governance" / "assumptions"
            assumptions_dir.mkdir(parents=True, exist_ok=True)

            exp_id = experiment.get("experiment_id", "unknown")
            prompt = experiment.get("prompt", "")[:100]
            conf = critique.get("confidence", 0)

            assumption = {
                "id": f"auto_{exp_id}",
                "title": f"自动实验结论: {prompt}",
                "status": "hypothesis",
                "confidence": conf,
                "description": f"由 Autonomous Kernel 自动生成，基于 {critique.get('successful_count',0)} 个 provider 的对照实验",
                "assertion": f"共识度 {critique.get('consensus_score',0)}",
                "evidence": [f"experiment:{exp_id}"],
                "counter_evidence": [],
                "sources": ["autonomous_kernel_v1"],
                "source_files": [f"experiments/{exp_id}.json"],
                "next_validation": ["扩大样本量验证", "增加更多provider"],
                "created": datetime.now().isoformat(),
                "updated": datetime.now().isoformat(),
                "owner": "autonomous_kernel",
                "tags": ["auto_generated", "experiment"],
            }

            ass_file = assumptions_dir / f"auto_{exp_id}.json"
            with open(ass_file, "w", encoding="utf-8") as f:
                json.dump(assumption, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _write_experience(self, critique: Dict, experiment: Dict):
        """写入经验（v1：存到 experience_deposition 目录）"""
        try:
            exp_dir = self.data_dir.parent.parent / "experience"
            exp_dir.mkdir(parents=True, exist_ok=True)

            exp_id = experiment.get("experiment_id", "unknown")
            conf = critique.get("confidence", 0)

            experience = {
                "id": f"exp_auto_{exp_id}",
                "title": f"对照实验经验: {experiment.get('prompt','')[:50]}",
                "context": "多 provider 对照实验",
                "lesson": f"在 {critique.get('successful_count',0)} 个 provider 上验证，共识度 {critique.get('consensus_score',0)}",
                "confidence": conf,
                "related_tasks": [],
                "tags": ["auto_generated", "experiment", "multi_provider"],
                "created": datetime.now().isoformat(),
                "experiment_id": exp_id,
            }

            exp_file = exp_dir / f"auto_{exp_id}.json"
            with open(exp_file, "w", encoding="utf-8") as f:
                json.dump(experience, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ─── ⑤ 完整闭环 ──────────────────────────────────────────────

    def run_autonomous_loop(self, max_triggers: int = 3) -> Dict[str, Any]:
        """
        跑一圈完整的自主闭环：

        scan_triggers → pick one → run_experiment → critique → writeback → snapshot

        v1 每轮最多处理 max_triggers 个信号。
        """
        if not self._ready:
            self.initialize()

        loop_result = {
            "loop_start": datetime.now().isoformat(),
            "triggers_detected": 0,
            "triggers_processed": 0,
            "experiments_run": 0,
            "writebacks": 0,
            "items": [],
        }

        # 1. 扫描触发信号
        signals = self.scan_triggers()
        loop_result["triggers_detected"] = len(signals)

        if not signals:
            loop_result["note"] = "no triggers detected"
            loop_result["loop_end"] = datetime.now().isoformat()
            return loop_result

        # 2. 按严重程度排序，处理前 N 个
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        signals = sorted(signals, key=lambda s: severity_order.get(s.severity, 99))

        processed = 0
        for sig in signals[:max_triggers]:
            try:
                item = self._process_trigger(sig)
                loop_result["items"].append(item)
                if item.get("experiment"):
                    loop_result["experiments_run"] += 1
                if item.get("writeback"):
                    loop_result["writebacks"] += len(item["writeback"].get("actions", []))
                processed += 1
            except Exception as e:
                loop_result["items"].append({"trigger": sig.to_dict(), "error": str(e)})

        loop_result["triggers_processed"] = processed
        loop_result["loop_end"] = datetime.now().isoformat()

        self._log_event("loop_complete", {
            "triggers": loop_result["triggers_detected"],
            "processed": processed,
            "experiments": loop_result["experiments_run"],
            "writebacks": loop_result["writebacks"],
        })

        return loop_result

    def _process_trigger(self, signal: TriggerSignal) -> Dict[str, Any]:
        """处理单个触发信号"""
        item = {"trigger": signal.to_dict()}

        # 根据触发类型生成实验 prompt
        prompt = self._trigger_to_prompt(signal)
        if not prompt:
            item["error"] = "cannot generate experiment prompt"
            return item

        # 跑对照实验
        experiment = self.run_experiment(
            prompt=prompt,
            system_prompt="你是一个严谨的验证者。请准确回答以下问题，答案要简短明确。",
            max_tokens=200,
        )
        item["experiment"] = {"id": experiment.get("experiment_id"), "providers": list(experiment.get("results", {}).keys())}

        # 批判对比
        critique = self.critique(experiment)
        item["critique"] = {
            "consensus": critique.get("consensus_score"),
            "confidence": critique.get("confidence"),
            "successful_count": critique.get("successful_count"),
        }

        # 写回
        writeback = self.writeback(critique, experiment, signal)
        item["writeback"] = writeback

        return item

    def _trigger_to_prompt(self, signal: TriggerSignal) -> Optional[str]:
        """把触发信号转换成实验 prompt"""
        t = signal.type
        if t == "provider_failure":
            provider = signal.data.get("provider", "")
            return f"请用一句话回答：{provider} 这个API提供商常见的认证错误有哪些原因？"
        elif t == "contradiction":
            return "请用一句话回答：当两个结论互相矛盾时，应该优先相信哪一个？"
        elif t == "low_confidence":
            return "请用一句话回答：如何提高一个结论的置信度？"
        elif t == "drift":
            return "请用一句话回答：系统决策发生漂移时，应该如何修正？"
        else:
            return None

    # ─── 工具方法 ────────────────────────────────────────────────

    def _log_event(self, event_type: str, data: Dict = None):
        """记录事件日志（append-only）"""
        try:
            entry = {
                "type": event_type,
                "timestamp": datetime.now().isoformat(),
                "data": data or {},
            }
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_stats(self) -> Dict[str, Any]:
        """统计信息"""
        return {
            "ready": self._ready,
            "trigger_history": len(self._trigger_history),
            "experiment_count": self._experiment_count,
            "writeback_count": self._writeback_count,
            "data_dir": str(self.data_dir),
        }
