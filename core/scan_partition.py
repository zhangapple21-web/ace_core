"""
扫描分区表 — ScanPartition

定义扫描优先级，减少不必要的IO。

高频区：每次扫描都检查
中频区：每N次扫描检查一次
低频区：仅首次扫描检查

不破坏 scan = truth 原则：
- 索引丢失时，回退到全量扫描
- 分区表损坏时，按默认优先级扫描
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime


# 默认分区配置
DEFAULT_PARTITION = {
    "high_frequency": [
        "task_pool/pending",
        "task_pool/active",
        "06_RUNTIME/ace/data/memory",
        "08_ARCHAEOLOGY",
    ],
    "medium_frequency": [
        "02_MEMORY/research",
        "09_KNOWLEDGE",
        "04_PROTOCOLS",
    ],
    "low_frequency": [
        "02_MEMORY/daily",
        "03_DATA",
        "telegram_archive",
    ],
    "skip": [
        ".git",
        "__pycache__",
        "node_modules",
        "venv",
    ],
    # 扫描频率控制
    "scan_interval": {
        "high": 1,      # 每次扫描
        "medium": 3,    # 每3次扫描
        "low": 10,      # 每10次扫描
    },
}


class ScanPartition:
    """
    扫描分区表 — 定义优先级，减少IO
    
    使用方式：
        partition = ScanPartition(base_dir)
        dirs_to_scan = partition.get_scan_dirs(scan_count=5)
    """
    
    def __init__(self, base_dir: str, config_file: Optional[str] = None):
        self.base_dir = Path(base_dir)
        
        if config_file:
            self.config_file = Path(config_file)
        else:
            self.config_file = self.base_dir / "06_RUNTIME" / "ace" / "data" / "scan_partition.json"
        
        self.partition: Dict[str, Any] = {}
        self._load()
    
    def _load(self):
        """加载分区配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    self.partition = json.load(f)
            except Exception:
                self.partition = DEFAULT_PARTITION
        else:
            self.partition = DEFAULT_PARTITION
            self._save()
    
    def _save(self):
        """保存分区配置"""
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(self.partition, f, ensure_ascii=False, indent=2)
    
    def get_scan_dirs(self, scan_count: int = 1) -> Dict[str, List[Path]]:
        """
        根据扫描计数返回当前应该扫描的目录
        
        Args:
            scan_count: 当前扫描次数（用于频率控制）
        
        Returns:
            {
                "high": [...],   # 高频区路径
                "medium": [...], # 中频区路径（仅当满足频率时）
                "low": [...],    # 低频区路径（仅当满足频率时）
            }
        """
        intervals = self.partition.get("scan_interval", DEFAULT_PARTITION["scan_interval"])
        result = {
            "high": [],
            "medium": [],
            "low": [],
        }
        
        # 高频区：每次扫描
        for rel in self.partition.get("high_frequency", []):
            abs_path = self.base_dir / rel
            if abs_path.exists():
                result["high"].append(abs_path)
        
        # 中频区：每N次扫描
        if scan_count % intervals.get("medium", 3) == 0:
            for rel in self.partition.get("medium_frequency", []):
                abs_path = self.base_dir / rel
                if abs_path.exists():
                    result["medium"].append(abs_path)
        
        # 低频区：每N次扫描
        if scan_count % intervals.get("low", 10) == 0:
            for rel in self.partition.get("low_frequency", []):
                abs_path = self.base_dir / rel
                if abs_path.exists():
                    result["low"].append(abs_path)
        
        return result
    
    def should_skip(self, path: Path) -> bool:
        """判断路径是否应该跳过"""
        path_str = str(path)
        for skip_pattern in self.partition.get("skip", []):
            if skip_pattern in path_str:
                return True
        return False
    
    def get_priority(self, rel_path: str) -> int:
        """
        获取路径的扫描优先级
        
        Returns:
            0 = 高频
            1 = 中频
            2 = 低频
            3 = 跳过
        """
        if any(s in rel_path for s in self.partition.get("skip", [])):
            return 3
        
        if rel_path in self.partition.get("high_frequency", []):
            return 0
        elif rel_path in self.partition.get("medium_frequency", []):
            return 1
        elif rel_path in self.partition.get("low_frequency", []):
            return 2
        
        # 未定义的路径，默认中频
        return 1
    
    def get_stats(self) -> Dict[str, Any]:
        """获取分区统计"""
        return {
            "high_dirs": len(self.partition.get("high_frequency", [])),
            "medium_dirs": len(self.partition.get("medium_frequency", [])),
            "low_dirs": len(self.partition.get("low_frequency", [])),
            "skip_patterns": len(self.partition.get("skip", [])),
            "scan_intervals": self.partition.get("scan_interval", {}),
        }