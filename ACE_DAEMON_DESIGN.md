# ACE 自动考古主循环 — 设计说明（v3 完整版）

## 一、定位

ACE Daemon 是 ACE Runtime 从"手动工具"向"自动生态"演进的核心。

**核心原则**：TRAE 负责叫醒，ACE 自己决定今天挖什么、怎么挖、挖多少。

**v2 升级**：从"简单磁盘扫描"升级为"深度挖矿主循环"。
**v3 升级**：统一导出到 mine-seed 仓库、JSON 结构自动分析、eco_layer 深度报告。

## 二、架构

```
TRAE 定时任务 (02:00 每日)
    ↓ 叫醒
ace_daemon.py (主循环)
    ↓
    ├─ 初始化挖矿模块（自动发现数据文件，不硬编码路径）
    │   ├─ EcoLayerParser — eco_layer 五层生态解析 + 深度报告生成
    │   ├─ SliceClusterer — Ω-FINAL 切片聚类分析
    │   ├─ ConceptMiner — 概念提取引擎 v2（强化过滤+打分）
    │   ├─ ArchaeologyExporter — 考古产物导出器
    │   └─ RepoSyncer — Git 仓库同步器
    │
    ├─ 状态检查 → 词库状态、记忆索引、挖矿进度、mine-seed连接状态
    ├─ 决策引擎 → 决定今日行动优先级
    ├─ 执行器 → 按优先级执行
    │   ├─ eco_mining → 挖一层生态（含深度报告自动生成）
    │   ├─ slice_mining → 做一种切片分析
    │   ├─ disk_scan → 扫描新路径（含 JSON 结构分析）
    │   └─ lexicon_gap → 词库缺口补全
    ├─ 概念提取 → 从挖到的材料中提炼新概念 → 入词库
    ├─ 自动归档 → 基于内容判断归档位置
    ├─ 导出同步 → 产物导出到 mine-seed → Git push
    └─ 写入摘要 → 今日考古摘要 → 记忆索引
```

## 三、决策逻辑（v3）

### 决策优先级（从高到低）

1. **eco_layer 挖矿** — 有未挖完的层就挖（从价值密度最高的叙事生态开始）
   - 叙事生态 → 行为生态 → 结构生态 → 交易生态 → 自由区
   - 每日预算：叙事100、行为150、结构100、交易150、自由区200
   - 可持续：记住 offset，第二天接着挖
   - 每次挖完自动生成深度报告存入记忆索引

2. **Ω-FINAL 切片考古** — 按顺序做不同维度的分析
   - 总览统计 → 按文件聚类 → 按功能类别聚类 → 核心模块识别 → 配置文件提取
   - 每天做一种，5天一轮回

3. **磁盘扫描** — 发现新路径/新文件时
   - **v3 新增**：JSON 文件自动结构分析 + 新概念自动入词库
   - 每天最多扫描 2 个路径

4. **词库缺口补全** — 分类概念数<=2时

5. **今日无新增** — 以上都没有时

### 每日预算（DAILY_BUDGET）

| 项目 | 每日量 |
|------|--------|
| eco_narrative | 100 条 |
| eco_behavioral | 150 条 |
| eco_structural | 100 条 |
| eco_transactional | 150 条 |
| eco_free_zone | 200 条 |
| slice_* | 各 1 次/天 |
| disk_scan_paths | 2 个/天 |
| concept_extraction | 10 个/天 |

## 四、挖矿模块

### 1. EcoLayerParser

- 解析 eco_layer 五层生态（285万条目）
- 分层采样、模式提取、自动索引、关键词搜索
- **v3 新增**：`generate_deep_report()` 生成全层深度报告（含进度洞察、跨层关系、建议）

### 2. SliceClusterer

- 总览统计、按来源文件聚类、按功能类别聚类
- 核心模块识别（打分机制）、配置文件提取

### 3. ConceptMiner v2

- 强化过滤：URL碎片（com/https/www/zhihu）、人名+数字（下午5）、通用字段（metadata/name/id）
- 新增模式识别：定义短语（"X是一种"、"X："）、CamelCase/snacle_case 识别
- 智能打分：出现频率 × 定义上下文 × 相关已有概念 × 技术术语加成
- 自动分类 + 自动关联 + 自动定义生成
- 垃圾词识别：含数字过多、域名碎片、社交媒体词

### 4. DiskScanner v2（JSON 结构分析）

- 发现 JSON 文件时自动解析结构
- 提取顶层键、嵌套键、数组结构、类型分布
- 对比已知结构库（core_data/slices/lexicon/executor/identity 等）
- 识别 CamelCase/snacle_case 字段 → 自动入词库
- 格式化分析报告存入记忆索引（memory_type: json_structure）

### 5. ArchaeologyExporter

- 词库快照（latest + 每日）
- 记忆索引快照（latest + 每日）
- 守护进程状态（挖矿进度）
- 每日考古摘要（markdown）
- eco_layer 统计 + 切片分析结果

### 6. RepoSyncer

- 检查变更 → git add → 自动生成 commit message → git push
- 失败不中断主循环，错误记入状态
- 支持指定子目录同步（只同步 r1_archaeology/）

## 五、文件存放位置 — 自动归档

**不硬编码路径** — 基于内容和词库概念自动判断。

| 概念/分类所属 | 归档目录 |
|---|---|
| 灵魂资产 / 治理原则 | 02_CONSTRAINT |
| 架构分层 / 架构模式 | 03_ARCHITECTURE |
| 核心机制 | 04_PROTOCOL |
| 恢复机制 | 05_MEMORY |
| ACE概念 | 06_RUNTIME |
| 演化机制 | 07_SEEDS |
| 身份系统 | 01_LEXICON |
| 考古发现 | 08_ARCHAEOLOGY |
| 身体层 | 09_BODY |
| 无匹配 | 00_INBOX |

## 六、状态管理

状态文件：`06_RUNTIME/ace/data/memory/daemon_state.json`

| 字段 | 说明 |
|------|------|
| last_run | 上次运行时间 |
| last_scan_paths | 已扫描路径记录 |
| last_lexicon_count | 上次词库概念数 |
| last_memory_count | 上次记忆索引数 |
| daily_summaries | 最近90天的每日摘要 |
| mining_progress.eco_layer.{layer} | 每层挖矿进度 |
| mining_progress.slices | 切片分析进度 |
| discovered_paths | 自动发现的路径记录 |
| errors | 最近50条错误记录 |

## 七、考古产物导出目录

```
mine-seed 仓库/
└── 03_DATA/research/r1_archaeology/
    ├── lexicon/
    │   ├── lexicon_latest.json
    │   └── lexicon_YYYYMMDD.json
    ├── memory_index/
    │   ├── memory_index_latest.json
    │   └── memory_index_YYYYMMDD.json
    ├── daily/
    │   └── YYYY-MM-DD.md
    ├── eco_layer/
    │   └── layer_stats.json
    ├── slices/
    │   └── *.json
    └── daemon_state.json
```

## 八、使用方式

```bash
python ace_daemon.py              # 运行一次主循环
python ace_daemon.py --dry-run    # 只看决策
python ace_daemon.py --force      # 强制运行
python ace.py daemon              # 通过主入口
```

TRAE 定时任务：每天 02:00（任务ID：078b4ae6）

## 九、进度追踪（2026-06-26 快照）

| 指标 | 数值 |
|------|------|
| 词库概念 | 167 个 |
| 词库分类 | 20 个 |
| 记忆索引 | 1009 条 |
| eco叙事生态 | 300/4347 (6.9%) |
| eco行为生态 | 未开始 |
| eco结构生态 | 未开始 |
| eco交易生态 | 未开始 |
| eco自由区 | 未开始 |
| Ω切片分析 | 3/5 种模式完成 |
| Git提交 | 4 次（3次成功push） |

## 十、后续演进方向

1. **概念质量提升** — 从 eco 层的技术层（结构/行为）挖，不要只挖叙事
2. **增量扫描** — 基于文件修改时间，只扫描新文件
3. **归档落地** — 从"分析归档位置"升级为"实际移动文件"
4. **挖矿策略优化** — 根据概念产出质量动态调整预算
5. **跨层关联** — 建立 eco_layer 各层之间的引用关系
6. **JSON 深挖** — 扫描 R1 的所有 JSON 配置文件，自动还原系统配置

---

**版本**：v3.0
**日期**：2026-06-26
**状态**：生产运行中
