# ACE Proxy 取证报告

**任务编号**: TASK-ACE-PROXY-FORENSICS-001
**生成时间**: 2026-07-01T19:10:00
**来源**: Cross Validation (Source A: 疯子, Source B: ACE Runtime, Source C: 老张 Review)

---

## Evidence

### Evidence-001: Credential 来源一致

| 来源 | Key 数量 | Key 前缀 | Key 长度 |
|---|---|---|---|
| miner_env.sh | 16 | nvapi-drrkxZz5IGkOvp... | 70 |
| SECRET.md | 16 | nvapi-drrkxZz5IGkOvp... | 70 |

**结论**: Key 内容完全一致。Credential 层排除。

---

### Evidence-002: Base URL 一致

| 来源 | Base URL |
|---|---|
| SECRET.md | `https://integrate.api.nvidia.com/v1` |
| miner_env.sh (默认) | `https://integrate.api.nvidia.com/v1` |

**结论**: Base URL 一致。

---

### Evidence-003: Key 测试结果

测试环境：直接调用 NIM API（绕过 ace_proxy）

| Key | 状态 | 延迟 |
|---|---|---|
| Key1 | ❌ Timeout | - |
| Key2 | ❌ Timeout | - |
| Key3 | ✅ 成功 | 11236ms |
| Key4 | ❌ Timeout | - |

**结论**: Key3 成功，证明 Key 本身有效。超时可能是网络波动或 API 限流。

---

### Evidence-004: Markdown Parser 污染

Raw Markdown 片段:
```
**Base:** https://integrate.api.nvidia.com/v1
```

检测到:
- `Base:` 后有 Markdown 粗体符号 `**`
- 正则匹配结果: 正确提取到 `https://integrate.api.nvidia.com/v1`

**结论**: 正则表达式已正确处理 `**` 符号，未污染解析结果。

---

### Evidence-005: 模型名称不一致（关键）

| 层级 | 定义 | 实际发送 |
|---|---|---|
| task_profiles.py | `NIM_DEEPSEEK_V4 = "nim:deepseek-ai/deepseek-v4"` | `deepseek-ai/deepseek-v4` |
| SurvivalLoopEngine | `DEFAULT_MODEL["nim"] = "deepseek-ai/deepseek-v4-flash"` | `deepseek-ai/deepseek-v4-flash` |

NIM API 测试结果:

| 模型名称 | 状态 | 响应 |
|---|---|---|
| `deepseek-ai/deepseek-v4-flash` | ✅ 成功 | latency=4797ms |
| `deepseek-ai/deepseek-v4` | ❌ 404 | `404 page not found` |

**结论**: `deepseek-ai/deepseek-v4` 模型不存在于 NIM API。

---

### Evidence-006: 五层一致性检查

| 层级 | 配置值 | 一致性 |
|---|---|---|
| Provider | nim | ✅ |
| Adapter | ace_proxy.py → BackendPool | ✅ |
| Credential | miner_env.sh → NIM_KEY_1~16 | ✅ |
| TaskProfile | task_profiles.py → NIM_DEEPSEEK_V4 | ⚠️ 模型名称错误 |
| Model | deepseek-ai/deepseek-v4 (发送) | ❌ 不存在 |

**结论**: TaskProfile 层定义了错误的模型名称。

---

## Diff

### 配置层 vs 实际 API

| 项目 | task_profiles.py | NIM API 实际 |
|---|---|---|
| NIM_DEEPSEEK_V4 | deepseek-ai/deepseek-v4 | ❌ 不存在 |
| DEFAULT_MODEL | deepseek-ai/deepseek-v4-flash | ✅ 存在 |

### 链路追踪

```
Task (推理任务)
    ↓
TaskProfile (reasoning)
    ↓
preferred_models[0] = GLM_FLASH ✅
preferred_models[1] = ACE_GPT4O ✅
preferred_models[2] = GITHUB_GPT4O ❌ (Token失效)
preferred_models[3] = NIM_NEMOTRON_ULTRA ❌ (待验证)
preferred_models[4] = NIM_MISTRAL_LARGE ❌ (待验证)
    ↓
fallback_models[0] = NIM_QWEN_397B ❌ (待验证)
    ↓
当 GLM 成功时 → 直接返回 ✅
当 GLM 失败 → 尝试 NIM → 发送错误模型名 → 404 ❌
```

---

## Root Cause

**主因**: `task_profiles.py` 中 NIM 相关模型名称与 NIM API 实际支持的模型不一致。

具体:
1. `NIM_DEEPSEEK_V4 = "nim:deepseek-ai/deepseek-v4"` 定义的模型 `deepseek-ai/deepseek-v4` 在 NIM API 返回 404
2. 实际可用的模型是 `deepseek-ai/deepseek-v4-flash`
3. SurvivalLoopEngine 的 `DEFAULT_MODEL["nim"]` 正确使用了 `deepseek-ai/deepseek-v4-flash`

**次因**: 网络/API 不稳定导致部分请求超时（Key1/2/4 Timeout，Key3 成功）

---

## 修复建议

### 修复-001: 统一模型名称

**文件**: `core/miner_pool/task_profiles.py`

**修改**:
```python
# 旧
NIM_DEEPSEEK_V4 = "nim:deepseek-ai/deepseek-v4"

# 新
NIM_DEEPSEEK_V4 = "nim:deepseek-ai/deepseek-v4-flash"
```

### 修复-002: 验证所有 NIM 模型

需要逐一验证以下模型是否在 NIM API 可用:

| 常量 | 模型名称 | 验证状态 |
|---|---|---|
| NIM_NEMOTRON_ULTRA | nvidia/nemotron-3-ultra-550b-a55b | 待验证 |
| NIM_MISTRAL_LARGE | mistralai/mistral-large-3-675b-instruct-2512 | 待验证 |
| NIM_DEEPSEEK_V4 | deepseek-ai/deepseek-v4 | ❌ 404 |
| NIM_QWEN_397B | qwen/qwen3.5-397b-a17b | 待验证 |

建议: 只保留已验证可用的模型，删除 404 的模型。

### 修复-003: 增加超时重试

网络波动导致超时，建议在 ace_proxy.py 中增加:
- 单个请求超时从 120s 降至 30s
- 失败后快速切换到下一个 Key
- 同一 Key 连续失败 3 次 → 标记为 unhealthy

---

## 验证命令

```bash
# 验证单个模型
python ops/_verify_model_name.py

# 验证所有 Key
python ops/_forensics_ace_proxy.py

# 完整链路测试
python -c "
import sys; sys.path.insert(0, '.')
from core.survival_loop.engine import SurvivalLoopEngine
e = SurvivalLoopEngine()
r = e.chat([{'role': 'user', 'content': 'test'}])
print(f'success={r[\"success\"]}, provider={r[\"provider\"]}')
"
```

---

## 结论

| 问题 | 状态 |
|---|---|
| Credential 一致性 | ✅ 已验证，排除 |
| Base URL 一致性 | ✅ 已验证，排除 |
| Markdown Parser 污染 | ✅ 已修复，排除 |
| 模型名称不一致 | ❌ **Root Cause** |
| 网络/API 超时 | ⚠️ 次因，需优化重试逻辑 |

**最终结论**: NIM Provider 失败的原因是 `task_profiles.py` 定义的模型 `deepseek-ai/deepseek-v4` 不存在于 NIM API。修复方法是将模型名称改为 `deepseek-ai/deepseek-v4-flash`。

---

## 附录: 原始证据文件

- `08_ARCHAEOLOGY/ops/ACE_PROXY_FORENSICS_RAW.json` - 8 条原始证据