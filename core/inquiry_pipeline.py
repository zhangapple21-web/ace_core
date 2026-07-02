"""
质询管道（Inquiry Pipeline）— Validator ↔ Researcher 多轮交锋

设计原则（笨但稳定）：
    - 不改现有 Validator.validate_task / Researcher.research_task
    - 在 validate_task 返回"需补充研究"时介入
    - 最多 3 轮质询-回答
    - LLM 不可用时降级为规则模式
    - 质询链全部记录到 task 的 validation_note / research_note

血缘：
    - Validator 的"找反例"职责的自然延伸
    - 连续性修正案 mandatory_consistency_check 的具体实现之一（任务级一致性检查）

接入点：
    ace_daemon.py 的 _process_task_lifecycle 中，validate_task 之后
"""

import re
from typing import Dict, Any, List, Optional


class InquiryPipeline:
    """质询管道 — Validator ↔ Researcher 多轮交锋"""

    def __init__(
        self,
        validator=None,
        researcher=None,
        llm_engine=None,
        max_rounds: int = 3,
    ):
        """
        Args:
            validator: ValidatorWithLLM 或 Validator 实例
            researcher: ResearcherWithLLM 或 Researcher 实例
            llm_engine: SurvivalLoopEngine 实例（可选，用于 LLM 质询）
            max_rounds: 最大质询轮数（默认 3）
        """
        self.validator = validator
        self.researcher = researcher
        self.llm_engine = llm_engine
        self.max_rounds = max_rounds

    def run(self, task, validate_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        运行质询管道

        Args:
            task: 待质询的任务（已有 validate_task 结果）
            validate_result: validate_task 的返回值

        Returns:
            {
                "inquiry_rounds": int,          # 实际质询轮数
                "questions": List[str],         # 每轮质询问题
                "answers": List[str],           # 每轮回答
                "final_verdict": str,           # passed / rejected / inconclusive / skipped
                "verdict_reason": str,          # 裁决理由
            }
        """
        # 如果已通过，不需要质询
        if validate_result.get("passed"):
            return {
                "inquiry_rounds": 0,
                "questions": [],
                "answers": [],
                "final_verdict": "skipped",
                "verdict_reason": "验证已通过，无需质询",
            }

        objections = validate_result.get("objections", [])
        if not objections:
            return {
                "inquiry_rounds": 0,
                "questions": [],
                "answers": [],
                "final_verdict": "skipped",
                "verdict_reason": "无异议，无需质询",
            }

        questions: List[str] = []
        answers: List[str] = []
        current_objections = list(objections)

        for round_num in range(1, self.max_rounds + 1):
            # 1. Validator 生成质询问题
            question = self._generate_question(task, current_objections, round_num)
            questions.append(question)
            task.add_validation_note(
                f"[质询R{round_num}] {question}",
                validator="inquiry_pipeline",
            )

            # 2. Researcher 补充证据
            answer, new_evidence = self._research_answer(task, question, round_num)
            answers.append(answer)
            task.add_research_note(
                f"[回答R{round_num}] {answer}",
                researcher="inquiry_pipeline",
            )

            # 如果有新证据，加到 task
            if new_evidence:
                for ev in new_evidence:
                    task.add_evidence(ev, source=f"inquiry_R{round_num}")

            # 3. Validator 再判
            re_judge = self._re_judge(task, question, answer, current_objections, round_num)

            if re_judge["resolved"]:
                # 质询解决
                task.add_validation_note(
                    f"[质询R{round_num}解决] {re_judge['reason']}",
                    validator="inquiry_pipeline",
                )
                return {
                    "inquiry_rounds": round_num,
                    "questions": questions,
                    "answers": answers,
                    "final_verdict": "passed",
                    "verdict_reason": re_judge["reason"],
                }

            # 未解决，更新剩余异议
            current_objections = re_judge.get(
                "remaining_objections", current_objections
            )

        # 3 轮后仍未解决
        task.add_validation_note(
            f"[质询未决] 经{self.max_rounds}轮质询仍有{len(current_objections)}个异议未解决",
            validator="inquiry_pipeline",
        )

        return {
            "inquiry_rounds": self.max_rounds,
            "questions": questions,
            "answers": answers,
            "final_verdict": "inconclusive",
            "verdict_reason": f"经{self.max_rounds}轮质询仍未解决，退回重审",
        }

    def _generate_question(
        self, task, objections: List[str], round_num: int
    ) -> str:
        """Validator 生成质询问题"""
        # LLM 模式：让 LLM 生成更尖锐的质询
        if self._llm_available():
            prompt = self._build_question_prompt(task, objections, round_num)
            result = self._call_llm(prompt, system_prompt="你是一个严谨的验证者，请针对以下异议生成一个具体的、可回答的质询问题。只输出问题本身，不要解释。")
            if result:
                return result[:300]

        # 规则模式：直接用异议作为质询
        top_objection = objections[0] if objections else "证据不足"
        return f"针对异议'{top_objection}'，请补充具体证据或说明原因"

    def _build_question_prompt(self, task, objections: List[str], round_num: int) -> str:
        """构建质询问题生成 prompt"""
        hypothesis = task.hypothesis or task.title
        evidence_summary = ""
        if task.evidence:
            evidence_summary = "\n".join(
                [str(e.get("content", ""))[:100] if isinstance(e, dict) else str(e)[:100]
                 for e in task.evidence[:3]]
            )
        return (
            f"假设：{hypothesis}\n"
            f"现有证据：\n{evidence_summary}\n"
            f"验证异议：\n" + "\n".join(f"  - {o}" for o in objections) + "\n\n"
            f"这是第{round_num}轮质询。请生成一个具体的质询问题，要求研究者补充证据或澄清。"
        )

    def _research_answer(
        self, task, question: str, round_num: int
    ) -> tuple:
        """Researcher 补充证据，返回 (回答文本, 新证据列表)"""
        new_evidence: List[str] = []

        # LLM 模式：让 LLM 补充证据
        if self._llm_available():
            prompt = self._build_answer_prompt(task, question, round_num)
            result = self._call_llm(
                prompt,
                system_prompt="你是一个研究者，请针对验证者的质询补充证据或澄清。用 JSON 输出：{\"answer\": \"回答\", \"evidence\": [\"证据1\", \"证据2\"]}"
            )
            if result:
                answer_text, evs = self._parse_answer_response(result)
                new_evidence.extend(evs)
                return answer_text, new_evidence

        # 规则模式：基于 task 现有证据生成回答
        if task.evidence:
            ev_count = len(task.evidence)
            return f"基于现有{ev_count}条证据，认为异议可解释，但需进一步确认", []
        else:
            return "暂无补充证据，建议扩大研究范围", []

    def _build_answer_prompt(self, task, question: str, round_num: int) -> str:
        """构建回答 prompt"""
        hypothesis = task.hypothesis or task.title
        evidence_summary = ""
        if task.evidence:
            evidence_summary = "\n".join(
                [str(e.get("content", ""))[:150] if isinstance(e, dict) else str(e)[:150]
                 for e in task.evidence[:5]]
            )
        return (
            f"假设：{hypothesis}\n"
            f"现有证据：\n{evidence_summary}\n"
            f"验证者质询：{question}\n\n"
            f"请补充证据或澄清。"
        )

    def _re_judge(
        self,
        task,
        question: str,
        answer: str,
        objections: List[str],
        round_num: int,
    ) -> Dict[str, Any]:
        """Validator 再判"""
        # LLM 模式：让 LLM 判断质询是否解决
        if self._llm_available():
            prompt = (
                f"质询：{question}\n"
                f"回答：{answer}\n"
                f"现有证据数量：{len(task.evidence)}\n\n"
                f"请判断这个质询是否已被回答解决。"
                f"用 JSON 输出：{{\"resolved\": true/false, \"reason\": \"...\", \"remaining_objections\": [\"...\"]}}"
            )
            result = self._call_llm(prompt, system_prompt="你是一个严谨的验证者，请判断质询是否已被解决。")
            if result:
                return self._parse_judge_response(result, objections)

        # 规则模式：基于证据数量判断
        ev_count = len(task.evidence)
        if ev_count >= 3 and round_num >= 2:
            return {
                "resolved": True,
                "reason": f"经{round_num}轮质询，证据数{ev_count}已达阈值",
                "remaining_objections": [],
            }
        if ev_count >= 5:
            return {
                "resolved": True,
                "reason": f"证据数{ev_count}充足，质询解决",
                "remaining_objections": [],
            }

        return {
            "resolved": False,
            "reason": "证据仍不充分",
            "remaining_objections": objections,
        }

    def _llm_available(self) -> bool:
        """检查 LLM 是否可用"""
        if not self.llm_engine:
            return False
        try:
            if hasattr(self.llm_engine, "initialize"):
                return self.llm_engine.initialize()
            return True
        except Exception:
            return False

    def _call_llm(self, prompt: str, system_prompt: str = "") -> Optional[str]:
        """调用 LLM"""
        try:
            from core.miner_pool.integration import _chat, _provider_default_model

            available = []
            if hasattr(self.llm_engine, "available_providers"):
                available = list(self.llm_engine.available_providers)

            for provider_name in available[:2]:  # 最多试 2 个 provider
                result = _chat(
                    self.llm_engine,
                    task_type="inquiry",
                    messages=[{"role": "user", "content": prompt}],
                    system_prompt=system_prompt,
                    model=_provider_default_model(provider_name),
                )
                if result.get("success") and result.get("content"):
                    return result["content"]
        except Exception:
            pass
        return None

    def _parse_answer_response(self, content: str) -> tuple:
        """解析回答响应"""
        import json
        try:
            json_match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                answer = parsed.get("answer", content[:200])
                evidence = parsed.get("evidence", [])
                if isinstance(evidence, list):
                    return answer, [str(e) for e in evidence if e]
                return answer, []
        except Exception:
            pass
        return content[:200], []

    def _parse_judge_response(self, content: str, default_objections: List[str]) -> Dict[str, Any]:
        """解析判断响应"""
        import json
        try:
            json_match = re.search(r'\{[^{}]+\}', content, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                return {
                    "resolved": parsed.get("resolved", False),
                    "reason": parsed.get("reason", ""),
                    "remaining_objections": parsed.get("remaining_objections", default_objections),
                }
        except Exception:
            pass
        return {
            "resolved": False,
            "reason": "LLM 响应解析失败",
            "remaining_objections": default_objections,
        }
