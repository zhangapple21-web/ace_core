"""
UnidbgHandler — Unidbg 模拟执行解包（Level 1，二级降级）

通过 Unidbg 在 PC 上模拟执行 .so 库中的解密函数。
使用 UnidbgPool 复用实例，避免重复加载。
"""

import json
import base64
import logging
from typing import Any, Dict, Optional
from ..base import ProtocolHandler, UnpackResult
from ..unidbg_pool import UnidbgPool

logger = logging.getLogger(__name__)


class UnidbgHandler(ProtocolHandler):
    """
    Unidbg 模拟执行解包处理器（Level 1）

    RPC 不可用时降级到这里。
    """

    name = "unidbg_emulate"
    protocol = "generic_encrypted"
    version = "0.1.0"
    priority = 20  # 比 RPC 低一级

    def __init__(
        self,
        so_path: str = "",
        decrypt_func: str = "",
        pool: Optional[UnidbgPool] = None,
    ):
        self.so_path = so_path
        self.decrypt_func = decrypt_func
        self._pool = pool or UnidbgPool(pool_size=3)
        self._available = bool(so_path and decrypt_func)

    def identify(self, data: bytes) -> bool:
        """
        判断是否能处理（骨架：只要数据非空就尝试）
        真实实现会检查 .so 支持的协议格式。
        """
        if not data or len(data) < 4:
            return False
        return True

    def unpack(self, data: bytes) -> UnpackResult:
        """
        Unidbg 模拟解包
        """
        if not self._available:
            return UnpackResult.fail(
                error="Unidbg so_path or decrypt_func not configured",
                protocol=self.protocol,
                handler=self.name,
                fallback_level=1,
                raw_size=len(data),
            )

        try:
            result = self._pool.call_function(
                so_path=self.so_path,
                function_name=self.decrypt_func,
                args=[data.hex()],
                timeout=5.0,
            )

            if result["success"]:
                decoded = self._process_result(result["result"], data)
                return UnpackResult.ok(
                    data=decoded,
                    protocol=self.protocol,
                    handler=self.name,
                    raw_size=len(data),
                )
            else:
                return UnpackResult.fail(
                    error=result["error"],
                    protocol=self.protocol,
                    handler=self.name,
                    fallback_level=1,
                    raw_size=len(data),
                )
        except Exception as e:
            logger.warning(f"[UnidbgHandler] 解包失败: {e}")
            return UnpackResult.fail(
                error=str(e),
                protocol=self.protocol,
                handler=self.name,
                fallback_level=1,
                raw_size=len(data),
            )

    def _process_result(self, result: Any, original_data: bytes) -> Dict[str, Any]:
        """处理 Unidbg 返回结果"""
        try:
            text = original_data.decode("utf-8", errors="replace")
        except Exception:
            text = base64.b64encode(original_data).decode()

        return {
            "decrypted": True,
            "method": "unidbg_simulated",
            "original_size": len(original_data),
            "content_preview": text[:200],
            "unidbg_result": result,
            "fields": {
                "magic": original_data[:4].hex() if len(original_data) >= 4 else "",
                "length": len(original_data),
            },
        }
