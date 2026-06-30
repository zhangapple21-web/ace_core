"""
ProtocolRegistry + FallbackChain — 协议注册表 + 降级链

降级策略（从高到低）：
  Level 0: 最优解（RPC 注入 / 完整解包）
  Level 1: 二级降级（Unidbg 模拟执行）
  Level 2: 三级降级（静态分析 / 字段提取）
  Level 3: 兜底（返回原始数据 + 未解包标记）

每个 handler 自己声明 fallback_level，
注册表按优先级排序，从上到下尝试，直到成功或全部失败。
"""

import logging
from typing import List, Optional, Dict, Any
from .base import ProtocolHandler, UnpackResult
from .cache import ProtocolLRUCache

logger = logging.getLogger(__name__)


class FallbackChain:
    """
    降级链 — 按优先级尝试多个 handler，直到成功

    设计原则：
      - 每个 handler 声明自己的 fallback_level
      - 从 level 0 开始尝试，逐级降级
      - 每一级失败了才试下一级
      - 全部失败返回兜底结果（原始数据 + 标记）
    """

    def __init__(self, handlers: Optional[List[ProtocolHandler]] = None):
        self._handlers: List[ProtocolHandler] = []
        if handlers:
            for h in handlers:
                self.add_handler(h)

    def add_handler(self, handler: ProtocolHandler) -> None:
        """添加 handler，按 priority 排序（数值小的在前）"""
        self._handlers.append(handler)
        self._handlers.sort(key=lambda h: h.priority)

    def identify(self, data: bytes) -> Optional[ProtocolHandler]:
        """找到第一个能处理的 handler"""
        for handler in self._handlers:
            try:
                if handler.identify(data):
                    return handler
            except Exception as e:
                logger.warning(f"[Fallback] identify 识别失败 {handler.name}: {e}")
        return None

    def unpack(self, data: bytes) -> UnpackResult:
        """
        按降级链顺序尝试解包

        优先级最高的先试，失败了试下一个，
        全部失败返回兜底结果。
        """
        last_error = ""
        last_level = -1

        for handler in self._handlers:
            try:
                if not handler.identify(data):
                    continue
                result = handler.unpack(data)
                if result.success:
                    return result
                last_error = result.error or "unknown"
                last_level = result.fallback_level
            except Exception as e:
                    logger.warning(f"[Fallback] {handler.name} 解包失败: {e}")
                    last_error = str(e)
                    last_level = getattr(handler, 'priority', 999)

        # 全部失败，兜底
        return UnpackResult.fail(
            error=f"所有降级链耗尽: {last_error}",
            protocol="unknown",
            handler="fallback_bottom",
            fallback_level=99,
            raw_size=len(data),
        )

    def get_handlers(self) -> List[Dict[str, Any]]:
        """获取所有 handler 信息"""
        return [h.get_info() for h in self._handlers]


class ProtocolRegistry:
    """
    协议注册表 — 管理所有协议 handler

    功能：
      - 注册 handler
      - 按协议名查找
      - 自动识别 + 解包
      - LRU 缓存
      - 降级链
    """

    def __init__(self, cache_size: int = 1000):
        self._handlers: Dict[str, ProtocolHandler] = {}
        self._chains: Dict[str, FallbackChain] = {}
        self._all_chain = FallbackChain()
        self.cache = ProtocolLRUCache(max_size=cache_size)
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "successful_unpacks": 0,
            "failed_unpacks": 0,
            "fallback_triggers": 0,
        }

    def register(self, handler: ProtocolHandler, protocol: Optional[str] = None) -> None:
        """
        注册一个协议 handler

        Args:
            handler: 协议处理器
            protocol: 协议名，默认用 handler.protocol
        """
        proto = protocol or handler.protocol
        self._handlers[handler.name] = handler

        # 加入全局降级链
        self._all_chain.add_handler(handler)

        # 每个协议有自己的降级链
        if proto not in self._chains:
            self._chains[proto] = FallbackChain()
        self._chains[proto].add_handler(handler)

        logger.info(f"[Registry] 注册协议处理器: {handler.name} ({proto}, priority={handler.priority}")

    def get_handler(self, name: str) -> Optional[ProtocolHandler]:
        """按名称获取 handler"""
        return self._handlers.get(name)

    def identify(self, data: bytes) -> Optional[str]:
        """识别数据对应的协议名"""
        handler = self._all_chain.identify(data)
        return handler.protocol if handler else None

    def unpack(self, data: bytes, protocol: Optional[str] = None) -> UnpackResult:
        """
        解包数据

        Args:
            data: 原始字节
            protocol: 指定协议名，None 则自动识别

        Returns:
            UnpackResult
        """
        self._stats["total_requests"] += 1

        # 决定用哪条降级链
        chain = self._chains.get(protocol) if protocol else self._all_chain
        if chain is None:
            self._stats["failed_unpacks"] += 1
            return UnpackResult.fail(
                error=f"未知协议: {protocol}",
                protocol=protocol or "unknown",
                handler="registry",
                fallback_level=99,
                raw_size=len(data),
            )

        # 先查缓存（用第一个 handler 的名字作为缓存键前缀可能不准，
        # 用 protocol + data hash）
        cache_key_prefix = protocol or "auto"
        cached = self.cache.get(data, cache_key_prefix)
        if cached:
            self._stats["cache_hits"] += 1
            return cached

        # 走降级链
        result = chain.unpack(data)

        if result.success:
            self._stats["successful_unpacks"] += 1
        else:
            self._stats["failed_unpacks"] += 1
            # 如果走了降级（fallback_level > 0 也算触发降级）
            if result.fallback_level > 0:
                self._stats["fallback_triggers"] += 1

        # 存入缓存（成功和失败都缓存，失败的也不重复尝试）
        self.cache.put(data, cache_key_prefix, result)

        return result

    def get_stats(self) -> Dict[str, Any]:
        """获取注册表统计"""
        cache_stats = self.cache.get_stats()
        total = self._stats["total_requests"]
        hit_rate = self._stats["cache_hits"] / total if total > 0 else 0.0
        success_rate = (
            self._stats["successful_unpacks"] / total if total > 0 else 0.0
        )
        return {
            **self._stats,
            "cache_hit_rate": hit_rate,
            "success_rate": success_rate,
            "handlers_registered": len(self._handlers),
            "protocols": len(self._chains),
            "cache": cache_stats,
        }

    def list_handlers(self) -> List[Dict[str, Any]]:
        """列出所有已注册的 handler"""
        return sorted(
            [h.get_info() for h in self._handlers.values()],
            key=lambda x: x["priority"]
        )
