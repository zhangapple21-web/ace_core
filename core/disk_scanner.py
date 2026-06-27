"""
磁盘扫描器（Disk Scanner）— 万物皆可切 + JSON 结构分析

主动扫描本地磁盘上的材料，用系统自己的语言结构进行分类和索引。
不是被动等待输入，而是主动寻找养料。

v2 新增：JSON 结构自动解析，对比词库识别新增协议/分类。

设计原则：
- 只读，不修改源文件
- 只记录结构和摘要，不泄露敏感内容
- 用Lexicon进行自动分类
- 扫描结果进Memory Index，可检索可追溯
"""

import os
import json
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any
from collections import Counter

from .identity import Identity
from .lexicon import Lexicon
from .memory_index import MemoryIndex


class DiskScanner:
    """磁盘扫描器 — 主动发现和分类本地材料"""

    SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".tox", ".egg-info", ".idea", ".vscode",
        "Cache", "cache", "Caches", "caches",
        "temp", "tmp", "Temp", "Tmp",
        "logs", "Log", "Logs",
        "$Recycle.Bin", "System Volume Information",
    }

    INTERESTING_EXTENSIONS = {
        ".md", ".txt", ".json", ".py", ".js", ".ts", ".html", ".css",
        ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
        ".csv", ".log",
    }

    def __init__(
        self,
        identity: Identity,
        lexicon: Lexicon,
        memory_index: MemoryIndex,
    ):
        self.identity = identity
        self.lexicon = lexicon
        self.memory_index = memory_index

    def scan_path(
        self,
        root_path: str,
        max_depth: int = 3,
        max_files: int = 200,
        auto_index: bool = True,
    ) -> Dict[str, Any]:
        """
        扫描一个路径下的文件和目录。
        返回扫描结果摘要。
        """
        root = Path(root_path)
        if not root.exists():
            return {"error": f"路径不存在: {root_path}", "found": 0}

        results = {
            "root": str(root),
            "scanned_at": datetime.now().isoformat(),
            "max_depth": max_depth,
            "directories": 0,
            "files": 0,
            "by_extension": {},
            "interesting_files": [],
            "skipped_dirs": 0,
            "indexed_count": 0,
        }

        file_count = 0
        for dirpath, dirnames, filenames in os.walk(root):
            current_depth = len(Path(dirpath).relative_to(root).parts)
            if current_depth >= max_depth:
                dirnames[:] = []
                continue

            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]
            results["skipped_dirs"] += len([d for d in dirnames if d in self.SKIP_DIRS])

            results["directories"] += len(dirnames)

            for fname in filenames:
                if file_count >= max_files:
                    break

                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()

                results["files"] += 1
                results["by_extension"][ext] = results["by_extension"].get(ext, 0) + 1

                if ext in self.INTERESTING_EXTENSIONS:
                    try:
                        size = fpath.stat().st_size
                    except Exception:
                        size = 0

                    file_info = {
                        "path": str(fpath),
                        "name": fname,
                        "extension": ext,
                        "size": size,
                        "depth": current_depth,
                    }
                    results["interesting_files"].append(file_info)

                    if auto_index and size < 500 * 1024:
                        try:
                            content = fpath.read_text(encoding="utf-8", errors="ignore")
                            title = f"{fname} ({fpath.parent.name})"
                            classifications = self.lexicon.classify(content[:2000])
                            category = classifications[0]["category"] if classifications else "未分类"
                            tags = [c["name"] for c in classifications[:3]]

                            memory_type = "file_scan"
                            extra_content = content[:2000]

                            if ext == ".json" and size < 2 * 1024 * 1024:
                                json_analysis = self._analyze_json_file(fpath, content)
                                if json_analysis:
                                    memory_type = "json_structure"
                                    extra_content = self._format_json_analysis(json_analysis, content)
                                    tags.extend(json_analysis.get("new_category_tags", []))
                                    tags = list(set(tags))[:8]

                                    for new_concept in json_analysis.get("new_concepts", []):
                                        if not self.lexicon.get_concept(new_concept):
                                            self.lexicon.add_concept(
                                                name=new_concept,
                                                definition=json_analysis["new_concepts"][new_concept],
                                                category="考古发现",
                                                source="disk_scanner:json",
                                                importance=60,
                                            )

                            self.memory_index.add(
                                title=title,
                                content=extra_content,
                                memory_type=memory_type,
                                category=category,
                                source="disk_scan",
                                source_path=str(fpath),
                                tags=tags,
                            )
                            results["indexed_count"] += 1
                        except Exception:
                            pass

                    file_count += 1

            if file_count >= max_files:
                break

        results["interesting_count"] = len(results["interesting_files"])
        return results

    def scan_mine_seed(self, mine_seed_path: str) -> Dict[str, Any]:
        """专门扫描mine-seed风格的项目结构"""
        return self.scan_path(mine_seed_path, max_depth=4, max_files=300)

    def _analyze_json_file(self, fpath: Path, raw_content: str) -> Optional[Dict[str, Any]]:
        """解析 JSON 文件，提取结构特征并对比词库"""
        try:
            data = json.loads(raw_content)
        except Exception:
            return None

        analysis = {
            "path": str(fpath),
            "name": fpath.name,
            "top_keys": [],
            "nested_keys": [],
            "types": Counter(),
            "arrays": [],
            "depth": 0,
            "size_bytes": len(raw_content),
            "has_known_structure": False,
            "new_concepts": {},
            "new_category_tags": [],
            "structure_type": "unknown",
        }

        def inspect(obj, prefix: str = "", depth: int = 0):
            analysis["depth"] = max(analysis["depth"], depth)
            if isinstance(obj, dict):
                for key, value in list(obj.items())[:30]:
                    full_key = f"{prefix}.{key}" if prefix else key
                    if depth == 0:
                        analysis["top_keys"].append(key)
                    else:
                        analysis["nested_keys"].append(full_key)
                    analysis["types"][type(value).__name__] += 1
                    if isinstance(value, list):
                        arr_info = {"key": full_key, "length": len(value)}
                        if value and isinstance(value[0], dict):
                            arr_info["item_keys"] = list(value[0].keys())[:10] if isinstance(value[0], dict) else []
                        analysis["arrays"].append(arr_info)
                    elif isinstance(value, dict) and depth < 3:
                        inspect(value, full_key, depth + 1)
                    elif isinstance(value, str) and depth < 2:
                        if len(value) > 5:
                            analysis["types"]["string_values"] += 1

        inspect(data)
        analysis["top_keys"] = analysis["top_keys"][:30]
        analysis["nested_keys"] = analysis["nested_keys"][:50]

        if analysis["top_keys"]:
            known_structures = {
                "slices": "代码切片集", "core_data": "核心数据集",
                "persona_matrix": "人格矩阵", "lexicon": "词库",
                "memory": "记忆库", "config": "配置文件",
                "settings": "设置", "metadata": "元数据",
                "executor": "执行器", "identity": "身份系统",
                "shadow": "影子层", "kernel": "内核",
                "constraints": "约束集", "protocols": "协议集",
                "routes": "路由表",
            }
            for key, label in known_structures.items():
                if key in [k.lower() for k in analysis["top_keys"]]:
                    analysis["has_known_structure"] = True
                    break

        existing_concepts = {c["name"] for c in self.lexicon.list_concepts(limit=2000)}
        potential_concepts = []
        for key in analysis["top_keys"]:
            clean_key = re.sub(r"[^a-zA-Z0-9_\u4e00-\u9fff]", "", key)
            if clean_key and clean_key not in existing_concepts and len(clean_key) >= 3:
                if not clean_key[0].isdigit():
                    potential_concepts.append(clean_key)

        for concept in potential_concepts[:20]:
            generic_terms = {
                "metadata", "content", "timestamp", "date", "time", "created", "updated",
                "modified", "version", "status", "name", "type", "id", "key", "value",
                "data", "result", "error", "message", "description", "title", "text",
                "author", "user", "email", "phone", "url", "link", "path", "file",
                "size", "length", "count", "total", "page", "index", "offset", "limit",
                "sort", "order", "filter", "query", "search", "config", "settings",
                "options", "params", "args", "body", "header", "headers", "method",
                "code", "status", "success", "failed", "enabled", "disabled", "active",
                "items", "list", "array", "children", "parent", "root", "nodes", "edges",
            }
            if concept.lower() in generic_terms:
                continue

            for pattern, ptype in [(r"^[a-z][a-z_]+$", "snake_case"), (r"^[A-Z][a-z]+(?:[A-Z][a-z]+)+$", "CamelCase"), (r"^[A-Z_]+$", "ALL_CAPS")]:
                if re.match(pattern, concept):
                    analysis["new_concepts"][concept] = f"JSON结构字段（{ptype}），来自{fpath.name}，类型: {dict(analysis['types'])}"
                    analysis["new_category_tags"].append(concept)
                    break

        if len(analysis["top_keys"]) >= 5 and not analysis["has_known_structure"]:
            analysis["structure_type"] = "unknown_complex"
        elif analysis["has_known_structure"]:
            analysis["structure_type"] = "known"
        elif len(analysis["top_keys"]) <= 3:
            analysis["structure_type"] = "simple_config"
        elif analysis["arrays"]:
            analysis["structure_type"] = "data_collection"
        else:
            analysis["structure_type"] = "nested_config"

        return analysis

    def _format_json_analysis(self, analysis: Dict, raw_content: str) -> str:
        """把 JSON 分析结果格式化为可读的文本摘要"""
        lines = []
        lines.append(f"【JSON 结构分析】{analysis['path']}")
        lines.append(f"结构类型: {analysis['structure_type']}")
        lines.append(f"顶层键 ({len(analysis['top_keys'])}): {', '.join(analysis['top_keys'][:15])}")
        if analysis["arrays"]:
            lines.append(f"数组字段:")
            for arr in analysis["arrays"][:5]:
                item_keys = arr.get("item_keys", [])
                if item_keys:
                    lines.append(f"  - {arr['key']}: 数组[{arr['length']}项]，字段: {', '.join(item_keys[:8])}")
                else:
                    lines.append(f"  - {arr['key']}: 数组[{arr['length']}项]")
        if analysis["new_concepts"]:
            lines.append(f"新增概念候选:")
            for concept, desc in list(analysis["new_concepts"].items())[:10]:
                lines.append(f"  - {concept}: {desc[:80]}")
        lines.append(f"\n【原始内容摘要】")
        lines.append(raw_content[:1500])
        return "\n".join(lines)

    def find_fragment_files(
        self,
        root_path: str,
        keywords: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        查找可能的碎片文件。
        碎片特征：文件名含碎片/fragment/碎片/新建/未命名/temp等
        """
        default_keywords = [
            "碎片", "fragment", "新建", "未命名", "temp", "tmp",
            "草稿", "draft", "笔记", "note", "记录", "record",
            "考古", "archaeology", "r1", "R1", "研究", "research",
        ]
        kws = keywords or default_keywords

        results = []
        root = Path(root_path)
        if not root.exists():
            return results

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in self.SKIP_DIRS]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()
                if ext not in self.INTERESTING_EXTENSIONS:
                    continue

                name_lower = fname.lower()
                if any(kw.lower() in name_lower for kw in kws):
                    try:
                        size = fpath.stat().st_size
                    except Exception:
                        size = 0
                    results.append({
                        "path": str(fpath),
                        "name": fname,
                        "size": size,
                        "matched_keywords": [
                            kw for kw in kws if kw.lower() in name_lower
                        ],
                    })

        return results
