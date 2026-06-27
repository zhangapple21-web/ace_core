"""
碎片索引 — FragmentIndex

持久化记录已扫描过的文件指纹，避免重复考古。

不是文件内容索引。
是"见过没见过"的索引。

指纹策略：
  - 文件路径 + 文件大小 + 修改时间
  - 三者全匹配 = 已见过，跳过
  - 任一变化 = 新碎片，重新考古

存储：
  - 02_FRAGMENT_INDEX/fragment_index.json
  - 结构：{ file_path: {size, mtime, first_seen, last_checked, status} }
"""

import json
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Set, Tuple


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
        if key in self.index:
            self.index[key]["size"] = size
            self.index[key]["mtime"] = mtime
            self.index[key]["last_checked"] = now
            self.index[key]["status"] = status
        else:
            self.index[key] = {
                "size": size,
                "mtime": mtime,
                "first_seen": now,
                "last_checked": now,
                "status": status,
            }
        self._save()

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
