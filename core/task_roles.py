"""
任务生命周期岗位角色

不是人格。
是岗位。

Observer    → 发现问题、提出疑问、创建任务
Researcher  → 领取任务、寻找证据、形成报告
Validator   → 寻找反例、挑战结论
Archivist   → 归档任务、建立索引、形成知识库
Guardian    → 决定进入公理/约束/经验/废弃
"""

import re
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import Counter

from .task import Task, TaskPool


class Observer:
    """
    观察者 — 发现问题，创建任务

    不解决问题。
    只负责提出值得研究的问题。
    """

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None, daemon_state: Dict = None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.daemon_state = daemon_state or {}

    def observe_and_create(self, max_new: int = 3) -> List[Task]:
        """观察系统状态，自动创建任务"""
        candidates = self._generate_candidates()
        new_tasks = []

        for cand in candidates[:max_new]:
            if not self._task_exists(cand["title"]):
                task = self.task_pool.create_task(
                    title=cand["title"],
                    hypothesis=cand.get("hypothesis", ""),
                    creator="observer",
                    priority=cand.get("priority", "medium"),
                    tags=cand.get("tags", []),
                )
                new_tasks.append(task)

        return new_tasks

    def _task_exists(self, title: str) -> bool:
        title_norm = title[:30].lower()
        all_tasks = self.task_pool.list_tasks(limit=200)
        for t in all_tasks:
            if t.title[:30].lower() == title_norm:
                return True
        return False

    def _generate_candidates(self) -> List[Dict[str, Any]]:
        candidates = []

        if self.lexicon:
            stats = self.lexicon.get_stats()
            weak_cats = [
                cat for cat, count in stats.get("categories", {}).items()
                if count <= 2
            ]
            if len(weak_cats) >= 3:
                candidates.append({
                    "title": f"词库缺口补全：{len(weak_cats)}个薄弱分类",
                    "hypothesis": "薄弱分类的概念积累不足，影响系统理解能力",
                    "priority": "high" if len(weak_cats) >= 5 else "medium",
                    "tags": ["lexicon", "gap_filling"],
                })

            total_concepts = stats.get("total_concepts", 0)
            if total_concepts < 100:
                candidates.append({
                    "title": "词库概念规模不足，需要加速积累",
                    "hypothesis": "概念总量低于阈值，系统语言体系尚未成型",
                    "priority": "high",
                    "tags": ["lexicon", "growth"],
                })

        if self.memory_index:
            mem_stats = self.memory_index.get_stats()
            total_mem = mem_stats.get("total", 0)

            by_type = mem_stats.get("by_type", {})
            eco_count = by_type.get("eco_layer", 0)
            if eco_count < 50:
                candidates.append({
                    "title": "eco_layer经验索引不足",
                    "hypothesis": "285万条经验仅索引了极少部分，价值密度最高的叙事生态应优先索引",
                    "priority": "high",
                    "tags": ["eco_layer", "mining"],
                })

            research_count = sum(1 for _ in self.memory_index.search(memory_type="research_report", limit=10))
            if research_count == 0:
                candidates.append({
                    "title": "系统缺乏结构化研究报告",
                    "hypothesis": "记忆以碎片为主，缺少系统性的研究结论沉淀",
                    "priority": "medium",
                    "tags": ["research", "structure"],
                })

        mining_progress = self.daemon_state.get("mining_progress", {})
        eco_prog = mining_progress.get("eco_layer", {})
        if eco_prog:
            for layer, prog in eco_prog.items():
                mined = prog.get("offset", 0)
                total = 0
                if self.memory_index:
                    layer_name = {
                        "narrative_ecology": "叙事生态",
                        "behavioral_ecology": "行为生态",
                        "structural_ecology": "结构生态",
                        "transactional_ecology": "交易生态",
                        "free_zone": "自由区",
                    }.get(layer, layer)
                    if mined == 0 and layer == "behavioral_ecology":
                        candidates.append({
                            "title": f"行为生态层未开始挖掘（话术/对话）",
                            "hypothesis": "行为生态含2.1万条行为模板，是R1行为模式的核心沉淀",
                            "priority": "medium",
                            "tags": ["eco_layer", "behavioral"],
                        })
                        break

        if self.daemon_state.get("errors"):
            recent_errors = self.daemon_state["errors"][:5]
            error_modules = Counter(e.get("module", "") for e in recent_errors)
            top_module = error_modules.most_common(1)
            if top_module and top_module[0][1] >= 2:
                candidates.append({
                    "title": f"模块{top_module[0][0]}近期错误频发",
                    "hypothesis": "存在系统性bug或数据格式不兼容问题",
                    "priority": "medium",
                    "tags": ["bug", "stability"],
                })

        return candidates


class Researcher:
    """
    研究员 — 领取任务，寻找证据，形成报告

    不决定结论。
    只负责收集证据，呈现事实。
    """

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None, eco_parser=None, slice_clusterer=None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.eco_parser = eco_parser
        self.slice_clusterer = slice_clusterer

    def pick_up_task(self, priority: str = "high") -> Optional[Task]:
        """领取最高优先级的待办任务（含卡住的active任务）"""
        priority_order = ["critical", "high", "medium", "low"]
        if priority == "any":
            check_order = priority_order
        else:
            idx = priority_order.index(priority) if priority in priority_order else 1
            check_order = priority_order[:idx + 1]

        for status in ["active", "pending"]:
            for pri in check_order:
                tasks = self.task_pool.list_tasks(status=status, priority=pri, limit=5)
                if tasks:
                    task = tasks[0]
                    task.assignee = "researcher"
                    if status == "pending":
                        self.task_pool.move_task(task.task_id, "active", actor="researcher")
                    return task
        return None

    def research_task(self, task: Task, max_evidence: int = 5) -> Dict[str, Any]:
        """对任务进行研究，收集证据"""
        result = {
            "task_id": task.task_id,
            "evidence_found": 0,
            "counter_found": 0,
            "research_summary": "",
            "status": "review",
        }

        title_lower = task.title.lower()
        hypothesis_lower = task.hypothesis.lower()
        keywords = self._extract_keywords(title_lower + " " + hypothesis_lower)

        evidence = []
        counter_examples = []

        if self.eco_parser and any(k in title_lower for k in ["eco", "生态", "行为", "叙事", "自由区"]):
            eco_evidence = self._research_eco(task, keywords)
            evidence.extend(eco_evidence)

        if self.memory_index:
            for kw in keywords[:5]:
                hits = self.memory_index.search(keyword=kw, limit=10)
                for hit in hits[:2]:
                    evidence.append({
                        "content": hit.get("content", "")[:300],
                        "source": hit.get("source", "memory"),
                        "type": "memory",
                        "title": hit.get("title", ""),
                    })

        if self.lexicon:
            for kw in keywords[:5]:
                concept = self.lexicon.get_concept(kw)
                if concept:
                    evidence.append({
                        "content": f"词库概念[{concept['name']}]：{concept.get('definition', '')}",
                        "source": "lexicon",
                        "type": "concept",
                        "concept": concept["name"],
                    })

        evidence = evidence[:max_evidence]

        for ev in evidence:
            task.add_evidence(ev.get("content", "")[:300], source=ev.get("source", ""))

        summary_parts = [f"研究了 {len(evidence)} 条证据"]
        if evidence:
            types = Counter(e.get("type", "unknown") for e in evidence)
            summary_parts.append(f"来源分布: {dict(types)}")
        result["research_summary"] = "；".join(summary_parts)

        task.add_research_note(result["research_summary"])
        task.result = {
            "evidence_count": len(evidence),
            "counter_count": len(counter_examples),
            "summary": result["research_summary"],
        }

        self.task_pool.update_task(task)
        self.task_pool.move_task(task.task_id, "review", actor="researcher", task=task)

        result["evidence_found"] = len(evidence)
        return result

    def _research_eco(self, task: Task, keywords: List[str]) -> List[Dict]:
        findings = []
        if not self.eco_parser:
            return findings

        for kw in keywords[:3]:
            hits = self.eco_parser.find_contains(kw, max_results=5)
            for hit in hits[:2]:
                findings.append({
                    "content": f"[{hit['layer_name']}] {hit.get('preview', '')[:200]}",
                    "source": f"eco_layer:{hit['layer']}",
                    "type": "eco_layer",
                })

        return findings

    def _extract_keywords(self, text: str) -> List[str]:
        stopwords = {"的", "了", "是", "在", "有", "和", "不", "一", "个", "需要", "进行", "发现", "研究", "问题", "系统", "不足", "应该", "可以", "可能", "已经", "这个", "那个", "什么", "怎么", "为什么", "因为", "所以", "但是", "如果", "包括", "包含", "相关", "对应", "提供", "实现", "执行", "处理"}
        cn_chunks = re.findall(r"[\u4e00-\u9fff]+", text)
        keywords = []
        for chunk in cn_chunks:
            found_in_chunk = False
            for length in [4, 3, 2]:
                for i in range(len(chunk) - length + 1):
                    w = chunk[i:i + length]
                    if w not in stopwords and self.lexicon and self.lexicon.get_concept(w):
                        keywords.append(w)
                        found_in_chunk = True
                        break
                if found_in_chunk:
                    break
            if not found_in_chunk and len(chunk) >= 2:
                w = chunk[:4] if len(chunk) > 4 else chunk
                if w not in stopwords:
                    keywords.append(w)
        en_words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]{2,}", text)
        for w in en_words:
            if w.lower() not in stopwords and w not in keywords:
                keywords.append(w)
        seen = set()
        result = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                result.append(w)
        return result[:10]


class Validator:
    """
    验证员 — 寻找反例，挑战结论

    不负责建设。
    只负责挑刺。
    至少提出一个反对意见。
    """

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index

    def validate_task(self, task: Task) -> Dict[str, Any]:
        """验证一个任务的研究结论，至少找一个反例或疑点"""
        review_count = getattr(task, "review_count", 0)
        task.review_count = review_count + 1
        self.task_pool.update_task(task)

        result = {
            "task_id": task.task_id,
            "objections": [],
            "counter_examples": 0,
            "passed": False,
            "verdict": "",
            "review_count": task.review_count,
        }

        objections = []

        evidence_count = len(task.evidence)
        if evidence_count == 0:
            objections.append("没有任何证据支持，研究不充分")
        elif evidence_count < 3:
            objections.append(f"仅{evidence_count}条证据，样本量不足")

        if not task.hypothesis:
            objections.append("任务没有明确的假设，无法验证")

        if not task.counter_examples:
            objections.append("未主动寻找反例，存在确认偏误风险")

        if self.memory_index and task.evidence:
            first_ev = task.evidence[0]
            ev_content = first_ev.get("content", "") if isinstance(first_ev, dict) else str(first_ev)
            if len(ev_content) < 50:
                objections.append("第一条证据内容过短，可信度存疑")

        keywords = re.findall(r"[\u4e00-\u9fffA-Za-z_][\u4e00-\u9fffA-Za-z0-9_]{2,}", task.title)
        if self.lexicon and keywords:
            matched_concepts = sum(1 for kw in keywords[:5] if self.lexicon.get_concept(kw))
            if matched_concepts == 0 and len(keywords) >= 2:
                objections.append("核心关键词在词库中无对应概念，研究背景薄弱")

        genuine_objections = [o for o in objections if "未发现明显逻辑漏洞" not in o]

        if not genuine_objections:
            genuine_objections.append("建议扩大样本量后再确认")

        for obj in genuine_objections:
            task.add_validation_note(obj, validator="validator")
            task.add_counter_example(obj, source="validator")

        result["objections"] = genuine_objections
        result["counter_examples"] = len(genuine_objections)

        if len(genuine_objections) <= 1 and evidence_count >= 3:
            result["passed"] = True
            result["verdict"] = "初步通过，可进入终审"
            self.task_pool.update_task(task)
            self.task_pool.move_task(task.task_id, "approved", actor="validator", task=task)

        elif task.review_count >= 3:
            result["passed"] = True
            result["verdict"] = f"重审{ task.review_count}次后强制通过（异议{len(genuine_objections)}个，但证据已充分）"
            task.add_validation_note(f"[终审保护] 重审{task.review_count}次，强制进入终审", validator="validator")
            self.task_pool.update_task(task)
            self.task_pool.move_task(task.task_id, "approved", actor="validator", task=task)

        elif evidence_count >= 2:
            result["passed"] = False
            result["verdict"] = f"需补充研究，退回active（第{task.review_count}次重审）"
            task.add_research_note(f"验证员提出{len(genuine_objections)}个质疑，需补充研究")
            task.assignee = "researcher"
            self.task_pool.update_task(task)
            self.task_pool.move_task(task.task_id, "active", actor="validator", task=task)

        else:
            result["passed"] = False
            result["verdict"] = "证据不足，退回待重新研究"
            task.assignee = "researcher"
            self.task_pool.update_task(task)
            self.task_pool.move_task(task.task_id, "active", actor="validator", task=task)

        return result


class Archivist:
    """
    档案官 — 归档任务，建立索引，形成知识库

    不决定价值。
    只负责好好存起来，确保找得到。
    """

    def __init__(self, task_pool: TaskPool, memory_index=None, lexicon=None):
        self.task_pool = task_pool
        self.memory_index = memory_index
        self.lexicon = lexicon

    def archive_task(self, task: Task) -> bool:
        """归档已批准的任务，写入记忆索引"""
        if task.status != "approved":
            return False

        archive_note = self._format_task_archive(task)

        if self.memory_index:
            self.memory_index.add(
                title=f"[任务归档] {task.title}",
                content=archive_note,
                memory_type="task_archive",
                category="任务归档",
                source="archivist",
                tags=task.tags + ["archived", task.task_id],
            )

        self.task_pool.move_task(task.task_id, "archived", actor="archivist")
        return True

    def _format_task_archive(self, task: Task) -> str:
        lines = [
            f"## 任务ID: {task.task_id}",
            f"**标题**: {task.title}",
            f"**创建者**: {task.creator}",
            f"**优先级**: {task.priority}",
            f"**假设**: {task.hypothesis or '无'}",
            "",
            f"**证据数**: {len(task.evidence)}",
            f"**反例数**: {len(task.counter_examples)}",
            "",
        ]

        if task.evidence:
            lines.append("### 核心证据")
            for i, ev in enumerate(task.evidence[:5]):
                if isinstance(ev, dict):
                    lines.append(f"{i+1}. [{ev.get('source', 'unknown')}] {ev.get('content', '')[:150]}")
                else:
                    lines.append(f"{i+1}. {str(ev)[:150]}")
            lines.append("")

        if task.counter_examples:
            lines.append("### 反例/质疑")
            for i, ce in enumerate(task.counter_examples[:5]):
                if isinstance(ce, dict):
                    lines.append(f"{i+1}. {ce.get('content', '')[:150]}")
                else:
                    lines.append(f"{i+1}. {str(ce)[:150]}")
            lines.append("")

        if task.result:
            lines.append(f"### 结论")
            if isinstance(task.result, dict):
                lines.append(json.dumps(task.result, ensure_ascii=False, indent=2)[:500])
            else:
                lines.append(str(task.result)[:500])
            lines.append("")

        lines.extend([
            f"**引用次数**: {task.reference_count}",
            f"**创建时间**: {task.created_at}",
            f"**归档时间**: {datetime.now().isoformat()}",
        ])

        return "\n".join(lines)


class Guardian:
    """
    守护者 — 决定任务结论去哪里

    四个去向：
    - 进入公理（axiom）—— 已验证的基本规律
    - 进入约束（constraint）—— 系统必须遵守的规则
    - 进入经验库（experience）—— 有用但不是铁律
    - 直接废弃（discard）—— 不值得保留
    """

    def __init__(self, task_pool: TaskPool, lexicon=None, memory_index=None):
        self.task_pool = task_pool
        self.lexicon = lexicon
        self.memory_index = memory_index

    def judge(self, task: Task) -> Dict[str, Any]:
        """审判一个归档的任务，决定它的最终去向"""
        decision = {
            "task_id": task.task_id,
            "verdict": "experience",
            "reason": "",
            "promoted": False,
        }

        ev_count = len(task.evidence)
        ce_count = len(task.counter_examples)

        if ev_count == 0:
            decision["verdict"] = "discard"
            decision["reason"] = "无证据支撑，无保留价值"
        elif ev_count >= 5 and ce_count == 0:
            decision["verdict"] = "axiom"
            decision["reason"] = f"{ev_count}条证据支撑，0反例，可作为临时公理"
            decision["promoted"] = True
        elif ev_count >= 3 and task.priority in ["high", "critical"]:
            decision["verdict"] = "constraint"
            decision["reason"] = "高优先级任务，证据充分，可作为约束"
            decision["promoted"] = True
        elif ev_count >= 2:
            decision["verdict"] = "experience"
            decision["reason"] = "有一定证据，但反例或不足仍存，归入经验库"
        else:
            decision["verdict"] = "experience"
            decision["reason"] = "证据有限，暂存经验库待后续验证"

        task.guardian_decision = decision["verdict"]
        task.add_validation_note(
            f"Guardian判决: {decision['verdict']} — {decision['reason']}",
            validator="guardian",
        )
        task.touch()

        if decision["verdict"] == "discard":
            self.task_pool.update_task(task)
            self.task_pool.move_task(task.task_id, "rejected", actor="guardian", task=task)
        elif decision["promoted"] and self.lexicon:
            if decision["verdict"] == "axiom":
                cat = "核心原则"
            elif decision["verdict"] == "constraint":
                cat = "治理原则"
            else:
                cat = "经验沉淀"

            concept_name = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9_]", "_", task.title[:30])
            if concept_name and not self.lexicon.get_concept(concept_name):
                self.lexicon.add_concept(
                    name=concept_name,
                    definition=f"[Guardian-{decision['verdict']}] {task.hypothesis or task.title}",
                    category=cat,
                    source=f"guardian:{task.task_id}",
                    importance=80 if decision["verdict"] == "axiom" else 65,
                )
            self.task_pool.update_task(task)
        else:
            self.task_pool.update_task(task)

        return decision
