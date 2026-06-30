"""
ProtocolHandler — 协议处理器统一接口

所有协议解包/解封装/解密 handler 必须实现这个接口。

设计原则：
  - 统一输入输出：bytes → dict
  - 自识别能力：每个 handler 自己判断能不能处理
  - 降级友好：失败时返回结构化错误，不抛异常
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime


@dataclass
class UnpackResult:
    """
    解包结果

    success=True  → data 是结构化明文
    success=False → error 说明失败原因，fallback_level 标记降级层级
    """
    success: bool
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    protocol: str = "unknown"
    handler: str = "unknown"
    fallback_level: int = 0  # 0=最优解, 1=一级降级, 2=二级降级, 3=三级降级
    cached: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    raw_size: int = 0

    @classmethod
    def ok(cls, data: Dict, protocol: str, handler: str, raw_size: int = 0) -> "UnpackResult":
        return cls(success=True, data=data, protocol=protocol, handler=handler, raw_size=raw_size)

    @classmethod
    def fail(cls, error: str, protocol: str = "unknown",
             handler: str = "unknown", fallback_level: int = 0,
             raw_size: int = 0) -> "UnpackResult":
        return cls(
            success=False, error=error, protocol=protocol,
            handler=handler, fallback_level=fallback_level, raw_size=raw_size
        )


class ProtocolHandler(ABC):
    """
    协议处理器抽象基类

    每个具体协议实现两个方法：
      - identify(data): 能不能处理
      - unpack(data):   处理并返回结果
    """

    name: str = "base"
    protocol: str = "unknown"
    version: str = "0.0.1"
    priority: int = 100  # 优先级，数值越小越先被尝试

    @abstractmethod
    def identify(self, data: bytes) -> bool:
        """
        判断这个 handler 能不能处理给定的数据

        Args:
            data: 原始字节数据

        Returns:
            True = 能处理，False = 不能处理
        """
        pass

    @abstractmethod
    def unpack(self, data: bytes) -> UnpackResult:
        """
        解包数据

        Args:
            data: 原始字节数据

        Returns:
            UnpackResult — 结构化解包结果
        """
        pass

    def get_info(self) -> Dict[str, Any]:
        """返回 handler 的元信息"""
        return {
            "name": self.name,
            "protocol": self.protocol,
            "version": self.version,
            "priority": self.priority,
        }
