"""
AMD Radeon Token Factory provider

Free tier models hosted on AMD's developer platform.
Uses token from AMD_RADEON_TOKEN env var.
"""
import os
import time
from typing import Dict, List, Any

from .openai_compatible import OpenAICompatibleProvider


class AMDRadeonProvider(OpenAICompatibleProvider):
    """
    AMD Radeon Token Factory provider.

    Models are free during the preview period. The token is read from
    AMD_RADEON_TOKEN environment variable at init time.
    """

    provider_name = "amd_radeon"

    def __init__(self, api_key: str = "", base_url: str = "https://developer.amd.com.cn/radeon/v1", **kwargs):
        # Token comes from env; api_key param kept for interface compatibility
        token = os.environ.get("AMD_RADEON_TOKEN", api_key)
        if not token:
            raise ValueError("AMD_RADEON_TOKEN environment variable not set")
        super().__init__(api_key=token, base_url=base_url, provider_name="amd_radeon", **kwargs)

    def list_models(self) -> List[str]:
        """List available models from the AMD endpoint."""
        try:
            import requests
            headers = self._build_headers()
            r = requests.get(f"{self.base_url}/models", headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json().get("data", [])
                return [m["id"] for m in data if m.get("id")]
        except Exception:
            pass
        # Fallback static list
        return [
            "DeepSeek-V4.1-Flash",
            "DeepSeek-V4-Flash",
            "DeepSeek-V4-Flash-Vision-Exp",
            "Gemma-4-31B-IT",
            "GLM-5.3-Flash",
            "MiMo-V2.6-Flash",
            "MiniCPM5-2B",
            "Qwen3.8-27B",
            "Qwen3.8-Flash-Next",
        ]