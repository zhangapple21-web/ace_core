# Sekiro RPC 框架结构考古报告（v2 — 五步处理法）

**日期**: 2026-06-30
**来源**: https://github.com/skyhee/sekiro + https://sekiro.iinti.cn/sekiro-doc/
**领域**: RPC 注入 / 机群调度 / 二进制协议
**吸收状态**: 骨架已吸收（v0.3.0），真实环境待接入
**处理法**: ①识别 → ②映射 → ③改造 → ④落地 → ⑤划界

---

## ① 识别

### 这是什么

Sekiro 是一个**私有 API 导出框架**，核心能力是把 Android APP 内部的 Java 方法通过 RPC 的方式暴露出来，供外部调用。

**三层协议架构**：
```
调用方(Python) --HTTP/REST--> Sekiro Server --二进制长连接--> Android Client
```

**典型应用场景**：
- APP 加解密算法逆向（调用真实的加密/解密函数）
- 批量数据采集（通过真实 APP 发起请求，绕过风控）
- 协议逆向分析（直接调用协议组包/解包函数）

**信号强度**: high（生产验证的 RPC 注入方案，有官方文档、商业版、活跃社区）

---

## ② 映射

### 逐层映射到 ACE 体系

| Sekiro 组件 | ACE 体系对应 | 映射结果 |
|---|---|---|
| HTTP REST API（/business/invoke） | `ProtocolToolProvider.protocol_unpack` 工具接口 | **已覆盖**。ACE 的解包图层已有统一工具接口，Sekiro HTTP Client 是其中一种实现 |
| 二进制协议（SekiroPacket） | `core/protocols/handlers/rpc_handler.py` 的 `SekiroPacket` | **已吸收**。编解码骨架已完整实现 |
| 机群调度（OneByOne/bindClient/一致性哈希） | `ProtocolRegistry` + `FallbackChain` + `MinerPool` | **可吸收**。调度策略概念可 enrich MinerPool 的负载均衡逻辑 |
| 鉴权机制（sekiro_token） | `Capability Registry v2` 的 Provider 鉴权 | **已覆盖**。Capability→Service→Provider 三级结构已包含鉴权抽象 |
| 分组管理（group/clientQueue） | `ProtocolVersionManager` + 协议版本追踪 | **可吸收**。group 概念可 enrich 协议版本管理，支持"按 group 追踪版本" |
| 心跳/注册包（HEARTBEAT/REGISTER） | `ProtocolLRUCache` + `UnidbgPool` 的健康检查 | **可吸收**。心跳机制可作为 Pool 健康检查的参考模式 |

### 根概念映射

| Sekiro 根概念 | ACE 体系对应 | 映射结果 |
|---|---|---|
| 调用方-服务端-执行端三层架构 | 解包图层的 Level 0/1/2 降级链 | **已覆盖**。RPCHandler(Level0)→UnidbgHandler(Level1)→StaticAnalyzer(Level2) |
| 真实环境执行 | RPCHandler 的"最优解"定位 | **已覆盖**。Sekiro 被定义为 Level 0，优先于模拟执行 |
| 机群弹性调度 | MinerPool 的算力调度 | **可吸收**。一致性哈希策略可引入到 MinerPool 的设备路由 |
| 会话绑定（bindClient） | `StabilityLayer` 的 input_hash→decision 映射 | **可吸收**。session 绑定概念可增强决策稳定性 |

---

## ③ 改造

### 可改造吸收的 3 个洞见

**洞见 1：一致性哈希调度（来自 consistent_key）**

核心思想：相同 key 的请求始终路由到同一设备，减少风控对抗中的设备跳跃问题。

改造方向：`MinerPool` 的负载均衡策略增强——在现有轮询/优先级调度基础上，增加"一致性哈希"选项，用于需要 session 保持的 RPC 调用场景。

**洞见 2：分组级版本追踪（来自 group 概念）**

核心思想：不同业务分组可以独立管理设备池和调用策略。

改造方向：`ProtocolVersionManager` 增强——当前按 protocol 追踪版本，可扩展为"protocol + group"二维追踪，支持同一协议在不同 group 中的差异化版本管理。

**洞见 3：心跳驱动的健康检查（来自 HEARTBEAT/REGISTER）**

核心思想：客户端主动注册 + 定期心跳，服务端据此判断设备可用性。

改造方向：`UnidbgPool` 的健康检查增强——当前基于 error_count 和 idle_timeout 判断，可加入"心跳信号"概念，模拟长连接的健康状态检查。

---

## ④ 落地

### 横切一致性检查（相关模块横向扫描）

做 Sekiro 接入时，同步扫描了协议层所有相关模块，评估一起改的收益和成本：

| 相关模块 | 同类问题 | 一起改？ | 理由 |
|---------|---------|---------|------|
| `UnidbgHandler` (v0.1.0) | 没有 `get_status()` 状态查询接口，RPCHandler 有 `get_sekiro_status()` | **记录待办** | 统一接口有价值，但 UnidbgPool 已经有统计数据，优先级低 |
| `StaticAnalyzerHandler` (v0.1.0) | 返回格式和 RPCHandler 不一致——RPC 返回 `original_size`，静态分析返回 `size` | **评估后不动** | 基础字段（`decrypted`/`method`/`fields`）已对齐，特有字段（RPC 的 `group`/`action`、静态分析的 `decoding_attempts`）保留各自特色，强行统一反而丢失信息 |
| `UnidbgPool` | 健康检查基于 error_count + idle_timeout，没有"心跳"概念 | **不动** | Unidbg 是进程内调用，不需要心跳机制，强行加会过度设计 |
| `ProtocolLRUCache` | 缓存按 handler 维度 key，没有 group 概念 | **不动** | 缓存 key 已经足够细粒度，加 group 会增加复杂度，收益不明 |
| `ProtocolVersionManager` | 只有 protocol 一维追踪，没有 group 维度 | **记录待办** | group 追踪在多业务线场景有用，但当前 ACE 是单业务线，暂时不需要 |
| `FallbackChain` | 降级只按 priority 排序，没有"一致性哈希/session 绑定"概念 | **不动** | FallbackChain 是能力降级（最优→次优→兜底），不是负载均衡，概念不同 |
| `raw_fallback.py` | 最简单的兜底 handler，直接返回原始数据 | **不动** | 它就是兜底，越简单越好 |

### 已落地（骨架实现）

文件：[core/protocols/handlers/rpc_handler.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/protocols/handlers/rpc_handler.py)

- ✅ `SekiroPacket` 类 — 二进制协议编解码（v0.3.0）
- ✅ `SekiroHTTPClient` 类 — HTTP API 客户端骨架
- ✅ 三种调度策略常量（SEKIRO_STRATEGY_*）
- ✅ `RPCHandler` 集成 HTTP 调用链路
- ✅ `get_sekiro_status()` 状态查询
- ✅ sekiro_token 鉴权支持

### 本次一起改的（横向收益）

- 无。本次扫描发现 7 个相关模块，0 个需要立即一起改。
- 结论：当前协议层各模块的设计差异是合理的（职责不同），不是"同样的问题重复犯"。

### 记录待办的（暂不阻塞）

- `UnidbgHandler` 增加 `get_status()` 接口，和 RPCHandler 对齐
- `ProtocolVersionManager` 增加 group 维度追踪（多业务线场景再做）

### 明确不动的（避免过度设计）

- 不给 UnidbgPool 加心跳机制（进程内调用不需要）
- 不给 ProtocolLRUCache 加 group 维度（当前 key 足够）
- 不给 FallbackChain 加负载均衡策略（概念不同，Fallback 是能力降级不是负载均衡）

### 待落地（真实环境接入）

前置条件：
1. Linux 服务器（或 Docker 环境）
2. Android 设备/模拟器（ROOT 或 XPosed 框架）
3. 目标 APP（需要逆向的应用）

接入步骤：
1. 部署 Sekiro 服务端（Docker 一键启动）
2. 在 Android 设备上安装 Sekiro 客户端 + 目标 APP
3. 编写 Sekiro handler，注册目标解密方法
4. 替换 `SekiroHTTPClient._simulate_invoke()` 为真实 HTTP 调用
5. 端到端测试，验证调用链路
6. 接入 `ace_daemon.py` 主循环

### 增量写入点

- `MinerPool`：增加一致性哈希调度策略（可选增强）
- `ProtocolVersionManager`：增加 group 维度追踪（可选增强）
- `UnidbgPool`：增加心跳健康检查模式（可选增强）

---

## ⑤ 划界

### 明确拒绝的部分

| Sekiro 概念 | 拒绝理由 | ACE 的替代 |
|---|---|---|
| 具体 Android 客户端实现（XPosed/Frida 插件） | 这是执行层细节，不属于 ACE 的治理/协议层 | 由外部 Sekiro 社区维护，ACE 只调用 HTTP API |
| Docker 部署配置 / docker-compose.yml | 运维层，不属于 ACE 结构资产 | Infrastructure 层的 Health Check 接口 |
| 商业版授权机制细节 | 实现细节，不属于治理层 | 抽象为 `sekiro_token` 参数，具体鉴权由服务端处理 |
| 具体 Java handler 编写指南 | 这是逆向工程执行技能，不是结构资产 | 09_KNOWLEDGE/ 可记录经验，但不纳入协议层 |
| 前端 Web UI（conf/static/*） | 与 ACE 无关 | 不涉及 |

### 不可协商的边界

- 不把 Sekiro 的 Android 客户端实现纳入 ACE 代码库
- 不引入 Sekiro 的生物学隐喻（它本身没有，但其他项目可能有）
- 不照搬 Sekiro 的文件组织结构到 ACE 的 protocols/ 目录
- 不改变 `ProtocolHandler` 统一接口来适应 Sekiro 的特殊参数
- 不把商业版授权逻辑硬编码到 ACE（保持参数化）

---

## 判断依据

**为什么吸收 Sekiro**：

1. **架构成熟**：服务端+客户端+机群调度的完整方案，不是零散脚本
2. **协议清晰**：二进制协议 + HTTP API 两层都有文档，可逆向可扩展
3. **社区活跃**：官方文档、demo、商业版，说明经过生产验证
4. **与 ACE 方向高度契合**：逆向工程 → 协议分析 → 解包执行，正好是 ACE 狩猎核心领域
5. **骨架价值高**：即使不用 Sekiro 本身，"调用方-服务端-执行端"三层架构、机群调度、多策略路由，都是可复用的结构资产

---

## 认知熵检查

```yaml
entropy_check:
  new_active_concepts: 0       # SekiroPacket、SekiroHTTPClient 都是已有概念的新实现
  existing_concepts_enhanced: 3  # MinerPool(调度策略)、ProtocolVersionManager(group追踪)、UnidbgPool(心跳检查)
  concept_density_delta: "+0.00"  # 无新概念膨胀
  new_files_created: 0         # 全部写入已有 rpc_handler.py
  judgment: "越学越稳，没有膨胀。Sekiro 的骨架被完整映射到现有体系，无架构侵入。"
```

---

## 相关文件

- 实现代码：[rpc_handler.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/protocols/handlers/rpc_handler.py)
- 协议基类：[base.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/protocols/base.py)
- 解包图层报告：[2026-06-30_unpack_layer_integration.md](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/08_ARCHAEOLOGY/2026-06-30_unpack_layer_integration.md)
- 三系统对比报告：[2026-06-30_three_systems_comparison.md](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/08_ARCHAEOLOGY/2026-06-30_three_systems_comparison.md)
