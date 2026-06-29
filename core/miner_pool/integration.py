"""
矿工池集成适配层 — MinerPool Integration Adapter

这不是修改原有角色，而是给它们插上算力翅膀。

设计原则：
  1. 不侵入原有 Researcher / Validator / Archivist 代码
  2. 通过组合方式增强它们的能力
  3. 原有逻辑不变，只是增加「模型辅助」能力
  4. 结构资产（角色分工、协议）不变，模型只是执行节点

使用方式：
  from ace_runtime.core.miner_pool.integration import (
      ResearcherWithMinerPool,
      ValidatorWithMinerPool,
      ArchivistWithMinerPool,
  )

  # 增强版 Researcher
  researcher = ResearcherWithMinerPool(
      base_researcher=original_researcher,
      miner_pool=miner_pool,
  )

  # 调用方式和原来一样，但会获得模型辅助
  candidates = researcher.generate_candidates(task, use_miner=True)
"""

from typing import Dict, List, Any, Optional
from dataclasses import dataclass

from .miner_pool import MinerPool
from .task_profiles import list_task_types


class ResearcherWithMinerPool:
    """
    增强版 Researcher — 有矿工池加持的研究员

    原有能力不变，新增：
      - generate_candidates_with_miner: 用模型生成候选假设
      - deepen_research: 用模型深化研究方向
    """

    def __init__(self, base_researcher=None, miner_pool: Optional[MinerPool] = None):
        self.base = base_researcher
        self.miner_pool = miner_pool
        self._miner_ready = False

    def _ensure_miner(self) -> bool:
        """确保矿工池就绪"""
        if self._miner_ready:
            return True
        if not self.miner_pool:
            return False
        self._miner_ready = self.miner_pool.initialize()
        return self._miner_ready

    def generate_candidates(
        self,
        task=None,
        max_candidates: int = 3,
        use_miner: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        生成候选假设

        use_miner=True 时：
          1. 先用原有逻辑生成基础候选
          2. 再用模型补充创造性候选
          3. 合并后返回
        """
        base_candidates = []
        if self.base and task:
            base_candidates = self.base.generate_candidates(task, max_candidates)

        if not use_miner or not task:
            return base_candidates

        if not self._ensure_miner():
            return base_candidates

        try:
            miner_candidates = self._generate_candidates_with_miner(
                task_title=task.title,
                task_hypothesis=task.hypothesis,
                max_candidates=max_candidates,
            )
            # 合并，矿工生成的放后面
            return base_candidates + miner_candidates
        except Exception:
            return base_candidates

    def _generate_candidates_with_miner(
        self,
        task_title: str,
        task_hypothesis: str = "",
        max_candidates: int = 3,
    ) -> List[Dict[str, Any]]:
        """用模型生成候选假设"""
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

        result = self.miner_pool.chat(
            task_type="hypothesis_generation",
            messages=[{"role": "user", "content": user_msg}],
            system_prompt=system_prompt,
        )

        if not result.get("success"):
            return []

        candidates = []
        try:
            import json
            import re
            content = result["content"]
            # 尝试提取 JSON 数组
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
                        "type": c.get("type", "miner_generated"),
                        "source_model": result.get("model", ""),
                        "source_provider": result.get("provider", ""),
                    })
        except Exception:
            pass

        return candidates[:max_candidates]

    def __getattr__(self, name):
        """委托给 base_researcher 的其他方法"""
        if self.base and hasattr(self.base, name):
            return getattr(self.base, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class ValidatorWithMinerPool:
    """
    增强版 Validator — 有矿工池加持的验证者

    原有能力不变，新增：
      - cross_validate: 多模型交叉验证
      - miner_assisted_assessment: 模型辅助评估
    """

    def __init__(self, base_validator=None, miner_pool: Optional[MinerPool] = None):
        self.base = base_validator
        self.miner_pool = miner_pool
        self._miner_ready = False

    def _ensure_miner(self) -> bool:
        if self._miner_ready:
            return True
        if not self.miner_pool:
            return False
        self._miner_ready = self.miner_pool.initialize()
        return self._miner_ready

    def cross_validate(
        self,
        hypothesis: str,
        context: str = "",
        model_count: int = 3,
    ) -> Dict[str, Any]:
        """
        多模型交叉验证

        让多个不同厂商的模型同时质疑一个假设，
        看是否能达成共识。
        """
        if not self._ensure_miner():
            return {
                "hypothesis": hypothesis,
                "consensus": "unknown",
                "error": "miner pool not available",
            }

        return self.miner_pool.cross_validate(
            hypothesis=hypothesis,
            context=context,
            model_count=model_count,
        )

    def assess_prospect(
        self,
        candidate: Dict = None,
        use_miner: bool = False,
    ) -> Dict[str, Any]:
        """
        评估候选假设的前景

        use_miner=True 时，除了原有逻辑，还会加入模型评估
        """
        base_result = {}
        if self.base and candidate:
            base_result = self.base.assess_prospect.__call__(candidate) if hasattr(self.base, 'assess_prospect') else {}

        if not use_miner or not candidate:
            return base_result

        if not self._ensure_miner():
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

            result = self.miner_pool.chat(
                task_type="cross_validation",
                messages=[{"role": "user", "content": user_msg}],
                system_prompt=system_prompt,
            )

            if result.get("success"):
                import json
                import re
                try:
                    json_match = re.search(r'\{[^{}]+\}', result["content"])
                    if json_match:
                        miner_assessment = json.loads(json_match.group())
                        base_result["miner_assessment"] = miner_assessment
                        base_result["miner_model"] = result.get("model", "")
                        base_result["miner_provider"] = result.get("provider", "")
                except Exception:
                    pass
        except Exception:
            pass

        return base_result

    def __getattr__(self, name):
        if self.base and hasattr(self.base, name):
            return getattr(self.base, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


class ArchivistWithMinerPool:
    """
    增强版 Archivist — 有矿工池加持的归档者

    原有能力不变，新增：
      - miner_summarize: 模型辅助总结
      - miner_extract_knowledge: 从文本中提取知识
    """

    def __init__(self, base_archivist=None, miner_pool: Optional[MinerPool] = None):
        self.base = base_archivist
        self.miner_pool = miner_pool
        self._miner_ready = False

    def _ensure_miner(self) -> bool:
        if self._miner_ready:
            return True
        if not self.miner_pool:
            return False
        self._miner_ready = self.miner_pool.initialize()
        return self._miner_ready

    def summarize(
        self,
        content: str = "",
        content_list: List[str] = None,
        use_miner: bool = False,
        max_length: int = 500,
    ) -> Dict[str, Any]:
        """
        总结内容

        use_miner=True 时用模型做高质量总结
        """
        base_result = {}
        if self.base and hasattr(self.base, 'summarize'):
            base_result = self.base.summarize(content, content_list) if content_list else self.base.summarize(content)

        if not use_miner or (not content and not content_list):
            return base_result

        if not self._ensure_miner():
            return base_result

        try:
            if content_list:
                full_content = "\n\n---\n\n".join(content_list)
            else:
                full_content = content

            system_prompt = (
                "你是一个擅长提炼总结的档案管理员。请从以下内容中提取核心要点，"
                "生成结构化的总结。"
                "输出 JSON：{\"summary\": \"总结文本\", \"key_points\": [\"要点1\", \"要点2\"], "
                "\"categories\": {\"类别1\": [\"子项1\", \"子项2\"]}, \"action_items\": []}"
            )

            user_msg = f"请总结以下内容（不超过{max_length}字）：\n\n{full_content[:15000]}"

            result = self.miner_pool.chat(
                task_type="synthesis",
                messages=[{"role": "user", "content": user_msg}],
                system_prompt=system_prompt,
            )

            if result.get("success"):
                import json
                import re
                try:
                    json_match = re.search(r'\{[^{}]+\}', result["content"])
                    if json_match:
                        miner_summary = json.loads(json_match.group())
                        base_result["miner_summary"] = miner_summary
                        base_result["miner_model"] = result.get("model", "")
                        base_result["miner_provider"] = result.get("provider", "")
                except Exception:
                    base_result["miner_summary_raw"] = result.get("content", "")
        except Exception:
            pass

        return base_result

    def extract_knowledge(
        self,
        text: str,
        knowledge_type: str = "general",
    ) -> Dict[str, Any]:
        """
        从文本中提取结构化知识
        """
        if not self._ensure_miner():
            return {"success": False, "error": "miner pool not available"}

        system_prompts = {
            "general": "从文本中提取关键知识，输出 JSON：{\"entities\": [], \"relations\": [], \"key_insights\": []}",
            "constraints": "从文本中提取约束/规则，输出 JSON：{\"constraints\": [{\"name\": \"\", \"description\": \"\", \"severity\": \"high|medium|low\"}]}",
            "experience": "从文本中提取经验教训，输出 JSON：{\"lessons\": [{\"title\": \"\", \"context\": \"\", \"lesson\": \"\"}]}",
        }

        system_prompt = system_prompts.get(knowledge_type, system_prompts["general"])

        result = self.miner_pool.chat(
            task_type="extraction",
            messages=[{"role": "user", "content": f"从以下文本中提取知识：\n\n{text[:10000]}"}],
            system_prompt=system_prompt,
        )

        if not result.get("success"):
            return {"success": False, "error": result.get("error", "unknown")}

        try:
            import json
            import re
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


def create_miner_pool(coze_assets_path: Optional[str] = None) -> MinerPool:
    """
    便捷函数：创建并初始化矿工池
    """
    pool = MinerPool(coze_assets_path=coze_assets_path)
    pool.initialize()
    return pool


def enhance_roles(
    researcher=None,
    validator=None,
    archivist=None,
    coze_assets_path: Optional[str] = None,
    miner_pool: Optional[MinerPool] = None,
) -> Dict[str, Any]:
    """
    一次性增强所有角色

    返回增强后的角色字典。
    """
    if not miner_pool:
        miner_pool = create_miner_pool(coze_assets_path)

    enhanced = {}

    if researcher:
        enhanced["researcher"] = ResearcherWithMinerPool(
            base_researcher=researcher,
            miner_pool=miner_pool,
        )
    if validator:
        enhanced["validator"] = ValidatorWithMinerPool(
            base_validator=validator,
            miner_pool=miner_pool,
        )
    if archivist:
        enhanced["archivist"] = ArchivistWithMinerPool(
            base_archivist=archivist,
            miner_pool=miner_pool,
        )

    enhanced["miner_pool"] = miner_pool
    enhanced["task_types"] = list_task_types()

    return enhanced
