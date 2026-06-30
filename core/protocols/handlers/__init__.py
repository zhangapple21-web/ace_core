"""
协议处理器集合

降级顺序（从高到低）：
  Level 0: RPC 注入（Sekiro / Frida）
  Level 1: Unidbg 模拟执行
  Level 2: 静态分析（字段提取）
  Level 3: 兜底（原始数据 + 未解包标记）
"""

from .rpc_handler import RPCHandler
from .unidbg_handler import UnidbgHandler
from .static_analyzer import StaticAnalyzerHandler
from .raw_fallback import RawFallbackHandler

__all__ = [
    "RPCHandler",
    "UnidbgHandler",
    "StaticAnalyzerHandler",
    "RawFallbackHandler",
]
