"""
LLM 角色增强层 — 用 SurvivalLoopEngine 给 Researcher / Validator / Archivist 插上算力翅膀

设计原则：
  1. 不侵入原有角色代码
  2. 通过组合方式增强
  3. 结构资产（角色分工、协议）不变，模型只是执行节点
  4. 引擎是 SurvivalLoopEngine（极简单循环），不是 MinerPool

使用方式：
  from core.miner_pool.integration import (
      ResearcherWithLLM,
      ValidatorWithLLM,
      ArchivistWithLLM,
  )

  researcher = ResearcherWithLLM(
      base_researcher=original_researcher,
      llm_engine=survival_loop_engine,
  )

  candidates = researcher.generate_candidates(task, use_llm=True)
"""

import json
import re
from typing import Dict, List, Any, Optional

try:
    from core.survival_loop import SurvivalLoopEngine
    _HAS_ENGINE = True
except ImportError:
    _HAS_ENGINE = False

from .task_profiles import get_task_profile


def _chat(engine, task_type: str, messages: List[Dict[str, str]],
          system_prompt: str = "", **kwargs) -> Dict[str, Any]:
    """
    统一的 chat 接口。

    优先用 SurvivalLoopEngine（笨但活得久），
    兼容 MinerPool（旧代码保留血缘）。
    """
    try:
        if _HAS_ENGINE and isinstance(engine, SurvivalLoopEngine):
            profile = get_task_profile(task_type)
            temperature = kwargs.pop("temperature", profile.get("temperature", 0.7))
            max_tokens = kwargs.pop("max_tokens", profile.get("max_tokens", 1024))
            timeout = kwargs.pop("timeout", profile.get("timeout", 60))
            return engine.chat(
                messages=messages,
                system_prompt=system_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout,
                **kwargs,
            )
        elif hasattr(engine, 'chat'):
            return engine.chat(
                task_type=task_type,
                messages=messages,
                system_prompt=system_prompt,
                **kwargs,
            )
    except Exception:
        pass
    return {
        "success": False,
        "content": "",
        "model": "",
        "provider": "",
        "usage": {},
        "latency_ms": 0,
        "error": "engine unavailable",
        "tried": [],
    }


def _provider_default_model(provider_name: str) -> str:
    """provider 的默认模型名"""
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


class ResearcherWithLLM:
    """
    增强版 Researcher — 有 LLM 加持的研究员

    原有能力不变，新增：
      - generate_candidates 可选 use_llm=True 用模型补充候选
      - deepen_research: 用模型深化研究方向
    """

    def __init__(self, base_researcher=None, llm_engine=None, miner_pool=None):
        self.base = base_researcher
        self.engine = llm_engine or miner_pool
        self._ready = False

    def _ensure_engine(self) -> bool:
        if self._ready:
            return True
        if not self.engine:
            return False
        try:
            if hasattr(self.engine, 'initialize'):
                self._ready = self.engine.initialize()
            else:
                self._ready = True
        except Exception:
            self._ready = False
        return self._ready

    def generate_candidates(
        self,
        task=None,
        max_candidates: int = 3,
        use_miner: bool = False,
        use_llm: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        生成候选假设

        use_llm=True 时：
          1. 先用原有逻辑生成基础候选
          2. 再用模型补充创造性候选
          3. 合并后返回
        """
        base_candidates = []
        if self.base and task:
            try:
                base_candidates = self.base.generate_candidates(task, max_candidates)
            except Exception:
                base_candidates = []

        use_model = use_llm or use_miner
        if not use_model or not task:
            return base_candidates

        if not self._ensure_engine():
            return base_candidates

        try:
            title = getattr(task, 'title', '')
            hypothesis = getattr(task, 'hypothesis', '')
            llm_candidates = self._gen_with_llm(
                task_title=title,
                task_hypothesis=hypothesis,
                max_candidates=max_candidates,
            )
            return base_candidates + llm_candidates
        except Exception:
            return base_candidates

    def _gen_with_llm(
        self,
        task_title: str,
        task_hypothesis: str = "",
        max_candidates: int = 3,
    ) -> List[Dict[str, Any]]:
        system_prompt = (
            "你是一个擅长提出假设的研究员。给定一个研究主题，"
            "请从不同角度提出多个候选假设。每个假设要有明确的验证方向。"
            "用 JSON 数组输出，每个元素包含："
            "{\"hypothesis\": \"假设内容\", \"keywords\": [\"关键词1\", \"关键词2\"], "
            "\"confidence\": 0-1, \"reasoning\": \"推导过程\", \"type\": \"creative|analogy|first_principles\"}"
        )
        user_msg = f"研究主题：{task_title}"
        if task_hypothesis:
            user_msg += f"\n现有假设：{task_hypothesis}"
        user_msg += f"\n\n请提出 {max_candidates} 个不同角度的候选假设。"

        result = _chat(
            self.engine,
            task_type="hypothesis_generation",
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=system_prompt,
        )

        if not result.get("success"):
            return []

        candidates = []
        try:
            content = result["content"]
            array_match = re.search(r'\[[^\]]+\]', content, re.DOTALL)
            if array_match:
                parsed = json.loads(array_match.group())
                for i, c in enumerate(parsed):
                    candidates.append({
                        "candidate_id": f"M_{i}",
                        "hypothesis": c.get("hypothesis", ""),
                        "keywords": c.get("keywords", []),
                        "confidence": c.get("confidence", 0.5),
                        "reasoning": c.get("reasoning", "模型生成"),
                        "type": c.get("type", "llm_generated"),
                        "source_model": result.get("model", ""),
                        "source_provider": result.get("provider", ""),
                    })
        except Exception:
            pass
        return candidates[:max_candidates]

    def __getattr__(self, name):
        if self.base and hasattr(self.base, name):
            return getattr(self.base, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class ValidatorWithLLM:
    """
    增强版 Validator — 有 LLM 加持的验证者

    原有能力不变，新增：
      - cross_validate: 多模型交叉验证
      - llm_assisted_assessment: 模型辅助评估
    """

    def __init__(self, base_validator=None, llm_engine=None, miner_pool=None):
        self.base = base_validator
        self.engine = llm_engine or miner_pool
        self._ready = False

    def _ensure_engine(self) -> bool:
        if self._ready:
            return True
        if not self.engine:
            return False
        try:
            if hasattr(self.engine, 'initialize'):
                self._ready = self.engine.initialize()
            else:
                self._ready = True
        except Exception:
            self._ready = False
        return self._ready

    def cross_validate(
        self,
        hypothesis: str,
        context: str = "",
        model_count: int = 3,
    ) -> Dict[str, Any]:
        """
        多模型交叉验证

        让多个不同厂商的模型同时质疑一个假设，看是否能达成共识。
        注意：在 SurvivalLoopEngine 下，是按顺序尝试的，不是真并行。
        """
        if not self._ensure_engine():
            return {
                "hypothesis": hypothesis,
                "consensus": "unknown",
                "error": "engine not available",
                "validations": [],
                "agree_count": 0,
                "disagree_count": 0,
                "total_models": 0,
            }

        if hasattr(self.engine, 'cross_validate'):
            try:
                return self.engine.cross_validate(
                    hypothesis=hypothesis,
                    context=context,
                    model_count=model_count,
                )
            except Exception:
                pass

        return self._cv_with_engine(hypothesis, context, model_count)

    def _cv_with_engine(
        self,
        hypothesis: str,
        context: str,
        model_count: int,
    ) -> Dict[str, Any]:
        system_prompt = (
            "你是一个严谨的验证者。你的任务是批判性审视给定的假设，"
            "寻找反例、逻辑漏洞、证据不足的地方。"
            "不要轻易同意，要保持怀疑态度。"
            "用 JSON 输出：{\"agree\": true/false, \"reason\": \"...\", \"confidence\": 0-1}"
        )
        user_msg = f"假设：{hypothesis}\n\n背景信息：{context}\n\n请验证这个假设是否成立。"

        validations = []
        agree_count = 0
        disagree_count = 0
        success_count = 0

        available = []
        if hasattr(self.engine, 'available_providers'):
            available = list(self.engine.available_providers)

        for provider_name in available:
            if success_count >= model_count:
                break

            result = _chat(
                self.engine,
                task_type="cross_validation",
                messages=[{"role": "user", "content": user_msg}],
                system_prompt=system_prompt,
                model=_provider_default_model(provider_name),
            )

            validation = {
                "model": result.get("model", ""),
                "provider": result.get("provider", provider_name),
                "success": result.get("success", False),
                "agree": None,
                "reason": "",
                "confidence": 0,
            }

            if result.get("success") and result.get("content"):
                success_count += 1
                try:
                    content = result["content"]
                    json_match = re.search(r'\{[^{}]+\}', content)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        validation["agree"] = parsed.get("agree")
                        validation["reason"] = parsed.get("reason", "")
                        validation["confidence"] = parsed.get("confidence", 0)
                    else:
                        text_lower = content.lower()
                        validation["agree"] = "同意" in content or "agree" in text_lower
                        validation["reason"] = content[:500]
                except Exception:
                    validation["reason"] = result["content"][:500]

                if validation["agree"] is True:
                    agree_count += 1
                elif validation["agree"] is False:
                    disagree_count += 1

            validations.append(validation)

        consensus = "mixed"
        if agree_count > 0 and disagree_count == 0:
            consensus = "agree"
        elif disagree_count > 0 and agree_count == 0:
            consensus = "disagree"

        return {
            "hypothesis": hypothesis,
            "validations": validations,
            "consensus": consensus,
            "agree_count": agree_count,
            "disagree_count": disagree_count,
            "total_models": len(validations),
        }

    def assess_prospect(
        self,
        candidate: Dict = None,
        use_miner: bool = False,
        use_llm: bool = False,
    ) -> Dict[str, Any]:
        base_result = {}
        if self.base and candidate:
            try:
                if hasattr(self.base, 'assess_prospect'):
                    base_result = self.base.assess_prospect(candidate)
            except Exception:
                base_result = {}

        use_model = use_llm or use_miner
        if not use_model or not candidate:
            return base_result

        if not self._ensure_engine():
            return base_result

        try:
            hypothesis = candidate.get("hypothesis", "")
            reasoning = candidate.get("reasoning", "")

            system_prompt = (
                "你是一个严谨的评估者。请评估这个研究假设的前景价值。"
                "评估维度：新颖性、可验证性、潜在影响、证据强度。"
                "输出 JSON：{\"prospect_score\": 0-100, \"risk_level\": \"low|medium|high\", "
                "\"key_strengths\": [], \"key_risks\": [], \"verdict\": \"pursue|hold|drop\"}"
            )
            user_msg = f"假设：{hypothesis}\n推导过程：{reasoning}\n\n请评估前景。"

            result = _chat(
                self.engine,
                task_type="cross_validation",
                messages=[{"role": "user", "content": user_msg}],
                system_prompt=system_prompt,
            )

            if result.get("success"):
                try:
                    json_match = re.search(r'\{[^{}]+\}', result["content"])
                    if json_match:
                        assessment = json.loads(json_match.group())
                        base_result["llm_assessment"] = assessment
                        base_result["llm_model"] = result.get("model", "")
                        base_result["llm_provider"] = result.get("provider", "")
                except Exception:
                    pass
        except Exception:
            pass

        return base_result

    def __getattr__(self, name):
        if self.base and hasattr(self.base, name):
            return getattr(self.base, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class ArchivistWithLLM:
    """
    增强版 Archivist — 有 LLM 加持的归档者

    原有能力不变，新增：
      - llm_summarize: 模型辅助总结
      - llm_extract_knowledge: 从文本中提取知识
    """

    def __init__(self, base_archivist=None, llm_engine=None, miner_pool=None):
        self.base = base_archivist
        self.engine = llm_engine or miner_pool
        self._ready = False

    def _ensure_engine(self) -> bool:
        if self._ready:
            return True
        if not self.engine:
            return False
        try:
            if hasattr(self.engine, 'initialize'):
                self._ready = self.engine.initialize()
            else:
                self._ready = True
        except Exception:
            self._ready = False
        return self._ready

    def summarize(
        self,
        content: str = "",
        content_list: List[str] = None,
        use_miner: bool = False,
        use_llm: bool = False,
        max_length: int = 500,
    ) -> Dict[str, Any]:
        base_result = {}
        if self.base and hasattr(self.base, 'summarize'):
            try:
                if content_list:
                    base_result = self.base.summarize(content, content_list)
                else:
                    base_result = self.base.summarize(content)
            except Exception:
                base_result = {}

        use_model = use_llm or use_miner
        if not use_model or (not content and not content_list):
            return base_result

        if not self._ensure_engine():
            return base_result

        try:
            if content_list:
                full = "\n\n---\n\n".join(content_list)
            else:
                full = content

            system_prompt = (
                "你是一个擅长提炼总结的档案管理员。请从以下内容中提取核心要点，"
                "生成结构化的总结。"
                "输出 JSON：{\"summary\": \"总结文本\", \"key_points\": [\"要点1\", \"要点2\"], "
                "\"categories\": {\"类别1\": [\"子项1\", \"子项2\"]}, \"action_items\": []}"
            )
            user_msg = f"请总结以下内容（不超过{max_length}字）：\n\n{full[:15000]}"

            result = _chat(
                self.engine,
                task_type="synthesis",
                messages=[{"role": "user", "content": user_msg}],
                system_prompt=system_prompt,
            )

            if result.get("success"):
                try:
                    json_match = re.search(r'\{[^{}]+\}', result["content"])
                    if json_match:
                        summary = json.loads(json_match.group())
                        base_result["llm_summary"] = summary
                        base_result["llm_model"] = result.get("model", "")
                        base_result["llm_provider"] = result.get("provider", "")
                except Exception:
                    base_result["llm_summary_raw"] = result.get("content", "")
        except Exception:
            pass

        return base_result

    def extract_knowledge(
        self,
        text: str,
        knowledge_type: str = "general",
    ) -> Dict[str, Any]:
        if not self._ensure_engine():
            return {"success": False, "error": "engine not available"}

        prompts = {
            "general": "从文本中提取关键知识，输出 JSON：{\"entities\": [], \"relations\": [], \"key_insights\": []}",
            "constraints": "从文本中提取约束/规则，输出 JSON：{\"constraints\": [{\"name\": \"\", \"description\": \"\", \"severity\": \"high|medium|low\"}]}",
            "experience": "从文本中提取经验教训，输出 JSON：{\"lessons\": [{\"title\": \"\", \"context\": \"\", \"lesson\": \"\"}]}",
        }
        system_prompt = prompts.get(knowledge_type, prompts["general"])

        result = _chat(
            self.engine,
            task_type="extraction",
            messages=[{"role": "user", "content": f"从以下文本中提取知识：\n\n{text[:10000]}"}],
            system_prompt=system_prompt,
        )

        if not result.get("success"):
            return {"success": False, "error": result.get("error", "unknown")}

        try:
            json_match = re.search(r'\{[^{}]+\}', result["content"])
            if json_match:
                return {
                    "success": True,
                    "extracted": json.loads(json_match.group()),
                    "model": result.get("model", ""),
                    "provider": result.get("provider", ""),
                }
        except Exception:
            pass

        return {
            "success": True,
            "extracted_raw": result.get("content", ""),
            "model": result.get("model", ""),
            "provider": result.get("provider", ""),
        }

    def __getattr__(self, name):
        if self.base and hasattr(self.base, name):
            return getattr(self.base, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


ResearcherWithMinerPool = ResearcherWithLLM
ValidatorWithMinerPool = ValidatorWithLLM
ArchivistWithMinerPool = ArchivistWithLLM


def create_miner_pool(coze_assets_path: Optional[str] = None):
    """
    兼容旧接口 — 返回 SurvivalLoopEngine 而不是 MinerPool
    """
    if _HAS_ENGINE:
        engine = SurvivalLoopEngine(coze_assets_path=coze_assets_path)
        engine.initialize()
        return engine
    return None


def enhance_roles(
    researcher=None,
    validator=None,
    archivist=None,
    coze_assets_path: Optional[str] = None,
    llm_engine=None,
    miner_pool=None,
) -> Dict[str, Any]:
    """
    一次性增强所有角色

    返回增强后的角色字典。
    """
    engine = llm_engine or miner_pool
    if not engine:
        engine = create_miner_pool(coze_assets_path)

    enhanced = {}
    if researcher:
        enhanced["researcher"] = ResearcherWithLLM(
            base_researcher=researcher,
            llm_engine=engine,
        )
    if validator:
        enhanced["validator"] = ValidatorWithLLM(
            base_validator=validator,
            llm_engine=engine,
        )
    if archivist:
        enhanced["archivist"] = ArchivistWithLLM(
            base_archivist=archivist,
            llm_engine=engine,
        )

    enhanced["llm_engine"] = engine
    enhanced["miner_pool"] = engine
    from .task_profiles import list_task_types
    enhanced["task_types"] = list_task_types()

    return enhanced
