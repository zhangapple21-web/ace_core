# Public APIs 考古报告 — 2026-06-30

**AUM-TASK-2026-06-30-001**
**来源**：https://github.com/public-apis/public-apis
**考古日期**：2026-06-30

---

## 一、仓库概述

| 指标 | 数值 |
|------|------|
| 总 API 数量 | 1,479 |
| 分类数量 | 51 |
| HTTPS 支持 | 1,392 (94%) |
| 无需认证 | 695 (47%) |
| CORS 支持 | 461 (31%) |

---

## 二、分类分布（Top 15）

| 分类 | API 数量 | 说明 |
|------|---------|------|
| Development | 120 | 开发工具 |
| Government | 94 | 政府数据 |
| Games & Comics | 85 | 游戏动漫 |
| Geocoding | 83 | 地理编码 |
| Cryptocurrency | 68 | 加密货币 |
| Transportation | 56 | 交通 |
| Finance | 51 | 金融 |
| Open Data | 43 | 开放数据 |
| Security | 42 | 安全 |
| Social | 42 | 社交 |
| Health | 41 | 健康 |
| Science & Math | 39 | 科学数学 |
| Environment | 38 | 环境 |
| News | 35 | 新闻 |
| Food & Drink | 32 | 饮食 |

---

## 三、认证方式分布

| 认证方式 | 数量 | 占比 |
|---------|------|------|
| No（无需认证） | 695 | 47% |
| API Key | 634 | 43% |
| OAuth | 141 | 9.5% |
| 其他 | 8 | 0.5% |

---

## 四、CORS 状态分布

| CORS 状态 | 数量 | 占比 |
|-----------|------|------|
| Unknown | 900 | 61% |
| Yes | 461 | 31% |
| No | 118 | 8% |

---

## 五、候选矿工筛选

### 筛选条件
1. 认证方式：No / API Key / OAuth
2. HTTPS 支持：Yes

### 结果
- 总候选矿工：1,370
- 其中 CORS 支持：~400

---

## 六、连通性测试结果（Top 20 CORS=Yes）

| API 名称 | 状态 | 响应时间 | 分类 |
|----------|------|----------|------|
| Cat Facts | ✅ 200 | 910ms | Animals |
| Dog Facts (dukengn) | ✅ 200 | 828ms | Animals |
| Dog Facts (kinduff) | ✅ 200 | 807ms | Animals |
| Dogs | ✅ 200 | 745ms | Animals |
| FishWatch | ❌ timeout | - | Animals |
| HTTP Cat | ✅ 200 | 607ms | Animals |
| HTTP Dog | ✅ 200 | 603ms | Animals |
| Movebank | ✅ 200 | 1239ms | Animals |
| PlaceBear | ✅ 200 | 1524ms | Animals |
| PlaceDog | ✅ 200 | 1234ms | Animals |
| RandomDog | ✅ 200 | 1591ms | Animals |
| Shibe.Online | ❌ 连接失败 | - | Animals |
| AnimeFacts | ✅ 200 | 879ms | Anime |
| AnimeNewsNetwork | ✅ 200 | 828ms | Anime |
| Catboy | ✅ 200 | 964ms | Anime |
| NekosBest | ✅ 200 | 928ms | Anime |
| Studio Ghibli | ✅ 404 | 1540ms | Art & Design |
| Trace Moe | ✅ 200 | 904ms | Anime |
| Waifu.im | ✅ 200 | 1286ms | Anime |
| URLhaus | ✅ 200 | 1203ms | Anti-Malware |

**测试结果**：18/20 可达 (90%)

---

## 七、优先接入建议

### Tier 1：立即可用（无需认证 + HTTPS + CORS + 已验证可达）

| API | URL | 用途 |
|-----|-----|------|
| Dog Facts | https://dog-facts-api.herokuapp.com/ | 动物数据 |
| Dogs | https://dog.ceo/dog-api/ | 动物图片 |
| HTTP Cat | https://http.cat/ | HTTP 状态码 |
| HTTP Dog | https://http.dog/ | HTTP 状态码 |
| Movebank | https://www.movebank.org/ | 动物迁移 |
| AnimeFacts | https://anime-facts.herokuapp.com/ | 动漫数据 |
| AnimeNewsNetwork | https://cdn.animenewsnetwork.com/ | 动漫新闻 |
| Waifu.im | https://api.waifu.im/ | 动漫图片 |

### Tier 2：需要认证但可用

| API | URL | 认证方式 |
|-----|-----|---------|
| Weatherstack | https://api.weatherstack.com/ | API Key |
| Marketstack | https://api.marketstack.com/ | API Key |
| IPstack | https://ipstack.com/ | API Key |

---

## 八、发现的缺口

### 1. 缺少中文数据源
- 现有分类全是英文
- 建议增加：中文新闻、中文天气、中文政府数据

### 2. 缺少实时数据接口
- 大多数是静态数据
- 建议优先接入：实时天气、实时汇率、实时加密货币

### 3. 缺少健康度监控
- URLhaus 可达但可能是恶意软件数据库
- 建议增加：API 健康度定期检查机制

---

## 九、接入步骤

1. **建立 API Gateway**
   - 统一入口
   - 认证管理
   - 限流控制

2. **建立健康度监控**
   - 定期检查可达性
   - 记录响应时间
   - 标记不可用 API

3. **建立数据质量评估**
   - 评估响应格式
   - 评估数据准确性
   - 评估更新频率

4. **接入 MinerPool**
   - 优先 Tier 1
   - 逐步扩展到 Tier 2
   - 建立反馈机制

---

## 十、结论

### 骨架提取

| 骨架 | 说明 |
|------|------|
| **分类体系** | 51 个分类，覆盖主要领域 |
| **认证分层** | No / API Key / OAuth 三层 |
| **CORS 标识** | 可直接判定是否可浏览器调用 |
| **可用性模式** | 可达率 ~90%，但需验证 |

### 建议

1. **立即可接入**：Tier 1 的 8 个 API
2. **短期目标**：接入 50 个高质量 API
3. **长期目标**：建立 API 发现层，作为 MinerPool 的数据源

---

*考古完成时间：2026-06-30*
*骨架提取：4 个核心模式*
*可接入 API：1,370 个候选*
*优先接入：8 个立即可用*
