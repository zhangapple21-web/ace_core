"""
RPCHandler — RPC 注入模式解包（Level 0，最优解）

通过 Sekiro / Frida 等 RPC 框架调用真实 APP 的解密函数。

两层协议骨架：
  1. HTTP REST API（调用方 → Sekiro 服务端）
     - /business/invoke  (POST/JSON，调用转发)
     - /business/groupList (查看分组)
     - /business/clientQueue?group=xxx (查看队列状态)
  
  2. 二进制长连接协议（服务端 → 客户端，即 Sekiro 内部协议）
     - packet_length (int32, 大端)
     - message_type (int8)
     - serial_number (int64, 请求/响应关联)
     - ext_length (int8)
     - ext (字符串，UTF-8)
     - payload (二进制 body)

三种调度策略：
  - OneByOne (轮询，默认)
  - bindClient (指定设备)
  - consistent_hash (一致性哈希)

当前是骨架实现，真实 Sekiro 服务端接入后替换内部 HTTP 调用。
"""

import json
import base64
import struct
import logging
from typing import Any, Dict, Optional, List
from ..base import ProtocolHandler, UnpackResult

logger = logging.getLogger(__name__)


# Sekiro 消息类型常量（二进制协议）
SEKIRO_TYPE_HEARTBEAT = 0x07
SEKIRO_TYPE_REGISTER = 0x01
SEKIRO_TYPE_INVOKE = 0x02

# Sekiro 调度策略
SEKIRO_STRATEGY_ROUND_ROBIN = "one_by_one"
SEKIRO_STRATEGY_BIND_CLIENT = "bind_client"
SEKIRO_STRATEGY_CONSISTENT_HASH = "consistent_hash"


class SekiroPacket:
    """
    Sekiro 二进制协议包（服务端 ↔ 客户端之间的长连接协议）

    协议格式（大端编码）：
      int32  packet_length  数据包总长度（不含自身）
      int8   message_type   消息类型
      int64  serial_number  序列号（请求响应关联）
      int8   ext_length     扩展数据长度
      bytes  ext            扩展数据（UTF-8 字符串）
      bytes  payload        业务数据
    """

    def __init__(
        self,
        message_type: int = 0,
        serial_number: int = 0,
        ext: str = "",
        payload: bytes = b"",
    ):
        self.message_type = message_type
        self.serial_number = serial_number
        self.ext = ext
        self.payload = payload

    @property
    def ext_bytes(self) -> bytes:
        return self.ext.encode("utf-8")

    @property
    def packet_length(self) -> int:
        """packet_length = message_type(1) + serial_number(8) + ext_length(1) + ext + payload"""
        return 1 + 8 + 1 + len(self.ext_bytes) + len(self.payload)

    def encode(self) -> bytes:
        """编码为二进制数据包"""
        ext_b = self.ext_bytes
        packet_len = 1 + 8 + 1 + len(ext_b) + len(self.payload)

        buf = bytearray()
        buf += struct.pack(">i", packet_len)    # int32 大端
        buf += struct.pack(">b", self.message_type)  # int8
        buf += struct.pack(">q", self.serial_number)  # int64 大端
        buf += struct.pack(">b", len(ext_b))   # int8
        buf += ext_b
        buf += self.payload
        return bytes(buf)

    @classmethod
    def decode(cls, data: bytes) -> "SekiroPacket":
        """从二进制数据解码"""
        if len(data) < 4:
            raise ValueError("data too short for packet_length")

        packet_length = struct.unpack(">i", data[:4])[0]
        offset = 4

        if len(data) < 4 + packet_length:
            raise ValueError(
                f"incomplete packet: expected {4 + packet_length}, got {len(data)}"
            )

        message_type = struct.unpack(">b", data[offset:offset + 1])[0]
        offset += 1

        serial_number = struct.unpack(">q", data[offset:offset + 8])[0]
        offset += 8

        ext_length = struct.unpack(">b", data[offset:offset + 1])[0]
        offset += 1

        ext = data[offset:offset + ext_length].decode("utf-8", errors="replace")
        offset += ext_length

        payload = data[offset:4 + packet_length]

        return cls(
            message_type=message_type,
            serial_number=serial_number,
            ext=ext,
            payload=payload,
        )


class SekiroHTTPClient:
    """
    Sekiro HTTP API 客户端（调用方视角）

    这是 Python 调用 Sekiro 的真实接口：
      - 调用方 → HTTP → Sekiro 服务端 → 二进制长连接 → 客户端（Android）

    API 列表：
      - invoke(group, action, ...)           调用转发
      - group_list()                         查看分组列表
      - client_queue(group)                  查看队列状态

    调度策略：
      - one_by_one: 轮询（默认）
      - bind_client: 指定设备，传 bind_client 参数
      - consistent_hash: 一致性哈希，传 consistent_key 参数
    """

    def __init__(
        self,
        server_url: str = "http://127.0.0.1:5612",
        sekiro_token: str = "",
        timeout: float = 10.0,
    ):
        self.server_url = server_url.rstrip("/")
        self.sekiro_token = sekiro_token
        self.timeout = timeout
        self._available = bool(server_url)

    @property
    def is_available(self) -> bool:
        return self._available

    def invoke(
        self,
        group: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        strategy: str = SEKIRO_STRATEGY_ROUND_ROBIN,
        bind_client: str = "",
        consistent_key: str = "",
    ) -> Dict[str, Any]:
        """
        调用 Sekiro RPC（HTTP POST + JSON）

        Args:
            group: 业务分组
            action: 动作名（对应客户端注册的 handler）
            params: 业务参数
            strategy: 调度策略
            bind_client: 指定设备 ID（strategy=bind_client 时用）
            consistent_key: 一致性哈希 key（strategy=consistent_hash 时用）

        Returns:
            Sekiro 服务端返回的响应（JSON）
        """
        if not self._available:
            return {
                "success": False,
                "error": "Sekiro server not configured",
                "data": None,
            }

        # 构造请求体
        body: Dict[str, Any] = {
            "group": group,
            "action": action,
        }
        if params:
            body.update(params)

        if self.sekiro_token:
            body["sekiro_token"] = self.sekiro_token

        if strategy == SEKIRO_STRATEGY_BIND_CLIENT and bind_client:
            body["bind_client"] = bind_client
        elif strategy == SEKIRO_STRATEGY_CONSISTENT_HASH and consistent_key:
            body["consistent_key"] = consistent_key

        # TODO: 真实 HTTP 调用
        # 当前是骨架，返回模拟结果
        return self._simulate_invoke(body)

    def group_list(self) -> Dict[str, Any]:
        """获取分组列表"""
        if not self._available:
            return {"success": False, "error": "not configured", "groups": []}

        # TODO: GET /business/groupList
        return {
            "success": True,
            "groups": ["default"],
        }

    def client_queue(self, group: str) -> Dict[str, Any]:
        """查看指定分组的设备队列状态"""
        if not self._available:
            return {"success": False, "error": "not configured", "clients": []}

        # TODO: GET /business/clientQueue?group=xxx
        return {
            "success": True,
            "group": group,
            "online_clients": 0,
            "clients": [],
        }

    def _simulate_invoke(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """模拟调用响应（骨架用）"""
        return {
            "success": True,
            "simulated": True,
            "server": self.server_url,
            "request_body": body,
            "client_id": "simulated_client_001",
            "result": {
                "note": "this is a simulated response from SekiroHTTPClient skeleton",
            },
            "timestamp": __import__("datetime").datetime.now().isoformat(),
        }


class RPCHandler(ProtocolHandler):
    """
    RPC 注入解包处理器（Level 0）

    优先级最高，因为调用真实环境，结果最准确。

    支持的 RPC 后端：
      - Sekiro（HTTP API + 二进制长连接，机群管理）
      - Frida RPC（待接入）
      - 自定义 HTTP RPC（待接入）

    调用链：
      ACE → RPCHandler → SekiroHTTPClient → HTTP → Sekiro Server → 二进制 → Android Client
    """

    name = "rpc_inject"
    protocol = "generic_encrypted"
    version = "0.3.0"  # 升级：加入 Sekiro HTTP API 客户端骨架
    priority = 10  # 数值越小优先级越高

    def __init__(
        self,
        rpc_endpoint: str = "",
        target_class: str = "",
        target_method: str = "",
        rpc_type: str = "sekiro",
        sekiro_group: str = "default",
        sekiro_action: str = "decrypt",
        sekiro_client_id: str = "",
        sekiro_token: str = "",
        sekiro_strategy: str = SEKIRO_STRATEGY_ROUND_ROBIN,
        sekiro_bind_client: str = "",
        sekiro_consistent_key: str = "",
    ):
        self.rpc_endpoint = rpc_endpoint
        self.target_class = target_class
        self.target_method = target_method
        self.rpc_type = rpc_type
        self.sekiro_group = sekiro_group
        self.sekiro_action = sekiro_action
        self.sekiro_client_id = sekiro_client_id
        self.sekiro_token = sekiro_token
        self.sekiro_strategy = sekiro_strategy
        self.sekiro_bind_client = sekiro_bind_client
        self.sekiro_consistent_key = sekiro_consistent_key

        # HTTP 客户端
        self._http_client: Optional[SekiroHTTPClient] = None
        if rpc_endpoint and rpc_type == "sekiro":
            self._http_client = SekiroHTTPClient(
                server_url=rpc_endpoint,
                sekiro_token=sekiro_token,
            )

        self._available = self._http_client is not None and self._http_client.is_available

        # 序列号计数器（二进制协议用）
        self._serial_counter = 0

    def identify(self, data: bytes) -> bool:
        """
        判断是否能处理（骨架：只要数据非空就尝试）
        真实实现会检查魔术字、协议头、特征字段等。
        """
        if not data or len(data) < 4:
            return False
        return True

    def unpack(self, data: bytes) -> UnpackResult:
        """
        RPC 解包

        真实实现流程：
          1. 构造调用参数（密文 + 目标方法）
          2. 通过 SekiroHTTPClient 调用 /business/invoke
          3. 解析响应，返回明文

        当前：骨架模式，返回模拟结果
        """
        if not self._available:
            return UnpackResult.fail(
                error="RPC endpoint not configured (Sekiro 骨架模式，未连接真实服务器)",
                protocol=self.protocol,
                handler=self.name,
                fallback_level=0,
                raw_size=len(data),
            )

        try:
            result = self._call_sekiro_http(data)
            return UnpackResult.ok(
                data=result,
                protocol=self.protocol,
                handler=self.name,
                raw_size=len(data),
            )
        except Exception as e:
            logger.warning(f"[RPCHandler] 解包失败: {e}")
            return UnpackResult.fail(
                error=str(e),
                protocol=self.protocol,
                handler=self.name,
                fallback_level=0,
                raw_size=len(data),
            )

    def _call_sekiro_http(self, data: bytes) -> Dict[str, Any]:
        """通过 HTTP API 调用 Sekiro"""
        if not self._http_client:
            raise RuntimeError("HTTP client not initialized")

        params = {
            "target_class": self.target_class,
            "target_method": self.target_method,
            "ciphertext": base64.b64encode(data).decode(),
            "ciphertext_encoding": "base64",
        }

        response = self._http_client.invoke(
            group=self.sekiro_group,
            action=self.sekiro_action,
            params=params,
            strategy=self.sekiro_strategy,
            bind_client=self.sekiro_bind_client,
            consistent_key=self.sekiro_consistent_key,
        )

        if not response.get("success"):
            raise RuntimeError(f"Sekiro invoke failed: {response.get('error', 'unknown')}")

        # 提取解密结果
        result_data = response.get("result", {})
        return {
            "decrypted": True,
            "method": "sekiro_http",
            "rpc_type": "sekiro",
            "group": self.sekiro_group,
            "action": self.sekiro_action,
            "strategy": self.sekiro_strategy,
            "client_id": response.get("client_id", ""),
            "server": self.rpc_endpoint,
            "original_size": len(data),
            "result": result_data,
            "fields": {
                "magic": data[:4].hex() if len(data) >= 4 else "",
                "length": len(data),
            },
        }

    def build_register_packet(self) -> bytes:
        """构造 Sekiro 注册包（二进制协议，客户端接入时用）"""
        client_id = self.sekiro_client_id or "ace_client"
        ext = f"{client_id}@{self.sekiro_group}"
        packet = SekiroPacket(
            message_type=SEKIRO_TYPE_REGISTER,
            serial_number=0,
            ext=ext,
            payload=b"",
        )
        return packet.encode()

    def build_heartbeat_packet(self) -> bytes:
        """构造 Sekiro 心跳包（二进制协议，客户端接入时用）"""
        packet = SekiroPacket(
            message_type=SEKIRO_TYPE_HEARTBEAT,
            serial_number=0,
            ext="",
            payload=b"",
        )
        return packet.encode()

    def get_sekiro_status(self) -> Dict[str, Any]:
        """获取 Sekiro 连接状态（分组、设备数等）"""
        if not self._http_client:
            return {
                "available": False,
                "rpc_type": self.rpc_type,
                "reason": "not configured",
            }

        try:
            queue_info = self._http_client.client_queue(self.sekiro_group)
            return {
                "available": True,
                "rpc_type": "sekiro_http",
                "server": self.rpc_endpoint,
                "group": self.sekiro_group,
                "strategy": self.sekiro_strategy,
                "online_clients": queue_info.get("online_clients", 0),
                "action": self.sekiro_action,
            }
        except Exception as e:
            return {
                "available": False,
                "rpc_type": self.rpc_type,
                "error": str(e),
            }
