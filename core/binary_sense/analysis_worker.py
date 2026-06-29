"""
分析 Worker 基类 — 从 ReVa skills 考古提取的工作流模式

核心骨架：
- binary-triage（广度优先：快速扫描，标记可疑点）
- deep-analysis（深度优先：沿着线索深入，增量改进数据库）
- ctf-rev / ctf-pwn / ctf-crypto（专项任务，有固定模式）

每个 skill 的核心不是代码，是**工作流协议**：
1. 明确的输入输出
2. 标准化的步骤
3. 内置的质量检查（on-task check）
4. 增量改进机制（每次迭代都让数据库更清晰）
"""

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..task_roles import BaseWorker


class AnalysisWorker(BaseWorker):
    """
    分析工作者基类

    从 ReVa skill 体系考古提取的核心设计：
    1. READ → UNDERSTAND → IMPROVE → VERIFY → FOLLOW THREADS
    2. 每 3-5 步做一次 on-task check，防止跑偏
    3. 所有结论必须有证据支撑
    4. 增量改进数据库，而不是一次性输出
    """

    def __init__(self, sensor):
        self.sensor = sensor
        self._iteration_count = 0
        self._max_iterations = 20
        self._findings: List[Dict[str, Any]] = []

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """执行任务"""
        session_id = task.get("session_id")
        if not session_id:
            target = task.get("target_path", "")
            session_id = self.sensor.create_analysis_session(target, self.worker_type)

        self.sensor.update_session(session_id, status="running", phase=self.phase_number)

        try:
            result = self._run_analysis(session_id, task)
            self.sensor.update_session(session_id, status="completed")
            return {
                "status": "success",
                "outputs": {
                    "session_id": session_id,
                    "findings": len(self._findings),
                    "iterations": self._iteration_count,
                    **result,
                },
            }
        except Exception as e:
            self.sensor.update_session(session_id, status="failed")
            self.sensor.log_error(f"{self.worker_type} failed", e)
            return {
                "status": "failed",
                "outputs": {"session_id": session_id, "error": str(e)},
                "failure_reason": str(e),
            }

    @abstractmethod
    def _run_analysis(
        self, session_id: str, task: Dict[str, Any]
    ) -> Dict[str, Any]:
        """具体分析逻辑，子类实现"""
        pass

    @property
    @abstractmethod
    def worker_type(self) -> str:
        """工作者类型"""
        pass

    @property
    @abstractmethod
    def phase_number(self) -> int:
        """阶段编号"""
        pass

    def _on_task_check(self) -> bool:
        """
        任务检查点 — 从 ReVa deep-analysis skill 考古提取

        每 3-5 次迭代检查一次：
        - 是否还在回答原始问题？
        - 这条线索是产出的还是干扰？
        - 是否有足够证据可以下结论？
        - 是否应该先返回部分结果？
        """
        return True

    def _add_finding(
        self,
        session_id: str,
        finding_type: str,
        description: str,
        evidence: Optional[List[Dict[str, Any]]] = None,
        confidence: float = 0.5,
    ) -> None:
        """添加发现"""
        self.sensor.add_finding(session_id, finding_type, description, evidence, confidence)
        self._findings.append({
            "type": finding_type,
            "description": description,
            "confidence": confidence,
        })
