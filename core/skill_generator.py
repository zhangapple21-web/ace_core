"""
Skill Generator — DNA → 技能自动沉淀机制

从已归档任务中自动提取可复用的执行模式，沉淀为技能模板。

核心设计原则：
1. 技能只存储"执行模式"，不存储具体任务数据
2. 技能生成是可选的，由系统判断是否可复用
3. 技能模板与Worker类型对应（research/pattern/synthesis）
4. 技能可被TaskCreator检索并用于快速创建任务
"""

import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
from collections import defaultdict


SKILL_VERSION = "1.0"


class SkillGenerator:
    """
    技能生成器 — 从已归档任务中自动沉淀技能

    工作流程：
    1. 扫描已归档任务，按标签/创建者/输出格式聚类
    2. 判断聚类是否达到可复用阈值（>=2个相似任务）
    3. 生成技能模板（任务模板 + Worker配置 + 使用示例）
    4. 存入 09_KNOWLEDGE/skills/ 目录
    5. 更新 manifest.json 技能清单
    """

    def __init__(self, skills_dir: Path, task_pool=None):
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.task_pool = task_pool
        self.manifest_path = self.skills_dir / "manifest.json"
        self._load_manifest()

    def _load_manifest(self):
        """加载技能清单"""
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    self.manifest = json.load(f)
            except Exception:
                self.manifest = self._empty_manifest()
        else:
            self.manifest = self._empty_manifest()

    def _empty_manifest(self) -> Dict[str, Any]:
        return {
            "version": SKILL_VERSION,
            "generated_at": datetime.now().isoformat(),
            "total_skills": 0,
            "by_type": {},
            "skills": [],
        }

    def _save_manifest(self):
        """保存技能清单"""
        self.manifest["generated_at"] = datetime.now().isoformat()
        self.manifest["total_skills"] = len(self.manifest["skills"])

        by_type = defaultdict(int)
        for skill in self.manifest["skills"]:
            by_type[skill.get("skill_type", "unknown")] += 1
        self.manifest["by_type"] = dict(by_type)

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(self.manifest, f, ensure_ascii=False, indent=2)

    def _skill_file_path(self, skill_name: str) -> Path:
        return self.skills_dir / f"SKILL-{skill_name}.json"

    def analyze_archived_tasks(self, archived_tasks: List[Any]) -> Dict[str, Any]:
        """
        分析已归档任务，识别可复用模式

        Args:
            archived_tasks: Task对象列表

        Returns:
            {
                "patterns_found": int,
                "patterns": [...],
                "new_skills": [...],
                "skipped": [...],
            }
        """
        result = {
            "tasks_analyzed": len(archived_tasks),
            "patterns_found": 0,
            "patterns": [],
            "new_skills": [],
            "skipped": [],
        }

        if not archived_tasks:
            return result

        clusters = self._cluster_tasks(archived_tasks)
        result["patterns_found"] = len(clusters)
        result["patterns"] = clusters

        for cluster in clusters:
            if cluster["task_count"] >= 2:
                existing = self._find_existing_skill(cluster["name"])
                if existing:
                    result["skipped"].append({
                        "pattern": cluster["name"],
                        "reason": "skill_already_exists",
                        "existing_skill": existing,
                    })
                else:
                    skill = self._generate_skill_from_cluster(cluster)
                    if skill:
                        self._save_skill(skill)
                        self._register_skill_in_manifest(skill)
                        result["new_skills"].append(skill["skill_name"])
            else:
                result["skipped"].append({
                    "pattern": cluster["name"],
                    "reason": "insufficient_tasks",
                    "task_count": cluster["task_count"],
                })

        self._save_manifest()
        return result

    def _cluster_tasks(self, tasks: List[Any]) -> List[Dict[str, Any]]:
        """
        按多维特征聚类任务

        聚类维度：
        1. 标签组合（主要）
        2. 创建者（辅助）
        3. 输出格式结构（辅助）
        4. 标题关键词模式（辅助）
        """
        clusters = []

        tag_clusters = self._cluster_by_tags(tasks)
        for name, c_tasks in tag_clusters.items():
            if len(c_tasks) >= 1:
                cluster = {
                    "name": name,
                    "task_count": len(c_tasks),
                    "task_ids": [t.task_id for t in c_tasks],
                    "tasks": c_tasks,
                    "common_tags": self._extract_common_tags(c_tasks),
                    "worker_type": self._infer_worker_type(c_tasks),
                    "creators": list(set(t.creator for t in c_tasks)),
                }
                clusters.append(cluster)

        clusters.sort(key=lambda c: -c["task_count"])
        return clusters

    def _cluster_by_tags(self, tasks: List[Any]) -> Dict[str, List[Any]]:
        """按标签模式聚类"""
        tag_patterns = {
            "experience_validation": ["experience", "experience_pattern"],
            "local_archaeology_absorption": ["local_archaeology", "absorption"],
            "archaeology_report_analysis": ["archaeology", "report", "archaeology_report"],
            "lexicon_gap_filling": ["lexicon", "gap_filling"],
            "axiom_candidate_promotion": ["axiom_candidate"],
            "fragment_archaeology": ["fragment_archaeology"],
            "structure_research": ["research", "structure"],
        }

        clusters = defaultdict(list)
        assigned = set()

        for pattern_name, required_tags in tag_patterns.items():
            for task in tasks:
                if task.task_id in assigned:
                    continue
                task_tags = set(task.tags or [])
                if any(tag in task_tags for tag in required_tags):
                    clusters[pattern_name].append(task)
                    assigned.add(task.task_id)

        for task in tasks:
            if task.task_id not in assigned:
                generic_name = self._generic_skill_name(task)
                clusters[generic_name].append(task)
                assigned.add(task.task_id)

        return dict(clusters)

    def _generic_skill_name(self, task) -> str:
        """从任务标题生成通用技能名"""
        title = task.title
        title = re.sub(r'[：:].*$', '', title)
        title = re.sub(r'[\d年月日\-\.]', '', title)
        title = title.strip()
        if len(title) > 20:
            title = title[:20]
        return re.sub(r'[^a-zA-Z0-9_\u4e00-\u9fff]', '_', title) or 'generic_task'

    def _extract_common_tags(self, tasks: List[Any]) -> List[str]:
        """提取任务组的共同标签"""
        if not tasks:
            return []
        tag_sets = [set(t.tags or []) for t in tasks]
        common = tag_sets[0]
        for ts in tag_sets[1:]:
            common = common & ts
        return sorted(list(common))

    def _infer_worker_type(self, tasks: List[Any]) -> str:
        """推断任务组对应的Worker类型"""
        if not tasks:
            return "research"

        type_counts = defaultdict(int)
        for task in tasks:
            tags = set(task.tags or [])
            if "archaeology" in tags or "report" in tags or "synthesis" in tags:
                type_counts["synthesis"] += 1
            elif "pattern" in tags or "eco" in tags:
                type_counts["pattern"] += 1
            elif "lexicon" in tags or "gap" in tags:
                type_counts["lexicon"] += 1
            else:
                type_counts["research"] += 1

        return max(type_counts.items(), key=lambda x: x[1])[0]

    def _generate_skill_from_cluster(self, cluster: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从任务聚类生成技能模板"""
        tasks = cluster["tasks"]
        if not tasks:
            return None

        sample_task = tasks[0]
        skill_name = cluster["name"]
        worker_type = cluster["worker_type"]

        title_template = self._extract_title_pattern(tasks)
        priority = self._most_common_priority(tasks)

        examples = []
        for task in tasks[:3]:
            examples.append({
                "task_id": task.task_id,
                "title": task.title,
                "priority": task.priority,
                "tags": task.tags,
                "hypothesis_preview": (task.hypothesis or "")[:100],
                "output_keys": list((task.outputs or {}).keys()),
            })

        skill = {
            "skill_name": skill_name,
            "skill_version": SKILL_VERSION,
            "skill_type": worker_type,
            "description": f"自动生成的技能：{cluster.get('description', skill_name)}",
            "created_at": datetime.now().isoformat(),
            "created_from": cluster["task_ids"],
            "usage_count": 0,
            "last_used_at": None,
            "task_template": {
                "title_pattern": title_template,
                "priority": priority,
                "common_tags": cluster["common_tags"],
                "hypothesis_template": self._extract_hypothesis_pattern(tasks),
                "depends_on_pattern": [],
                "outputs_expected": self._extract_common_outputs(tasks),
            },
            "worker_config": {
                "worker_type": worker_type,
                "tools": self._infer_tools(tasks),
                "data_sources": self._infer_data_sources(tasks),
                "validation_required": True,
                "guardian_review": True,
            },
            "examples": examples,
            "matching_rules": {
                "tag_match": cluster["common_tags"],
                "title_keywords": self._extract_title_keywords(tasks),
                "creator_match": cluster["creators"],
            },
        }

        return skill

    def _extract_title_pattern(self, tasks: List[Any]) -> str:
        """提取标题模式"""
        if not tasks:
            return ""
        titles = [t.title for t in tasks]
        if len(titles) == 1:
            return titles[0]

        prefix = titles[0]
        for t in titles[1:]:
            while not t.startswith(prefix) and len(prefix) > 0:
                prefix = prefix[:-1]
        if len(prefix) >= 4:
            return prefix + "{topic}"
        return "{topic}"

    def _most_common_priority(self, tasks: List[Any]) -> str:
        """最常见的优先级"""
        counts = defaultdict(int)
        for t in tasks:
            counts[t.priority] += 1
        return max(counts.items(), key=lambda x: x[1])[0] if counts else "medium"

    def _extract_hypothesis_pattern(self, tasks: List[Any]) -> str:
        """提取假设模板"""
        for t in tasks:
            if t.hypothesis and len(t.hypothesis) > 10:
                return t.hypothesis
        return ""

    def _extract_common_outputs(self, tasks: List[Any]) -> List[str]:
        """提取共同的输出字段"""
        if not tasks:
            return []
        all_keys = [set((t.outputs or {}).keys()) for t in tasks if t.outputs]
        if not all_keys:
            return []
        common = all_keys[0]
        for keys in all_keys[1:]:
            common = common & keys
        return sorted(list(common))

    def _infer_tools(self, tasks: List[Any]) -> List[str]:
        """推断使用的工具"""
        tools = []
        tags = set()
        for t in tasks:
            tags.update(t.tags or [])

        if "lexicon" in tags:
            tools.append("lexicon")
        if any("memory" in k for t in tasks for k in (t.outputs or {}).keys()):
            tools.append("memory_index")
        if any("eco" in k for t in tasks for k in (t.outputs or {}).keys()):
            tools.append("eco_parser")
        if "archaeology" in tags or "report" in tags:
            tools.append("synthesis")

        return tools

    def _infer_data_sources(self, tasks: List[Any]) -> List[str]:
        """推断数据源"""
        sources = set()
        for t in tasks:
            for ev in (t.evidence or []):
                if isinstance(ev, dict) and ev.get("source"):
                    sources.add(ev["source"])
        return sorted(list(sources))[:5]

    def _extract_title_keywords(self, tasks: List[Any]) -> List[str]:
        """提取标题关键词"""
        keywords = set()
        for t in tasks:
            cn_chunks = re.findall(r"[\u4e00-\u9fff]{2,}", t.title)
            keywords.update(cn_chunks)
            en_words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", t.title)
            keywords.update(en_words)
        return sorted(list(keywords))[:10]

    def _save_skill(self, skill: Dict[str, Any]):
        """保存技能模板"""
        path = self._skill_file_path(skill["skill_name"])
        with open(path, "w", encoding="utf-8") as f:
            json.dump(skill, f, ensure_ascii=False, indent=2)

    def _register_skill_in_manifest(self, skill: Dict[str, Any]):
        """在清单中注册技能"""
        entry = {
            "skill_name": skill["skill_name"],
            "skill_type": skill["skill_type"],
            "description": skill["description"],
            "created_at": skill["created_at"],
            "created_from": skill["created_from"],
            "usage_count": skill.get("usage_count", 0),
        }

        existing = [s for s in self.manifest["skills"] if s["skill_name"] == skill["skill_name"]]
        if existing:
            idx = self.manifest["skills"].index(existing[0])
            self.manifest["skills"][idx] = entry
        else:
            self.manifest["skills"].append(entry)

    def _find_existing_skill(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """查找已存在的技能"""
        path = self._skill_file_path(skill_name)
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def find_matching_skill(self, task_candidate: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        为任务候选查找匹配的技能

        Args:
            task_candidate: {title, tags, type, ...}

        Returns:
            匹配的技能模板，或None
        """
        best_match = None
        best_score = 0

        for skill_entry in self.manifest.get("skills", []):
            skill = self._find_existing_skill(skill_entry["skill_name"])
            if not skill:
                continue

            score = self._calc_match_score(task_candidate, skill)
            if score > best_score and score >= 2:
                best_score = score
                best_match = skill

        return best_match

    def _calc_match_score(self, candidate: Dict[str, Any], skill: Dict[str, Any]) -> int:
        """计算匹配分数"""
        score = 0
        rules = skill.get("matching_rules", {})

        cand_tags = set(candidate.get("tags", []))
        skill_tags = set(rules.get("tag_match", []))
        tag_overlap = cand_tags & skill_tags
        if tag_overlap:
            score += len(tag_overlap) * 2

        title = candidate.get("title", "").lower()
        title_keywords = [kw.lower() for kw in rules.get("title_keywords", [])]
        for kw in title_keywords:
            if kw in title:
                score += 1

        if candidate.get("creator") and candidate["creator"] in rules.get("creator_match", []):
            score += 1

        return score

    def record_usage(self, skill_name: str):
        """记录技能使用"""
        skill = self._find_existing_skill(skill_name)
        if skill:
            skill["usage_count"] = skill.get("usage_count", 0) + 1
            skill["last_used_at"] = datetime.now().isoformat()
            self._save_skill(skill)

            for entry in self.manifest.get("skills", []):
                if entry["skill_name"] == skill_name:
                    entry["usage_count"] = skill["usage_count"]
                    entry["last_used_at"] = skill["last_used_at"]
                    break
            self._save_manifest()

    def list_skills(self, skill_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """列出所有技能"""
        skills = []
        for entry in self.manifest.get("skills", []):
            if skill_type and entry.get("skill_type") != skill_type:
                continue
            skills.append(entry)
        return skills

    def get_stats(self) -> Dict[str, Any]:
        """获取技能统计"""
        return {
            "total_skills": self.manifest.get("total_skills", 0),
            "by_type": self.manifest.get("by_type", {}),
            "most_used": sorted(
                self.manifest.get("skills", []),
                key=lambda s: s.get("usage_count", 0),
                reverse=True
            )[:5],
        }

    def generate_skill_from_task(self, task) -> Optional[Dict[str, Any]]:
        """
        从单个任务生成技能（任务归档时调用）

        先检查是否有同类型的已归档任务，如果形成聚类则生成技能
        """
        if not self.task_pool:
            return None

        archived = self.task_pool.list_tasks(status="archived", limit=100)
        similar = [t for t in archived if self._is_similar_task(t, task)]

        if len(similar) >= 2:
            cluster_name = self._generic_skill_name(task)
            cluster = {
                "name": cluster_name,
                "task_count": len(similar),
                "task_ids": [t.task_id for t in similar],
                "tasks": similar,
                "common_tags": self._extract_common_tags(similar),
                "worker_type": self._infer_worker_type(similar),
                "creators": list(set(t.creator for t in similar)),
            }

            existing = self._find_existing_skill(cluster_name)
            if not existing:
                skill = self._generate_skill_from_cluster(cluster)
                if skill:
                    self._save_skill(skill)
                    self._register_skill_in_manifest(skill)
                    self._save_manifest()
                    return skill

        return None

    def _is_similar_task(self, task_a, task_b) -> bool:
        """判断两个任务是否相似"""
        tags_a = set(task_a.tags or [])
        tags_b = set(task_b.tags or [])
        common_tags = tags_a & tags_b

        if len(common_tags) >= 2:
            return True

        if task_a.creator == task_b.creator and common_tags:
            return True

        return False
