"""
Observation 模块 — RO（Runtime Observer）核心

RO 的职责：
  - 持续观察系统状态
  - 记录 Observation（不是 Task，是观察事实）
  - 通过规则引擎，将 Observation 转换为 Task
  - 不干预、不执行，只记录和路由

Observation ≠ Task：
  - Observation：系统当前状态的客观记录
  - Task：从 Observation 经过规则转换而来的行动单元

设计原则：
  - 每个 Observation 有全局唯一编号（递增）
  - Observation 有生命周期：active → archived
  - 同一个 Observation 只能触发一次 Task 生成（防抖）
  - RO 不做判断，只做记录和转换
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


@dataclass
class Observation:
    """
    单一观察记录

    示例：
      obs_id: OBS-20260628-001
      system_state: {"review堵塞": 10}
      description: "review队列连续积压，Runtime流水线阻塞"
      severity: high  # low / medium / high / critical
      source: "patrol_loop" | "worker_report" | "daemon_loop" | "manual"
      related_tasks: []
      task_generated: None | task_id
      auto_generated: bool  # 是否由系统自动生成（vs 人工记录）
      created_at: ISO timestamp
    """
    obs_id: str
    description: str
    system_state: Dict[str, Any]
    severity: str  # low / medium / high / critical
    source: str  # patrol_loop / worker_report / daemon_loop / manual
    category: str  # bottleneck / gap / anomaly / improvement / health
    related_tasks: List[str]  # 关联的 task_id 列表
    task_generated: Optional[str]  # 由哪个 task 消化了这个 observation
    auto_generated: bool
    created_at: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuntimeObserver:
    """
    Runtime Observer — 持续观察者

    职责边界：
      ✓ 记录 Observation
      ✓ 维护 Observation 编号序列
      ✓ 查找历史 Observation
      ✓ 标记 Observation 被某 Task 消化
      ✗ 不执行任何操作
      ✗ 不创建 Task（那是 ObservationToTask 的职责）
    """

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            base = Path(__file__).resolve().parent.parent
            data_dir = base / "06_RUNTIME" / "ace" / "data" / "observations"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.observations_file = self.data_dir / "observations.jsonl"
        self.index_file = self.data_dir / "observation_index.json"
        self._seq_file = self.data_dir / "seq_counter.txt"

        self._observations: List[Observation] = []
        self._seq: int = 0
        self._load()

    def _load(self):
        """加载已有 Observation 记录和序号"""
        # 加载序号
        if self._seq_file.exists():
            try:
                self._seq = int(self._seq_file.read_text().strip())
            except Exception:
                self._seq = 0

        # 加载历史记录（只加载最近 200 条）
        if self.observations_file.exists():
            try:
                with open(self.observations_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            self._observations.append(Observation(**data))
                        except Exception:
                            pass
                # 只保留最近 200 条
                if len(self._observations) > 200:
                    self._observations = self._observations[-200:]
            except Exception:
                pass

    def _save_seq(self):
        """保存序号"""
        self._seq_file.write_text(str(self._seq))

    def _append(self, obs: Observation):
        """追加单条 Observation 到文件"""
        self._observations.append(obs)
        try:
            with open(self.observations_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(obs.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass
        # 只在内存中保留最近 200 条
        if len(self._observations) > 200:
            self._observations = self._observations[-200:]

    def _next_id(self) -> str:
        """生成下一个 Observation ID"""
        self._seq += 1
        self._save_seq()
        today = datetime.now().strftime("%Y%m%d")
        return f"OBS-{today}-{self._seq:04d}"

    def record(
        self,
        description: str,
        system_state: Dict[str, Any],
        severity: str = "medium",
        source: str = "daemon_loop",
        category: str = "anomaly",
        auto_generated: bool = True,
    ) -> Observation:
        """
        记录一条 Observation

        Args:
            description: 客观描述（不要包含判断词：应该/需要/必须）
            system_state: 触发这条观察的具体系统状态
            severity: low / medium / high / critical
            source: 来源（patrol_loop/worker_report/daemon_loop/manual）
            category: bottleneck / gap / anomaly / improvement / health
            auto_generated: 是否系统自动生成

        Returns:
            Observation 对象
        """
        obs = Observation(
            obs_id=self._next_id(),
            description=description,
            system_state=system_state,
            severity=severity,
            source=source,
            category=category,
            related_tasks=[],
            task_generated=None,
            auto_generated=auto_generated,
            created_at=datetime.now().isoformat(),
        )
        self._append(obs)
        return obs

    def get_recent(self, limit: int = 20) -> List[Observation]:
        """获取最近 N 条 Observation"""
        return list(reversed(self._observations[-limit:]))

    def get_by_category(self, category: str, limit: int = 20) -> List[Observation]:
        """按类别获取 Observation"""
        return [
            o for o in reversed(self._observations)
            if o.category == category
        ][:limit]

    def get_unprocessed(self, limit: int = 50) -> List[Observation]:
        """获取所有未生成 Task 的 Observation"""
        return [
            o for o in reversed(self._observations)
            if o.task_generated is None
        ][:limit]

    def mark_consumed(self, obs_id: str, task_id: str):
        """标记某 Observation 被某 Task 消化"""
        for obs in reversed(self._observations):
            if obs.obs_id == obs_id:
                obs.task_generated = task_id
                break
        # 重新写入文件（只重写最后 200 条）
        try:
            with open(self.observations_file, "w", encoding="utf-8") as f:
                for obs in self._observations[-200:]:
                    f.write(json.dumps(obs.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_stats(self) -> Dict[str, Any]:
        """获取 Observation 统计"""
        total = len(self._observations)
        by_category = {}
        by_severity = {}
        unprocessed = 0
        for obs in self._observations:
            by_category[obs.category] = by_category.get(obs.category, 0) + 1
            by_severity[obs.severity] = by_severity.get(obs.severity, 0) + 1
            if obs.task_generated is None:
                unprocessed += 1
        return {
            "total": total,
            "unprocessed": unprocessed,
            "by_category": by_category,
            "by_severity": by_severity,
            "last_obs_id": self._observations[-1].obs_id if self._observations else None,
        }
