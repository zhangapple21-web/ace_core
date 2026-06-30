# 解包图层工程化落地接入报告

**派单编号**: AUM-TASK-2026-06-30-007  
**任务名称**: 解包图层工程化落地（Unidbg/RPC 骨架接入主循环）  
**报告日期**: 2026-06-30  
**执行状态**: 已完成  

---

## 一、新增文件清单

### 核心模块（结构资产）

| 文件 | 说明 | 行数 | 优先级 |
|------|------|------|--------|
| `core/protocols/base.py` | ProtocolHandler 抽象基类 + UnpackResult 数据结构 | ~97 | P0 |
| `core/protocols/cache.py` | ProtocolLRUCache — LRU 缓存（默认 1000 条） | ~100 | P0 |
| `core/protocols/version.py` | ProtocolVersionManager — 协议版本管理 + 变更触发 | ~150 | P1 |
| `core/protocols/registry.py` | ProtocolRegistry + FallbackChain — 注册表 + 降级链 | ~218 | P0 |
| `core/protocols/unidbg_pool.py` | UnidbgPool — Unidbg 实例复用池（默认池大小 3） | ~280 | P0 |
| `core/protocols/async_logger.py` | AsyncAuditLogger — 异步审计日志（队列 10000 条） | ~280 | P1 |
| `core/protocols/tool_provider.py` | ProtocolToolProvider — 工具接口层（接入主循环） | ~350 | P0 |

### 处理器集合（执行层骨架）

| 文件 | 说明 | 降级层级 | 优先级 |
|------|------|----------|--------|
| `core/protocols/handlers/rpc_handler.py` | RPCHandler — RPC 注入模式（Sekiro/Frida） | Level 0（最优） | P0 |
| `core/protocols/handlers/unidbg_handler.py` | UnidbgHandler — Unidbg 模拟执行 | Level 1 | P0 |
| `core/protocols/handlers/static_analyzer.py` | StaticAnalyzerHandler — 静态分析/字段提取 | Level 2 | P0 |
| `core/protocols/handlers/raw_fallback.py` | RawFallbackHandler — 兜底（原始数据） | Level 99（最后防线） | P0 |
| `core/protocols/handlers/__init__.py` | 处理器集合导出 | - | - |

### 测试文件

| 文件 | 说明 |
|------|------|
| `test_protocols_e2e.py` | 端到端验证测试脚本 |

**总计**: 11 个文件，约 1600 行代码

---

## 二、接口设计说明

### 2.1 核心设计哲学

```
结构 → 协议 → 记忆 → 路由 → 模型
```

本层属于 **协议层**，是结构资产的一部分。  
真实的解包引擎（Unidbg、RPC、静态分析）只是可替换的执行节点。

### 2.2 ProtocolHandler 统一接口

```python
class ProtocolHandler(ABC):
    name: str           # 处理器名称
    protocol: str       # 处理的协议名
    version: str        # 版本号
    priority: int       # 优先级（数值越小越先尝试）

    @abstractmethod
    def identify(self, data: bytes) -> bool:
        """判断能不能处理"""

    @abstractmethod
    def unpack(self, data: bytes) -> UnpackResult:
        """解包数据，返回结构化结果"""
```

关键特性：
- **自识别**：每个 handler 自己判断能不能处理
- **自降级**：失败时返回 fallback_level，不抛异常
- **元信息**：自带 name/protocol/version/priority，便于注册表管理

### 2.3 降级策略（FallbackChain）

```
Level 0: RPC 注入（Sekiro / Frida）  ← 最优解，真实环境
    ↓ 失败
Level 1: Unidbg 模拟执行            ← 次优，PC 模拟
    ↓ 失败
Level 2: 静态分析（字段提取）        ← 保底，不执行代码
    ↓ 失败
Level 3: 兜底（原始数据 + 标记）      ← 最后防线，永不失败
```

实现方式：
- 每个 handler 声明自己的 `priority`（数值越小优先级越高）
- `FallbackChain` 按优先级排序，从上到下尝试
- 第一个成功的结果直接返回
- 全部失败则返回兜底结果（RawFallbackHandler 永远成功）

### 2.4 LRU 缓存设计

```python
class ProtocolLRUCache:
    max_size: int = 1000    # 缓存大小上限
    _cache: OrderedDict     # 有序字典，LRU 淘汰
    
    def get(data, handler_name) -> Optional[UnpackResult]
    def put(data, handler_name, result) -> None
```

- 键：`sha256(data) + handler_name`
- 淘汰策略：最久未使用（LRU）
- 成功和失败结果都缓存（失败的也不重复尝试）

### 2.5 UnidbgPool 复用池

```python
class UnidbgPool:
    pool_size: int = 3              # 默认池大小
    idle_timeout: int = 300         # 空闲超时（秒）
    max_errors_per_instance: int = 5  # 单实例最大错误数
    
    def acquire(so_path) -> UnidbgInstance
    def release(instance, success)
    def call_function(so_path, func_name, args) -> Dict
```

- 按 `so_path` 分组管理实例
- LRU 淘汰最久未使用的实例
- 错误超过阈值自动销毁重建
- 线程安全（带锁）

### 2.6 异步日志（AsyncAuditLogger）

```python
class AsyncAuditLogger:
    max_queue_size: int = 10000     # 队列上限
    flush_interval: float = 1.0     # 刷新间隔（秒）
    batch_size: int = 100           # 批量写入大小
    
    def log(event_type, data, level) -> bool
    def log_unpack(data_hash, result)
    def get_stats() -> Dict
```

- 队列 + 后台线程，不阻塞主循环
- 队列满时丢弃并告警（每丢弃 100 条告警一次）
- 按天切割日志文件（JSONL 格式）
- 内存保留最近 1000 条供查询

### 2.7 工具接口层（ProtocolToolProvider）

参考 ReVa / binary_sense 的 ToolProvider 模式，提供 6 个标准工具：

| 工具名 | 功能 |
|--------|------|
| `protocol_unpack` | 解包数据（自动降级） |
| `protocol_identify` | 识别协议类型 |
| `protocol_list_handlers` | 列出所有处理器 |
| `protocol_stats` | 获取协议层统计 |
| `protocol_unidbg_stats` | 获取 Unidbg 池统计 |
| `protocol_log_recent` | 获取最近审计日志 |

主循环通过调用这些工具使用协议层能力，不需要直接依赖内部实现。

---

## 三、性能测试结果

### 3.1 测试环境

- **运行方式**: 本地 Python 脚本
- **测试脚本**: `test_protocols_e2e.py`
- **数据量**: 端到端 4 项测试 + 100 条日志压测

### 3.2 测试结果

#### 测试 1：端到端完整链路

| 指标 | 结果 |
|------|------|
| 第一次解包 | 成功，static_analyzer 处理 |
| 第二次解包（相同数据） | 缓存命中 ✓ |
| 协议识别 | 成功，识别为 generic_encrypted |
| 已注册处理器 | 4 个（rpc/unidbg/static/raw） |

#### 测试 2：降级策略验证

使用 PNG 魔数二进制数据测试：

| 指标 | 结果 |
|------|------|
| 最终处理 Handler | static_analyzer（Level 2） |
| 魔术字识别 | 89504e47 → png ✓ |
| 字节分布统计 | unique_bytes=7, unique_ratio=0.027 |
| 成功率 | 100% |

说明：RPC 和 Unidbg 未配置（骨架模式），自动降级到静态分析，符合预期。

#### 测试 3：异步日志性能

| 指标 | 结果 |
|------|------|
| 写入 100 条日志耗时 | 0.0010 秒 |
| 平均每条耗时 | 0.0100 毫秒 |
| 队列积压 | 0（全部已刷新） |
| 丢弃数 | 0 |
| 日志刷新数 | 100 |

**结论**：异步日志写入几乎不阻塞主循环，性能满足要求。

#### 测试 4：Unidbg 池复用

调用同一个 .so 5 次：

| 指标 | 结果 |
|------|------|
| 总创建实例数 | 1 |
| 复用次数 | 4 |
| 命中率 | 80% |
| 实例 ID | unidbg-0001（全部复用） |

**结论**：池复用机制工作正常，避免了重复加载。

### 3.3 综合评估

| 维度 | 评估 | 说明 |
|------|------|------|
| 功能完整性 | ✓ 完整 | 全部 10 项任务均完成 |
| 降级策略 | ✓ 生效 | 4 级降级链完整 |
| 缓存机制 | ✓ 工作 | LRU + 命中验证通过 |
| 异步日志 | ✓ 不阻塞 | 100 条 0.001 秒 |
| 实例复用 | ✓ 生效 | 池命中率 80% |
| 工具接口 | ✓ 完整 | 6 个标准工具 |
| 代码质量 | ✓ 良好 | 统一风格，类型注解完整 |

---

## 四、已知限制和后续优化方向

### 4.1 当前限制（骨架阶段）

1. **RPC 注入未真实接入**：RPCHandler 是骨架，需要真实 Sekiro/Frida 端点
2. **Unidbg 未真实接入**：UnidbgPool 是模拟层，需要替换为真实 Unidbg 调用
3. **协议识别简单**：目前只做基础判断，真实协议需要特征库
4. **静态分析能力有限**：目前只做格式识别和基础解码，未做协议级解析

### 4.2 后续优化方向

#### Phase 2（真实解包能力接入）

- [ ] 接入真实 Sekiro RPC 框架（Android 端）
- [ ] 接入真实 Unidbg（Java 或 Python 绑定）
- [ ] 建立协议特征库（魔术字、长度模式、加密特征等）
- [ ] 增加具体协议 Handler（如 MTProto、HTTP2、自定义协议等）

#### Phase 3（智能化升级）

- [ ] 协议自动聚类（未知协议自动发现和分类）
- [ ] 解包成功率反馈学习（动态调整降级顺序）
- [ ] 多协议并行解包（同时尝试多个，取最快结果）
- [ ] 协议演化追踪（版本变更时自动差异分析）

#### Phase 4（规模化）

- [ ] 分布式 Unidbg 池（多机共享实例）
- [ ] 解包任务队列（批量解包，异步回调）
- [ ] 解包结果质量评估（置信度评分）
- [ ] 协议逆向辅助（从流量中反推协议结构）

### 4.3 架构建议

```
当前阶段（骨架）：  结构完整，执行层模拟
Phase 2：          结构不变，替换执行节点
Phase 3：          结构扩展，增加智能层
Phase 4：          结构不变，扩展规模
```

**核心原则**：结构资产（接口、降级、缓存、池化、版本）保持稳定，  
执行节点（RPC、Unidbg、具体协议）可以随时替换和升级。

---

## 五、额外补充（任务 10：自行发现的缺口）

在实现过程中发现并补充了以下内容：

### 5.1 工具接口层（ProtocolToolProvider）

原任务只提到 "接入 MinerPool"，但 MinerPool 是模型调度系统，  
解包能力属于工具/能力层，不适合作为 MinerPool 的 Provider。

**补充方案**：参考 binary_sense 的 ToolProvider 模式，  
创建 `ProtocolToolProvider` 作为协议层对外的统一工具接口。  
主循环 / Agent 通过调用工具的方式使用协议层能力，  
与现有的工具生态（binary_sense 等）保持一致。

### 5.2 UnpackResult 数据类

原任务只提到 "输入密文，输出结构化明文"，  
但缺少统一的结果结构定义。

**补充方案**：增加 `UnpackResult` dataclass，包含：
- `success` / `data` / `error`（基础）
- `protocol` / `handler` / `fallback_level`（溯源）
- `cached` / `timestamp` / `raw_size`（元信息）

确保所有 handler 返回格式一致，便于上层处理。

### 5.3 静态分析的丰富能力

原任务只提到 "静态分析（仅做字段提取）"，  
实际补充了以下能力：
- 魔术字识别（20+ 种已知格式）
- Base64 / Hex 解码尝试
- UTF-8 文本检测
- JSON 解析尝试
- gzip 解压尝试
- 字节分布/熵值估算

这些都是零成本但非常实用的静态分析能力。

### 5.4 版本管理的触发机制

原任务提到 "版本变更时自动触发重新狩猎"，  
但未定义触发条件。

**补充方案**：`ProtocolVersionManager.register()` 返回 `needs_rehunt` 标记，  
调用方可以根据这个标记决定是否触发重新狩猎。  
同时记录完整的版本变更历史（history），便于追溯。

---

## 六、架构总览

```
┌─────────────────────────────────────────────────┐
│              ProtocolToolProvider               │  ← 工具接口层（接入主循环）
│  (6 tools: unpack/identify/list/stats/...)      │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│               ProtocolRegistry                  │  ← 注册表 + 统计
│  (handler 管理 / 协议路由 / 全局降级链)          │
└──────────┬───────────────────┬──────────────────┘
           │                   │
┌──────────▼──────┐  ┌─────────▼────────┐  ┌──────────────┐
│  FallbackChain  │  │ ProtocolLRUCache │  │ VersionMgr   │  ← 降级 + 缓存 + 版本
│  (4 级降级链)    │  │  (1000 条 LRU)   │  │              │
└──────────┬──────┘  └──────────────────┘  └──────────────┘
           │
     ┌─────┴──────────────────────┐
     │                            │
┌────▼─────┐  ┌──────────┐  ┌────▼──────┐  ┌──────────────┐
│   RPC    │  │ Unidbg   │  │  Static   │  │  Raw Fallback │
│  Inject  │  │  Pool    │  │  Analyzer │  │  (兜底)      │
└──────────┘  └──────────┘  └───────────┘  └──────────────┘
  Level 0       Level 1        Level 2        Level 99
```

---

## 七、验证结论

**全部测试通过，架构完整，可以接入主循环。**

结构资产已沉淀：
- ✅ ProtocolHandler 统一接口（可扩展任意协议）
- ✅ FallbackChain 降级策略（4 级完整链路）
- ✅ LRU 缓存（性能基础）
- ✅ UnidbgPool 复用池（避免重复加载）
- ✅ AsyncAuditLogger 异步日志（不阻塞主循环）
- ✅ ProtocolVersionManager 版本管理（演化追踪）
- ✅ ProtocolToolProvider 工具接口（接入主循环）

执行层为骨架（可替换节点）：
- RPCHandler：待真实 RPC 接入
- UnidbgHandler：待真实 Unidbg 接入
- StaticAnalyzer：已有基础能力，可扩展
- RawFallback：完整可用，永不失败

---

**报告生成时间**: 2026-06-30  
**报告生成者**: ACE 自动考古系统  
**下一个动作**: 等待主循环调度，按需接入真实解包能力
