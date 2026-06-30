"""
ProtocolVersionManager — 协议版本管理

记录每个协议的版本号，版本变更时自动触发重新狩猎。

设计原则：
  - 版本变更 = 协议演化，需要重新验证和学习
  - 版本记录存在 JSON 文件中，便于查看和回溯
  - 支持版本对比，快速定位变更点
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class ProtocolVersionManager:
    """
    协议版本管理器

    功能：
      - 注册协议及其版本
      - 检测版本变更
      - 记录版本历史
      - 版本变更触发重新狩猎标记
    """

    def __init__(self, version_file: str):
        self.version_file = Path(version_file)
        self.version_file.parent.mkdir(parents=True, exist_ok=True)
        self._versions: Dict[str, Dict] = {}
        self._history: List[Dict] = []
        self._load()

    def register(self, protocol: str, version: str, handler: str = "",
                 notes: str = "") -> Dict[str, Any]:
        """
        注册或更新协议版本

        Returns:
            {changed: bool, old_version, new_version, needs_rehunt}
        """
        old = self._versions.get(protocol)
        old_version = old.get("version", "0.0.0") if old else "0.0.0"
        changed = old_version != version

        if changed:
            history_entry = {
                "protocol": protocol,
                "old_version": old_version,
                "new_version": version,
                "handler": handler,
                "notes": notes,
                "timestamp": datetime.now().isoformat(),
            }
            self._history.append(history_entry)
            self._versions[protocol] = {
                "version": version,
                "handler": handler,
                "first_seen": old.get("first_seen", datetime.now().isoformat()) if old else datetime.now().isoformat(),
                "last_updated": datetime.now().isoformat(),
                "update_count": (old.get("update_count", 0) + 1) if old else 1,
            }
            self._save()
            logger.info(f"[Version] 协议 {protocol} 版本变更: {old_version} → {version}")

        return {
            "changed": changed,
            "old_version": old_version,
            "new_version": version,
            "needs_rehunt": changed,  # 版本变更 = 需要重新狩猎
        }

    def get_version(self, protocol: str) -> Optional[str]:
        """获取协议版本"""
        info = self._versions.get(protocol)
        return info.get("version") if info else None

    def get_all_versions(self) -> Dict[str, str]:
        """获取所有协议版本"""
        return {k: v["version"] for k, v in self._versions.items()}

    def get_history(self, protocol: Optional[str] = None,
                    limit: int = 20) -> List[Dict]:
        """获取版本历史"""
        if protocol:
            return [h for h in self._history if h["protocol"] == protocol][-limit:]
        return self._history[-limit:]

    def needs_rehunt(self, protocol: str, current_version: str) -> bool:
        """检查是否需要重新狩猎（版本是否变更）"""
        registered = self.get_version(protocol)
        if registered is None:
            return True  # 新协议，需要狩猎
        return registered != current_version

    def get_stats(self) -> Dict[str, Any]:
        """获取统计"""
        return {
            "total_protocols": len(self._versions),
            "total_updates": sum(v.get("update_count", 0) for v in self._versions.values()),
            "history_entries": len(self._history),
        }

    def _load(self):
        if not self.version_file.exists():
            return
        try:
            with open(self.version_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self._versions = data.get("versions", {})
                self._history = data.get("history", [])
        except Exception as e:
            logger.warning(f"[Version] 版本文件加载失败: {e}")

    def _save(self):
        try:
            with open(self.version_file, "w", encoding="utf-8") as f:
                json.dump({
                    "versions": self._versions,
                    "history": self._history,
                    "last_updated": datetime.now().isoformat(),
                }, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"[Version] 版本文件保存失败: {e}")
