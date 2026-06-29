"""
OpenAI 兼容提供商适配器

所有 OpenAI 兼容的 API（NIM、GitHub Models、OpenRouter、API易、OneAPI、SambaNova 等）
都可以用这个适配器。

只在必要时创建特化适配器。
"""

import json
import time
import urllib.request
import urllib.error
from typing import Dict, List, Any, Optional

from . import BaseProvider


class OpenAICompatibleProvider(BaseProvider):
    """
    OpenAI 兼容提供商

    只要是 OpenAI Chat Completions 格式的 API 都能用。
    用 urllib 实现，不依赖第三方库。
    """

    provider_name = "openai_compatible"

    def __init__(self, api_key: str, base_url: str, provider_name: str = "", **kwargs):
        super().__init__(api_key, base_url, **kwargs)
        if provider_name:
            self.provider_name = provider_name

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 60,
        extra_headers: Dict = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """发送聊天请求"""
        start_time = time.time()
        result = {
            "success": False,
            "content": "",
            "model": model,
            "usage": {},
            "error": "",
            "latency_ms": 0,
            "provider": self.provider_name,
        }

        if not model:
            result["error"] = "model is required"
            return result

        try:
            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            # 传递额外参数
            for k in ["top_p", "frequency_penalty", "presence_penalty", "stream"]:
                if k in kwargs:
                    payload[k] = kwargs[k]

            data = json.dumps(payload).encode("utf-8")

            req = urllib.request.Request(
                self._chat_completions_url(),
                data=data,
                headers=self._build_headers(extra_headers),
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                resp_data = json.loads(resp_body)

                if resp_data.get("error"):
                    result["error"] = str(resp_data["error"])
                else:
                    choices = resp_data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        result["content"] = msg.get("content", "")
                        result["model"] = resp_data.get("model", model)
                        result["usage"] = resp_data.get("usage", {})
                        result["success"] = True
                    else:
                        result["error"] = "no choices in response"

        except urllib.error.HTTPError as e:
            try:
                err_body = e.read().decode("utf-8", errors="replace")
                err_data = json.loads(err_body)
                result["error"] = err_data.get("error", {}).get("message", str(e))
            except Exception:
                result["error"] = f"HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            result["error"] = f"URL Error: {e.reason}"
        except json.JSONDecodeError as e:
            result["error"] = f"JSON decode error: {e}"
        except Exception as e:
            result["error"] = str(e)

        result["latency_ms"] = int((time.time() - start_time) * 1000)
        return result

    def list_models(self) -> List[str]:
        """列出可用模型（可选实现）"""
        models_url = f"{self.base_url}/models"
        try:
            req = urllib.request.Request(
                models_url,
                headers=self._build_headers(),
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m.get("id", "") for m in data.get("data", [])]
        except Exception:
            return []


class NIMProvider(OpenAICompatibleProvider):
    """NVIDIA NIM 提供商"""

    provider_name = "nim"

    def __init__(self, api_key: str, base_url: str = "https://integrate.api.nvidia.com/v1", **kwargs):
        super().__init__(api_key, base_url, provider_name="nim", **kwargs)


class GitHubModelsProvider(OpenAICompatibleProvider):
    """GitHub Models 提供商"""

    provider_name = "github_models"

    def __init__(self, api_key: str, base_url: str = "https://models.inference.ai.azure.com", **kwargs):
        super().__init__(api_key, base_url, provider_name="github_models", **kwargs)


class GLMProvider(OpenAICompatibleProvider):
    """智谱 GLM 提供商"""

    provider_name = "glm"

    def __init__(self, api_key: str, base_url: str = "https://open.bigmodel.cn/api/paas/v4", **kwargs):
        super().__init__(api_key, base_url, provider_name="glm", **kwargs)


class OpenRouterProvider(OpenAICompatibleProvider):
    """OpenRouter 提供商"""

    provider_name = "openrouter"

    def __init__(self, api_key: str, base_url: str = "https://openrouter.ai/api/v1", **kwargs):
        super().__init__(api_key, base_url, provider_name="openrouter", **kwargs)

    def _build_headers(self, extra_headers: Dict = None) -> Dict[str, str]:
        headers = super()._build_headers(extra_headers)
        headers["HTTP-Referer"] = "https://ace-runtime.local"
        headers["X-Title"] = "ACE Runtime"
        return headers


class APIYiProvider(OpenAICompatibleProvider):
    """API易 提供商（含 Gemini 中转）"""

    provider_name = "apiyi"

    def __init__(self, api_key: str, base_url: str = "https://api.apiyi.com", **kwargs):
        super().__init__(api_key, base_url, provider_name="apiyi", **kwargs)

    def _chat_completions_url(self) -> str:
        return f"{self.base_url}/v1/chat/completions"


class SambaNovaProvider(OpenAICompatibleProvider):
    """SambaNova 提供商"""

    provider_name = "sambanova"

    def __init__(self, api_key: str, base_url: str = "https://api.sambanova.ai/v1", **kwargs):
        super().__init__(api_key, base_url, provider_name="sambanova", **kwargs)


class OneAPIProvider(OpenAICompatibleProvider):
    """OneAPI 提供商"""

    provider_name = "oneapi"

    def __init__(self, api_key: str, base_url: str = "http://localhost:3000/v1", **kwargs):
        super().__init__(api_key, base_url, provider_name="oneapi", **kwargs)
