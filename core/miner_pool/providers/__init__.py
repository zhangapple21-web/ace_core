"""
模型提供商适配器

所有提供商实现统一的 OpenAI 兼容接口：
  POST /chat/completions
  Authorization: Bearer {api_key}

返回格式统一为：
{
    "content": "模型回复内容",
    "model": "实际使用的模型名",
    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    "raw_response": {...},
}
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional
import json


class BaseProvider(ABC):
    """
    提供商基类

    所有模型提供商必须实现 chat() 方法。
    不做重试、不做降级，那是 MinerPool 的事。
    """

    provider_name: str = "base"

    def __init__(self, api_key: str, base_url: str, **kwargs):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.extra = kwargs

    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 60,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        发送聊天请求

        Args:
            messages: 对话消息列表 [{"role": "user", "content": "..."}]
            model: 模型名
            temperature: 温度
            max_tokens: 最大输出 token
            timeout: 超时秒数

        Returns:
            {
                "success": bool,
                "content": str,
                "model": str,
                "usage": dict,
                "error": str (if failed),
                "latency_ms": int,
            }
        """
        pass

    @abstractmethod
    def list_models(self) -> List[str]:
        """列出可用模型"""
        pass

    def _build_headers(self, extra_headers: Dict = None) -> Dict[str, str]:
        """构建请求头"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if extra_headers:
            headers.update(extra_headers)
        return headers

    def _chat_completions_url(self) -> str:
        """获取 chat completions 端点"""
        return f"{self.base_url}/chat/completions"
