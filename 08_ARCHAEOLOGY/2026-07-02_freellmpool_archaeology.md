# freellmpool 考古报告

**日期**: 2026-07-02
**来源**: https://github.com/0xzr/freellmpool
**处理法**: 五步处理法 + 认知熵检查
**结论**: ACE 已有 70% 能力，3 个可借鉴点，不替换不安装，等 moratorium 结束后提取骨架

---

## ① 识别

freellmpool 是一个免费 LLM 提供商池化工具：

- 19 个提供商（Groq/Cerebras/NIM/Gemini/OpenRouter/GitHub Models/Cloudflare/Mistral/Cohere/Pollinations/OVHcloud/Kilo/LLM7 等）
- 237 条路由、358 个模型
- CLI + Python 库 + 本地代理（OpenAI 兼容端点）
- MCP server（`freellmpool mcp`）
- Failover + 健康探测 + 延迟感知路由 + 角色预设
- 无 key 启动（3 个 keyless provider）
- Python 3.11+，只依赖 httpx
- `tokenmax` 模式：同一 prompt 多模型并发，对比答案

**信号强度**: ⭐⭐⭐ （有 3 个 ACE 没有的能力，但核心功能 ACE 已有）

---

## ② 映射

| freellmpool 能力 | ACE 对应 | 覆盖度 |
|----------------|---------|--------|
| 19 提供商池化 | miner_pool + credential_manager | ✅ 80%（取决于配置） |
| Failover | ProviderWatchdog.get_best_provider() | ✅ 85% |
| 健康探测 | ProviderWatchdog.is_healthy + record_success/failure | ✅ 85% |
| 延迟感知路由 | ModelRouter + task_profiles | ✅ 75% |
| 角色预设 | task_profiles | ✅ 70% |
| MCP server | ❌ 无 | 0% |
| 无 key 启动 | ❌ 无（必须先配置 credential） | 0% |
| tokenmax 多模型对比 | ❌ 无（三重交叉验证在知识层，不在 LLM 层） | 0% |
| 异步 API | ❌ 无（当前同步） | 0% |
| 插件系统 | PROVIDER_FACTORY | ✅ 70% |

**整体覆盖度**: ~65%

---

## ③ 改造

### 可借鉴的 3 个洞见

**洞见 1：Keyless Provider 作为最后兜底**

freellmpool 有 3 个不需要 API key 的提供商（Pollinations/OVHcloud/LLM7）。

ACE 的 miner_pool 目前必须先配置 credential 才能启动。如果所有配置的 provider 都挂了，系统就完全没有 LLM 能力了。

改造方向：在 miner_pool 的 providers/ 下增加 keyless provider 实现，作为 FallbackChain 的最后一级。

**洞见 2：MCP Server 暴露 LLM 池**

freellmpool 用 `freellmpool mcp` 把 LLM 池暴露为 MCP 工具，外部 agent 可以直接调用。

ACE 的 miner_pool 目前只被主循环内部调用，没有暴露为标准接口。如果其他 agent/工具想用 ACE 的 LLM 池，只能改代码。

改造方向：在 ProtocolToolProvider 里增加 `llm_chat` 工具，封装 miner_pool 的 chat 方法。

**洞见 3：Tokenmax 模式 = LLM 层交叉验证**

freellmpool 的 `tokenmax` 把同一 prompt 同时发给多个模型，对比答案。这和 ACE 的三重交叉验证思路一致，但做在 LLM 层而不是知识层。

改造方向：在 miner_pool 增加 `chat_multi()` 方法，同一 prompt 发给 N 个 provider，返回所有结果 + 一致性分析。Governor 在做重要决策时可以用这个模式。

### 明确拒绝的

- ❌ 不替换 miner_pool — ACE 的 miner_pool 和治理体系打通，替换破坏结构
- ❌ 不安装 freellmpool 作为依赖 — 提取骨架，不引入外部依赖
- ❌ 不现在做 — 30 天 moratorium

---

## ④ 落地

### 横切一致性检查

| 相关模块 | 同类问题 | 一起改？ | 理由 |
|---------|---------|---------|------|
| miner_pool/miner_pool.py | 缺 keyless provider | **记录待办** | moratorium 结束后加 |
| miner_pool/providers/ | 只有 openai_compatible | **记录待办** | 增加 keyless provider |
| protocols/tool_provider.py | 缺 llm_chat 工具 | **记录待办** | 暴露 miner_pool 为工具 |
| triple_cross_validation.py | 知识层交叉验证，没有 LLM 层 | **不动** | 维度不同，不合并 |

### 记录待办

1. miner_pool 增加 keyless provider（Pollinations/LLM7）作为兜底
2. ProtocolToolProvider 增加 `llm_chat` 工具
3. miner_pool 增加 `chat_multi()` 方法（LLM 层交叉验证）

---

## ⑤ 划界

- 不替换 miner_pool
- 不安装 freellmpool 作为依赖
- 不现在实现（moratorium）
- 只记录骨架和借鉴方向

---

## 认知熵检查

```yaml
entropy_check:
  new_active_concepts: 0
  existing_concepts_enhanced: 3  # miner_pool(keyless)、tool_provider(llm_chat)、miner_pool(chat_multi)
  concept_density_delta: "+0.00"
  new_files_created: 0
  judgment: "越学越稳。freellmpool 的核心能力 ACE 已有 65%，3 个缺口记录待办，不引入新依赖。"
```
