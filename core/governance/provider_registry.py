"""
Provider Registry（Provider 注册中心 / 唯一模型注册表）

核心职责：
    成为所有 Provider 和模型定义的唯一来源。
    禁止每个模块自己写模型名。
    解决模型名称分裂问题。

    以前：
        task_profiles.py 自己写一个模型名
        SurvivalLoop 自己写一个模型名
        两边不一样，一边 404 一边 PASS

    现在：
        所有模块都从 Provider Registry 取模型名。
        Registry 是唯一真相来源 (Single Source of Truth)。

    每个模型定义包含：
        - provider: Provider 名称
        - model_id: 模型 ID（API 实际调用的）
        - display_name: 显示名称
        - capabilities: 能力标签（reasoning / vision / embedding / tool_calling / streaming / json_mode）
        - context_window: 上下文窗口
        - max_output: 最大输出 token
        - status: active / deprecated / beta
        - verified: 是否已验证存在
        - last_verified: 最后验证时间

    设计原则：
        - Single Source of Truth：唯一真相来源
        - Evidence First：每个模型都有验证证据
        - Append-only：模型只标记 deprecated，不删除
        - Lineage Track：模型有演化历史
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ProviderModel:
    """Provider 模型定义"""
    provider: str                # Provider 名称
    model_id: str                # 模型 ID（API 实际调用的）
    display_name: str = ""       # 显示名称
    capabilities: List[str] = field(default_factory=list)  # 能力标签
    context_window: int = 0      # 上下文窗口
    max_output: int = 0          # 最大输出 token
    status: str = "active"       # active / deprecated / beta / unknown
    verified: bool = False       # 是否已验证存在
    last_verified: str = ""      # 最后验证时间
    last_verification_result: str = ""  # 最后验证结果（PASS/FAIL/404等）
    aliases: List[str] = field(default_factory=list)  # 别名（旧名称）
    description: str = ""        # 描述
    meta: Dict[str, Any] = field(default_factory=dict)  # 元数据

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "display_name": self.display_name,
            "capabilities": self.capabilities,
            "context_window": self.context_window,
            "max_output": self.max_output,
            "status": self.status,
            "verified": self.verified,
            "last_verified": self.last_verified,
            "last_verification_result": self.last_verification_result,
            "aliases": self.aliases,
            "description": self.description,
            "meta": self.meta,
        }


@dataclass
class ProviderEntry:
    """Provider 定义"""
    name: str                    # Provider 名称
    base_url: str                # Base URL
    api_key_env: str = ""        # API Key 环境变量名
    status: str = "active"       # active / inactive / degraded
    models: List[ProviderModel] = field(default_factory=list)  # 模型列表
    description: str = ""
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "status": self.status,
            "models": [m.to_dict() for m in self.models],
            "description": self.description,
            "meta": self.meta,
        }


class ProviderRegistry:
    """
    Provider 注册中心

    唯一真相来源。所有模块都从这里取 Provider 和模型定义。
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.registry_dir = self.data_dir / "provider_registry"
        self.registry_dir.mkdir(parents=True, exist_ok=True)

        self.registry_file = self.registry_dir / "registry.json"

        self.providers: Dict[str, ProviderEntry] = {}
        self._model_index: Dict[str, ProviderModel] = {}  # "provider:model_id" -> model

        self._load()

        # 如果是空的，初始化默认 Provider（从现有配置推导）
        if not self.providers:
            self._initialize_default()

    def _load(self):
        """加载注册表"""
        if not self.registry_file.exists():
            return

        try:
            with open(self.registry_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for pdata in data.get("providers", []):
                models = []
                for mdata in pdata.get("models", []):
                    models.append(ProviderModel(
                        provider=mdata["provider"],
                        model_id=mdata["model_id"],
                        display_name=mdata.get("display_name", ""),
                        capabilities=mdata.get("capabilities", []),
                        context_window=mdata.get("context_window", 0),
                        max_output=mdata.get("max_output", 0),
                        status=mdata.get("status", "active"),
                        verified=mdata.get("verified", False),
                        last_verified=mdata.get("last_verified", ""),
                        last_verification_result=mdata.get("last_verification_result", ""),
                        aliases=mdata.get("aliases", []),
                        description=mdata.get("description", ""),
                        meta=mdata.get("meta", {}),
                    ))

                entry = ProviderEntry(
                    name=pdata["name"],
                    base_url=pdata.get("base_url", ""),
                    api_key_env=pdata.get("api_key_env", ""),
                    status=pdata.get("status", "active"),
                    models=models,
                    description=pdata.get("description", ""),
                    meta=pdata.get("meta", {}),
                )
                self.providers[entry.name] = entry

            self._rebuild_index()
            logger.info(f"加载了 {len(self.providers)} 个 Provider，共 {len(self._model_index)} 个模型")
        except Exception as e:
            logger.error(f"加载 Provider Registry 失败: {e}")

    def _save(self):
        """保存注册表"""
        try:
            data = {
                "version": "1.0",
                "updated_at": datetime.now().isoformat(),
                "providers": [p.to_dict() for p in self.providers.values()],
                "total_providers": len(self.providers),
                "total_models": len(self._model_index),
            }
            with open(self.registry_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Provider Registry 已保存: {len(self.providers)} 个 Provider")
        except Exception as e:
            logger.error(f"保存 Provider Registry 失败: {e}")

    def _rebuild_index(self):
        """重建模型索引"""
        self._model_index = {}
        for provider in self.providers.values():
            for model in provider.models:
                key = f"{model.provider}:{model.model_id}"
                self._model_index[key] = model
                # 别名也加入索引
                for alias in model.aliases:
                    alias_key = f"{model.provider}:{alias}"
                    if alias_key not in self._model_index:
                        self._model_index[alias_key] = model

    def _initialize_default(self):
        """从 SurvivalLoopEngine 推导初始 Provider 列表"""
        try:
            import sys
            sys.path.insert(0, str(self.data_dir.parent.parent))
            from core.survival_loop.engine import SurvivalLoopEngine

            engine = SurvivalLoopEngine()

            for name, config in engine._providers.items():
                model_id = config.get("model", "")
                display = model_id.split("/")[-1] if "/" in model_id else model_id

                model = ProviderModel(
                    provider=name,
                    model_id=model_id,
                    display_name=display,
                    status="active",
                    verified=False,
                )

                entry = ProviderEntry(
                    name=name,
                    base_url=config.get("base_url", ""),
                    status="active",
                    models=[model],
                )

                self.providers[name] = entry

            self._rebuild_index()
            self._save()
            logger.info(f"初始化了 {len(self.providers)} 个默认 Provider")
        except Exception as e:
            logger.warning(f"初始化默认 Provider 失败: {e}")

    # =========================================================================
    # 查询接口
    # =========================================================================

    def get_provider(self, name: str) -> Optional[ProviderEntry]:
        """获取 Provider"""
        return self.providers.get(name)

    def get_model(self, provider: str, model_id: str = "") -> Optional[ProviderModel]:
        """
        获取模型定义

        Args:
            provider: Provider 名称
            model_id: 模型 ID（可以是完整 "provider:model_id" 格式，也可以只是 model_id）

        Returns:
            ProviderModel 或 None
        """
        # 如果 model_id 包含 ":"，解析成 provider:model
        if ":" in provider and not model_id:
            full_key = provider
        else:
            full_key = f"{provider}:{model_id}"

        return self._model_index.get(full_key)

    def list_providers(self, status: str = None) -> List[ProviderEntry]:
        """列出所有 Provider"""
        result = list(self.providers.values())
        if status:
            result = [p for p in result if p.status == status]
        return result

    def list_models(self, provider: str = None,
                    capability: str = None,
                    status: str = "active",
                    verified_only: bool = False) -> List[ProviderModel]:
        """
        列出模型，可按条件过滤

        Args:
            provider: Provider 名称
            capability: 必须包含的能力
            status: 状态过滤
            verified_only: 只返回已验证的

        Returns:
            模型列表
        """
        models = list(self._model_index.values())

        if provider:
            models = [m for m in models if m.provider == provider]
        if capability:
            models = [m for m in models if capability in m.capabilities]
        if status:
            models = [m for m in models if m.status == status]
        if verified_only:
            models = [m for m in models if m.verified]

        return models

    def get_capability_matrix(self) -> Dict[str, Dict[str, bool]]:
        """
        获取能力矩阵

        Returns:
            {model_key: {capability: bool}}
        """
        matrix = {}
        for key, model in self._model_index.items():
            matrix[key] = {cap: True for cap in model.capabilities}
            matrix[key]["provider"] = model.provider
            matrix[key]["verified"] = model.verified
            matrix[key]["status"] = model.status
        return matrix

    # =========================================================================
    # 写入接口（Governor 才能调用）
    # =========================================================================

    def register_provider(self, name: str, base_url: str,
                          description: str = "") -> ProviderEntry:
        """注册一个新 Provider"""
        if name in self.providers:
            return self.providers[name]

        entry = ProviderEntry(
            name=name,
            base_url=base_url,
            status="active",
            description=description,
        )
        self.providers[name] = entry
        self._save()
        return entry

    def register_model(self, provider: str, model_id: str,
                       display_name: str = "",
                       capabilities: List[str] = None,
                       status: str = "active") -> ProviderModel:
        """注册一个新模型"""
        if provider not in self.providers:
            self.register_provider(provider, "")

        # 检查是否已存在
        key = f"{provider}:{model_id}"
        if key in self._model_index:
            return self._model_index[key]

        model = ProviderModel(
            provider=provider,
            model_id=model_id,
            display_name=display_name or model_id,
            capabilities=capabilities or [],
            status=status,
        )
        self.providers[provider].models.append(model)
        self._rebuild_index()
        self._save()
        return model

    def update_model_verification(self, provider: str, model_id: str,
                                  passed: bool, result: str = ""):
        """更新模型验证状态"""
        key = f"{provider}:{model_id}"
        model = self._model_index.get(key)
        if not model:
            # 自动注册
            model = self.register_model(provider, model_id)

        model.verified = passed
        model.last_verified = datetime.now().isoformat()
        model.last_verification_result = result

        if not passed and "404" in result:
            model.status = "deprecated"

        self._save()

    def deprecate_model(self, provider: str, model_id: str,
                        reason: str = ""):
        """标记模型为已弃用"""
        key = f"{provider}:{model_id}"
        model = self._model_index.get(key)
        if model:
            model.status = "deprecated"
            model.meta["deprecation_reason"] = reason
            model.meta["deprecated_at"] = datetime.now().isoformat()
            self._save()

    def generate_markdown_report(self) -> str:
        """生成 Markdown 格式的注册表报告"""
        lines = []
        lines.append("# Provider Registry")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.now().isoformat()}")
        lines.append(f"**Provider 数量**: {len(self.providers)}")
        lines.append(f"**模型总数**: {len(self._model_index)}")
        lines.append("")

        # 按 Provider 分组
        for pname, provider in sorted(self.providers.items()):
            verified_count = sum(1 for m in provider.models if m.verified)
            lines.append(f"## {pname}")
            lines.append("")
            lines.append(f"- Base URL: `{provider.base_url}`")
            lines.append(f"- 状态: {provider.status}")
            lines.append(f"- 模型数: {len(provider.models)} (已验证: {verified_count})")
            lines.append("")

            if provider.models:
                lines.append("| 模型 | 状态 | 已验证 | 能力 |")
                lines.append("|------|------|--------|------|")
                for m in provider.models:
                    v = "✅" if m.verified else "❌"
                    caps = ", ".join(m.capabilities[:3]) if m.capabilities else "-"
                    lines.append(
                        f"| `{m.model_id}` | {m.status} | {v} | {caps} |"
                    )
                lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("> **Provider Registry 是模型定义的唯一真相来源。**")
        lines.append("> 所有模块必须从这里取模型名，禁止自己定义。")

        return "\n".join(lines)
