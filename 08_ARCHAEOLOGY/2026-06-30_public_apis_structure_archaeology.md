# Public APIs 三层结构考古报告 — 2026-06-30

**AUM-TASK-2026-06-30-001**
**来源**：https://github.com/public-apis/public-apis
**考古日期**：2026-06-30

---

## 核心发现

public-apis 能活 8 年、收录 1400+ API 的原因**不是 API 数量**，而是它的**三层结构骨架**。

这才是真正值得 ACE 吸收的。

---

## 一、分类体系骨架

### 1.1 分类设计原则

```
原则1：按领域分，不是按技术分
    ❌ 按协议分：REST API / GraphQL / gRPC
    ✅ 按领域分：Animals / Finance / Health / Games

原则2：按用途分，不是按来源分
    ❌ 按公司分：Google API / Microsoft API / Amazon API
    ✅ 按用途分：Geocoding / Translation / Authentication

原则3：每个分类都是"用户意图"的表达
    ❌ Animals 是动物数据
    ✅ Animals 是"我想用动物相关 API"这个意图
```

### 1.2 51 个分类清单

```
Animals              # 动物
Anime                # 动漫
Anti-Malware         # 反恶意软件
Art & Design         # 艺术设计
Authentication       # 身份认证
Blockchain           # 区块链
Books                # 图书
Business             # 商业
Calendar             # 日历
Cloud Storage        # 云存储
Continuous Integration # CI/CD
Cryptocurrency       # 加密货币
Currency Exchange    # 汇率
Data Validation      # 数据验证
Development          # 开发工具
Dictionaries         # 词典
Documents            # 文档
Email                # 邮件
Entertainment        # 娱乐
Environment          # 环境
Events               # 事件
Finance              # 金融
Food & Drink         # 饮食
Games & Comics       # 游戏动漫
Geocoding            # 地理编码
Government           # 政府
Health               # 健康
Jobs                 # 招聘
Machine Learning     # 机器学习
Music                # 音乐
News                 # 新闻
Open Data            # 开放数据
Open Source          # 开源
Patent               # 专利
Personality          # 人格测试
Phone                # 电话
Photography          # 摄影
Programming          # 编程
Science & Math       # 科学数学
Security             # 安全
Shopping             # 购物
Social               # 社交
Sports & Fitness     # 运动健身
Test Data            # 测试数据
Text Analysis        # 文本分析
Tracking             # 追踪
Transportation       # 交通
URL Shorteners       # 短链接
Vehicle              # 车辆
Video                # 视频
Weather              # 天气
```

### 1.3 ACE 词库分类对照

| public-apis 分类 | ACE 对应 | 说明 |
|-----------------|---------|------|
| Development | Tool / Skill | 开发工具 |
| Finance | Knowledge | 金融知识 |
| Health | Knowledge | 健康知识 |
| Security | Constraint | 安全约束 |
| Science & Math | Pattern | 科学模式 |
| Government | Protocol | 政府协议 |
| Open Data | Lexicon | 开放数据 |
| Blockchain | Pattern | 区块链模式 |

**ACE 可以直接借鉴的分类结构**：

```python
ACE_CATEGORIES = {
    # 核心层
    "knowledge": ["finance", "health", "science", "environment"],
    "pattern": ["blockchain", "security", "machine_learning"],
    "protocol": ["government", "open_data", "standard"],
    "constraint": ["security", "validation", "policy"],

    # 执行层
    "tool": ["development", "communication", "storage"],
    "skill": ["analysis", "generation", "retrieval"],

    # 治理层
    "governance": ["admission", "revision", "evolution"],
    "repository": ["archive", "sync", "publish"],
}
```

---

## 二、元数据模型骨架

### 2.1 API 描述协议

public-apis 的每个 API 条目包含 6 个字段：

```
| 字段 | 类型 | 说明 | ACE 对应 |
|------|------|------|---------|
| API | 名称+链接 | API 名称和文档链接 | asset.name + asset.url |
| Description | 文本 | 不超过 100 字符 | asset.description |
| Auth | 枚举 | OAuth/apiKey/No/User-Agent | asset.auth_type |
| HTTPS | 布尔 | 是否支持 HTTPS | asset.secure |
| CORS | 枚举 | Yes/No/Unknown | asset.cors_status |
| Call this API | 链接 | Postman 集合 | asset.test_url |
```

### 2.2 元数据协议（ACE 外部资源协议）

```yaml
# External Resource Metadata Protocol (ERMP)

external_resource:
  name: string (required)
  url: url (required)
  description: string (max_length=100)
  category: category_enum (required)

  # 访问控制
  auth:
    type: enum[no, api_key, oauth, user_agent]
    required: boolean
    endpoint: url (if needed)

  # 网络属性
  network:
    https: boolean
    cors: enum[yes, no, unknown]
    rate_limit: string (optional)

  # 质量指标
  quality:
    status: enum[active, deprecated, unknown]
    last_verified: datetime
    response_time_ms: integer
    uptime_percent: float

  # 版本控制
  version:
    current: string
    latest: string
    deprecated: boolean
```

### 2.3 ACE 资源描述协议

```python
class ExternalAsset:
    """外部资产元数据"""

    # 必需字段
    name: str                      # 资源名称
    url: str                       # 资源 URL
    category: str                   # 所属分类

    # 访问控制
    auth_type: AuthType            # no/api_key/oauth/user_agent
    auth_endpoint: Optional[str]   # 认证端点

    # 网络属性
    https: bool                    # 是否支持 HTTPS
    cors: CorsStatus               # yes/no/unknown

    # 质量指标
    status: AssetStatus            # active/deprecated/unknown
    last_verified: datetime        # 最后验证时间
    response_time_ms: int          # 响应时间
    health_score: float            # 健康度评分

    # 版本控制
    version_current: str            # 当前版本
    version_latest: str            # 最新版本
    deprecated: bool               # 是否废弃

    # 来源追踪
    source: str                    # 来源仓库
    discovered_at: datetime        # 发现时间
    added_to_civilization: bool   # 是否已进入文明
```

---

## 三、社区维护模式骨架

### 3.1 治理协议（从 CONTRIBUTING.md 提取）

```
═══════════════════════════════════════════════════════════════════════

PUBLIC-APIS GOVERNANCE PROTOCOL

═══════════════════════════════════════════════════════════════════════

第一条：准入标准

一个 API 要进入清单，必须满足：

1. 必须是免费的（或有免费层）
2. 必须有完整文档
3. 必须是非营销性质（不是推广付费 API）
4. 不能依赖购买设备/服务

═══════════════════════════════════════════════════════════════════════

第二条：提交规则

PR 格式要求：

1. 标题格式：Add {API-Name} API
   ❌ Update Readme.md
   ✅ Add NASA API to Space

2. 每个 PR 只提交一个 API
   ❌ Add Weather and News APIs
   ✅ Add Weather API
   ✅ Add News API

3. 必须 squashed commits
   ❌ Multiple commits
   ✅ One squashed commit

4. 按字母顺序排列
   ❌ 随意插入
   ✅ 按名称字母顺序

5. 不能重复
   ❌ 添加已有的 API
   ✅ 先搜索确认不存在

═══════════════════════════════════════════════════════════════════════

第三条：拒绝标准

以下情况会被拒绝：

1. 营销推广目的
2. 需要购买设备才能使用（如智能插座 API）
3. 不是真正免费的
4. 缺乏文档
5. 格式不符合要求
6. 是已有 API 的更新版本

═══════════════════════════════════════════════════════════════════════

第四条：质量保证

1. 自动构建检查所有链接有效性
2. 必须确保构建通过才能合并
3. 持续集成验证 PR 质量

═══════════════════════════════════════════════════════════════════════

第五条：决策权

1. 任何人可以提交 PR
2. 协作者（Collaborators）决定是否合并
3. APILayer 提供基础设施支持

═══════════════════════════════════════════════════════════════════════
```

### 3.2 ACE 文明治理协议（可借鉴）

```yaml
# ACE Civilization Governance Protocol (ACGP)

═══════════════════════════════════════════════════════════════════════

第一条：准入标准

一个知识要进入文明，必须满足：

1. 必须有 Evidence（证据）
2. 必须经过 Validation（验证）
3. 必须通过 Governor 审批
4. 不能是 Hypothesis 直接变成 Fact

═══════════════════════════════════════════════════════════════════════

第二条：提交规则

PR 格式要求：

1. 标题格式：feat: Add {Concept} to {Category}
   ❌ Update knowledge.md
   ✅ feat: Add "笨者生存" to Principles

2. 每个 PR 只提交一个知识单元
   ❌ Add patterns and principles
   ✅ Add "笨者生存" pattern
   ✅ Add "流动优先" principle

3. 必须 squashed commits
   ❌ Multiple commits
   ✅ One squashed commit

4. 不得重复
   ❌ 添加已有的概念
   ✅ 先搜索 Lexicon 确认不存在

═══════════════════════════════════════════════════════════════════════

第三条：拒绝标准

以下情况会被拒绝：

1. 缺乏 Evidence
2. Validation 失败
3. 违反已有 Law
4. 格式不符合模板
5. 是已有知识的更新版本（应该走 Revision）

═══════════════════════════════════════════════════════════════════════

第四条：质量保证

1. 自动检查 Evidence 有效性
2. 必须通过 Validator 审查
3. Governor 评估 ROI

═══════════════════════════════════════════════════════════════════════

第五条：决策权

1. 任何人可以提交（通过 PR 或自动发现）
2. Governor 决定是否进入
3. Evolution 决定演化方向

═══════════════════════════════════════════════════════════════════════
```

---

## 四、三层结构的演化关系

```
                    三层结构
                    
═══════════════════════════════════════════════════════════════════════

                    ┌─────────────┐
                    │  分类体系   │  ← 用户意图的表达层
                    │ (Category)  │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  元数据模型  │  ← 资源描述协议层
                    │ (Metadata)  │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  社区维护   │  ← 治理协议层
                    │ (Governance)│
                    └─────────────┘

═══════════════════════════════════════════════════════════════════════

                    ACE 对应
                    
═══════════════════════════════════════════════════════════════════════

                    ┌─────────────┐
                    │   Lexicon   │  ← 分类体系
                    │  (词库)     │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Asset      │  ← 元数据协议
                    │  Registry   │
                    └──────┬──────┘
                           │
                           ▼
                    ┌─────────────┐
                    │  Governor   │  ← 治理协议
                    │ (治理层)    │
                    └─────────────┘
```

---

## 五、ACE 吸收方案

### 5.1 分类体系 → Lexicon 分类

```python
# ACE 可以直接采用的分类结构
LEXICON_CATEGORIES = {
    # 一级分类（按领域）
    "domain": {
        "animals": "动物相关",
        "finance": "金融相关",
        "health": "健康相关",
        "security": "安全相关",
        "development": "开发相关",
    },

    # 二级分类（按类型）
    "type": {
        "knowledge": "知识",
        "pattern": "模式",
        "principle": "原则",
        "law": "定律",
        "paradigm": "范式",
    },

    # 三级分类（按属性）
    "attribute": {
        "verified": "已验证",
        "hypothesis": "假设",
        "deprecated": "已废弃",
    }
}
```

### 5.2 元数据协议 → Asset Registry

```python
# ACE 可以直接采用的资源描述协议
@dataclass
class AssetMetadata:
    """外部资产元数据"""
    name: str
    url: str
    category: str

    # 访问控制
    auth_type: str  # no/api_key/oauth
    https: bool
    cors: str       # yes/no/unknown

    # 质量
    status: str     # active/deprecated
    last_verified: datetime
    health_score: float

    # 来源
    source: str
    discovered_at: datetime
```

### 5.3 治理协议 → Governor Protocol

```python
# ACE 可以直接采用的治理协议
GOVERNOR_PROTOCOL = {
    "admission_criteria": [
        "必须有 Evidence",
        "必须经过 Validation",
        "必须通过 Governor 审批",
        "不得是 Hypothesis 直接变 Fact",
    ],

    "submission_rules": [
        "标题格式：feat: Add {concept} to {category}",
        "每个 PR 只提交一个单元",
        "必须 squashed commits",
        "不得重复已有知识",
    ],

    "rejection_reasons": [
        "缺乏 Evidence",
        "Validation 失败",
        "违反已有 Law",
        "格式不符合",
    ],

    "decision_authority": {
        "anyone": "可以提交 PR",
        "governor": "决定是否进入",
        "evolution": "决定演化方向",
    }
}
```

---

## 六、发现的差距

### 6.1 ACE 当前差距

| 层级 | public-apis | ACE | 差距 |
|------|------------|-----|------|
| 分类 | 51 个领域分类 | 基础分类 | 需要扩展到 51 个 |
| 元数据 | 6 字段完整描述 | 缺失 | 需要建立 Asset Registry |
| 治理 | 完整 PR 协议 | 基础约束 | 需要完善 Governor Protocol |

### 6.2 建议补充

1. **Lexicon 分类扩展**：增加到 51 个领域分类
2. **Asset Registry 建立**：实现外部资源的元数据协议
3. **Governor Protocol 完善**：建立完整的准入/拒绝/审批流程

---

## 七、结论

### 骨架提取总结

| 骨架 | 来源 | ACE 对应 | 吸收状态 |
|------|------|---------|---------|
| 分类体系 | README.md Index | Lexicon 分类 | 🆕 需建立 |
| 元数据模型 | API 表格格式 | Asset Registry | 🆕 需建立 |
| 社区维护 | CONTRIBUTING.md | Governor Protocol | ⚠️ 需完善 |

### 最重要的发现

public-apis 能活 8 年的原因**不是 API 数量**，而是：

1. **清晰的分类体系**（用户意图导向）
2. **标准化的元数据协议**（6 字段描述）
3. **严格的治理协议**（准入/拒绝/审批）

这三层结构才是**骨架**，API 只是**血肉**。

---

*考古完成时间：2026-06-30*
*骨架提取：3 层核心结构*
*ACE 吸收：3 个待建立模块*
