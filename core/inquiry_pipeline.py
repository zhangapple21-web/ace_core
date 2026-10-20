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
        unverified_candidates: List[str] = []
        # Repeating an objection is not asking twice.  Measured across all 67
        # non-convergent blocked tasks (2026-10-11): every one of them stored a
        # 12-16 item objection list holding only 2-4 distinct texts, and every
        # round interrogated ``objections[0]``.  The pipeline spent its whole
        # budget re-asking one question, got the same answer back, and then
        # reported three rounds as if they were three independent findings.
        # Rounds are now capped by the number of DISTINCT objections - still a
        # hard bound, but one the pipeline cannot fill by talking to itself.
        current_objections = self._distinct_objections(objections)
        duplicate_objections_dropped = len(list(objections)) - len(current_objections)
        # In rule mode the researcher answer is canned and never adds evidence,
        # so a repeated question provably cannot change the verdict. With an LLM
        # a repeat can still draw new evidence, so the retry is kept there.
        repeat_can_inform = self._llm_available()
        asked_objections: set[str] = set()

        rounds_run = 0
        for round_num in range(1, self.max_rounds + 1):
            # Stop only when there is genuinely nothing new left to ask about.
            if len(asked_objections) >= len(current_objections) and not repeat_can_inform:
                task.add_validation_note(
                    f"[质询无新异议] 没有新的不同异议可质询，"
                    f"规则模式下重复提问不会改变裁决",
                    validator="inquiry_pipeline",
                )
                break
            # 1. Validator 生成质询问题
            question = self._generate_question(task, current_objections, round_num, asked_objections)
            asked_objections.add(self._objection_for_round(current_objections, asked_objections))
            rounds_run += 1
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

            # 模型若声称有新证据，只登记为待核验候选
            if new_evidence:
                for ev in new_evidence:
                    # 模型声称的证据不是独立来源，绝不能直接进入
                    # Task.evidence，否则下一轮 Validator 会把模型自述
                    # 当作现实证据。只保存在待核验区，交给下一次
                    # Researcher 重新取源；这条管道本身没有事实写权。
                    candidate = str(ev).strip()
                    if candidate and candidate not in unverified_candidates:
                        unverified_candidates.append(candidate[:500])
                        task.add_research_note(
                            f"[待核验模型候选R{round_num}] {candidate[:500]}",
                            researcher="inquiry_pipeline",
                        )

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
                    "unverified_candidates": unverified_candidates,
                    "final_verdict": "passed",
                    "verdict_reason": re_judge["reason"],
                }

            # 未解决，更新剩余异议。去重后异议可能变短；没有新异议可质询时
            # 立即收手，而不是把同一句异议再问一遍充当进展。
            current_objections = self._distinct_objections(
                re_judge.get("remaining_objections", current_objections)
            )

        # 轮次用尽仍未解决
        task.add_validation_note(
            f"[质询未决] 经{rounds_run}轮质询仍有{len(current_objections)}个异议未解决",
            validator="inquiry_pipeline",
        )

        return {
            "inquiry_rounds": rounds_run,
            "questions": questions,
            "answers": answers,
            "unverified_candidates": unverified_candidates,
            "distinct_objections": len(self._distinct_objections(objections)),
            "duplicate_objections_dropped": duplicate_objections_dropped,
            "final_verdict": "inconclusive",
            "verdict_reason": f"经{rounds_run}轮质询仍未解决，退回重审",
        }

    @staticmethod
    def _objection_for_round(objections: List[str], asked: set) -> str:
        """The next distinct objection not yet asked, else the first one."""
        for objection in objections:
            if objection not in asked:
                return objection
        return objections[0] if objections else "证据不足"

    def _generate_question(
        self, task, objections: List[str], round_num: int, asked: Optional[set] = None
    ) -> str:
        """Validator 生成质询问题"""
        # LLM 模式：让 LLM 生成更尖锐的质询
        if self._llm_available():
            prompt = self._build_question_prompt(task, objections, round_num)
            result = self._call_llm(prompt, system_prompt="你是一个严谨的验证者，请针对以下异议生成一个具体的、可回答的质询问题。只输出问题本身，不要解释。")
            if result:
                return result[:300]

        # 规则模式：直接用异议作为质询。第 N 轮质询第 N 条**不同**异议；
        # 旧代码永远取 objections[0]，于是三轮问的是同一句话。
        top_objection = self._objection_for_round(objections, asked or set())
        return f"针对异议'{top_objection}'，请补充具体证据或说明原因"

    @staticmethod
    def _distinct_objections(objections: Any) -> List[str]:
        """Order-preserving dedup of objection text.

        The validator re-deposits its standard objections on every review pass,
        so the list ACE hands to this pipeline has been observed holding 16
        entries with 4 distinct texts.  Order is preserved because the first
        objection is the most load-bearing one.
        """
        seen: set[str] = set()
        distinct: List[str] = []
        for item in objections or []:
            text = str(item).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            distinct.append(text)
        return distinct

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

        # 规则模式：基于证据数量判断。注意没有 round_num >= 2 这个附加条件。
        # 它存在时，第 2 轮是第 1 轮的逐字复制：_research_answer 在规则模式下
        # 返回固定文本且不新增任何证据，task.evidence 不变，于是第 2 轮唯一
        # 变化的是计数器本身。要求"必须先被问满两轮"只是把"证据够了"改成
        # "证据够了并且我们多问了一次"。研究者此刻已经回答过，条件已满足。
        ev_count = len(task.evidence)
        if ev_count >= 3:
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
