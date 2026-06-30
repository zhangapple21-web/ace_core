"""
StaticAnalyzerHandler — 静态分析解包（Level 2，三级降级）

不执行代码，只做静态字段提取：
  - 魔术字识别
  - 长度字段解析
  - 已知协议头解析
  - Base64 / Hex 解码尝试
"""

import base64
import json
import struct
import zlib
import logging
from typing import Any, Dict
from ..base import ProtocolHandler, UnpackResult

logger = logging.getLogger(__name__)


class StaticAnalyzerHandler(ProtocolHandler):
    """
    静态分析处理器（Level 2）

    RPC 和 Unidbg 都不可用时降级到这里。
    做最轻量的字段提取和格式识别。
    """

    name = "static_analyzer"
    protocol = "generic_encrypted"
    version = "0.1.0"
    priority = 50  # 比模拟执行低

    _KNOWN_MAGICS = {
        b"\x1f\x8b": "gzip",
        b"PK": "zip",
        b"\x89PNG": "png",
        b"\xff\xd8\xff": "jpeg",
        b"GIF8": "gif",
        b"\x00\x00\x01\x00": "woff",
        b"BM": "bmp",
        b"RIFF": "riff/wav/avi",
        b"OggS": "ogg",
        b"ID3": "mp3",
        b"fLaC": "flac",
        b"\x7fELF": "elf",
        b"MZ": "pe/dll/exe",
        b"\xca\xfe\xba\xbe": "mach-o-fat",
        b"\xfe\xed\xfa\xce": "mach-o-32",
        b"\xfe\xed\xfa\xcf": "mach-o-64",
    }

    def identify(self, data: bytes) -> bool:
        """静态分析几乎能处理任何非空数据"""
        return len(data) > 0

    def unpack(self, data: bytes) -> UnpackResult:
        """
        静态分析：提取尽可能多的结构化信息
        """
        try:
            result = self._analyze(data)
            return UnpackResult.ok(
                data=result,
                protocol=self.protocol,
                handler=self.name,
                raw_size=len(data),
            )
        except Exception as e:
            logger.warning(f"[StaticAnalyzer] 分析失败: {e}")
            return UnpackResult.fail(
                error=str(e),
                protocol=self.protocol,
                handler=self.name,
                fallback_level=2,
                raw_size=len(data),
            )

    def _analyze(self, data: bytes) -> Dict[str, Any]:
        """执行静态分析"""
        result: Dict[str, Any] = {
            "decrypted": False,
            "method": "static_analysis",
            "size": len(data),
            "fields": {},
            "decoding_attempts": [],
        }

        # 1. 魔术字识别
        magic_info = self._detect_magic(data)
        if magic_info:
            result["fields"]["magic"] = magic_info["hex"]
            result["fields"]["magic_type"] = magic_info["type"]
            result["decoding_attempts"].append({
                "type": "magic_detection",
                "success": True,
                "result": magic_info["type"],
            })

        # 2. 尝试 Base64 解码
        try:
            stripped = data.strip()
            if all(c in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=" for c in stripped):
                decoded = base64.b64decode(stripped)
                result["decoding_attempts"].append({
                    "type": "base64",
                    "success": True,
                    "decoded_size": len(decoded),
                    "preview": decoded[:100].hex(),
                })
                result["fields"]["base64_decoded_size"] = len(decoded)
        except Exception as e:
            result["decoding_attempts"].append({
                "type": "base64",
                "success": False,
                "error": str(e),
            })

        # 3. 尝试 Hex 解码
        try:
            stripped = data.strip()
            if len(stripped) % 2 == 0 and all(c in b"0123456789abcdefABCDEF" for c in stripped):
                decoded = bytes.fromhex(stripped.decode("ascii"))
                result["decoding_attempts"].append({
                    "type": "hex",
                    "success": True,
                    "decoded_size": len(decoded),
                    "preview": decoded[:100].hex(),
                })
                result["fields"]["hex_decoded_size"] = len(decoded)
        except Exception as e:
            result["decoding_attempts"].append({
                "type": "hex",
                "success": False,
                "error": str(e),
            })

        # 4. 尝试 UTF-8 文本检测
        try:
            text = data.decode("utf-8")
            result["decoding_attempts"].append({
                "type": "utf8_text",
                "success": True,
                "preview": text[:500],
            })
            result["fields"]["is_text"] = True
            result["fields"]["text_preview"] = text[:200]
        except UnicodeDecodeError:
            result["fields"]["is_text"] = False

        # 5. 尝试 JSON 解析
        try:
            text = data.decode("utf-8")
            obj = json.loads(text)
            result["decoding_attempts"].append({
                "type": "json",
                "success": True,
                "keys": list(obj.keys()) if isinstance(obj, dict) else None,
            })
            result["fields"]["is_json"] = True
            result["fields"]["json_type"] = type(obj).__name__
        except Exception:
            result["fields"]["is_json"] = False

        # 6. 熵值估算（简单版：字节分布）
        result["fields"]["byte_distribution"] = self._byte_stats(data)

        # 7. 尝试 gzip 解压
        try:
            if data[:2] == b"\x1f\x8b":
                decompressed = zlib.decompress(data, 16 + zlib.MAX_WBITS)
                result["decoding_attempts"].append({
                    "type": "gzip",
                    "success": True,
                    "decompressed_size": len(decompressed),
                    "preview": decompressed[:100].hex(),
                })
        except Exception as e:
            result["decoding_attempts"].append({
                "type": "gzip",
                "success": False,
                "error": str(e),
            })

        return result

    def _detect_magic(self, data: bytes) -> Dict[str, str]:
        """检测文件魔术字"""
        for magic, mtype in self._KNOWN_MAGICS.items():
            if data.startswith(magic):
                return {
                    "hex": magic.hex(),
                    "type": mtype,
                }
        return {
            "hex": data[:4].hex() if len(data) >= 4 else data.hex(),
            "type": "unknown",
        }

    def _byte_stats(self, data: bytes) -> Dict[str, Any]:
        """简单的字节分布统计"""
        if not data:
            return {"unique_bytes": 0}
        unique = len(set(data))
        return {
            "unique_bytes": unique,
            "unique_ratio": round(unique / 256, 3),
            "zero_bytes": data.count(b"\x00"),
        }
