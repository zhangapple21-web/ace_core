"""
ProtocolLRUCache — 协议解包 LRU 缓存

相同输入直接返回缓存结果，避免重复解包。
默认 1000 条，达到上限淘汰最旧条目。

缓存键：data 的 SHA256 前 32 位 + handler name
"""

import hashlib
from collections import OrderedDict
from typing import Optional, Tuple
from .base import UnpackResult


class ProtocolLRUCache:
    """
    LRU 缓存 — 协议解包结果缓存

    淘汰策略：最久未使用（Least Recently Used）
    线程安全：单线程模型，不加锁
    """

    def __init__(self, max_size: int = 1000):
        self.max_size = max_size
        self._cache: OrderedDict[str, UnpackResult] = OrderedDict()
        self._hits = 0
        self._misses = 0

    def get(self, data: bytes, handler_name: str) -> Optional[UnpackResult]:
        """
        获取缓存

        Returns:
            UnpackResult if cached, None otherwise
        """
        key = self._make_key(data, handler_name)
        if key in self._cache:
            self._cache.move_to_end(key)
            self._hits += 1
            result = self._cache[key]
            result.cached = True
            return result
        self._misses += 1
        return None

    def put(self, data: bytes, handler_name: str, result: UnpackResult) -> None:
        """存入缓存"""
        key = self._make_key(data, handler_name)
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self.max_size:
                self._cache.popitem(last=False)
        self._cache[key] = result

    def clear(self) -> None:
        """清空缓存"""
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def get_stats(self) -> dict:
        """获取缓存统计"""
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "utilization": len(self._cache) / self.max_size if self.max_size > 0 else 0,
        }

    @staticmethod
    def _make_key(data: bytes, handler_name: str) -> str:
        """生成缓存键"""
        data_hash = hashlib.sha256(data).hexdigest()[:32]
        return f"{handler_name}:{data_hash}"
