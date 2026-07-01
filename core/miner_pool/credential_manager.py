"""
凭证管理器 — CredentialManager

职责：
  从 coze-assets 仓库读取所有 API 凭证，
  不硬编码路径，自动发现仓库位置。

设计原则：
  - 凭证只读，不在内存中明文存储超过必要时间
  - 按提供商分组，按需取用
  - 支持从环境变量覆盖（生产环境）
  - 失败不阻塞，返回空凭证（调用方自行降级）
"""

import re
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class ProviderCredential:
    """单个提供商的凭证"""
    provider: str
    base_url: str = ""
    api_keys: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)
    source: str = ""  # 凭证来源文件

    @property
    def is_valid(self) -> bool:
        return bool(self.api_keys) and bool(self.base_url)

    @property
    def primary_key(self) -> str:
        return self.api_keys[0] if self.api_keys else ""


class CredentialManager:
    """
    凭证管理器 — 所有 API Key 的唯一入口

    不直接给 Key。
    给 ProviderCredential 对象，调用方自己用。
    """

    def __init__(self, coze_assets_path: Optional[str] = None):
        self._coze_assets_path: Optional[Path] = None
        self._credentials: Dict[str, ProviderCredential] = {}
        self._loaded = False

        if coze_assets_path:
            self._coze_assets_path = Path(coze_assets_path)
        else:
            self._coze_assets_path = self._auto_discover_coze_assets()

    def _auto_discover_coze_assets(self) -> Optional[Path]:
        """自动发现 coze-assets 仓库位置"""
        candidates = []

        home = Path.home()

        search_roots = [
            Path.cwd(),
            Path.cwd().parent,
            home / "Downloads",
            home / "Desktop",
            home / "Documents",
            home / "projects",
            home / "workspace",
            home / ".trae" / "work",
        ]

        for root in search_roots:
            if not root.exists():
                continue
            try:
                for p in root.rglob("coze-assets/01_credentials/SECRET.md"):
                    if p.is_file():
                        candidates.append(p.parent.parent)
                        if len(candidates) >= 3:
                            break
            except Exception:
                pass
            if candidates:
                break

        return candidates[0] if candidates else None

    def load(self) -> bool:
        """加载所有凭证"""
        if self._loaded:
            return True

        if not self._coze_assets_path or not self._coze_assets_path.exists():
            return False

        try:
            self._load_from_secret_md()
            self._load_from_miner_env()
            self._load_from_env_override()
            self._loaded = True
            return True
        except Exception:
            return False

    def _load_from_secret_md(self):
        """从 SECRET.md 解析凭证"""
        secret_file = self._coze_assets_path / "01_credentials" / "SECRET.md"
        if not secret_file.exists():
            return

        content = secret_file.read_text(encoding="utf-8")
        source = "SECRET.md"

        # ACE OpenAI 代理（ACE 自己部署的独立代理）
        ace_base = self._extract_pattern(
            content,
            r"ACE OpenAI 代理[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            group=1,
        )
        ace_token = self._extract_pattern(
            content,
            r"ACE OpenAI 代理[\s\S]*?Token:\s*`?([\w\-]+)",
            group=1,
            default="ace-local-proxy",
        )
        if ace_base:
            self._credentials["ace_proxy"] = ProviderCredential(
                provider="ace_proxy",
                base_url=ace_base,
                api_keys=[ace_token] if ace_token else ["ace-local-proxy"],
                source=source,
            )

        # NVIDIA NIM
        nim_base = self._extract_pattern(
            content,
            r"NVIDIA NIM[\s\S]*?\*?\*?Base:\*?\*?\s*`?(https?://[^\s`]+)",
            group=1,
            default="https://integrate.api.nvidia.com/v1",
        )
        nim_keys = self._extract_nim_keys_from_env_sh()
        if nim_keys:
            self._credentials["nim"] = ProviderCredential(
                provider="nim",
                base_url=nim_base,
                api_keys=nim_keys,
                source=source,
            )

        # GitHub Models
        gh_token = self._extract_pattern(
            content,
            r"GitHub Models[\s\S]*?Token:\s*`?([\w\-_]+)",
            group=1,
        )
        gh_base = self._extract_pattern(
            content,
            r"GitHub Models[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            group=1,
            default="https://models.inference.ai.azure.com",
        )
        if gh_token:
            self._credentials["github_models"] = ProviderCredential(
                provider="github_models",
                base_url=gh_base,
                api_keys=[gh_token],
                source=source,
            )

        # 智谱 GLM
        glm_key = self._extract_pattern(
            content,
            r"智谱 GLM[\s\S]*?Key:\s*`?([\w\.\-]+)",
            group=1,
        )
        glm_base = self._extract_pattern(
            content,
            r"智谱 GLM[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            group=1,
            default="https://open.bigmodel.cn/api/paas/v4",
        )
        if glm_key:
            self._credentials["glm"] = ProviderCredential(
                provider="glm",
                base_url=glm_base,
                api_keys=[glm_key],
                source=source,
            )

        # 魔搭 ModelScope
        ms_key = self._extract_pattern(
            content,
            r"魔搭 ModelScope[\s\S]*?Key:\s*`?([\w\-]+)",
            group=1,
        )
        ms_base = self._extract_pattern(
            content,
            r"魔搭 ModelScope[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            group=1,
            default="https://api-inference.modelscope.cn/v1",
        )
        if ms_key:
            self._credentials["modelscope"] = ProviderCredential(
                provider="modelscope",
                base_url=ms_base,
                api_keys=[ms_key],
                source=source,
            )

        # API易
        apiyi_key = self._extract_pattern(
            content,
            r"API易[\s\S]*?Key:\s*`?(sk-[\w]+)",
            group=1,
        )
        apiyi_base = self._extract_pattern(
            content,
            r"API易[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            group=1,
            default="https://api.apiyi.com",
        )
        if apiyi_key:
            self._credentials["apiyi"] = ProviderCredential(
                provider="apiyi",
                base_url=apiyi_base,
                api_keys=[apiyi_key],
                source=source,
                extra={"gemini_via_apiyi": True},
            )

        # OpenRouter
        or_key = self._extract_pattern(
            content,
            r"OpenRouter[\s\S]*?Key:\s*`?(sk-or-v1-[\w]+)",
            group=1,
        )
        or_base = self._extract_pattern(
            content,
            r"OpenRouter[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            group=1,
            default="https://openrouter.ai/api/v1",
        )
        if or_key:
            self._credentials["openrouter"] = ProviderCredential(
                provider="openrouter",
                base_url=or_base,
                api_keys=[or_key],
                source=source,
            )

        # OneAPI
        oneapi_token = self._extract_pattern(
            content,
            r"OneAPI[\s\S]*?Token-miner:\s*`?([\w]+)",
            group=1,
        )
        oneapi_base = self._extract_pattern(
            content,
            r"OneAPI[\s\S]*?地址:\s*`?(https?://[^\s`]+)",
            group=1,
            default="http://localhost:3000",
        )
        if oneapi_token:
            self._credentials["oneapi"] = ProviderCredential(
                provider="oneapi",
                base_url=oneapi_base + "/v1" if not oneapi_base.endswith("/v1") else oneapi_base,
                api_keys=[oneapi_token],
                source=source,
            )

        # SambaNova
        sn_key = self._extract_pattern(
            content,
            r"SambaNova[\s\S]*?Key:\s*`?([\w\-]+)",
            group=1,
        )
        sn_base = self._extract_pattern(
            content,
            r"SambaNova[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            group=1,
            default="https://api.sambanova.ai/v1",
        )
        if sn_key:
            self._credentials["sambanova"] = ProviderCredential(
                provider="sambanova",
                base_url=sn_base,
                api_keys=[sn_key],
                source=source,
            )

        # HuggingFace
        hf_key = self._extract_pattern(
            content,
            r"HuggingFace[\s\S]*?Key:\s*`?([\w]+)",
            group=1,
        )
        if hf_key:
            self._credentials["huggingface"] = ProviderCredential(
                provider="huggingface",
                base_url="https://api-inference.huggingface.co/v1",
                api_keys=[hf_key],
                source=source,
            )

    def _extract_nim_keys_from_env_sh(self) -> List[str]:
        """从 miner_env.sh 提取 NIM Keys"""
        env_file = self._coze_assets_path / "02_miner_config" / "miner_env.sh"
        if not env_file.exists():
            return []

        content = env_file.read_text(encoding="utf-8")
        keys = []
        for match in re.finditer(r'NIM_KEY_\d+="([^"]+)"', content):
            key = match.group(1)
            if key and key not in keys:
                keys.append(key)
        return keys

    def _load_from_miner_env(self):
        """从 miner_env.sh 补充凭证"""
        env_file = self._coze_assets_path / "02_miner_config" / "miner_env.sh"
        if not env_file.exists():
            return

        content = env_file.read_text(encoding="utf-8")
        source = "miner_env.sh"

        # SambaNova
        sambanova_key = self._extract_pattern(content, r'SAMBANOVA_KEY="([^"]+)"', group=1)
        sambanova_base = self._extract_pattern(
            content, r'SAMBANOVA_BASE="([^"]+)"', group=1,
            default="https://api.sambanova.ai/v1"
        )
        if sambanova_key:
            self._credentials["sambanova"] = ProviderCredential(
                provider="sambanova",
                base_url=sambanova_base,
                api_keys=[sambanova_key],
                source=source,
            )

        # HuggingFace
        hf_key = self._extract_pattern(content, r'HF_KEY=([\w]+)', group=1)
        if hf_key:
            self._credentials["huggingface"] = ProviderCredential(
                provider="huggingface",
                base_url="https://api-inference.huggingface.co/v1",
                api_keys=[hf_key],
                source=source,
            )

        # GitHub PAT (补充)
        if "github_models" not in self._credentials:
            gh_pat = self._extract_pattern(content, r'GITHUB_PAT="([^"]+)"', group=1)
            if gh_pat:
                self._credentials["github_models"] = ProviderCredential(
                    provider="github_models",
                    base_url="https://models.inference.ai.azure.com",
                    api_keys=[gh_pat],
                    source=source,
                )

    def _load_from_env_override(self):
        """从环境变量覆盖凭证（生产环境用）"""
        # 遍历所有提供商，检查环境变量是否有覆盖
        provider_env_map = {
            "nim": ("NIM_API_KEY", "NIM_BASE_URL", "https://integrate.api.nvidia.com/v1"),
            "github_models": ("GITHUB_PAT", "GITHUB_MODELS_BASE_URL", "https://models.inference.ai.azure.com"),
            "glm": ("ZHIPU_KEY", "GLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"),
            "openrouter": ("OPENROUTER_KEY", "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            "oneapi": ("ONEAPI_KEY", "ONEAPI_BASE_URL", "http://localhost:3000/v1"),
            "sambanova": ("SAMBANOVA_KEY", "SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1"),
        }

        for provider, (key_env, base_env, default_base) in provider_env_map.items():
            key = os.environ.get(key_env)
            if key:
                base = os.environ.get(base_env, default_base)
                self._credentials[provider] = ProviderCredential(
                    provider=provider,
                    base_url=base,
                    api_keys=[key],
                    source="environment",
                )

    @staticmethod
    def _extract_pattern(text: str, pattern: str, group: int = 1, default: str = "") -> str:
        """从文本中提取正则匹配"""
        match = re.search(pattern, text)
        if match:
            return match.group(group).strip()
        return default

    def get(self, provider: str) -> Optional[ProviderCredential]:
        """获取指定提供商的凭证"""
        if not self._loaded:
            self.load()
        return self._credentials.get(provider)

    def list_providers(self) -> List[str]:
        """列出所有有有效凭证的提供商"""
        if not self._loaded:
            self.load()
        return [p for p, cred in self._credentials.items() if cred.is_valid]

    @property
    def coze_assets_path(self) -> Optional[str]:
        return str(self._coze_assets_path) if self._coze_assets_path else None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def get_stats(self) -> Dict[str, Any]:
        """获取凭证统计（不含明文）"""
        if not self._loaded:
            self.load()
        stats = {}
        for name, cred in self._credentials.items():
            stats[name] = {
                "is_valid": cred.is_valid,
                "key_count": len(cred.api_keys),
                "base_url": cred.base_url[:30] + "..." if len(cred.base_url) > 30 else cred.base_url,
                "source": cred.source,
            }
        return stats
