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
from datetime import datetime, date
from typing import Dict, List, Any, Optional, Set


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
            "min_absorption_gap": 0.2,   # 吸收率低于80%才建任务
        }

        self._state = self._load_state()

    # ── state 层 ────────────────────────────────────────────

    def _load_state(self) -> dict:
        if self.state_file.exists():
            try:
                raw = json.loads(self.state_file.read_text(encoding="utf-8"))
                raw["absorbed_files"] = set(raw.get("absorbed_files", []))
                raw["known_structures"] = set(raw.get("known_structures", []))
                return raw
            except Exception:
                pass

        return {
            "version": 1,
            "last_run": None,
            "last_scan_date": None,
            "absorbed_files": set(),   # 已完全吸收的文件指纹
            "known_structures": set(), # 已知的结构名
            "total_files_scanned": 0,
            "total_tasks_created": 0,
            "total_structures_found": 0,
            "errors": [],
            "history": [],
        }

    def _save_state(self):
        save_data = dict(self._state)
        save_data["absorbed_files"] = list(save_data["absorbed_files"])
        save_data["known_structures"] = list(save_data["known_structures"])
        self.state_file.write_text(
            json.dumps(save_data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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
                    stat = f.stat()
                    fingerprint = f"{f.resolve()}|{stat.st_mtime}|{stat.st_size}"
                except Exception:
                    fingerprint = str(f.resolve())

                # 跳过已完全吸收的
                if fingerprint in self._state["absorbed_files"]:
                    continue

                candidates.append({
                    "path": str(f.resolve()),
                    "relative": rel_path,
                    "category": desc,
                    "priority": priority,
                    "fingerprint": fingerprint,
                    "ext": f.suffix.lower(),
                })

        # 按优先级排序（高优先级在前）
        candidates.sort(key=lambda x: -x["priority"])
        return candidates

    # ── 执行层 ─────────────────────────────────────────────

    def scan(self, force: bool = False) -> Dict[str, Any]:
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
        to_scan = candidates if force else candidates[:max_files]

        files_scanned = 0
        all_new_structures = []
        created_tasks = []

        for file_info in to_scan:
            try:
                result = self._analyze_file(file_info)
                files_scanned += 1

                if result["absorption_rate"] < 1.0:
                    all_new_structures.extend(result["missing_structures"])

                    # 吸收率低于阈值 → 创建考古任务
                    if result["absorption_rate"] < self._budget["min_absorption_gap"]:
                        if len(created_tasks) < self._budget["max_tasks_per_scan"]:
                            task = self._create_absorption_task(file_info, result)
                            if task:
                                created_tasks.append(task)
                else:
                    # 完全吸收 → 标记
                    self._state["absorbed_files"].add(file_info["fingerprint"])

            except Exception as e:
                self._record_error(file_info["path"], str(e))

        # 更新 state
        self._state["last_run"] = datetime.now().isoformat()
        self._state["total_files_scanned"] += files_scanned
        self._state["total_structures_found"] += len(all_new_structures)
        self._state["total_tasks_created"] += len(created_tasks)

        # 去重已知结构
        for s in all_new_structures:
            self._state["known_structures"].add(s.lower())

        # 历史记录
        self._state.setdefault("history", []).insert(0, {
            "at": datetime.now().isoformat(),
            "files_scanned": files_scanned,
            "new_structures": len(all_new_structures),
            "tasks_created": len(created_tasks),
        })
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
        }

    # ── 分析层 ─────────────────────────────────────────────

    def _analyze_file(self, file_info: Dict[str, Any]) -> Dict[str, Any]:
        """分析单个文件的吸收状态"""
        path = Path(file_info["path"])
        ext = file_info["ext"]

        if ext == ".json":
            content = self._read_json_content(path)
        elif ext in (".md", ".txt"):
            content = self._read_text_content(path)
        else:
            content = ""

        # 提取结构候选
        structure_candidates = self._extract_structures(content)

        # 计算吸收率
        total_structures = len(structure_candidates)
        if total_structures == 0:
            return {
                "total_structures": 0,
                "absorbed_count": 0,
                "absorption_rate": 1.0,
                "missing_structures": [],
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
    ) -> Optional[Any]:
        """创建吸收任务"""
        if not self.task_pool:
            return None

        path = Path(file_info["path"])
        missing = analysis["missing_structures"]
        rate = analysis["absorption_rate"]

        title = f"本地考古吸收: {path.name}"
        hypothesis = (
            f"该文件（{file_info['category']}）吸收率仅 {rate:.0%}，"
            f"有 {len(missing)} 个结构未被词库/记忆吸收："
            f"{', '.join(missing[:8])}。需要深入考古和吸收。"
        )

        priority = "high" if rate < 0.3 else "medium"

        try:
            task = self.task_pool.create_task(
                title=title,
                hypothesis=hypothesis,
                creator="local_archaeologist",
                priority=priority,
                tags=[
                    "local_archaeology",
                    "absorption",
                    f"category:{file_info['category']}",
                    f"rate_{rate:.0f}",
                ],
            )
            if task:
                task.outputs = {
                    "source_file": str(path),
                    "absorption_rate": rate,
                    "total_structures": analysis["total_structures"],
                    "missing_structures": missing[:20],
                }
                self.task_pool.update_task(task)
                return task
        except Exception:
            pass

        return None

    # ── 工具方法 ──────────────────────────────────────────

    def _record_error(self, context: str, error: str):
        self._state.setdefault("errors", []).insert(0, {
            "at": datetime.now().isoformat(),
            "context": context[:100],
            "error": error[:200],
        })
        self._state["errors"] = self._state["errors"][:20]
        self._save_state()
