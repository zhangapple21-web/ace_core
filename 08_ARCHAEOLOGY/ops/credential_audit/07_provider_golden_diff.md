# Provider Golden Diff 报告

生成时间: 2026-06-30T20:37:20.763345

对比：SECRET.md 配置（真相源） vs Runtime 实际使用值

## nim

| 字段 | SECRET.md 配置 | Runtime 实际值 | 一致？ |
|------|--------------|--------------|-------|
| Base URL | https://integrate.api.nvidia.com/v1 | https://integrate.api.nvidia.com/v1 | ✅ |
| Token 来源 | SECRET.md | CredentialManager | ✅ |
| Token 前缀 | nvapi-drrkxZ... | nvapi-drrkxZ... | ✅ |
| Factory 类 | N/A | NIMProvider | N/A |
| Chat 状态 | N/A | HTTP 200 | N/A |

## github_models

| 字段 | SECRET.md 配置 | Runtime 实际值 | 一致？ |
|------|--------------|--------------|-------|
| Base URL | https://models.inference.ai.azure.com | https://models.inference.ai.azure.com | ✅ |
| Token 来源 | SECRET.md | CredentialManager | ✅ |
| Token 前缀 | github_pat_1... | github_pat_1... | ✅ |
| Factory 类 | N/A | GitHubModelsProvider | N/A |
| Chat 状态 | N/A | HTTP 401 | N/A |

## glm

| 字段 | SECRET.md 配置 | Runtime 实际值 | 一致？ |
|------|--------------|--------------|-------|
| Base URL | https://open.bigmodel.cn/api/paas/v4 | https://open.bigmodel.cn/api/paas/v4 | ✅ |
| Token 来源 | SECRET.md | CredentialManager | ✅ |
| Token 前缀 | c4c766faaf97... | c4c766faaf97... | ✅ |
| Factory 类 | N/A | GLMProvider | N/A |
| Chat 状态 | N/A | HTTP 200 | N/A |

## modelscope

| 字段 | SECRET.md 配置 | Runtime 实际值 | 一致？ |
|------|--------------|--------------|-------|
| Base URL | https://api-inference.modelscope.cn/v1 | https://api-inference.modelscope.cn/v1 | ✅ |
| Token 来源 | SECRET.md | CredentialManager | ✅ |
| Token 前缀 | ms-7ab1f34e-... | ms-7ab1f34e-... | ✅ |
| Factory 类 | N/A | OpenAICompatibleProvider | N/A |
| Chat 状态 | N/A | HTTP 400 | N/A |

## apiyi

| 字段 | SECRET.md 配置 | Runtime 实际值 | 一致？ |
|------|--------------|--------------|-------|
| Base URL | https://api.apiyi.com | https://api.apiyi.com | ✅ |
| Token 来源 | SECRET.md | CredentialManager | ✅ |
| Token 前缀 | sk-xQrs9IDbj... | sk-xQrs9IDbj... | ✅ |
| Factory 类 | N/A | APIYiProvider | N/A |
| Chat 状态 | N/A | HTTP 200 | N/A |

## openrouter

| 字段 | SECRET.md 配置 | Runtime 实际值 | 一致？ |
|------|--------------|--------------|-------|
| Base URL | https://openrouter.ai/api/v1 | https://openrouter.ai/api/v1 | ✅ |
| Token 来源 | SECRET.md | CredentialManager | ✅ |
| Token 前缀 | sk-or-v1-dc1... | sk-or-v1-dc1... | ✅ |
| Factory 类 | N/A | OpenRouterProvider | N/A |
| Chat 状态 | N/A | HTTP 401 | N/A |

## oneapi

| 字段 | SECRET.md 配置 | Runtime 实际值 | 一致？ |
|------|--------------|--------------|-------|
| Base URL | http://localhost:3000/v1 | http://localhost:3000/v1 | ✅ |
| Token 来源 | SECRET.md | CredentialManager | ✅ |
| Token 前缀 | jHhtKnCuHVri... | jHhtKnCuHVri... | ✅ |
| Factory 类 | N/A | OneAPIProvider | N/A |
| Chat 状态 | N/A | HTTP N/A | N/A |

## sambanova

| 字段 | SECRET.md 配置 | Runtime 实际值 | 一致？ |
|------|--------------|--------------|-------|
| Base URL | https://api.sambanova.ai/v1 | https://api.sambanova.ai/v1 | ✅ |
| Token 来源 | miner_env.sh | CredentialManager | ✅ |
| Token 前缀 | 820feeb9-020... | 820feeb9-020... | ✅ |
| Factory 类 | N/A | SambaNovaProvider | N/A |
| Chat 状态 | N/A | HTTP 410 | N/A |

## huggingface

| 字段 | SECRET.md 配置 | Runtime 实际值 | 一致？ |
|------|--------------|--------------|-------|
| Base URL | https://api-inference.huggingface.co/v1 | https://api-inference.huggingface.co/v1 | ✅ |
| Token 来源 | miner_env.sh | CredentialManager | ✅ |
| Token 前缀 | hf_rtqFhpEdO... | hf_rtqFhpEdO... | ✅ |
| Factory 类 | N/A | OpenAICompatibleProvider | N/A |
| Chat 状态 | N/A | HTTP N/A | N/A |
