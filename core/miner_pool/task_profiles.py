"""
任务画像 — 什么任务派什么模型

不是按模型好坏排序。
是按任务类型匹配最合适的算力。

任务类型定义：
  hypothesis_generation  — 生成候选假设（Researcher用，需要创造力+广度）
  cross_validation       — 交叉验证（Validator用，需要严谨+找反例）
  synthesis              — 综合总结（Archivist用，需要结构化+提炼）
  classification         — 分类任务（快速、便宜、量大）
  extraction             — 信息提取（精准、不漏）
  coding                 — 代码任务（深度推理+代码理解）
  reasoning              — 深度推理（复杂问题）
  fast_response          — 快速响应（低延迟优先）
"""

from typing import Dict, List, Any


TASK_PROFILES: Dict[str, Dict[str, Any]] = {
    "hypothesis_generation": {
        "description": "生成候选假设",
        "preferred_traits": ["creativity", "breadth", "diversity"],
        "avoid_traits": ["conservative", "over_confident"],
        "temperature": 0.8,
        "max_tokens": 2048,
        "timeout": 120,
        "preferred_models": [
            "ace_proxy:gpt-4o",
            "nim:nvidia/nemotron-3-ultra-550b-a55b",
            "nim:mistralai/mistral-large-3-675b-instruct-2512",
            "github_models:gpt-4o",
            "openrouter:anthropic/claude-3.5-sonnet",
        ],
        "fallback_models": [
            "ace_proxy:gpt-4o-mini",
            "nim:moonshotai/kimi-k2.6",
            "nim:qwen/qwen3.5-397b-a17b",
            "glm:glm-4-air",
        ],
        "strategy": "diverse",  # 多个模型生成不同视角
    },
    "cross_validation": {
        "description": "交叉验证/找反例",
        "preferred_traits": ["skepticism", "precision", "detail_oriented"],
        "avoid_traits": ["agreeable", "superficial"],
        "temperature": 0.3,
        "max_tokens": 1536,
        "timeout": 90,
        "preferred_models": [
            "nim:mistralai/mistral-large-3-675b-instruct-2512",
            "github_models:gpt-4o-mini",
            "nim:nvidia/nemotron-3-super-120b-a12b",
        ],
        "fallback_models": [
            "nim:qwen/qwen3.5-122b-a10b",
            "glm:glm-4-flash",
        ],
        "strategy": "conservative",
    },
    "synthesis": {
        "description": "综合总结/归档",
        "preferred_traits": ["structured", "concise", "pattern_recognition"],
        "avoid_traits": ["verbose", "distracted"],
        "temperature": 0.5,
        "max_tokens": 3072,
        "timeout": 120,
        "preferred_models": [
            "nim:mistralai/mistral-large-3-675b-instruct-2512",
            "nim:nvidia/nemotron-3-ultra-550b-a55b",
            "github_models:gpt-4o",
        ],
        "fallback_models": [
            "nim:qwen/qwen3.5-397b-a17b",
            "glm:glm-4-air",
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
            "glm:glm-4-flash",
            "nim:deepseek-ai/deepseek-v4-flash",
            "github_models:gpt-4o-mini",
        ],
        "fallback_models": [
            "nim:openai/gpt-oss-20b",
            "nim:stepfun-ai/step-3.7-flash",
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
            "glm:glm-4-air",
            "nim:mistralai/mistral-large-3-675b-instruct-2512",
            "github_models:gpt-4o-mini",
        ],
        "fallback_models": [
            "nim:qwen/qwen3.5-122b-a10b",
            "glm:glm-4-flash",
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
            "nim:nvidia/nemotron-3-ultra-550b-a55b",
            "nim:mistralai/mistral-large-3-675b-instruct-2512",
            "github_models:gpt-4o",
        ],
        "fallback_models": [
            "nim:qwen/qwen3.5-397b-a17b",
            "nim:deepseek-ai/deepseek-v4-flash",
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
            "nim:nvidia/nemotron-3-ultra-550b-a55b",
            "nim:mistralai/mistral-large-3-675b-instruct-2512",
            "github_models:DeepSeek-R1",
        ],
        "fallback_models": [
            "nim:qwen/qwen3.5-397b-a17b",
            "nim:moonshotai/kimi-k2.6",
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
            "glm:glm-4-flash",
            "nim:openai/gpt-oss-20b",
            "nim:stepfun-ai/step-3.7-flash",
            "github_models:gpt-4o-mini",
        ],
        "fallback_models": [
            "nim:google/gemma-4-31b-it",
            "nim:minimaxai/minimax-m2.7",
        ],
        "strategy": "latency_first",
    },
}


def get_task_profile(task_type: str) -> Dict[str, Any]:
    """获取任务画像，不存在则返回默认"""
    if task_type in TASK_PROFILES:
        return TASK_PROFILES[task_type]
    # 默认用 fast_response
    return TASK_PROFILES["fast_response"]


def list_task_types() -> List[str]:
    """列出所有任务类型"""
    return list(TASK_PROFILES.keys())
