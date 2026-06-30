# Claude Code MCP 架构考古报告

**日期**: 2026-06-30
**考古对象**: `claude-code-l3tchupkt/mcp/` 目录
**考古目标**: 提取 Claude Code 的 MCP 集成层骨架，为 ACE 吸收做准备

---

## 一、目录结构分析

### 1.1 文件清单

Claude Code 的 MCP 相关文件分布在多个目录中，不是集中在单一 `mcp/` 目录下：

```
services/mcp/                          ← 核心服务层（29个文件）
├── types.ts                           ← 类型定义（配置、连接状态、资源）
├── client.ts                          ← MCP 客户端核心（连接、工具调用、响应处理）
├── config.ts                          ← 配置管理（多scope、去重、策略过滤）
├── auth.ts                            ← OAuth 认证（完整的 OAuth2 + PKCE 流程）
├── channelPermissions.ts              ← 通道权限中继（Telegram/iMessage 等）
├── channelAllowlist.ts                ← 通道白名单
├── channelNotification.ts             ← 通道通知
├── normalization.ts                   ← 名称规范化
├── utils.ts                           ← 工具函数（过滤、哈希、状态检测）
├── officialRegistry.ts                ← 官方 MCP 注册表预取
├── claudeai.ts                        ← Claude.ai 连接器
├── elicitationHandler.ts              ← Elicitation 请求处理
├── envExpansion.ts                    ← 环境变量展开
├── headersHelper.ts                   ← HTTP Headers 辅助
├── mcpStringUtils.ts                  ← MCP 字符串工具
├── oauthPort.ts                       ← OAuth 回调端口管理
├── useManageMCPConnections.ts         ← React Hook 连接管理
├── SdkControlTransport.ts             ← SDK 控制传输
├── InProcessTransport.ts              ← 进程内传输（Chrome/Computer Use）
├── vscodeSdkMcp.ts                    ← VSCode SDK 集成
├── xaa.ts                             ← 跨应用访问（Cross-App Access）
├── xaaIdpLogin.ts                     ← XAA IdP 登录
└── ...

tools/MCPTool/                         ← MCP 工具层
├── MCPTool.ts                         ← MCP 工具定义骨架
├── prompt.ts                          ← 工具提示词
├── classifyForCollapse.ts             ← 结果折叠分类
└── UI.tsx                             ← UI 渲染

tools/ReadMcpResourceTool/             ← 资源读取工具
tools/ListMcpResourcesTool/            ← 资源列表工具
tools/McpAuthTool/                     ← MCP 认证工具

utils/mcp/                             ← MCP 工具函数
├── dateTimeParser.ts                  ← 日期时间解析
└── elicitationValidation.ts           ← Elicitation 验证

utils/
├── mcpValidation.ts                   ← MCP 输出验证与截断
├── mcpOutputStorage.ts                ← MCP 输出存储（大文件处理）
├── mcpInstructionsDelta.ts            ← 指令增量计算
├── mcpWebSocketTransport.ts           ← WebSocket 传输
└── ...

commands/mcp/                          ← MCP CLI 命令
├── index.ts                           ← 命令入口
├── addCommand.ts                      ← 添加 MCP 服务器命令
└── xaaIdpCommand.ts                   ← XAA 配置命令

components/mcp/                        ← UI 组件
```

### 1.2 架构层次

```
┌─────────────────────────────────────────────────────┐
│                   UI / CLI Layer                     │
│  (components/mcp, commands/mcp, tools/MCPTool/UI)   │
├─────────────────────────────────────────────────────┤
│              Tool Abstraction Layer                  │
│  (MCPTool.ts, ReadMcpResourceTool, ListMcpResources)│
├─────────────────────────────────────────────────────┤
│              Connection Management                   │
│  (useManageMCPConnections, client.ts 连接部分)       │
├─────────────────────────────────────────────────────┤
│                Core Client Layer                     │
│  (client.ts 工具调用/响应处理/错误处理)              │
├─────────────────────────────────────────────────────┤
│              Transport Layer                         │
│  (stdio/sse/http/ws/sdk/in-process)                 │
├─────────────────────────────────────────────────────┤
│              Auth Layer                              │
│  (auth.ts, OAuth, XAA, xaaIdpLogin)                 │
├─────────────────────────────────────────────────────┤
│              Configuration Layer                     │
│  (config.ts, types.ts, normalization.ts)            │
└─────────────────────────────────────────────────────┘
```

---

## 二、核心骨架提取（5个）

### 骨架1：多 Scope 配置层级系统

**位置**: `services/mcp/config.ts` + `services/mcp/types.ts`

**设计要点**:

1. **7 种配置作用域**，优先级从低到高：
   - `claudeai` — Claude.ai 连接器（最低优先级）
   - `dynamic` — 命令行动态配置
   - `plugin` — 插件提供的服务器
   - `user` — 用户全局配置
   - `project` — 项目级 `.mcp.json`（从 CWD 向上遍历）
   - `local` — 项目本地设置
   - `enterprise` — 企业托管配置（最高优先级，独占模式）

2. **去重策略**（内容签名而非名称）：
   ```typescript
   // 按命令或URL生成签名，检测重复
   function getMcpServerSignature(config: McpServerConfig): string | null {
     const cmd = getServerCommandArray(config)
     if (cmd) return `stdio:${jsonStringify(cmd)}`
     const url = getServerUrl(config)
     if (url) return `url:${unwrapCcrProxyUrl(url)}`
     return null
   }
   ```
   - 手动配置 > 插件配置
   - 先加载的插件 > 后加载的插件
   - Claude.ai 连接器最低，与手动配置去重

3. **企业策略过滤**：
   - Allowlist：`allowedMcpServers`（名称/命令/URL 三种匹配方式）
   - Denylist：`deniedMcpServers`（优先于 allowlist）
   - `allowManagedMcpServersOnly`：仅允许托管配置

4. **配置写入原子性**：
   ```typescript
   // 写临时文件 → datasync → 原子重命名 → 保留权限
   async function writeMcpjsonFile(config: McpJsonConfig): Promise<void> {
     const tempPath = `${mcpJsonPath}.tmp.${process.pid}.${Date.now()}`
     const handle = await open(tempPath, 'w', existingMode ?? 0o644)
     await handle.writeFile(jsonStringify(config, null, 2))
     await handle.datasync()  // 刷到磁盘
     await handle.close()
     await rename(tempPath, mcpJsonPath)  // 原子替换
   }
   ```

**可吸收点**: ACE 的配置系统目前只有单层，可吸收多 scope + 内容去重 + 策略过滤的设计。

---

### 骨架2：连接状态机与重连机制

**位置**: `services/mcp/client.ts` + `services/mcp/types.ts`

**设计要点**:

1. **5 种连接状态**（区分态，不是布尔值）：
   ```typescript
   type MCPServerConnection =
     | ConnectedMCPServer    // 已连接，有 client + capabilities
     | FailedMCPServer       // 连接失败，有 error
     | NeedsAuthMCPServer    // 需要认证
     | PendingMCPServer      // 等待重连（有 reconnectAttempt）
     | DisabledMCPServer     // 被禁用
   ```

2. **连接超时与失败处理**：
   ```typescript
   // 连接超时：30s（可通过 MCP_TIMEOUT 环境变量配置）
   const connectPromise = client.connect(transport)
   const timeoutPromise = new Promise<never>((_, reject) => {
     const timeoutId = setTimeout(() => {
       transport.close().catch(() => {})
       reject(new Error(`MCP server "${name}" connection timed out`))
     }, getConnectionTimeoutMs())
   })
   await Promise.race([connectPromise, timeoutPromise])
   ```

3. **终端错误检测与自动重连触发**：
   ```typescript
   // 检测终端连接错误
   function isTerminalConnectionError(msg: string): boolean {
     return (
       msg.includes('ECONNRESET') ||
       msg.includes('ETIMEDOUT') ||
       msg.includes('EPIPE') ||
       msg.includes('EHOSTUNREACH') ||
       msg.includes('ECONNREFUSED') ||
       msg.includes('SSE stream disconnected')
     )
   }

   // 连续 3 次终端错误 → 触发重连
   let consecutiveConnectionErrors = 0
   const MAX_ERRORS_BEFORE_RECONNECT = 3
   ```

4. **会话过期检测**（HTTP 传输特有）：
   ```typescript
   // 检测 MCP session expired（HTTP 404 + JSON-RPC -32001）
   function isMcpSessionExpiredError(error: Error): boolean {
     const httpStatus = (error as Error & { code?: number }).code
     if (httpStatus !== 404) return false
     return error.message.includes('"code":-32001')
   }
   ```

5. **Need-Auth 缓存**（避免反复尝试）：
   - 15 分钟 TTL 文件缓存
   - 并发写入通过 promise chain 序列化

**可吸收点**: ACE 的 worker 连接管理可吸收五态状态机 + 终端错误检测 + 指数退避重连。

---

### 骨架3：多传输层抽象与统一客户端

**位置**: `services/mcp/client.ts`

**设计要点**:

1. **7 种传输类型**，统一 Client 接口：
   - `stdio` — 子进程标准输入输出（最常用）
   - `sse` — Server-Sent Events（远程服务器）
   - `sse-ide` — IDE 扩展 SSE（内部用）
   - `http` — Streamable HTTP（MCP 2025-03-26 规范）
   - `ws` — WebSocket
   - `ws-ide` — IDE WebSocket（内部用）
   - `sdk` — SDK 控制传输（VSCode 等宿主）
   - `claudeai-proxy` — Claude.ai 代理

2. **传输创建工厂**（根据 type 分发）：
   ```typescript
   // 核心连接函数，按 transport type 分发
   export const connectToServer = memoize(async (name, serverRef) => {
     let transport
     
     if (serverRef.type === 'sse') {
       transport = new SSEClientTransport(new URL(serverRef.url), {
         authProvider: new ClaudeAuthProvider(name, serverRef),
         fetch: wrapFetchWithTimeout(wrapFetchWithStepUpDetection(...)),
       })
     } else if (serverRef.type === 'http') {
       transport = new StreamableHTTPClientTransport(new URL(serverRef.url), {
         authProvider, fetch, requestInit
       })
     } else if (serverRef.type === 'ws') {
       transport = new WebSocketTransport(wsClient)
     } else if (serverRef.type === 'stdio' || !serverRef.type) {
       transport = new StdioClientTransport({ command, args, env, stderr: 'pipe' })
     }
     // ... 其他类型
     
     const client = new Client({ name: 'claude-code', ... }, { capabilities: { roots: {}, elicitation: {} } })
     await client.connect(transport)
   })
   ```

3. **进程内传输优化**（避免子进程开销）：
   ```typescript
   // Chrome MCP 和 Computer Use MCP 使用进程内传输
   const { createLinkedTransportPair } = await import('./InProcessTransport.js')
   const [clientTransport, serverTransport] = createLinkedTransportPair()
   await inProcessServer.connect(serverTransport)
   transport = clientTransport
   ```

4. **HTTP 请求超时包装**（每次请求新鲜 timeout）：
   ```typescript
   // 避免单个 AbortSignal 在连接时创建后过期
   function wrapFetchWithTimeout(baseFetch: FetchLike): FetchLike {
     return async (url, init) => {
       if (method === 'GET') return baseFetch(url, init)  // SSE 长连接跳过
       
       const controller = new AbortController()
       const timer = setTimeout(c => c.abort(...), MCP_REQUEST_TIMEOUT_MS, controller)
       // ... 组合父 signal
       try {
         return await baseFetch(url, { ...init, signal: controller.signal })
       } finally {
         clearTimeout(timer)
       }
     }
   }
   ```

**可吸收点**: ACE 的工具调用层可吸收多传输抽象 + 统一 Client 接口 + 进程内优化。

---

### 骨架4：OAuth 认证体系（含 XAA）

**位置**: `services/mcp/auth.ts` + `services/mcp/xaa.ts` + `services/mcp/xaaIdpLogin.ts`

**设计要点**:

1. **完整的 OAuth2 + PKCE 流程**：
   - RFC 9728（受保护资源发现）→ RFC 8414（授权服务器元数据发现）
   - 动态客户端注册（DCR）
   - Authorization Code + PKCE 授权
   - Token 刷新（带退避重试）
   - Token 撤销（RFC 7009，双方法 fallback）

2. **Step-Up Auth 检测**：
   ```typescript
   // 检测 403 insufficient_scope → 标记需要 step-up
   function wrapFetchWithStepUpDetection(baseFetch, provider) {
     return async (url, init) => {
       const response = await baseFetch(url, init)
       if (response.status === 403) {
         const wwwAuth = response.headers.get('WWW-Authenticate')
         if (wwwAuth?.includes('insufficient_scope')) {
           const scopeMatch = wwwAuth.match(/scope=(?:"([^"]+)"|([^\s,]+))/)
           if (scopeMatch) provider.markStepUpPending(scopeMatch[1])
         }
       }
       return response
     }
   }
   ```

3. **XAA（Cross-App Access）跨应用访问**：
   - 一次 IdP 登录 → 多个 MCP 服务器复用
   - RFC 8693（Token Exchange）+ RFC 7523（JWT Bearer）
   - IdP id_token 缓存（减少浏览器弹窗）

4. **凭据安全存储**：
   - Keychain / Secure Storage
   - 按 serverKey（name + config hash）隔离
   - 锁文件并发控制（MAX_LOCK_RETRIES = 5）

5. **非标准 OAuth 兼容**：
   ```typescript
   // Slack 等返回 HTTP 200 + error body，包装成标准 400
   async function normalizeOAuthErrorBody(response) {
     if (!response.ok) return response
     const parsed = jsonParse(await response.text())
     if (OAuthErrorResponseSchema.safeParse(parsed).success) {
       // 重写为 400 响应
       return new Response(jsonStringify(normalized), { status: 400 })
     }
   }
   ```

**可吸收点**: ACE 的外部服务认证层可吸收 OAuth 完整流程 + 多服务器凭据管理。

---

### 骨架5：权限控制体系

**位置**: `services/mcp/channelPermissions.ts` + `services/mcp/config.ts` + `tools/MCPTool/MCPTool.ts`

**设计要点**:

1. **三层权限模型**：
   ```
   第一层：企业策略（allowlist/denylist）
       ↓ 配置加载时过滤
   第二层：服务器启用状态（enabled/disabled）
       ↓ 连接时过滤
   第三层：工具调用权限（MCPTool.checkPermissions）
       ↓ 每次调用前检查
   ```

2. **项目级 MCP 服务器审批流**：
   ```typescript
   // .mcp.json 中的服务器需要用户审批
   function getProjectMcpServerStatus(serverName): 'approved' | 'rejected' | 'pending' {
     // 1. 检查是否在拒绝列表
     // 2. 检查是否在批准列表 / 启用全部
     // 3. 非交互模式自动批准（SDK / -p / pipe）
     // 4. 危险模式跳过审批
     // 5. 默认 pending
   }
   ```

3. **通道权限中继**（Channel Permission Relay）：
   ```typescript
   // 通过 Telegram/iMessage 等通道发送权限请求，用户回复 yes/no + ID
   // 短 ID 生成（5个字母，排除 l，避免脏话）
   function shortRequestId(toolUseID: string): string {
     // FNV-1a → base-25 编码 → 过滤脏话 → 最多 10 次重试
   }

   // 回复格式正则
   const PERMISSION_REPLY_RE = /^\s*(y|yes|n|no)\s+([a-km-z]{5})\s*$/i
   ```

4. **权限竞赛模型**：
   - 本地 UI / Bridge / Hooks / Classifier / 通道中继
   - 第一个 resolver 胜出（claim 模式）
   - 通道服务器需要声明两个 capability 才能参与

**可吸收点**: ACE 的权限系统可吸收三层模型 + 多通道中继 + 竞赛式审批。

---

## 三、与 ACE 现有架构的对照

| 维度 | Claude Code MCP | ACE Runtime | 差距 |
|------|----------------|-------------|------|
| **配置层级** | 7 种 scope，优先级覆盖，内容去重 | 单层 ace_config.json | 大 |
| **传输抽象** | 7 种传输类型，统一 Client 接口 | 无（只有 LLM API 调用） | 大 |
| **连接状态** | 5 态状态机 + 自动重连 + 会话过期检测 | 无（worker 是同步函数） | 大 |
| **认证体系** | OAuth2 + PKCE + XAA + DCR + 撤销 | 无（API Key 硬编码） | 极大 |
| **权限控制** | 三层模型 + 通道中继 + 竞赛式审批 | 无（全凭 worker 自觉） | 极大 |
| **错误处理** | 分类错误 + 重试 + 退避 + 会话重建 | 简单 try/catch | 中 |
| **工具发现** | 动态列表 + 规范化命名 + 描述截断 | 硬编码工具列表 | 中 |
| **资源模型** | Resources + Prompts + Tools 三位一体 | 只有工具概念 | 中 |
| **输出处理** | 截断 + 二进制存储 + 折叠分类 | 原始输出 | 小 |

### 架构映射建议

```
Claude Code MCP                    ACE Runtime
─────────────                    ─────────────
services/mcp/types.ts       →     core/mcp/types.py
services/mcp/config.ts      →     core/mcp/config.py  (新建)
services/mcp/client.ts      →     core/mcp/client.py  (新建)
tools/MCPTool/              →     core/base_worker.py (增强)
services/mcp/auth.ts        →     core/mcp/auth.py    (新建)
services/mcp/utils.ts       →     core/mcp/utils.py   (新建)
```

---

## 四、R2 公理验证

### R2-1：结构 > 模型 ✅ 验证通过

Claude Code 的 MCP 架构完美体现了"结构 > 模型"：
- 7 层传输抽象，底层换了上层无感
- 5 态状态机，与具体传输无关
- 配置 scope 优先级系统，与配置源无关
- 权限三层模型，与权限通道无关

**可吸收**: 骨架 1/2/3 都是纯结构资产，与具体 LLM 无关。

### R2-2：统一身份 ⚠️ 部分验证

- MCP 客户端身份是统一的（`name: 'claude-code'`）
- 但 MCP 服务器是多身份的，每个 server 独立
- 凭据按 serverKey 隔离，不会串

**对 ACE 的启示**: ACE 的统一身份是内部的，对外服务可以多身份，但要做好隔离。

### R2-3：笨者生存（文件系统优先）❌ 不适用

Claude Code 是一个桌面应用，使用：
- Keychain 存凭据
- 内存缓存连接
- 配置文件持久化

不是分布式系统，不适用"文件系统做总线"原则。

### R2-4：沉淀链 ✅ 间接验证

MCP 的配置 scope 层级本身就是一种沉淀链：
```
claude.ai → plugin → user → project → local → enterprise
    （从弱到强，从临时到稳定）
```

越上层越稳定、越权威，与 OBS→RFC→TASK→CONST 的沉淀逻辑一致。

### R2-5：连续性优先 ✅ 验证通过

多处体现连续性优先：
- 连接断开自动重连（指数退避）
- 会话过期自动重建
- 凭据缓存（减少用户交互中断）
- stderr 累积 64MB 才截断（宁可占内存，不丢诊断信息）
- Need-Auth 缓存 15 分钟（宁可少连，不可反复失败）

---

## 五、可吸收的骨架清单

### P0（核心骨架，必须吸收）

| 骨架 | 来源文件 | 吸收价值 | 预估工作量 |
|------|---------|---------|-----------|
| **多 Scope 配置系统** | config.ts + types.ts | 配置分层、去重、策略过滤 | 高 |
| **连接状态机** | client.ts + types.ts | 5 态连接管理 + 自动重连 | 高 |
| **多传输抽象** | client.ts | 统一接口适配多种传输 | 高 |

### P1（重要骨架，应该吸收）

| 骨架 | 来源文件 | 吸收价值 | 预估工作量 |
|------|---------|---------|-----------|
| **OAuth 认证体系** | auth.ts | 标准化外部服务认证 | 极高 |
| **权限三层模型** | channelPermissions.ts + config.ts | 安全保障 | 中 |
| **输出截断与存储** | mcpValidation.ts + mcpOutputStorage.ts | 防止输出爆炸 | 低 |
| **名称规范化** | normalization.ts + mcpStringUtils.ts | 统一命名空间 | 低 |

### P2（可选骨架，有价值但不急）

| 骨架 | 来源文件 | 吸收价值 | 预估工作量 |
|------|---------|---------|-----------|
| **XAA 跨应用访问** | xaa.ts + xaaIdpLogin.ts | 企业级 SSO | 极高 |
| **通道权限中继** | channelPermissions.ts | 多渠道审批 | 中 |
| **官方注册表** | officialRegistry.ts | 可信服务器列表 | 低 |
| **Elicitation 处理** | elicitationHandler.ts | 服务器主动请求用户输入 | 中 |

---

## 六、吸收路线建议

### 第一阶段：骨架搭建（配置 + 连接）

1. 移植 `types.ts` 中的核心类型定义
2. 移植 `config.ts` 的多 scope 配置系统（简化为 3-4 层）
3. 移植 `client.ts` 的连接状态机 + stdio 传输
4. 实现 MCPTool 的基础调用封装

### 第二阶段：能力增强（认证 + 多传输）

1. 移植 OAuth 认证基础（SSE + HTTP 传输）
2. 实现权限基础框架
3. 增加 WebSocket 传输支持

### 第三阶段：生产级（错误处理 + 监控）

1. 完善错误分类与重试策略
2. 增加连接健康监控
3. 实现输出截断与二进制存储

---

## 七、关键代码速查

### 配置优先级顺序
```typescript
// config.ts L1231-1238
const configs = Object.assign(
  {},
  dedupedPluginServers,    // 最低：插件
  userServers,             // 用户
  approvedProjectServers,  // 项目（.mcp.json）
  localServers,            // 本地设置
  // 最高：enterprise（企业模式下独占）
)
```

### 连接状态转换
```
pending → connecting → connected
                    ↘ failed → pending (retry)
                    ↘ needs-auth
                    
connected → error → (if terminal) → pending (reconnect)
                  ↘ (if session expired) → reconnect
```

### 权限检查顺序
```
1. 企业 denylist → 拒绝
2. 企业 allowlist → 检查
3. 服务器 disabled → 跳过
4. 项目审批状态 → approved/rejected/pending
5. 工具调用时 checkPermissions → passthrough/allow/deny
```

---

**报告完成时间**: 2026-06-30
**考古人**: ACE Archaeology Engine
**后续行动**: 按吸收路线图，先启动 P0 骨架移植
