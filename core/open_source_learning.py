"""A bounded, governed backlog for ACE open-source study.

The backlog queues research tasks only. It never installs a package, changes a
runtime route, or treats a repository's claims as adopted knowledge.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from .discovery import DiscoveryCandidate


CATALOG: Tuple[Dict[str, str], ...] = (
    {"id": "alphalens-reloaded", "title": "考古 Alphalens 风格因子验真方法", "repository": "https://github.com/stefan-jansen/alphalens-reloaded", "disposition": "ABSORB", "objective": "提取 IC、分层、换手、衰减和样本外报告结构，映射到 ACE 的真实可成交标签；不安装或接入生产。"},
    {"id": "microsoft-qlib", "title": "考古 Qlib 分钟因子研究边界", "repository": "https://github.com/microsoft/qlib", "disposition": "ADAPT", "objective": "核验分钟研究、数据契约与实验追踪能力，提出对 ACE 数据血缘和 A 股微观结构的适配设计；不安装或接入生产。"},
    {"id": "vnpy-alpha", "title": "考古 vn.py Alpha 离线研究工作流", "repository": "https://github.com/vnpy/vnpy/tree/master/vnpy/alpha", "disposition": "ADAPT", "objective": "评估离线特征、实验与回测组织方式；明确不接 Gateway、券商或订单接口。"},
    {"id": "quantaalpha", "title": "考古 QuantaAlpha 因子生命周期", "repository": "https://github.com/QuantaAlpha/QuantaAlpha", "disposition": "RESEARCH", "objective": "核验因子生成、复杂度与冗余质量门，判断其日频实验与 ACE A 股超短数据门之间的缺口；不安装或接入生产。"},
)


class OpenSourceLearningBacklog:
    """Expose one unqueued study at a time to the existing DailyLearningLoop."""

    def __init__(self, task_pool):
        self.task_pool = task_pool

    def candidates(self) -> List[Tuple[DiscoveryCandidate, List[Dict[str, Any]]]]:
        existing = {
            task.outputs.get("discovery", {}).get("fingerprint")
            for task in self.task_pool.list_tasks(limit=10000)
            if isinstance(task.outputs.get("discovery", {}), dict)
        }
        for item in CATALOG:
            fingerprint = f"open_source_learning:{item['id']}:v1"
            if fingerprint in existing:
                continue
            learning = {
                "why_learn": f"The governed catalog marks {item['id']} as {item['disposition']} pending evidence review.",
                "learning_objective": item["objective"],
                "required_evidence": ["official repository documentation", "local ACE compatibility and governance review"],
                "mastery_criteria": ["Record ABSORB, ADAPT, CONFLICT, REDUNDANT, or REJECT with evidence and a production boundary."],
                "requires_miner": True,
            }
            candidate = DiscoveryCandidate(
                fingerprint=fingerprint, title=item["title"],
                description="A catalogued open-source study candidate. Repository claims are hypotheses until independently reviewed.",
                reason=learning["why_learn"], objective=learning["learning_objective"],
                completion_criteria=learning["mastery_criteria"][0],
                verification_method="Read official repository documentation and compare it with local ACE data, runtime, and governance boundaries.",
                priority="medium", task_type="reasoning", severity="medium",
                candidate_source="open_source_learning_backlog",
                metadata={"learning": learning, "open_source_catalog": dict(item)},
            )
            evidence = [{
                "source": "official_repository_catalog", "source_ref": item["repository"],
                "content": f"Catalog disposition={item['disposition']}; objective={item['objective']}",
                "confidence": 0.5, "author": "ACE curated open-source catalog", "source_location": item["repository"],
                "metadata": {"source_tier": "documentation", "upstream_identity": item["repository"],
                    "independence_group": f"official_repo:{item['id']}", "lineage_observable": True,
                    "directness": "primary", "cross_validation_source": "external", "catalog_disposition": item["disposition"]},
            }, {
                "source": "ace_curated_catalog", "source_ref": f"catalog://open-source/{item['id']}",
                "content": "Local catalogue entry authorizes bounded archaeology only; it is not validation or production approval.",
                "confidence": 0.9, "author": "ACE Repository Curator", "source_location": "core/open_source_learning.py",
                "metadata": {"source_tier": "official", "upstream_identity": "ACE governed catalogue",
                    "independence_group": "ace_internal_catalog", "lineage_observable": True,
                    "directness": "primary", "cross_validation_source": "local", "catalog_disposition": item["disposition"]},
            }]
            return [(candidate, evidence)]
        return []
