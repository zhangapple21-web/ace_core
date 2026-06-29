"""
LLM Client — ACE 本地 LLM 客户端

从 coze-assets 读取配置，直连 API。
不依赖 OneAPI 容器，直接调用。

优先级：
1. 本地 API Key（从 coze-assets 读取）
2. 云端 OneAPI（作为备用）

配置来源：
- coze-assets/01_credentials/SECRET.md
- coze-assets/02_miner_config/miner_env.sh
"""

import os
import json
import requests
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    """LLM 配置"""
    base_url: str
    api_key: str
    model: str = "gpt-4o"
    timeout: int = 120

    def to_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }


@dataclass
class ModelInfo:
    """模型信息"""
    name: str
    provider: str
    config: LLMConfig
    priority: int = 100  # 越小越优先


class LLMRouter:
    """
    LLM 路由 — 根据任务类型选择最佳模型

    模型优先级：
    - quick（快速任务）：用便宜快的模型
    - medium（标准任务）：用标准模型
    - deep（深度任务）：用最强模型
    """

    def __init__(self, coze_assets_path: str):
        self.coze_assets_path = Path(coze_assets_path)
        self.models: List[ModelInfo] = []
        self._load_configs()
        self._sort_by_priority()

    def _load_configs(self):
        """从 coze-assets 加载所有模型配置"""
        # 读取环境变量文件
        env_file = self.coze_assets_path / "02_miner_config" / "miner_env.sh"
        if env_file.exists():
            env_vars = self._parse_env_file(env_file)

            # GitHub Models
            if github_pat := env_vars.get("GITHUB_PAT"):
                self.models.append(ModelInfo(
                    name="gpt-4o",
                    provider="github",
                    config=LLMConfig(
                        base_url="https://models.inference.ai.azure.com/v1/chat/completions",
                        api_key=github_pat,
                        model="gpt-4o",
                    ),
                    priority=10,
                ))

            # 智谱 GLM
            if zhipu_key := env_vars.get("ZHIPU_KEY"):
                self.models.append(ModelInfo(
                    name="glm-4-flash",
                    provider="zhipu",
                    config=LLMConfig(
                        base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
                        api_key=zhipu_key,
                        model="glm-4-flash",
                    ),
                    priority=20,
                ))
                self.models.append(ModelInfo(
                    name="glm-4",
                    provider="zhipu",
                    config=LLMConfig(
                        base_url="https://open.bigmodel.cn/api/paas/v4/chat/completions",
                        api_key=zhipu_key,
                        model="glm-4",
                    ),
                    priority=30,
                ))

            # OpenRouter
            if openrouter_key := env_vars.get("OPENROUTER_KEY"):
                self.models.append(ModelInfo(
                    name="claude-3.5-sonnet",
                    provider="openrouter",
                    config=LLMConfig(
                        base_url="https://openrouter.ai/api/v1/chat/completions",
                        api_key=openrouter_key,
                        model="anthropic/claude-3.5-sonnet",
                    ),
                    priority=15,
                ))

            # NVIDIA NIM Keys
            nim_keys = [
                ("NIM_KEY_8", "deepseek-ai/deepseek-v4"),
                ("NIM_KEY_15", "mistralai/mistral-medium-3.5-128b"),
                ("NIM_KEY_16", "deepseek-ai/deepseek-v4-pro"),
            ]
            for key_name, model_name in nim_keys:
                if key := env_vars.get(key_name):
                    self.models.append(ModelInfo(
                        name=model_name,
                        provider="nvidia",
                        config=LLMConfig(
                            base_url="https://integrate.api.nvidia.com/v1/chat/completions",
                            api_key=key,
                            model=model_name,
                        ),
                        priority=25,
                    ))

        # 云端 OneAPI（备用）
        self.models.append(ModelInfo(
            name="oneapi-cloud",
            provider="oneapi",
            config=LLMConfig(
                base_url="http://localhost:3000/v1/chat/completions",
                api_key="jHhtKnCuHVriXUaHC992D9B645D44e8a9c901625A17fCd41",
                model="gpt-4o",
            ),
            priority=50,
        ))

    def _parse_env_file(self, path: Path) -> Dict[str, str]:
        """解析 .sh 环境变量文件"""
        result = {}
        for line in path.read_text().split("\n"):
            line = line.strip()
            if line.startswith("export ") and "=" in line:
                # export VAR="value" 或 export VAR='value'
                rest = line[7:]  # 去掉 "export "
                if "=" in rest:
                    key, _, value = rest.partition("=")
                    value = value.strip().strip('"\'')
                    result[key.strip()] = value
        return result

    def _sort_by_priority(self):
        """按优先级排序"""
        self.models.sort(key=lambda m: m.priority)

    def get_model(self, tier: str = "medium") -> ModelInfo:
        """
        获取模型

        tier:
        - quick: 便宜快（priority 10-20）
        - medium: 标准（priority 20-40）
        - deep: 最强（priority 40+）
        """
        if tier == "quick":
            return next((m for m in self.models if m.priority <= 20), self.models[0])
        elif tier == "deep":
            return next((m for m in self.models if m.priority >= 30), self.models[-1])
        else:
            return self.models[0]

    def call(
        self,
        messages: List[Dict[str, str]],
        tier: str = "medium",
        **kwargs,
    ) -> Dict[str, Any]:
        """
        调用 LLM

        自动路由，失败自动切换下一个
        """
        # 根据 tier 确定最小优先级
        if tier == "quick":
            max_priority = 20
        elif tier == "deep":
            max_priority = 999  # 用所有模型
        else:
            max_priority = 40

        # 只尝试优先级 <= max_priority 的模型
        candidates = [m for m in self.models if m.priority <= max_priority]
        if not candidates:
            candidates = self.models  # 如果没有匹配的，用所有模型

        for m in candidates:
            try:
                response = requests.post(
                    m.config.base_url,
                    headers=m.config.to_headers(),
                    json={
                        "model": m.config.model,
                        "messages": messages,
                        **kwargs,
                    },
                    timeout=m.config.timeout,
                )
                if response.status_code == 200:
                    return response.json()
                else:
                    print(f"⚠️ {m.name} 失败: {response.status_code} - {response.text[:100]}")
            except Exception as e:
                print(f"⚠️ {m.name} 错误: {str(e)[:80]}")
                continue

        raise Exception("所有模型都失败了")

    def list_models(self) -> List[Dict[str, Any]]:
        """列出所有可用模型"""
        return [
            {
                "name": m.name,
                "provider": m.provider,
                "priority": m.priority,
            }
            for m in self.models
        ]


# 全局实例
_llm_router: Optional[LLMRouter] = None


def get_llm_router() -> LLMRouter:
    """获取 LLM 路由单例"""
    global _llm_router
    if _llm_router is None:
        coze_assets = Path(__file__).parent.parent.parent / "coze-assets"
        if not coze_assets.exists():
            coze_assets = Path("c:/Users/USER/Downloads/Telegram Desktop/coze-assets")
        _llm_router = LLMRouter(str(coze_assets))
    return _llm_router


def chat(messages: List[Dict[str, str]], tier: str = "medium") -> str:
    """简单聊天接口"""
    router = get_llm_router()
    result = router.call(messages, tier=tier)
    return result.get("choices", [{}])[0].get("message", {}).get("content", "")
