"""
碎片索引 — FragmentIndex

持久化记录已扫描过的文件指纹，避免重复考古。

不是文件内容索引。
是"见过没见过"的索引。

指纹策略：
  - 文件路径 + 文件大小 + 修改时间
  - 三者全匹配 = 已见过，跳过
  - 任一变化 = 新碎片，重新考古

主题标签：
  - 从文件路径自动提取
  - 基于目录结构和文件名关键词
  - 用于"按主题搜索"而非"按关键词搜索"

存储：
  - 02_FRAGMENT_INDEX/fragment_index.json
  - 结构：{ file_path: {size, mtime, first_seen, last_checked, status, topics} }
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Tuple
import re


# 主题关键词映射表
TOPIC_KEYWORDS = {
    "task": ["task", "任务", "派单", "调度", "queue", "pending", "active"],
    "memory": ["memory", "记忆", "索引", "index", "lexicon", "词库", "概念"],
    "archaeology": ["archaeology", "考古", "fragment", "碎片", "scan", "发现"],
    "protocol": ["protocol", "协议", "constraint", "约束", "rule", "规则"],
    "runtime": ["runtime", "运行", "daemon", "worker", "executor", "执行"],
    "sync": ["sync", "同步", "git", "backup", "备份", "push", "pull"],
    "health": ["health", "健康", "check", "检查", "monitor", "监控"],
    "config": ["config", "配置", "setting", "env", "环境"],
    "experience": ["experience", "经验", "lesson", "教训", "deposition"],
    "r1": ["r1", "r2", "r3", "ruin", "遗迹", "废墟", "survivor", "幸存者"],
    "eco": ["eco", "生态", "layer", "层", "narrative", "叙事", "behavior"],
    "api": ["api", "接口", "gateway", "bridge", "桥接"],
    "security": ["security", "安全", "guardian", "守护", "shadow", "影子"],
    "business": ["business", "业务", "客户", "培训", "话术", "策略"],
    "engineering": ["engineering", "工程", "python", "script", "脚本"],
    "knowledge": ["knowledge", "知识", "knowledge_base", "知识库"],
    "observation": ["observation", "观察", "observer", "runtime_observer"],
}


class FragmentIndex:
    """
    碎片索引 — 记住哪些文件已经考古过了

    设计原则：
    - 慢启动：第一次扫描全量标记，不一次性建任务
    - 增量感知：每次只处理新出现/新变化的文件
    - 持久化：重启不丢历史
    """

    def __init__(self, index_dir: str):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.index_file = self.index_dir / "fragment_index.json"
        self.index: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self):
        if self.index_file.exists():
            try:
                with open(self.index_file, "r", encoding="utf-8") as f:
                    self.index = json.load(f)
            except Exception:
                self.index = {}

    def _save(self):
        tmp = self.index_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=2)
        tmp.replace(self.index_file)

    def _fingerprint(self, path: Path) -> Tuple[int, float]:
        st = path.stat()
        return st.st_size, st.st_mtime

    def is_known(self, path: Path) -> bool:
        key = str(path.resolve())
        if key not in self.index:
            return False
        try:
            size, mtime = self._fingerprint(path)
        except Exception:
            return True
        rec = self.index[key]
        return rec.get("size") == size and abs(rec.get("mtime", 0) - mtime) < 0.001

    def mark_seen(self, path: Path, status: str = "seen"):
        key = str(path.resolve())
        try:
            size, mtime = self._fingerprint(path)
        except Exception:
            return
        now = datetime.now().isoformat()
        
        # 自动提取主题标签
        topics = self._extract_topics(path)
        
        if key in self.index:
            self.index[key]["size"] = size
            self.index[key]["mtime"] = mtime
            self.index[key]["last_checked"] = now
            self.index[key]["status"] = status
            # 合并主题标签（不覆盖已有的）
            existing_topics = set(self.index[key].get("topics", []))
            existing_topics.update(topics)
            self.index[key]["topics"] = list(existing_topics)
        else:
            self.index[key] = {
                "size": size,
                "mtime": mtime,
                "first_seen": now,
                "last_checked": now,
                "status": status,
                "topics": topics,
            }
        self._save()
    
    def _extract_topics(self, path: Path) -> List[str]:
        """从路径提取主题标签"""
        path_str = str(path).lower()
        topics = []
        
        for topic, keywords in TOPIC_KEYWORDS.items():
            for kw in keywords:
                if kw in path_str:
                    topics.append(topic)
                    break
        
        # 从目录结构推断
        parts = path.parts
        for part in parts:
            part_lower = part.lower()
            # 特殊目录映射
            if "task" in part_lower or "派单" in part_lower:
                topics.append("task")
            elif "memory" in part_lower or "记忆" in part_lower:
                topics.append("memory")
            elif "archaeology" in part_lower or "考古" in part_lower:
                topics.append("archaeology")
            elif "protocol" in part_lower or "协议" in part_lower:
                topics.append("protocol")
            elif "ops" in part_lower or "运维" in part_lower:
                topics.append("health")
        
        # 去重
        return list(set(topics))
    
    def get_by_topic(self, topic: str) -> List[Dict[str, Any]]:
        """获取指定主题的所有文件"""
        results = []
        for path_str, rec in self.index.items():
            topics = rec.get("topics", [])
            if topic in topics:
                results.append({
                    "path": path_str,
                    "status": rec.get("status"),
                    "last_checked": rec.get("last_checked"),
                })
        return results
    
    def get_all_topics(self) -> Dict[str, int]:
        """获取所有主题及其文件数量"""
        topic_count: Dict[str, int] = {}
        for rec in self.index.values():
            for topic in rec.get("topics", []):
                topic_count[topic] = topic_count.get(topic, 0) + 1
        return topic_count

    def mark_archaeologized(self, path: Path, task_id: str = ""):
        key = str(path.resolve())
        if key in self.index:
            self.index[key]["status"] = "archaeologized"
            self.index[key]["task_id"] = task_id
            self.index[key]["last_checked"] = datetime.now().isoformat()
            self._save()

    def get_stats(self) -> Dict[str, Any]:
        total = len(self.index)
        by_status: Dict[str, int] = {}
        for rec in self.index.values():
            s = rec.get("status", "seen")
            by_status[s] = by_status.get(s, 0) + 1
        return {
            "total": total,
            "by_status": by_status,
        }
