"""
ProtocolToolProvider — 协议层工具提供者

将协议解包能力封装为标准工具接口，
供主循环 / Agent 调用。

参考 ReVa / binary_sense 的 ToolProvider 模式：
  - 小工具原则：每个工具做一件事
  - 自动异常封装
  - 结构化输出

（结构资产：工具接口模式比具体解包能力更重要。）
"""

import base64
import json
import hashlib
import logging
from typing import Any, Dict, List, Optional

from .registry import ProtocolRegistry
from .base import ProtocolHandler, UnpackResult
from .unidbg_pool import UnidbgPool
from .version import ProtocolVersionManager
from .async_logger import AsyncAuditLogger
from .handlers import (
    RPCHandler,
    UnidbgHandler,
    StaticAnalyzerHandler,
    RawFallbackHandler,
)

logger = logging.getLogger(__name__)


class ProtocolToolProvider:
    """
    协议层工具提供者

    提供的工具：
      - protocol_unpack: 解包数据（自动降级）
      - protocol_identify: 识别协议类型
      - protocol_list_handlers: 列出所有已注册的处理器
      - protocol_stats: 获取协议层统计
      - protocol_unidbg_stats: 获取 Unidbg 池统计
      - protocol_log_recent: 获取最近的审计日志
    """

    def __init__(
        self,
        data_dir: str = "",
        cache_size: int = 1000,
        unidbg_pool_size: int = 3,
    ):
        self.data_dir = data_dir

        # 初始化组件
        self.registry = ProtocolRegistry(cache_size=cache_size)
        self.unidbg_pool = UnidbgPool(pool_size=unidbg_pool_size)
        self.version_manager = None
        self.audit_logger = None

        if data_dir:
            from pathlib import Path
            p = Path(data_dir)
            p.mkdir(parents=True, exist_ok=True)

            version_file = p / "protocol_versions.json"
            self.version_manager = ProtocolVersionManager(str(version_file))

            log_dir = p / "audit_logs"
            self.audit_logger = AsyncAuditLogger(
                log_dir=str(log_dir),
                max_queue_size=10000,
            )
            self.audit_logger.start()

        # 注册默认 Handler
        self._register_default_handlers()

        # 工具映射
        self._tools = {
            "protocol_unpack": {
                "name": "protocol_unpack",
                "description": "解包加密/编码数据，自动识别协议并降级处理",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "string",
                            "description": "待解包的数据（base64 编码或 hex 编码）",
                        },
                        "encoding": {
                            "type": "string",
                            "description": "输入编码方式: base64, hex, raw",
                            "default": "base64",
                        },
                        "protocol": {
                            "type": "string",
                            "description": "指定协议名（可选，不指定则自动识别）",
                        },
                    },
                    "required": ["data"],
                },
                "handler": self._tool_unpack,
            },
            "protocol_identify": {
                "name": "protocol_identify",
                "description": "识别数据的协议类型",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "data": {
                            "type": "string",
                            "description": "待识别的数据（base64 编码）",
                        },
                        "encoding": {
                            "type": "string",
                            "description": "输入编码方式",
                            "default": "base64",
                        },
                    },
                    "required": ["data"],
                },
                "handler": self._tool_identify,
            },
            "protocol_list_handlers": {
                "name": "protocol_list_handlers",
                "description": "列出所有已注册的协议处理器",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
                "handler": self._tool_list_handlers,
            },
            "protocol_stats": {
                "name": "protocol_stats",
                "description": "获取协议层统计信息（缓存命中率、成功率等）",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
                "handler": self._tool_stats,
            },
            "protocol_unidbg_stats": {
                "name": "protocol_unidbg_stats",
                "description": "获取 Unidbg 实例池统计",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                },
                "handler": self._tool_unidbg_stats,
            },
            "protocol_log_recent": {
                "name": "protocol_log_recent",
                "description": "获取最近的协议审计日志",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "返回条数",
                            "default": 50,
                        },
                        "event_type": {
                            "type": "string",
                            "description": "按事件类型过滤",
                        },
                    },
                },
                "handler": self._tool_log_recent,
            },
        }

    def _register_default_handlers(self) -> None:
        """注册默认的处理器链"""
        # Level 0: RPC 注入（未配置时会自动失败降级）
        rpc_handler = RPCHandler()
        self.registry.register(rpc_handler)

        # Level 1: Unidbg 模拟执行（未配置时会自动失败降级）
        unidbg_handler = UnidbgHandler(pool=self.unidbg_pool)
        self.registry.register(unidbg_handler)

        # Level 2: 静态分析
        static_handler = StaticAnalyzerHandler()
        self.registry.register(static_handler)

        # Level 3: 兜底（原始数据）
        fallback_handler = RawFallbackHandler()
        self.registry.register(fallback_handler)

        logger.info(
            f"[ProtocolToolProvider] 已注册 {len(self.registry.list_handlers())} 个处理器"
        )

    def register_handler(self, handler: ProtocolHandler, protocol: Optional[str] = None) -> None:
        """注册一个自定义协议处理器"""
        self.registry.register(handler, protocol)

        # 注册版本
        if self.version_manager:
            self.version_manager.register(
                protocol=handler.protocol,
                version=handler.version,
                handler=handler.name,
            )

    def get_tools(self) -> List[Dict[str, Any]]:
        """获取所有工具的元数据（供 LLM 选择使用）"""
        return [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
            for t in self._tools.values()
        ]

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """调用一个工具"""
        tool = self._tools.get(name)
        if not tool:
            return {
                "success": False,
                "error": f"Unknown tool: {name}",
                "available_tools": list(self._tools.keys()),
            }

        try:
            return tool["handler"](args)
        except Exception as e:
            logger.error(f"[ProtocolToolProvider] 工具 {name} 执行失败: {e}")
            return {
                "success": False,
                "error": str(e),
                "tool": name,
            }

    # === 工具实现 ===

    def _tool_unpack(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """protocol_unpack 工具实现"""
        data_str = args.get("data", "")
        encoding = args.get("encoding", "base64")
        protocol = args.get("protocol") or None

        # 解码输入
        try:
            raw_data = self._decode_input(data_str, encoding)
        except Exception as e:
            return {
                "success": False,
                "error": f"输入解码失败: {e}",
                "encoding": encoding,
            }

        if not raw_data:
            return {
                "success": False,
                "error": "空数据",
            }

        # 执行解包
        result = self.registry.unpack(raw_data, protocol=protocol)

        # 审计日志
        if self.audit_logger:
            data_hash = hashlib.sha256(raw_data).hexdigest()[:16]
            self.audit_logger.log_unpack(data_hash, result.__dict__)

        # 转换为字典输出
        return {
            "success": True,
            "data": {
                "unpack_success": result.success,
                "unpack_data": result.data,
                "error": result.error,
                "protocol": result.protocol,
                "handler": result.handler,
                "fallback_level": result.fallback_level,
                "cached": result.cached,
                "timestamp": result.timestamp,
                "raw_size": result.raw_size,
            },
        }

    def _tool_identify(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """protocol_identify 工具实现"""
        data_str = args.get("data", "")
        encoding = args.get("encoding", "base64")

        try:
            raw_data = self._decode_input(data_str, encoding)
        except Exception as e:
            return {
                "success": False,
                "error": f"输入解码失败: {e}",
            }

        protocol = self.registry.identify(raw_data)

        return {
            "success": True,
            "data": {
                "protocol": protocol or "unknown",
                "identified": protocol is not None,
                "raw_size": len(raw_data),
            },
        }

    def _tool_list_handlers(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """protocol_list_handlers 工具实现"""
        handlers = self.registry.list_handlers()
        return {
            "success": True,
            "data": {
                "handlers": handlers,
                "total": len(handlers),
            },
        }

    def _tool_stats(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """protocol_stats 工具实现"""
        stats = self.registry.get_stats()
        return {
            "success": True,
            "data": stats,
        }

    def _tool_unidbg_stats(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """protocol_unidbg_stats 工具实现"""
        stats = self.unidbg_pool.get_stats()
        return {
            "success": True,
            "data": stats,
        }

    def _tool_log_recent(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """protocol_log_recent 工具实现"""
        limit = args.get("limit", 50)
        event_type = args.get("event_type")

        if not self.audit_logger:
            return {
                "success": False,
                "error": "审计日志未启用",
            }

        logs = self.audit_logger.get_recent_logs(
            limit=limit,
            event_type=event_type,
        )
        stats = self.audit_logger.get_stats()

        return {
            "success": True,
            "data": {
                "logs": logs,
                "stats": stats,
            },
        }

    # === 辅助方法 ===

    def _decode_input(self, data_str: str, encoding: str) -> bytes:
        """解码输入数据为原始字节"""
        if isinstance(data_str, bytes):
            return data_str

        if encoding == "base64":
            return base64.b64decode(data_str)
        elif encoding == "hex":
            return bytes.fromhex(data_str)
        elif encoding == "raw":
            return data_str.encode("utf-8")
        else:
            raise ValueError(f"未知编码方式: {encoding}")

    def shutdown(self) -> None:
        """关闭所有资源"""
        if self.audit_logger:
            self.audit_logger.stop()
        self.unidbg_pool.shutdown()
        logger.info("[ProtocolToolProvider] 已关闭")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown()
        return False
