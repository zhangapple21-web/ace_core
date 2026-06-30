"""
RawFallbackHandler — 兜底处理器（Level 3 / 最后防线）

所有解包方式都失败时，返回原始数据 + 标记"未解包"。
确保链路永不中断。
"""

import base64
import logging
from typing import Any, Dict
from ..base import ProtocolHandler, UnpackResult

logger = logging.getLogger(__name__)


class RawFallbackHandler(ProtocolHandler):
    """
    原始数据兜底处理器（Level 99）

    永远不会失败，永远返回原始数据。
    确保系统在没有任何解包能力时也能正常运行。
    """

    name = "raw_fallback"
    protocol = "raw"
    version = "1.0.0"
    priority = 999  # 最低优先级，最后才会尝试

    def identify(self, data: bytes) -> bool:
        """兜底处理器能处理任何数据，包括空数据"""
        return True

    def unpack(self, data: bytes) -> UnpackResult:
        """
        兜底解包：返回原始数据 + 未解包标记

        这是最后一道防线，永远不会失败。
        """
        try:
            result = {
                "decrypted": False,
                "method": "raw_fallback",
                "note": "所有解包方式均失败，返回原始数据",
                "original_size": len(data),
                "raw_hex": data[:64].hex() + ("..." if len(data) > 64 else ""),
                "raw_base64": base64.b64encode(data[:64]).decode() + ("..." if len(data) > 64 else ""),
                "warnings": [
                    "数据未解包",
                    "请检查 RPC / Unidbg / 静态分析配置",
                ],
            }

            # 尝试解码文本
            try:
                text = data.decode("utf-8", errors="replace")
                result["text_preview"] = text[:200]
            except Exception:
                pass

            return UnpackResult.ok(
                data=result,
                protocol="raw",
                handler=self.name,
                raw_size=len(data),
            )
        except Exception as e:
            # 极端兜底：连构造结果都失败了
            return UnpackResult(
                success=False,
                data={"raw_hex": data.hex() if data else ""},
                error=f"fallback handler failed: {e}",
                protocol="raw",
                handler=self.name,
                fallback_level=99,
                raw_size=len(data),
            )
