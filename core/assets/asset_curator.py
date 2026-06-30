"""
Asset Curator — 资产管理员

职责：
  发现、验证、索引基础设施资产
  从 coze-assets 仓库读取配置，统一管理 API、端点、Worker、代理、网关、密钥等资产

资产类型：
  - api_key: API 密钥
  - endpoint: API 端点
  - worker: 工作节点
  - proxy: 代理服务
  - gateway: 网关服务
  - secret: 敏感凭证
"""

import json
import re
import time
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

ASSET_TYPES = {"api_key", "endpoint", "worker", "proxy", "gateway", "secret"}
AUTH_TYPES = {"bearer", "basic", "api_key", "token", "none"}


@dataclass
class Asset:
    """基础设施资产"""
    name: str
    url: str
    type: str
    auth_type: str = "none"
    status: str = "unknown"
    last_verified: Optional[str] = None
    response_time_ms: Optional[float] = None
    health_score: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.type not in ASSET_TYPES:
            raise ValueError(f"Invalid asset type: {self.type}. Must be one of {ASSET_TYPES}")
        if self.auth_type not in AUTH_TYPES:
            raise ValueError(f"Invalid auth type: {self.auth_type}. Must be one of {AUTH_TYPES}")

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Asset":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class AssetCurator:
    """
    Asset Curator — 资产管理员

    负责发现、验证、索引基础设施资产
    """

    def __init__(self, coze_assets_path: Optional[str] = None):
        self._assets: Dict[str, Asset] = {}
        self._coze_assets_path: Optional[Path] = None

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

    @property
    def assets(self) -> List[Asset]:
        return list(self._assets.values())

    def _add_asset(self, asset: Asset):
        """添加或更新资产"""
        self._assets[asset.name] = asset

    def discover_from_repo(self, repo_path: Optional[str] = None) -> int:
        """
        从仓库发现资产

        Args:
            repo_path: coze-assets 仓库路径，默认使用初始化时的路径

        Returns:
            发现的资产数量
        """
        path = Path(repo_path) if repo_path else self._coze_assets_path
        if not path or not path.exists():
            logger.warning(f"coze-assets repo not found: {path}")
            return 0

        count = 0
        count += self._discover_from_secret_md(path / "01_credentials" / "SECRET.md")
        count += self._discover_from_miner_env(path / "02_miner_config" / "miner_env.sh")
        count += self._discover_from_worker_registry(path / "02_miner_config" / "worker_registry.json")

        logger.info(f"Discovered {count} assets from {path}")
        return count

    def _discover_from_secret_md(self, secret_path: Path) -> int:
        """从 SECRET.md 发现资产"""
        if not secret_path.exists():
            return 0

        count = 0
        content = secret_path.read_text(encoding="utf-8")

        nvidia_nim_base = "https://integrate.api.nvidia.com/v1"
        nim_match = re.search(r"NVIDIA NIM.*?Base:\s*(\S+)", content, re.DOTALL)
        if nim_match:
            nvidia_nim_base = nim_match.group(1).strip()

        self._add_asset(Asset(
            name="nvidia_nim_endpoint",
            url=nvidia_nim_base,
            type="endpoint",
            auth_type="bearer",
            metadata={"provider": "nvidia_nim", "source": "SECRET.md"}
        ))
        count += 1

        github_match = re.search(r"GitHub Models.*?- Token:\s*(\S+).*?- Base:\s*(\S+)", content, re.DOTALL)
        if github_match:
            token = github_match.group(1).strip()
            base = github_match.group(2).strip()
            self._add_asset(Asset(
                name="github_models_endpoint",
                url=base,
                type="endpoint",
                auth_type="bearer",
                metadata={"provider": "github_models", "source": "SECRET.md"}
            ))
            self._add_asset(Asset(
                name="github_models_key",
                url=base,
                type="api_key",
                auth_type="bearer",
                metadata={"provider": "github_models", "key": token, "source": "SECRET.md"}
            ))
            count += 2

        zhipu_match = re.search(r"智谱 GLM.*?- Key:\s*(\S+).*?- Base:\s*(\S+)", content, re.DOTALL)
        if zhipu_match:
            key = zhipu_match.group(1).strip()
            base = zhipu_match.group(2).strip()
            self._add_asset(Asset(
                name="zhipu_glm_endpoint",
                url=base,
                type="endpoint",
                auth_type="api_key",
                metadata={"provider": "zhipu_glm", "source": "SECRET.md"}
            ))
            self._add_asset(Asset(
                name="zhipu_glm_key",
                url=base,
                type="api_key",
                auth_type="api_key",
                metadata={"provider": "zhipu_glm", "key": key, "source": "SECRET.md"}
            ))
            count += 2

        modelscope_match = re.search(r"魔搭 ModelScope.*?- Key:\s*(\S+).*?- Base:\s*(\S+)", content, re.DOTALL)
        if modelscope_match:
            key = modelscope_match.group(1).strip()
            base = modelscope_match.group(2).strip()
            self._add_asset(Asset(
                name="modelscope_endpoint",
                url=base,
                type="endpoint",
                auth_type="bearer",
                metadata={"provider": "modelscope", "source": "SECRET.md"}
            ))
            self._add_asset(Asset(
                name="modelscope_key",
                url=base,
                type="api_key",
                auth_type="bearer",
                metadata={"provider": "modelscope", "key": key, "source": "SECRET.md"}
            ))
            count += 2

        apiyi_match = re.search(r"API易.*?- Key:\s*(\S+).*?- Base:\s*(\S+)", content, re.DOTALL)
        if apiyi_match:
            key = apiyi_match.group(1).strip()
            base = apiyi_match.group(2).strip()
            self._add_asset(Asset(
                name="apiyi_endpoint",
                url=base,
                type="endpoint",
                auth_type="bearer",
                metadata={"provider": "apiyi", "source": "SECRET.md"}
            ))
            self._add_asset(Asset(
                name="apiyi_key",
                url=base,
                type="api_key",
                auth_type="bearer",
                metadata={"provider": "apiyi", "key": key, "source": "SECRET.md"}
            ))
            count += 2

        openrouter_match = re.search(r"OpenRouter.*?- Key:\s*(\S+).*?- Base:\s*(\S+)", content, re.DOTALL)
        if openrouter_match:
            key = openrouter_match.group(1).strip()
            base = openrouter_match.group(2).strip()
            self._add_asset(Asset(
                name="openrouter_endpoint",
                url=base,
                type="endpoint",
                auth_type="bearer",
                metadata={"provider": "openrouter", "source": "SECRET.md"}
            ))
            self._add_asset(Asset(
                name="openrouter_key",
                url=base,
                type="api_key",
                auth_type="bearer",
                metadata={"provider": "openrouter", "key": key, "source": "SECRET.md"}
            ))
            count += 2

        oneapi_match = re.search(r"OneAPI.*?- 地址:\s*(\S+).*?- Token-v2:\s*(\S+).*?- Token-miner:\s*(\S+)", content, re.DOTALL)
        if oneapi_match:
            addr = oneapi_match.group(1).strip()
            token_v2 = oneapi_match.group(2).strip()
            token_miner = oneapi_match.group(3).strip()
            self._add_asset(Asset(
                name="oneapi_gateway",
                url=addr,
                type="gateway",
                auth_type="bearer",
                metadata={"provider": "oneapi", "source": "SECRET.md"}
            ))
            self._add_asset(Asset(
                name="oneapi_admin_token",
                url=addr,
                type="secret",
                auth_type="bearer",
                metadata={"provider": "oneapi", "token": token_v2, "role": "admin", "source": "SECRET.md"}
            ))
            self._add_asset(Asset(
                name="oneapi_miner_token",
                url=addr,
                type="secret",
                auth_type="bearer",
                metadata={"provider": "oneapi", "token": token_miner, "role": "miner", "source": "SECRET.md"}
            ))
            count += 3

        ace_proxy_match = re.search(r"ACE OpenAI 代理.*?- 地址:\s*(\S+).*?- Base:\s*(\S+)", content, re.DOTALL)
        if ace_proxy_match:
            addr = ace_proxy_match.group(1).strip()
            base = ace_proxy_match.group(2).strip()
            self._add_asset(Asset(
                name="ace_local_proxy",
                url=base,
                type="proxy",
                auth_type="bearer",
                metadata={"provider": "ace_local", "address": addr, "source": "SECRET.md"}
            ))
            count += 1

        tg_bot_matches = re.findall(r"Bot\d+:\s*(\S+)", content)
        for i, bot_token in enumerate(tg_bot_matches, 1):
            self._add_asset(Asset(
                name=f"telegram_bot_{i}",
                url="https://api.telegram.org",
                type="api_key",
                auth_type="token",
                metadata={"provider": "telegram", "bot_token": bot_token, "source": "SECRET.md"}
            ))
            count += 1

        return count

    def _discover_from_miner_env(self, env_path: Path) -> int:
        """从 miner_env.sh 发现资产"""
        if not env_path.exists():
            return 0

        count = 0
        content = env_path.read_text(encoding="utf-8")

        nim_keys = re.findall(r'export NIM_KEY_\d+="([^"]+)"', content)
        for i, key in enumerate(nim_keys, 1):
            self._add_asset(Asset(
                name=f"nvidia_nim_key_{i}",
                url="https://integrate.api.nvidia.com/v1",
                type="api_key",
                auth_type="bearer",
                metadata={"provider": "nvidia_nim", "key": key, "index": i, "source": "miner_env.sh"}
            ))
            count += 1

        sambanova_match = re.search(r'export SAMBANOVA_KEY="([^"]+)".*?export SAMBANOVA_BASE="([^"]+)"', content, re.DOTALL)
        if sambanova_match:
            key = sambanova_match.group(1).strip()
            base = sambanova_match.group(2).strip()
            self._add_asset(Asset(
                name="sambanova_endpoint",
                url=base,
                type="endpoint",
                auth_type="bearer",
                metadata={"provider": "sambanova", "source": "miner_env.sh"}
            ))
            self._add_asset(Asset(
                name="sambanova_key",
                url=base,
                type="api_key",
                auth_type="bearer",
                metadata={"provider": "sambanova", "key": key, "source": "miner_env.sh"}
            ))
            count += 2

        openrouter_env_match = re.search(r'export OPENROUTER_KEY="([^"]+)".*?export OPENROUTER_BASE="([^"]+)"', content, re.DOTALL)
        if openrouter_env_match:
            key = openrouter_env_match.group(1).strip()
            base = openrouter_env_match.group(2).strip()
            self._add_asset(Asset(
                name="openrouter_env_endpoint",
                url=base,
                type="endpoint",
                auth_type="bearer",
                metadata={"provider": "openrouter", "source": "miner_env.sh"}
            ))
            self._add_asset(Asset(
                name="openrouter_env_key",
                url=base,
                type="api_key",
                auth_type="bearer",
                metadata={"provider": "openrouter", "key": key, "source": "miner_env.sh"}
            ))
            count += 2

        hf_match = re.search(r'export HF_KEY=(\S+)', content)
        if hf_match:
            key = hf_match.group(1).strip()
            self._add_asset(Asset(
                name="huggingface_key",
                url="https://huggingface.co",
                type="api_key",
                auth_type="bearer",
                metadata={"provider": "huggingface", "key": key, "source": "miner_env.sh"}
            ))
            count += 1

        return count

    def _discover_from_worker_registry(self, registry_path: Path) -> int:
        """从 worker_registry.json 发现 Worker 资产"""
        if not registry_path.exists():
            return 0

        count = 0
        try:
            with open(registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            workers = data.get("workers", {})
            for worker_id, worker_data in workers.items():
                model = worker_data.get("model", "")
                corps = worker_data.get("corps", "")
                status = worker_data.get("status", "unknown")
                avg_latency = worker_data.get("avg_latency")
                success_rate = worker_data.get("success_rate")
                rpm = worker_data.get("rpm", 0)

                health_score = 0.0
                if success_rate is not None and isinstance(success_rate, (int, float)):
                    health_score = float(success_rate) * 100

                self._add_asset(Asset(
                    name=worker_id,
                    url=f"worker://{corps.lower()}/{model}",
                    type="worker",
                    auth_type="none",
                    status=status,
                    response_time_ms=float(avg_latency) * 1000 if avg_latency and isinstance(avg_latency, (int, float)) else None,
                    health_score=health_score,
                    metadata={
                        "model": model,
                        "corps": corps,
                        "rpm": rpm,
                        "strengths": worker_data.get("strengths", []),
                        "weaknesses": worker_data.get("weaknesses", []),
                        "context_window": worker_data.get("context_window"),
                        "notes": worker_data.get("notes", ""),
                        "source": "worker_registry.json"
                    }
                ))
                count += 1
        except Exception as e:
            logger.error(f"Error loading worker registry: {e}")

        return count

    def verify_asset(self, asset: Asset, timeout: float = 10.0) -> Asset:
        """
        验证资产可用性（ping/health check）

        Args:
            asset: 要验证的资产
            timeout: 超时时间（秒）

        Returns:
            更新后的资产对象
        """
        asset.last_verified = datetime.utcnow().isoformat() + "Z"

        if asset.type == "worker":
            if asset.status in ("alive", "dead"):
                asset.health_score = asset.health_score if asset.health_score else 0.0
            return asset

        if not asset.url or asset.url.startswith("worker://"):
            asset.status = "unverifiable"
            asset.health_score = 0.0
            return asset

        try:
            parsed = urlparse(asset.url)
            if not parsed.scheme or not parsed.netloc:
                asset.status = "invalid_url"
                asset.health_score = 0.0
                return asset

            health_url = asset.url.rstrip("/") + "/health"
            start_time = time.time()

            try:
                req = urllib.request.Request(health_url, method="GET")
                if asset.auth_type == "bearer" and asset.metadata.get("key"):
                    req.add_header("Authorization", f"Bearer {asset.metadata['key']}")
                elif asset.auth_type == "api_key" and asset.metadata.get("key"):
                    req.add_header("Authorization", f"Bearer {asset.metadata['key']}")

                with urllib.request.urlopen(req, timeout=timeout) as response:
                    elapsed_ms = (time.time() - start_time) * 1000
                    asset.response_time_ms = round(elapsed_ms, 2)
                    asset.status = "healthy" if response.status == 200 else "degraded"
                    asset.health_score = max(0.0, min(100.0, 100.0 - (elapsed_ms / 1000.0) * 10))
                    return asset
            except (urllib.error.HTTPError, urllib.error.URLError):
                pass

            start_time = time.time()
            base_url = asset.url.rstrip("/") + "/v1/models"
            try:
                req = urllib.request.Request(base_url, method="GET")
                if asset.auth_type == "bearer" and asset.metadata.get("key"):
                    req.add_header("Authorization", f"Bearer {asset.metadata['key']}")
                elif asset.auth_type == "api_key" and asset.metadata.get("key"):
                    req.add_header("Authorization", f"Bearer {asset.metadata['key']}")

                with urllib.request.urlopen(req, timeout=timeout) as response:
                    elapsed_ms = (time.time() - start_time) * 1000
                    asset.response_time_ms = round(elapsed_ms, 2)
                    asset.status = "healthy" if response.status == 200 else "degraded"
                    asset.health_score = max(0.0, min(100.0, 100.0 - (elapsed_ms / 1000.0) * 10))
                    return asset
            except (urllib.error.HTTPError, urllib.error.URLError, Exception):
                pass

            start_time = time.time()
            simple_url = asset.url.rstrip("/")
            try:
                req = urllib.request.Request(simple_url, method="GET")
                if asset.auth_type == "bearer" and asset.metadata.get("key"):
                    req.add_header("Authorization", f"Bearer {asset.metadata['key']}")

                with urllib.request.urlopen(req, timeout=timeout) as response:
                    elapsed_ms = (time.time() - start_time) * 1000
                    asset.response_time_ms = round(elapsed_ms, 2)
                    asset.status = "reachable" if response.status < 500 else "unhealthy"
                    asset.health_score = max(0.0, min(100.0, 50.0 - (elapsed_ms / 1000.0) * 5))
                    return asset
            except Exception as e:
                asset.status = "unreachable"
                asset.health_score = 0.0
                asset.response_time_ms = None
                return asset

        except Exception as e:
            logger.debug(f"Verification error for {asset.name}: {e}")
            asset.status = "error"
            asset.health_score = 0.0
            asset.response_time_ms = None
            return asset

    def verify_all(self, type_filter: Optional[str] = None, timeout: float = 10.0) -> Dict[str, Asset]:
        """
        验证所有资产

        Args:
            type_filter: 只验证指定类型的资产
            timeout: 单个资产验证超时时间（秒）

        Returns:
            验证后的资产字典
        """
        assets_to_verify = []
        if type_filter:
            assets_to_verify = [a for a in self._assets.values() if a.type == type_filter]
        else:
            assets_to_verify = list(self._assets.values())

        logger.info(f"Verifying {len(assets_to_verify)} assets...")

        for asset in assets_to_verify:
            self.verify_asset(asset, timeout=timeout)

        healthy_count = sum(1 for a in assets_to_verify if a.status in ("healthy", "reachable", "alive"))
        logger.info(f"Verification complete: {healthy_count}/{len(assets_to_verify)} healthy")

        return self._assets

    def get_available(self, type: Optional[str] = None, min_health: float = 0.0) -> List[Asset]:
        """
        获取可用资产

        Args:
            type: 资产类型过滤（可选）
            min_health: 最低健康分数（0-100）

        Returns:
            可用资产列表，按健康分数降序排列
        """
        available = []
        for asset in self._assets.values():
            if type and asset.type != type:
                continue
            if asset.health_score < min_health:
                continue
            if asset.status in ("healthy", "reachable", "alive", "unknown"):
                available.append(asset)

        available.sort(key=lambda a: a.health_score, reverse=True)
        return available

    def save_index(self, path: str) -> bool:
        """
        保存资产索引到 JSON

        Args:
            path: 保存路径

        Returns:
            是否保存成功
        """
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "assets": [asset.to_dict() for asset in self._assets.values()]
            }
            save_path = Path(path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Asset index saved to {path} ({len(self._assets)} assets)")
            return True
        except Exception as e:
            logger.error(f"Failed to save asset index: {e}")
            return False

    def load_index(self, path: str) -> int:
        """
        加载资产索引

        Args:
            path: 索引文件路径

        Returns:
            加载的资产数量
        """
        try:
            load_path = Path(path)
            if not load_path.exists():
                logger.warning(f"Asset index not found: {path}")
                return 0

            with open(load_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            assets_data = data.get("assets", [])
            count = 0
            for asset_data in assets_data:
                try:
                    asset = Asset.from_dict(asset_data)
                    self._add_asset(asset)
                    count += 1
                except Exception as e:
                    logger.warning(f"Skipping invalid asset: {e}")

            logger.info(f"Loaded {count} assets from {path}")
            return count
        except Exception as e:
            logger.error(f"Failed to load asset index: {e}")
            return 0

    def get_by_name(self, name: str) -> Optional[Asset]:
        """按名称获取资产"""
        return self._assets.get(name)

    def get_by_type(self, asset_type: str) -> List[Asset]:
        """按类型获取资产"""
        return [a for a in self._assets.values() if a.type == asset_type]

    def stats(self) -> Dict[str, Any]:
        """获取资产统计信息"""
        type_counts = {}
        status_counts = {}
        total_health = 0.0
        healthy_count = 0

        for asset in self._assets.values():
            type_counts[asset.type] = type_counts.get(asset.type, 0) + 1
            status_counts[asset.status] = status_counts.get(asset.status, 0) + 1
            if asset.health_score > 0:
                total_health += asset.health_score
                healthy_count += 1

        avg_health = total_health / healthy_count if healthy_count > 0 else 0.0

        return {
            "total": len(self._assets),
            "by_type": type_counts,
            "by_status": status_counts,
            "avg_health_score": round(avg_health, 2),
            "healthy_count": healthy_count
        }
