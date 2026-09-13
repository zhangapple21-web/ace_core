"""Self-Evolution Coordinator — 主动发现、融合与受治理提案。

ACE 过去已经有主动扫描器、知识演化追踪器和每日演化规划器，但它们
分别产出结果，运行时没有一个小而明确的闭环把「我看到了什么」变成
「我下一步应该验证什么」。本模块补上这个缺口：

    observe → fuse → propose → Observation → Task → 验证/归档

它只创建可审计的 Observation，不直接修改协议、知识或生产代码。所有
提案都必须经过现有 ObservationToTaskConverter、TaskPool、Validator 和
Guardian；夜间运行因此仍然是可回滚、可限流的。
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvolutionSignal:
    source: str
    kind: str
    subject: str
    detail: str
    weight: float = 1.0
    evidence_ref: str = ""


@dataclass(frozen=True)
class EvolutionProposal:
    proposal_id: str
    fingerprint: str
    title: str
    reason: str
    objective: str
    completion_criteria: str
    verification_method: str
    priority: str
    route: str
    confidence: float
    evidence: List[Dict[str, Any]]
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class SelfEvolutionCoordinator:
    """在不越过现有治理边界的前提下主动提出下一步演化方向。"""

    MAX_REPOSITORIES = 12
    MAX_ARCHAEOLOGY_FILES = 8
    MAX_SIGNALS = 32
    MIN_CONFIDENCE = 0.45

    def __init__(self, base_dir: str | Path, observer=None, task_pool=None):
        self.base_dir = Path(base_dir).resolve()
        self.observer = observer
        self.task_pool = task_pool
        self.runtime_data_dir = self.base_dir / "06_RUNTIME" / "ace" / "data" / "self_evolution"
        self.knowledge_dir = self.base_dir / "09_KNOWLEDGE" / "self_evolution"
        self.runtime_data_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.knowledge_dir / "proposals.jsonl"
        self.state_path = self.runtime_data_dir / "state.json"
        self._state = self._load_state()

    def run_cycle(self, runtime_state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """运行一次有上限的主动演化循环。

        返回值可直接放入 daemon cycle receipt；没有足够交叉证据时保持
        静默，不制造任务。相同指纹在 Observation 仍活跃时不会重复写入。
        """
        signals = self.collect_signals(runtime_state or {})[: self.MAX_SIGNALS]
        proposal = self.fuse(signals)
        result: Dict[str, Any] = {
            "status": "NO_ACTION",
            "signals": len(signals),
            "proposal": None,
            "observation_id": None,
        }
        if proposal is None:
            self._state.update({"last_run_at": datetime.now().isoformat(), "last_signal_count": len(signals)})
            self._save_state()
            return result

        result["proposal"] = proposal.to_dict()
        if proposal.fingerprint == self._state.get("active_fingerprint"):
            result["status"] = "ALREADY_ACTIVE"
            self._state.update({"last_run_at": datetime.now().isoformat(), "last_signal_count": len(signals)})
            self._save_state()
            return result

        self._append_proposal(proposal)
        self._state.update({
            "active_fingerprint": proposal.fingerprint,
            "last_run_at": datetime.now().isoformat(),
            "last_signal_count": len(signals),
        })
        self._save_state()

        if self.observer is not None:
            discovery = proposal.to_dict()
            discovery.update({
                "candidate_source": "self_evolution",
                "task_type": "reasoning",
                "autonomous_maintenance": {
                    "why_now": proposal.reason,
                    "evidence": [
                        {
                            "source_ref": item.get("ref") or item.get("source"),
                            "detail": item.get("detail", ""),
                        }
                        for item in proposal.evidence
                    ],
                    "priority": proposal.priority,
                    "expected_result": proposal.completion_criteria,
                    "verification_method": proposal.verification_method,
                    "risk": "仅生成受治理验证任务，不直接修改生产代码或知识库。",
                    "source": "self_evolution_coordinator",
                    "estimated_scope": "单个候选、一次验证循环",
                },
            })
            observation = self.observer.record(
                description=f"主动演化候选：{proposal.title}（置信度 {proposal.confidence:.2f}）",
                system_state={"discovery": discovery, "evolution": {"signals": [asdict(s) for s in signals]}},
                severity="high" if proposal.priority == "high" else "medium",
                source="discovery_mode",
                category="improvement",
                dedup_key=proposal.fingerprint,
            )
            result["observation_id"] = observation.obs_id
            result["status"] = "OBSERVED"
        else:
            result["status"] = "PROPOSED_NO_OBSERVER"
        return result

    def collect_signals(self, runtime_state: Dict[str, Any]) -> List[EvolutionSignal]:
        signals: List[EvolutionSignal] = []
        signals.extend(self._runtime_signals(runtime_state))
        signals.extend(self._archaeology_signals())
        signals.extend(self._repository_signals())
        signals.extend(self._remote_catalog_signals())
        return signals

    def fuse(self, signals: Iterable[EvolutionSignal]) -> Optional[EvolutionProposal]:
        """按稳定 subject 聚合多源证据，选择一个最高价值候选。"""
        grouped: Dict[str, List[EvolutionSignal]] = {}
        for signal in signals:
            # 只按归一化主题分组，允许 runtime / archaeology / git 以不同语义
            # 描述同一条演化缺口；kind 仍保留在证据中，不丢失来源语义。
            key = self._canonical_subject(signal)
            grouped.setdefault(key, []).append(signal)
        candidates = []
        for key, items in grouped.items():
            unique_sources = {item.source for item in items}
            score = min(1.0, sum(max(0.0, item.weight) for item in items) / 2.5)
            if len(unique_sources) < 2 and score < 0.8:
                continue
            candidates.append((score, len(unique_sources), key, items))
        if not candidates:
            return None
        score, source_count, key, items = max(candidates, key=lambda item: (item[0], item[1], item[2]))
        subject = key
        kind = max(items, key=lambda item: item.weight).kind
        fingerprint = hashlib.sha256(
            json.dumps({"subject": subject, "kinds": sorted({i.kind for i in items}), "sources": sorted({i.source for i in items})}, sort_keys=True).encode()
        ).hexdigest()[:20]
        now = datetime.now().isoformat()
        priority = "high" if score >= 0.8 or any(i.kind in {"runtime_bottleneck", "runtime_anomaly"} for i in items) else "medium"
        title = f"验证主动演化方向：{subject[:70]}"
        evidence = [
            {"source": item.source, "kind": item.kind, "detail": item.detail, "ref": item.evidence_ref}
            for item in items
        ]
        return EvolutionProposal(
            proposal_id=f"SEP-{datetime.now().strftime('%Y%m%d%H%M%S')}-{fingerprint[:8]}",
            fingerprint=fingerprint,
            title=title,
            reason=f"{source_count} 个独立来源共同指向 {subject}，融合置信度 {score:.2f}。",
            objective=f"围绕“{subject}”完成一次受限验证，确认是否值得沉淀为能力或治理改进。",
            completion_criteria="形成带来源的验证记录，并由 Validator/Guardian 判定采纳、延后或拒绝。",
            verification_method="复跑同一指纹的观察，检查证据是否增加且置信度漂移不超过 0.15。",
            priority=priority,
            route="self_evolution",
            confidence=round(score, 3),
            evidence=evidence,
            created_at=now,
        )

    @staticmethod
    def _canonical_subject(signal: EvolutionSignal) -> str:
        """把不同来源对同一系统性缺口的叫法归一化。"""
        subject = signal.subject.strip().lower()
        if signal.kind in {"repository_activity", "repository_gap"} or any(token in subject for token in ("主动发现", "演化索引", "self-evolution")):
            return "主动演化闭环"
        return subject

    def _runtime_signals(self, state: Dict[str, Any]) -> List[EvolutionSignal]:
        if not state and self.task_pool is not None:
            try:
                stats = self.task_pool.get_stats()
                state = {"task_pool": stats, "recent_error_count": len(stats.get("errors", []))}
            except Exception:
                state = {}
        signals: List[EvolutionSignal] = []
        task_pool = state.get("task_pool", state)
        by_status = task_pool.get("by_status", {}) if isinstance(task_pool, dict) else {}
        review = int(by_status.get("review", state.get("review", 0)) or 0)
        pending = int(by_status.get("pending", state.get("pending", 0)) or 0)
        if review >= 5:
            signals.append(EvolutionSignal("runtime", "runtime_bottleneck", "review 队列治理", f"review={review}, pending={pending}", 1.2, "daemon:task_pool"))
            # 队列压力本身不是结论，但它是“发现→验证→反馈”闭环值得
            # 主动检查的运行时证据；与考古/仓库信号可融合成同一提案。
            signals.append(EvolutionSignal("runtime", "evolution_gap", "主动演化闭环", f"review backlog={review}", 0.8, "daemon:task_pool"))
        errors = int(state.get("recent_error_count", 0) or 0)
        if errors >= 3:
            signals.append(EvolutionSignal("runtime", "runtime_anomaly", "近期错误模式", f"recent_error_count={errors}", 1.2, "daemon:errors"))
        return signals

    def _archaeology_signals(self) -> List[EvolutionSignal]:
        roots = [self.base_dir / "08_ARCHAEOLOGY", self.base_dir / "09_KNOWLEDGE"]
        cutoff = datetime.now() - timedelta(days=14)
        files: List[Path] = []
        for root in roots:
            if root.exists():
                files.extend(path for path in root.rglob("*.md") if self._recent(path, cutoff))
        signals: List[EvolutionSignal] = []
        for path in sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)[: self.MAX_ARCHAEOLOGY_FILES]:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:12000]
            except OSError:
                continue
            if not any(token in text.lower() for token in ("主动发现", "自我融合", "自我演化", "self-evolution", "evolution")):
                continue
            subject = "主动发现与跨域融合闭环"
            signals.append(EvolutionSignal("archaeology", "evolution_gap", subject, f"历史材料 {path.name} 明确记录主动发现/融合模式", 1.1, str(path)))
        return signals

    def _repository_signals(self) -> List[EvolutionSignal]:
        signals: List[EvolutionSignal] = []
        parent = self.base_dir.parent
        if not parent.exists():
            return signals
        repos = [p for p in parent.iterdir() if p.is_dir() and (p / ".git").exists() and p.resolve() != self.base_dir]
        for repo in sorted(repos, key=lambda p: p.name.lower())[: self.MAX_REPOSITORIES]:
            remote, commit = self._git_snapshot(repo)
            if not remote and not commit:
                continue
            signals.append(EvolutionSignal("git", "repository_activity", "跨仓库演化索引", f"{repo.name}: {commit or 'unknown'}", 0.9, remote or str(repo)))
        return signals

    def _remote_catalog_signals(self) -> List[EvolutionSignal]:
        """读取已有的远程文明地图快照；不联网、不执行远程写入。"""
        research = self.base_dir / "research"
        reports = sorted(research.glob("remote_civilization_map_*.json"), key=lambda p: p.stat().st_mtime, reverse=True) if research.exists() else []
        if not reports:
            return []
        try:
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        signals: List[EvolutionSignal] = []
        repositories = payload.get("repositories")
        if not isinstance(repositories, list):
            repositories = payload.get("scan", {}).get("repositories", [])
        for repo in repositories[: self.MAX_REPOSITORIES]:
            if not isinstance(repo, dict) or repo.get("stale_level") not in {"Critical", "Abandoned"}:
                continue
            name = str(repo.get("name", "unknown"))
            detail = f"远程仓库 {name} stale={repo.get('stale_level')} pushed_at={repo.get('pushed_at', 'unknown')}"
            signals.append(EvolutionSignal("remote_git", "repository_gap", "跨仓库演化索引", detail, 1.0, str(repo.get("url", reports[0]))))
        return signals

    @staticmethod
    def _git_snapshot(repo: Path) -> tuple[str, str]:
        try:
            remote = subprocess.run(["git", "-C", str(repo), "config", "--get", "remote.origin.url"], capture_output=True, text=True, timeout=2, check=False).stdout.strip()
            commit = subprocess.run(["git", "-C", str(repo), "log", "-1", "--format=%h %ad", "--date=short"], capture_output=True, text=True, timeout=2, check=False).stdout.strip()
            return remote, commit
        except (OSError, subprocess.SubprocessError, RuntimeError):
            return "", ""

    @staticmethod
    def _recent(path: Path, cutoff: datetime) -> bool:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime) >= cutoff
        except OSError:
            return False

    def _append_proposal(self, proposal: EvolutionProposal) -> None:
        try:
            with self.ledger_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(proposal.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("写入主动演化提案失败: %s", exc)

    def _load_state(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_state(self) -> None:
        try:
            temporary = self.state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.state_path)
        except OSError as exc:
            logger.warning("保存主动演化状态失败: %s", exc)
