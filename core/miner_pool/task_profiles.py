"""
任务画像 — 什么任务派什么模型

不是按模型好坏排序。
是按任务类型匹配最合适的算力。

路由优先级（2026-06-30 实际可用性扫描后更新）：
  1. glm:glm-4-flash（智谱，当前唯一稳定可用的独立API）
  2. ace_proxy（ACE 本地代理，如已启动则自动接管）
  3. github_models（GitHub Models，Token 失效待更新）
  4. nim（NVIDIA NIM，模型路径待排查）
  5. 其他提供商（OpenRouter、SambaNova 等，作为兜底）

注意：模型顺序 = 尝试顺序。
     第一个可用的会被直接使用，失败自动降级试下一个。
"""

from typing import Dict, List, Any


GLM_FLASH = "glm:glm-4-flash"
ACE_GPT4O = "ace_proxy:gpt-4o"
ACE_GPT4O_MINI = "ace_proxy:gpt-4o-mini"
GITHUB_GPT4O = "github_models:gpt-4o"
GITHUB_GPT4O_MINI = "github_models:gpt-4o-mini"
NIM_NEMOTRON_ULTRA = "nim:nvidia/nemotron-3-ultra-550b-a55b"
NIM_MISTRAL_LARGE = "nim:mistralai/mistral-large-3-675b-instruct-2512"
NIM_DEEPSEEK_V4 = "nim:deepseek-ai/deepseek-v4"
NIM_QWEN_397B = "nim:qwen/qwen3.5-397b-a17b"
OPENROUTER_CLAUDE = "openrouter:anthropic/claude-3.5-sonnet"


TASK_PROFILES: Dict[str, Dict[str, Any]] = {
    "hypothesis_generation": {
        "description": "生成候选假设",
        "preferred_traits": ["creativity", "breadth", "diversity"],
        "avoid_traits": ["conservative", "over_confident"],
        "temperature": 0.8,
        "max_tokens": 2048,
        "timeout": 120,
        "preferred_models": [
            GLM_FLASH,
            ACE_GPT4O,
            GITHUB_GPT4O,
            NIM_MISTRAL_LARGE,
            NIM_NEMOTRON_ULTRA,
            OPENROUTER_CLAUDE,
        ],
        "fallback_models": [
            ACE_GPT4O_MINI,
            GITHUB_GPT4O_MINI,
            NIM_QWEN_397B,
        ],
        "strategy": "quality_first",
    },
    "cross_validation": {
        "description": "交叉验证/找反例",
        "preferred_traits": ["skepticism", "precision", "detail_oriented"],
        "avoid_traits": ["agreeable", "superficial"],
        "temperature": 0.3,
        "max_tokens": 1536,
        "timeout": 90,
        "preferred_models": [
            GLM_FLASH,
            ACE_GPT4O_MINI,
            GITHUB_GPT4O_MINI,
            NIM_MISTRAL_LARGE,
        ],
        "fallback_models": [
            NIM_QWEN_397B,
        ],
        "strategy": "quality_first",
    },
    "synthesis": {
        "description": "综合总结/归档",
        "preferred_traits": ["structured", "concise", "pattern_recognition"],
        "avoid_traits": ["verbose", "distracted"],
        "temperature": 0.5,
        "max_tokens": 3072,
        "timeout": 120,
        "preferred_models": [
            GLM_FLASH,
            ACE_GPT4O,
            GITHUB_GPT4O,
            NIM_MISTRAL_LARGE,
            NIM_NEMOTRON_ULTRA,
        ],
        "fallback_models": [
            NIM_QWEN_397B,
        ],
        "strategy": "quality_first",
    },
    "classification": {
        "description": "分类任务",
        "preferred_traits": ["fast", "consistent", "cheap"],
        "avoid_traits": ["creative", "slow"],
        "temperature": 0.1,
        "max_tokens": 256,
        "timeout": 30,
        "preferred_models": [
            GLM_FLASH,
            ACE_GPT4O_MINI,
            GITHUB_GPT4O_MINI,
            NIM_DEEPSEEK_V4,
        ],
        "fallback_models": [
            NIM_QWEN_397B,
        ],
        "strategy": "cost_effective",
    },
    "extraction": {
        "description": "信息提取",
        "preferred_traits": ["precise", "thorough", "structured"],
        "avoid_traits": ["creative", "hallucinatory"],
        "temperature": 0.2,
        "max_tokens": 1024,
        "timeout": 60,
        "preferred_models": [
            GLM_FLASH,
            ACE_GPT4O_MINI,
            GITHUB_GPT4O_MINI,
            NIM_MISTRAL_LARGE,
        ],
        "fallback_models": [
            NIM_QWEN_397B,
        ],
        "strategy": "precision_first",
    },
    "coding": {
        "description": "代码任务",
        "preferred_traits": ["code_understanding", "debugging", "implementation"],
        "avoid_traits": ["verbose"],
        "temperature": 0.4,
        "max_tokens": 4096,
        "timeout": 180,
        "preferred_models": [
            GLM_FLASH,
            ACE_GPT4O,
            GITHUB_GPT4O,
            NIM_NEMOTRON_ULTRA,
            NIM_MISTRAL_LARGE,
        ],
        "fallback_models": [
            NIM_DEEPSEEK_V4,
            NIM_QWEN_397B,
        ],
        "strategy": "quality_first",
    },
    "reasoning": {
        "description": "深度推理",
        "preferred_traits": ["logical", "step_by_step", "thorough"],
        "avoid_traits": ["superficial", "fast_but_wrong"],
        "temperature": 0.5,
        "max_tokens": 4096,
        "timeout": 240,
        "preferred_models": [
            GLM_FLASH,
            ACE_GPT4O,
            GITHUB_GPT4O,
            NIM_NEMOTRON_ULTRA,
            NIM_MISTRAL_LARGE,
        ],
        "fallback_models": [
            NIM_QWEN_397B,
        ],
        "strategy": "quality_first",
    },
    "fast_response": {
        "description": "快速响应",
        "preferred_traits": ["low_latency", "concise"],
        "avoid_traits": ["slow", "verbose"],
        "temperature": 0.7,
        "max_tokens": 512,
        "timeout": 20,
        "preferred_models": [
            GLM_FLASH,
            ACE_GPT4O_MINI,
            GITHUB_GPT4O_MINI,
        ],
        "fallback_models": [
            NIM_QWEN_397B,
        ],
        "strategy": "latency_first",
    },
}


def get_task_profile(task_type: str) -> Dict[str, Any]:
    """获取任务画像，不存在则返回默认"""
    if task_type in TASK_PROFILES:
        return TASK_PROFILES[task_type]
    return TASK_PROFILES["fast_response"]


def list_task_types() -> List[str]:
    return list(TASK_PROFILES.keys())
