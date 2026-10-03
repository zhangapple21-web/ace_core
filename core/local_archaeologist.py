"""
本地考古扫描器（Local Archaeologist）

结构核版本 — state 为唯一真源，去叙事化。

职责：
扫描本地考古目录中所有尚未被完全吸收的材料，
发现新结构、新协议、新概念、新血缘关系。

扫描范围（优先级从高到低）：
  1. 08_ARCHAEOLOGY/   — 考古报告（最浓缩）
  2. telegram_archive/04_FINDINGS/  — TG收藏考古发现
  3. 04_PROTOCOLS/     — 协议层
  4. 02_MEMORY/        — 记忆层
  5. 09_KNOWLEDGE/     — 经验/知识层
  6. 03_DATA/          — 数据层

不是文件发现器。
是内容吸收检查器。
检查：这些材料里的结构，词库里有没有？记忆里有没有？经验里有没有？
如果没有 → 标记为"未吸收" → 建任务 → 交给 Researcher 去挖。
"""

import json
import re
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Dict, List, Any, Optional, Set
import hashlib
import os
import time
from collections import defaultdict


# 扫描目录定义 — (路径, 优先级, 描述)
SCAN_DIRS = [
    ("08_ARCHAEOLOGY", 5, "考古报告"),
    ("telegram_archive/04_FINDINGS", 4, "TG考古发现"),
    ("04_PROTOCOLS", 4, "协议层"),
    ("02_MEMORY/recent_memory/research", 3, "研究笔记"),
    ("02_MEMORY/recent_memory/daily", 2, "每日记录"),
    ("09_KNOWLEDGE", 3, "经验知识层"),
    ("telegram_archive/03_CLUSTERS", 2, "TG聚类结果"),
    ("telegram_archive/02_INDEX", 1, "TG索引"),
]

# 感兴趣的文件类型
EXT_PRIORITY = {".md": "high", ".txt": "medium", ".json": "medium"}
TARGET_EXTS = {".md", ".json", ".txt"}


class LocalArchaeologist:
    """本地考古扫描器 — 检查已有材料的吸收状态

    输入：词库、记忆索引、任务池
    输出：更新 state，返回结构化结果
    副作用：创建任务、更新吸收索引
    """

    def __init__(
        self,
        base_dir: Path,
        lexicon,
        memory_index,
        task_pool=None,
        state_file: Optional[Path] = None,
    ):
        self.base_dir = base_dir
        self.lexicon = lexicon
        self.memory_index = memory_index
        self.task_pool = task_pool

        if state_file is None:
            state_file = base_dir / "06_RUNTIME" / "ace" / "data" / "local_archaeologist_state.json"
        self.state_file = state_file
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        self._budget = {
            "max_files_per_scan": 10,    # 每次最多扫描10个文件
            "max_tasks_per_scan": 3,     # 每次最多创建3个任务
            "min_absorption_gap": 0.8,   # 吸收率低于80%就进入受限考古任务
        }

        self._state = self._load_state()

    # ── state 层 ────────────────────────────────────────────

    def _load_state(self) -> dict:
        defaults = {
            "version": 2, "last_run": None, "last_scan_date": None,
            "absorbed_files": set(), "known_structures": set(),
            "fingerprints": {}, "source_last_seen": {},
            "total_files_scanned": 0, "total_tasks_created": 0,
            "total_structures_found": 0, "errors": [], "history": [],
        }
        if self.state_file.exists():
            try:
                raw = json.loads(self.state_file.read_text(encoding="utf-8"))
                defaults.update(raw)
                defaults["absorbed_files"] = set(defaults.get("absorbed_files", []))
                defaults["known_structures"] = set(defaults.get("known_structures", []))
                defaults.setdefault("fingerprints", {})
                defaults.setdefault("source_last_seen", {})
                return defaults
            except Exception:
                pass
        return defaults

    def _save_state(self):
        save_data = dict(self._state)
        save_data["absorbed_files"] = list(save_data.get("absorbed_files", set()))
        save_data["known_structures"] = list(save_data.get("known_structures", set()))
        save_data["fingerprints"] = dict(save_data.get("fingerprints", {}))
        save_data["source_last_seen"] = dict(save_data.get("source_last_seen", {}))
        self.state_file.write_text(json.dumps(save_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _ensure_today(self):
        today = date.today().isoformat()
        if self._state.get("last_scan_date") != today:
            self._state["last_scan_date"] = today

    def get_stats(self) -> Dict[str, Any]:
        s = self._state
        return {
            "last_run": s.get("last_run"),
            "absorbed_files_count": len(s.get("absorbed_files", set())),
            "known_structures_count": len(s.get("known_structures", set())),
            "total_files_scanned": s.get("total_files_scanned", 0),
            "total_tasks_created": s.get("total_tasks_created", 0),
            "total_structures_found": s.get("total_structures_found", 0),
            "error_count": len(s.get("errors", [])),
        }

    # ── 决策层 ─────────────────────────────────────────────

    def _collect_candidate_files(self) -> List[Dict[str, Any]]:
        """收集待扫描文件，按优先级排序"""
        candidates = []

        for rel_path, priority, desc in SCAN_DIRS:
            full_path = self.base_dir / rel_path
            # telegram_archive 可能在 base_dir 的父级
            if not full_path.exists() and rel_path.startswith("telegram_archive"):
                full_path = self.base_dir.parent / rel_path

            if not full_path.exists():
                continue

            for f in full_path.rglob("*"):
                if not f.is_file():
                    continue
                if f.suffix.lower() not in TARGET_EXTS:
                    continue

                # 计算文件指纹（路径+mtime+size）
                try:
                    content_fingerprint = hashlib.sha256(f.read_bytes()).hexdigest()
                    fingerprint = f"sha256:{content_fingerprint}"
                except Exception:
                    fingerprint = str(f.resolve())
                if fingerprint in self._state["absorbed_files"]:
                    continue
                relative = str(f)
                source_class = self._classify_source(f, relative)
                intake = self._intake_policy(source_class, f.suffix.lower(), f)
                if intake["decision"] == "skip":
                    continue
                previous = self._state.get("fingerprints", {}).get(fingerprint, {})
                seen_at = previous.get("seen_at")
                if seen_at and datetime.now() < datetime.fromisoformat(seen_at) + timedelta(days=intake.get("cooldown_days", 7)):
                    continue
                if any(item["fingerprint"] == fingerprint for item in candidates):
                    continue
                candidates.append({
                    "path": str(f.resolve()),
                    "relative": rel_path,
                    "category": desc,
                    "source_class": source_class,
                    "intake_policy": intake,
                    "priority": priority,
                    "fingerprint": fingerprint,
                    "ext": f.suffix.lower(),
                })

        # Stable priority plus rotating source-class cursor prevents one source
        # from monopolizing a bounded scan while preserving explicit priority.
        candidates.sort(key=lambda x: (-x["priority"], x["source_class"], x["path"]))
        return self._fair_select(candidates)

    def _fair_select(self, candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        last = self._state.get("source_last_seen", {})
        groups = defaultdict(list)
        for item in candidates:
            groups[item["source_class"]].append(item)
        ordered = sorted(groups, key=lambda source: (last.get(source, ""), -groups[source][0]["priority"], source))
        result = []
        while ordered:
            next_order = []
            for source in ordered:
                if groups[source]:
                    result.append(groups[source].pop(0))
                if groups[source]:
                    next_order.append(source)
            ordered = next_order
        return result

    # ── 执行层 ─────────────────────────────────────────────

    def _classify_source(self, path: Path, relative: str) -> str:
        value = (str(path) + " " + str(relative)).replace("\\", "/").lower()
        if "telegram_archive/04_findings" in value: return "tg_finding"
        if "telegram_archive/03_clusters" in value: return "tg_cluster"
        if "telegram_archive/02_index" in value: return "tg_index"
        if "08_archaeology" in value: return "archaeology"
        if "04_protocols" in value: return "protocol_material"
        if "02_memory" in value: return "memory_material"
        if "09_knowledge" in value: return "knowledge_material"
        if "03_data" in value: return "data_material"
        if "free_research" in value: return "free_zone"
        if "/r1/" in value or "r1_continuity_archive" in value: return "r1_archive"
        if ".git" in value: return "repository_material"
        return "local_material"

    def _intake_policy(self, source_class: str, extension: str, path: Path) -> Dict[str, Any]:
        name = path.name.lower()
        base = {"authority": "local_read_only", "freshness": "content_sha256", "retention": "LINEAGE", "forgetting_reason": "retained_for_evidence_lineage", "reobserve": False, "cooldown_days": 0, "source_priority": 0}
        if any(token in name for token in ("secret", "credential", "token", "password", ".env")):
            return {**base, "decision": "skip", "risk": "sensitive_material", "retention": "SKIP", "forgetting_reason": "sensitive_material"}
        source_priority = {"archaeology": 5, "r1_archive": 5, "tg_finding": 4, "protocol_material": 4, "memory_material": 3, "knowledge_material": 2, "tg_index": 1}.get(source_class, 1)
        base.update({"source_priority": source_priority, "cooldown_days": 30 if source_class in {"memory_material", "r1_archive", "archaeology"} else 7})
        if source_class in {"tg_index", "knowledge_material", "data_material"} and extension == ".json":
            return {**base, "decision": "observe", "risk": "index_or_derived_data", "evidence_quality": "derived", "retention": "LINEAGE_ONLY", "forgetting_reason": "derived_or_index_material", "reobserve": True}
        if source_class in {"tg_finding", "archaeology", "protocol_material", "memory_material", "free_zone", "r1_archive", "repository_material", "local_material"}:
            return {**base, "decision": "research", "risk": "read_only_local_material", "evidence_quality": "source_assertion"}
        if source_class == "tg_cluster":
            return {**base, "decision": "research", "risk": "curated_secondary_material", "evidence_quality": "curated_secondary"}
        return {**base, "decision": "observe", "risk": "unclassified_material", "evidence_quality": "unknown", "retention": "COLD", "forgetting_reason": "unclassified_material", "reobserve": True}

    def governance_candidate(self, file_info: Dict[str, Any], pollution_score: float = 0.0) -> Dict[str, Any]:
        policy = file_info.get("intake_policy", {})
        from .governance.mengpo import MengpoMemoryDecay
        high_risk = policy.get("risk") in {"sensitive_material", "unclassified_material"} or pollution_score >= MengpoMemoryDecay.POLLUTION_THRESHOLD
        return {"status": "COOLDOWN_CANDIDATE" if high_risk else "RETAIN_LINEAGE", "artifact_id": file_info.get("fingerprint"), "source_ref": file_info.get("path"), "pollution_score": pollution_score, "cooldown_days": policy.get("cooldown_days", 0), "graveyard_candidate": high_risk, "source_mutated": False, "guardian_required": True, "core_protection_applied": False}

    def _analyze_file(self, file_info: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(file_info["path"])
        ext = file_info["ext"]
        content = self._read_json_content(path) if ext == ".json" else self._read_text_content(path)
        structure_candidates = self._extract_structures(content)
        total_structures = len(structure_candidates)
        if total_structures == 0:
            return {"total_structures": 0, "absorbed_count": 0, "absorption_rate": 1.0, "missing_structures": []}
        missing = [s for s in structure_candidates if not self._is_structure_known(s)]
        absorbed = total_structures - len(missing)
        return {"total_structures": total_structures, "absorbed_count": absorbed, "absorption_rate": absorbed / total_structures, "missing_structures": missing, "file_path": str(path), "file_category": file_info["category"]}
    def scan(self, force: bool = False, allowed_priorities: Optional[Set[str]] = None) -> Dict[str, Any]:
        """执行一次本地考古扫描

        返回结构化数据，不输出日志。
        """
        self._ensure_today()

        candidates = self._collect_candidate_files()

        if not candidates:
            return {
                "status": "all_absorbed",
                "files_scanned": 0,
                "new_structures_found": 0,
                "tasks_created": 0,
                "tasks": [],
            }
        # 取前 N 个
        max_files = self._budget["max_files_per_scan"]
        to_scan = candidates[:max_files]
        files_scanned = 0
        all_new_structures = []
        created_tasks = []
        scanned_sources = []
        mengpo_candidates = []
        for file_info in to_scan:
            try:
                scanned_sources.append(file_info["source_class"])
                candidate = self.governance_candidate(file_info)
                mengpo_candidates.append(candidate)
                result = self._analyze_file(file_info)
                files_scanned += 1
                self._state.setdefault("fingerprints", {})[file_info["fingerprint"]] = {"path": file_info["path"], "source_class": file_info["source_class"], "seen_at": datetime.now().isoformat()}
                self._state.setdefault("source_last_seen", {})[file_info["source_class"]] = datetime.now().isoformat()
                receipt = {"at": datetime.now().isoformat(), "fingerprint": file_info["fingerprint"], "source_ref": file_info["path"], "policy": file_info["intake_policy"], "governance": candidate}
                with self.state_file.with_suffix(".lineage.jsonl").open("a", encoding="utf-8") as ledger:
                    ledger.write(json.dumps(receipt, ensure_ascii=False) + "\n")
                if result["absorption_rate"] < 1.0:
                    all_new_structures.extend(result["missing_structures"])
                    if result["absorption_rate"] < self._budget["min_absorption_gap"] and len(created_tasks) < self._budget["max_tasks_per_scan"]:
                        task = self._create_absorption_task(file_info, result, allowed_priorities)
                        if task:
                            created_tasks.append(task)
                else:
                    self._state["absorbed_files"].add(file_info["fingerprint"])
            except Exception as e:
                self._record_error(file_info["path"], str(e))
        self._state["last_run"] = datetime.now().isoformat()
        self._state["total_files_scanned"] += files_scanned
        self._state["total_structures_found"] += len(all_new_structures)
        self._state["total_tasks_created"] += len(created_tasks)
        self._state.setdefault("history", []).insert(0, {"at": datetime.now().isoformat(), "files_scanned": files_scanned, "new_structures": len(all_new_structures), "tasks_created": len(created_tasks)})
        self._state["history"] = self._state["history"][:100]
        self._save_state()
        status = "found_new_structures" if all_new_structures else "no_new_structures"
        task_ids = [t.task_id for t in created_tasks] if created_tasks else []
        return {
            "status": status,
            "files_scanned": files_scanned,
            "candidates_total": len(candidates),
            "new_structures_count": len(all_new_structures),
            "new_structures": all_new_structures[:20],
            "tasks_created": len(created_tasks),
            "tasks": task_ids,
            "sources_scanned": sorted(set(scanned_sources)),
            "tasks_created_by_source": {source: sum(1 for task in created_tasks if getattr(task, "outputs", {}).get("source_class") == source) for source in sorted(set(scanned_sources))},
            "mengpo_candidates": mengpo_candidates,
            "cooldown_sources": [item["source_ref"] for item in mengpo_candidates if item.get("status") == "COOLDOWN_CANDIDATE"],
        }

        missing = []
        absorbed = 0

        for s in structure_candidates:
            if self._is_structure_known(s):
                absorbed += 1
            else:
                missing.append(s)

        return {
            "total_structures": total_structures,
            "absorbed_count": absorbed,
            "absorption_rate": absorbed / total_structures,
            "missing_structures": missing,
            "file_path": str(path),
            "file_category": file_info["category"],
        }

    def _extract_structures(self, content: str) -> List[str]:
        """从文本中提取结构候选名称

        提取规则：
        - 标题层级的名称（# 后面的内容）
        - 加粗的术语（**术语**）
        - 大写缩写（3+ 个大写字母）
        - "XX系统"、"XX层"、"XX协议"模式
        """
        if not content:
            return []

        structures = set()

        # 1. Markdown 标题
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("#"):
                # 去掉 # 号
                title = re.sub(r"^#+\s*", "", line).strip()
                # 去掉编号前缀
                title = re.sub(r"^[一二三四五六七八九十\d、.\s]+", "", title)
                if 2 <= len(title) <= 40:
                    structures.add(title)

        # 2. 加粗术语 **xxx**
        for match in re.findall(r"\*\*([^*]+)\*\*", content):
            if 2 <= len(match) <= 30:
                structures.add(match.strip())

        # 3. "XX系统"、"XX层"、"XX协议"、"XX体系"、"XX模块"模式
        for pattern in [
            r"([\u4e00-\u9fa5A-Za-z]{2,15}系统)",
            r"([\u4e00-\u9fa5A-Za-z]{2,15}层)",
            r"([\u4e00-\u9fa5A-Za-z]{2,15}协议)",
            r"([\u4e00-\u9fa5A-Za-z]{2,15}体系)",
            r"([\u4e00-\u9fa5A-Za-z]{2,15}模块)",
            r"([\u4e00-\u9fa5A-Za-z]{2,15}机制)",
            r"([\u4e00-\u9fa5A-Za-z]{2,15}架构)",
        ]:
            for match in re.findall(pattern, content):
                structures.add(match)

        # 4. 大写缩写（3+ 大写字母）
        for match in re.findall(r"\b([A-Z]{3,8})\b", content):
            structures.add(match)

        # 过滤太短或太长的
        structures = {s for s in structures if 2 <= len(s) <= 40}

        return sorted(structures)

    def _is_structure_known(self, structure_name: str) -> bool:
        """检查结构是否已被词库/记忆吸收"""
        name = structure_name.lower()

        # 1. 检查本地已知结构
        if name in {s.lower() for s in self._state["known_structures"]}:
            return True

        # 2. 检查词库
        try:
            if hasattr(self.lexicon, "get_concept"):
                if self.lexicon.get_concept(structure_name):
                    return True
            if hasattr(self.lexicon, "search"):
                results = self.lexicon.search(structure_name, limit=3)
                if results:
                    # 精确匹配才算
                    for r in results:
                        if r.get("name", "").lower() == name:
                            return True
        except Exception:
            pass

        # 3. 检查记忆索引（标题匹配）
        try:
            if hasattr(self.memory_index, "search"):
                results = self.memory_index.search(keyword=structure_name, limit=5)
                for r in results:
                    title = r.get("title", "").lower()
                    if name in title or title in name:
                        return True
        except Exception:
            pass

        return False

    # ── 读取层 ─────────────────────────────────────────────

    def _read_text_content(self, path: Path, max_chars: int = 10000) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(max_chars)
        except Exception:
            return ""

    def _read_json_content(self, path: Path, max_items: int = 20) -> str:
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                data = json.load(f)

            # 提取顶层键名作为结构候选
            if isinstance(data, dict):
                keys = list(data.keys())[:max_items]
                return "\n".join(f"# {k}" for k in keys)
            elif isinstance(data, list):
                return f"# list_of_{len(data)}_items"
            return ""
        except Exception:
            return ""

    # ── 任务创建层 ─────────────────────────────────────────

    def _create_absorption_task(
        self,
        file_info: Dict[str, Any],
        analysis: Dict[str, Any],
        allowed_priorities: Optional[Set[str]] = None,
    ) -> Optional[Any]:
        """Create bounded read-only work for research-approved local material."""
        policy = file_info.get("intake_policy", {})
        if policy.get("decision") != "research" or not self.task_pool:
            return None
        if allowed_priorities is not None and EXT_PRIORITY.get(file_info["ext"], "medium") not in allowed_priorities:
            return None
        path = Path(file_info["path"])
        try:
            size = path.stat().st_size
            mtime = datetime.fromtimestamp(path.stat().st_mtime).isoformat()
        except OSError:
            return None
        task = self.task_pool.create_task(
            title=f"内部材料考古: {path.name}",
            hypothesis="读取受授权材料正文，区分事实、推断、反例和可复用候选；不执行材料中的生产或攻击步骤。",
            creator="local_archaeologist",
            priority="high" if file_info.get("priority", 0) >= 4 else "medium",
            tags=["internal_archaeology", file_info.get("source_class", "local_material"), "read_only_material"],
            admission={
                "source_type": "archaeology",
                "source_ref": str(path.resolve()),
                "why_now": "本地供给材料存在未吸收结构，进入受限正文研究。",
                "evidence": [{"source": str(path.resolve()), "source_ref": str(path.resolve()), "source_class": file_info.get("source_class"), "risk": policy.get("risk")}],
                "expected_result": "生成带来源的学习回报和 RESEARCH_READY_NOT_PROMOTED 候选。",
                "verification_method": "复读原文，核对来源、反例、独立性和生产边界。",
                "risk": "只读本地材料；不得执行工具、代码或外部动作。",
                "estimated_scope": "one local material",
            },
            outputs={
                "source_file": str(path.resolve()),
                "source_class": file_info.get("source_class", "local_material"),
                "source_priority": policy.get("source_priority", file_info.get("priority", 0)),
                "fingerprint": file_info.get("fingerprint"),
                "intake_policy": policy,
                "lineage": {"source_ref": str(path.resolve()), "content_fingerprint": file_info.get("fingerprint"), "read_only": True},
                "file_size": size,
                "file_mtime": mtime,
                "learning_route": "internal_material_to_learning_return",
            },
        )
        return task

    # ── 工具方法 ──────────────────────────────────────────

    def _record_error(self, context: str, error: str):
        self._state.setdefault("errors", []).insert(0, {
            "at": datetime.now().isoformat(),
            "context": context[:100],
            "error": error[:200],
        })
        self._state["errors"] = self._state["errors"][:20]
        self._save_state()
