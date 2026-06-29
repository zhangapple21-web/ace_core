"""
深度分析工作者（DeepAnalysis Worker）— 从 ReVa deep-analysis skill 考古提取

核心工作流：The Investigation Loop（调查循环）

1. READ - 收集当前上下文（1-2个工具调用）
2. UNDERSTAND - 分析看到的内容
3. IMPROVE - 做小的数据库改进（1-3个工具调用）
4. VERIFY - 重读确认改进效果（1个工具调用）
5. FOLLOW THREADS - 追踪证据（1-2个工具调用）
6. TRACK PROGRESS - 记录发现（1个工具调用）
7. ON-TASK CHECK - 每3-5步检查是否跑偏

与 ACE 现有系统的映射：
- READ/FOLLOW THREADS → Researcher（搜索和发现）
- UNDERSTAND → HypothesisTree（理解和推理）
- IMPROVE → 增量写入词库/记忆
- VERIFY → Validator（验证和确认）
- ON-TASK CHECK → Constraint（约束检查）
"""

from typing import Any, Dict, List, Optional
import json
from pathlib import Path

from .analysis_worker import AnalysisWorker


class DeepAnalysisWorker(AnalysisWorker):
    """
    深度分析工作者 — 迭代式深度调查

    核心设计原则（从 ReVa deep-analysis skill 考古提取）：

    1. **深度优先**：沿着一条线索挖到底，再分支
       （区别于 triage 的广度优先）

    2. **增量改进**：每次迭代都让数据库更清晰一点
       - 重命名变量：var_1 → encryption_key
       - 修正类型：undefined4 → uint32_t
       - 添加注释：记录关键发现
       而不是一次性输出所有结论

    3. **证据链**：每个结论都必须有证据支撑
       - 地址证据：函数地址、数据地址
       - 字符串证据：引用的字符串
       - 交叉引用：谁调用它、它调用谁
       - 数据流证据：变量传递路径

    4. **任务自检**：每 3-5 次迭代检查一次
       - 还在回答原始问题吗？
       - 这条线索是产出的还是干扰？
       - 有足够证据下结论了吗？
       - 是否应该先返回部分结果？

    5. **多线程发现**：每次分析不仅回答问题，
       还产生新的调查线索（investigation threads）
    """

    @property
    def worker_type(self) -> str:
        return "deep_analysis"

    @property
    def phase_number(self) -> int:
        return 4

    def _run_analysis(
        self, session_id: str, task: Dict[str, Any]
    ) -> Dict[str, Any]:
        target = task.get("target_path", "")
        focus_point = task.get("focus_point", "")
        question = task.get("question", "analyze this binary")

        investigation_threads = []
        iterations = 0
        max_iterations = min(task.get("max_iterations", 10), self._max_iterations)

        context = self._gather_context(target, focus_point)

        while iterations < max_iterations:
            iterations += 1
            self._iteration_count = iterations

            understanding = self._analyze_context(context, question)
            improvements = self._propose_improvements(understanding)
            self._apply_improvements(session_id, improvements)

            new_threads = self._follow_threads(understanding, context)
            investigation_threads.extend(new_threads)

            if iterations % 3 == 0:
                if not self._on_task_check():
                    break

            if self._has_sufficient_evidence(understanding):
                break

            if investigation_threads:
                next_thread = investigation_threads.pop(0)
                context = self._gather_context(target, next_thread.get("focus", ""))

        conclusion = self._synthesize_conclusion(
            session_id, question, iterations
        )

        return {
            "iterations": iterations,
            "conclusion": conclusion,
            "investigation_threads": len(investigation_threads),
            "threads": investigation_threads[:5],
        }

    def _gather_context(self, target: str, focus_point: str) -> Dict[str, Any]:
        """
        步骤 1: READ - 收集当前上下文

        对应 ReVa:
        - get-decompilation（获取反编译）
        - find-cross-references（查找交叉引用）
        - get-data / read-memory（读取数据）

        设计原则：
        - 每次只读少量上下文（20-50行反编译）
        - 包含 incoming references 和 reference context
        - 避免一次性加载过多数据导致上下文爆炸
        """
        return {
            "target": target,
            "focus": focus_point,
            "artifacts_found": 0,
            "strings_found": [],
            "patterns_found": [],
        }

    def _analyze_context(
        self, context: Dict[str, Any], question: str
    ) -> Dict[str, Any]:
        """
        步骤 2: UNDERSTAND - 分析看到的内容

        关键问题：
        - 什么不清晰？（变量名、类型、逻辑流程）
        - 在执行什么操作？
        - 引用了什么 API/字符串/数据？
        - 我在做什么假设？
        """
        return {
            "question": question,
            "clarity_score": 0.3,
            "unclear_points": [],
            "operations_identified": [],
            "assumptions": [],
        }

    def _propose_improvements(
        self, understanding: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        步骤 3: IMPROVE - 提出小的数据库改进

        改进优先级：
        1. 重命名变量（最大的清晰度提升）
        2. 修正数据类型
        3. 设置函数原型
        4. 应用数据类型（如 S-box）
        5. 添加反编译注释
        6. 设置书签

        对应 ACE：增量改进词库/记忆，而不是一次性重写
        """
        improvements = []
        return improvements

    def _apply_improvements(
        self, session_id: str, improvements: List[Dict[str, Any]]
    ) -> None:
        """应用改进（ACE 中对应写入词库/经验）"""
        for imp in improvements:
            self._add_finding(
                session_id,
                "improvement",
                imp.get("description", ""),
                confidence=imp.get("confidence", 0.6),
            )

    def _follow_threads(
        self, understanding: Dict[str, Any], context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        步骤 5: FOLLOW THREADS - 追踪证据线索

        追踪方向：
        - 沿着交叉引用追踪（被调用/调用函数）
        - 追踪数据流（通过变量传递）
        - 检查字符串/常量的使用
        - 搜索相似模式

        对应 ACE：
        - Researcher 扩展搜索范围
        - HypothesisTree 生成新的候选假设
        """
        threads = []
        return threads

    def _on_task_check(self) -> bool:
        """
        步骤 7: ON-TASK CHECK - 任务自检

        从 ReVa 考古提取的关键质量控制机制：
        每 3-5 次迭代强制检查一次，防止分析跑偏

        检查清单：
        1. "我还在回答原始问题吗？"
        2. "这条线索是产出的还是干扰？"
        3. "我有足够的证据下结论了吗？"
        4. "我应该现在返回部分结果吗？"
        """
        return super()._on_task_check()

    def _has_sufficient_evidence(
        self, understanding: Dict[str, Any]
    ) -> bool:
        """判断是否有足够证据下结论"""
        clarity = understanding.get("clarity_score", 0)
        return clarity >= 0.8

    def _synthesize_conclusion(
        self, session_id: str, question: str, iterations: int
    ) -> Dict[str, Any]:
        """
        综合结论

        ReVa 风格的输出格式：
        - 直接回答问题
        - 附带证据（地址、字符串、交叉引用）
        - 列出未回答的问题（新的调查线索）
        - 记录置信度

        ACE 的额外价值：
        - 把发现的模式沉淀到词库
        - 把分析过程记录为经验
        - 建立与已有知识的关联
        """
        return {
            "question": question,
            "answer": "",
            "evidence": [],
            "confidence": 0.5,
            "unanswered_questions": [],
            "iterations": iterations,
        }
