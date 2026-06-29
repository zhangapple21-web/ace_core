"""
工具提供者基类 — 从 ReVa 考古提取的骨架

核心模式：
- 小工具原则：每个工具做一件事，避免上下文爆炸
- 自动异常封装：register_tool() 自动捕获异常并转化为结构化错误
- 参数提取辅助：getString/getInt/getOptional* 等 helper，自动类型转换
- 程序验证：统一的 program_path 标识和验证机制

来源：
- ReVa AbstractToolProvider（tool driven approach, small tools philosophy）
- android-reverse-engineering-skill（phase-based workflow, auto deps install）
"""

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable


class ToolProvider(ABC):
    """工具提供者接口 — 定义工具的生命周期"""

    @abstractmethod
    def register_tools(self) -> None:
        """注册所有工具到 sensor"""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """清理资源"""
        pass


class AbstractToolProvider(ToolProvider):
    """
    工具提供者基类

    核心设计原则（从 ReVa 考古提取）：
    1. 小工具哲学：大量小工具而非少数大工具，减少上下文消耗
    2. 容错输入：参数自动类型转换，容忍 LLM 的格式偏差
    3. 自动异常：register_tool 自动封装异常，统一错误格式
    4. 结构化输出：每个工具返回 success + data + metadata 的统一格式
    """

    def __init__(self, sensor):
        self.sensor = sensor
        self._registered_tools: Dict[str, Dict[str, Any]] = {}
        self._tool_handlers: Dict[str, Callable] = {}

    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable[[Dict[str, Any]], Dict[str, Any]],
    ) -> None:
        """
        注册一个工具，自动封装异常处理

        封装逻辑：
        - IllegalArgumentException → 结构化错误响应
        - 其他异常 → 记录日志 + 通用错误响应
        """

        def safe_handler(args: Dict[str, Any]) -> Dict[str, Any]:
            try:
                return handler(args)
            except ValueError as e:
                return self._error_result(str(e))
            except KeyError as e:
                return self._error_result(f"Missing required parameter: {e}")
            except Exception as e:
                self.sensor.log_error(f"Tool {name} failed", e)
                return self._error_result(f"Tool execution failed: {e}")

        self._tool_handlers[name] = safe_handler
        self._registered_tools[name] = {
            "name": name,
            "description": description,
            "input_schema": input_schema,
            "registered_at": datetime.now().isoformat(),
        }

    def call_tool(self, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """调用已注册的工具"""
        if name not in self._tool_handlers:
            return self._error_result(f"Unknown tool: {name}")
        return self._tool_handlers[name](args)

    def get_tools(self) -> List[Dict[str, Any]]:
        """获取所有已注册工具的元数据"""
        return list(self._registered_tools.values())

    def cleanup(self) -> None:
        """默认清理，子类可覆盖"""
        pass

    def _success_result(self, data: Any, **metadata) -> Dict[str, Any]:
        """构造成功响应"""
        result = {"success": True, "data": data}
        result.update(metadata)
        return result

    def _error_result(self, message: str, **details) -> Dict[str, Any]:
        """构造错误响应"""
        result = {"success": False, "error": message}
        if details:
            result["details"] = details
        return result

    def get_string(self, args: Dict[str, Any], key: str) -> str:
        """获取字符串参数，自动转换类型"""
        val = args[key]
        if isinstance(val, str):
            return val
        return str(val)

    def get_optional_string(
        self, args: Dict[str, Any], key: str, default: str = ""
    ) -> str:
        if key not in args or args[key] is None:
            return default
        return self.get_string(args, key)

    def get_int(self, args: Dict[str, Any], key: str) -> int:
        """获取整数参数，自动转换类型"""
        val = args[key]
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            return int(val)
        if isinstance(val, float):
            return int(val)
        return int(val)

    def get_optional_int(
        self, args: Dict[str, Any], key: str, default: int = 0
    ) -> int:
        if key not in args or args[key] is None:
            return default
        return self.get_int(args, key)

    def get_bool(self, args: Dict[str, Any], key: str) -> bool:
        """获取布尔参数，自动转换字符串"""
        val = args[key]
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ("true", "1", "yes", "y")
        return bool(val)

    def get_optional_bool(
        self, args: Dict[str, Any], key: str, default: bool = False
    ) -> bool:
        if key not in args or args[key] is None:
            return default
        return self.get_bool(args, key)

    def get_list(
        self, args: Dict[str, Any], key: str
    ) -> List[Any]:
        val = args[key]
        if isinstance(val, list):
            return val
        if isinstance(val, str):
            return [item.strip() for item in val.split(",")]
        return [val]

    def get_optional_list(
        self, args: Dict[str, Any], key: str, default: Optional[List] = None
    ) -> List[Any]:
        if default is None:
            default = []
        if key not in args or args[key] is None:
            return default
        return self.get_list(args, key)
