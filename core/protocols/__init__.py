"""
协议处理层 — Protocol Layer

统一接口、缓存、版本管理、降级策略、注册表、Unidbg 池、异步日志。

ACE 的协议层哲学：
  - 不重写解包能力，只做封装和接入
  - 降级是一等公民（每个协议都可能失败）
  - 缓存是性能基础（相同输入不重复解包）
  - 版本是演化基础（协议会变，追踪变化）
  - 复用是效率基础（实例池避免重复加载）
  - 异步是稳定性基础（日志不阻塞主循环）
"""

from .base import ProtocolHandler, UnpackResult
from .cache import ProtocolLRUCache
from .version import ProtocolVersionManager
from .registry import ProtocolRegistry, FallbackChain
from .unidbg_pool import UnidbgPool, UnidbgInstance
from .async_logger import AsyncAuditLogger
from .tool_provider import ProtocolToolProvider

__all__ = [
    'ProtocolHandler',
    'UnpackResult',
    'ProtocolLRUCache',
    'ProtocolVersionManager',
    'ProtocolRegistry',
    'FallbackChain',
    'UnidbgPool',
    'UnidbgInstance',
    'AsyncAuditLogger',
    'ProtocolToolProvider',
]
