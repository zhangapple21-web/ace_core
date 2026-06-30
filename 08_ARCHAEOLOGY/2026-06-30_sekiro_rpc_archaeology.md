# Sekiro RPC 框架结构考古报告

**日期**: 2026-06-30
**来源**: https://github.com/skyhee/sekiro + https://sekiro.iinti.cn/sekiro-doc/
**领域**: RPC 注入 / 机群调度 / 二进制协议
**吸收状态**: 骨架已吸收（v0.3.0），真实环境待接入

---

## 一、Sekiro 是什么

Sekiro 是一个**私有 API 导出框架**，核心能力是把 Android APP 内部的 Java 方法通过 RPC 的方式暴露出来，供外部调用。

典型应用场景：
- APP 加解密算法逆向（调用真实的加密/解密函数）
- 批量数据采集（通过真实 APP 发起请求，绕过风控）
- 协议逆向分析（直接调用协议组包/解包函数）

---

## 二、整体架构

Sekiro 采用经典的**服务端-客户端**长连接架构：

```
┌─────────────┐    HTTP/REST     ┌─────────────────┐   二进制长连接    ┌─────────────────┐
│  调用方(Python) │ ───────────────▶ │  Sekiro Server  │ ───────────────▶ │  Android Client  │
│  (我们的代码)    │ ◀─────────────── │  (机群调度)      │ ◀─────────────── │  (真实APP环境)    │
└─────────────┘                 └─────────────────┘                 └─────────────────┘
```

**三层协议**：
1. **调用方 → 服务端**：HTTP REST API（JSON）
2. **服务端 → 客户端**：自定义二进制协议（长连接）
3. **客户端内部**：Java 反射调用（实际执行目标方法）

---

## 三、骨架提取

### 3.1 HTTP REST API 层（调用方视角）

**三个核心接口**：

| 接口 | 方法 | 作用 |
|------|------|------|
| `/business/invoke` | GET/POST | 调用转发（核心） |
| `/business/groupList` | GET | 查看分组列表 |
| `/business/clientQueue` | GET | 查看指定分组的设备队列 |

**调用参数**：
- `group`：业务分组（必选）
- `action`：动作名，对应客户端注册的 handler（必选）
- `sekiro_token`：鉴权 token（商业版需要）
- `bind_client`：指定设备 ID（调度策略用）
- `consistent_key`：一致性哈希 key（调度策略用）
- 其他自定义参数：透传给客户端 handler

**调用方式**：
- GET：直接拼 URL 参数，方便调试
- POST JSON：正式调用，支持复杂参数、子 JSON
- POST form-urlencoded：表单形式

### 3.2 二进制协议层（服务端↔客户端）

**包格式（大端编码）**：

```
┌─────────────────┬──────────────┬──────────────────┬────────────┬───────┬─────────┐
│  packet_length  │ message_type │  serial_number   │ ext_length │  ext  │ payload │
│   (int32)       │   (int8)     │    (int64)       │  (int8)    │(bytes)│ (bytes) │
└─────────────────┴──────────────┴──────────────────┴────────────┴───────┴─────────┘
```

- `packet_length`：数据包总长度（不含自身）
- `message_type`：消息类型
  - `0x01` = 注册（REGISTER）
  - `0x02` = 调用（INVOKE）
  - `0x07` = 心跳（HEARTBEAT）
- `serial_number`：序列号，请求响应配对用
- `ext`：扩展数据，UTF-8 字符串
  - 注册时：`clientId@group`
  - 调用时：content-type，如 `application/json; charset=utf-8`
- `payload`：业务数据

### 3.3 调度策略

Sekiro 服务端支持三种设备调度策略：

| 策略 | 参数 | 说明 | 适用场景 |
|------|------|------|---------|
| OneByOne（轮询） | 默认 | 平均分配，一个接一个 | 无状态任务、负载均衡 |
| bindClient（指定设备） | `bind_client` | 调用方指定特定设备 | session 绑定、特定设备调试 |
| 一致性哈希 | `consistent_key` | 相同 key 始终路由到同一设备 | 风控对抗、缓存命中 |

### 3.4 鉴权机制

三种场景：

| 版本/模式 | 是否需要鉴权 | 说明 |
|-----------|------------|------|
| Demo 版 | 否 | 开源 demo，无授权检查 |
| 商业版 + 匿名 group | 否（低 QPS） | 未在后台创建的 group，匿名访问，有 QPS 限制 |
| 商业版 + 正式 group | 是 | 必须传 `sekiro_token` |

---

## 四、ACE 吸收情况

### 4.1 已吸收到 RPCHandler v0.3.0

文件：`core/protocols/handlers/rpc_handler.py`

**已实现的骨架**：
- ✅ `SekiroPacket` 类 — 二进制协议编解码
- ✅ `SekiroHTTPClient` 类 — HTTP API 客户端骨架
- ✅ 三种调度策略常量
- ✅ `RPCHandler` 集成 HTTP 调用链路
- ✅ `get_sekiro_status()` 状态查询
- ✅ sekiro_token 鉴权支持

**当前状态**：骨架完整，模拟返回。等有真实 Sekiro 服务端环境，替换 `SekiroHTTPClient._simulate_invoke()` 为真实 HTTP 调用即可。

### 4.2 吸收评估

| 维度 | 评级 | 说明 |
|------|------|------|
| 结构完整性 | ⭐⭐⭐⭐ | 两层协议骨架都有了，缺真实调用实现 |
| 可复用性 | ⭐⭐⭐⭐⭐ | RPC 注入是逆向工程的核心能力，通用 |
| 接入难度 | ⭐⭐ | 需要 Android 环境 + Sekiro 服务端 + 目标 APP |
| 战略价值 | ⭐⭐⭐⭐⭐ | 直接解锁"真实环境执行"能力，从静态分析跃升到动态执行 |

---

## 五、与 ACE 现有体系的关系

### 5.1 在解包图层中的位置

```
Level 0: RPCHandler (Sekiro) — 真实环境执行，结果最准确
Level 1: UnidbgHandler     — 模拟执行，次之
Level 2: StaticAnalyzer    — 静态分析，兜底
```

Sekiro 是最优解（Level 0），因为它调用的是**真实的 APP 代码**，不存在模拟偏差。

### 5.2 与 Protocol 体系的对接

- 符合 `ProtocolHandler` 统一接口
- 通过 `ProtocolRegistry` 注册
- 通过 `FallbackChain` 降级
- 通过 `ProtocolLRUCache` 缓存
- 通过 `ProtocolVersionManager` 管理版本

---

## 六、后续接入计划

### 前置条件
1. Linux 服务器（或 Docker 环境）
2. Android 设备/模拟器（ROOT 或 XPosed 框架）
3. 目标 APP（需要逆向的应用）

### 接入步骤
1. 部署 Sekiro 服务端（Docker 一键启动）
2. 在 Android 设备上安装 Sekiro 客户端 + 目标 APP
3. 编写 Sekiro handler，注册目标解密方法
4. 替换 `SekiroHTTPClient._simulate_invoke()` 为真实 HTTP 调用
5. 端到端测试，验证调用链路
6. 接入 `ace_daemon.py` 主循环

### 风险点
- Android 环境搭建成本较高
- 不同 APP 的 handler 需要单独编写
- 风控对抗可能导致设备被封禁
- 商业版需要授权（demo 版功能有限）

---

## 七、判断依据

**为什么吸收 Sekiro 而不是其他 RPC 框架**：

1. **架构成熟**：服务端+客户端+机群调度的完整方案，不是零散的脚本
2. **协议清晰**：二进制协议 + HTTP API 两层都有文档，可逆向可扩展
3. **社区活跃**：有官方文档、有 demo、有商业版本，说明经过生产验证
4. **与 ACE 方向高度契合**：逆向工程 → 协议分析 → 解包执行，正好是 ACE 狩猎的核心领域
5. **骨架价值高**：即使不用 Sekiro 本身，它的"调用方-服务端-执行端"三层架构、机群调度、多策略路由，都是可以复用的结构资产

---

## 八、相关文件

- 实现代码：[rpc_handler.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/protocols/handlers/rpc_handler.py)
- 协议基类：[base.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/protocols/base.py)
- 解包图层报告：[2026-06-30_unpack_layer_integration.md](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/08_ARCHAEOLOGY/2026-06-30_unpack_layer_integration.md)
