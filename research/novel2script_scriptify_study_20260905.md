# Novel2Script / Scriptify 偷师研究收据

日期：2026-09-05（Asia/Shanghai）
范围：只读研究 + 本地构建/测试验证；未修改两个上游仓库，也未改动现有视频生产代码。

## 1. 已拉取仓库

- `C:\tmp\novel2script`
  - remote：`https://github.com/wswhhhc/novel2script`
  - HEAD：`323e6ab style: prettier格式化 CharacterGraph.test.tsx`
  - 许可证：MIT
- `C:\tmp\scriptify`
  - remote：`https://github.com/wordflowlab/scriptify`
  - HEAD：`7a9d5e2 chore: 发布 v0.8.2 - 补充 CHANGELOG`
  - 许可证：MIT

## 2. 运行证据

### Novel2Script

- `python -m compileall -q backend`：PASS
- 隔离环境 `C:\tmp\novel2script-venv` 安装 `backend/requirements.txt` 后：
  - `pytest backend/tests -q`：**80 passed**
- 前端 `npm ci --ignore-scripts` 后：
  - `npm test --prefix frontend -- --run`：**9 files / 90 tests passed**
  - `npm run build`：**PASS**（Vite 生产包生成）
- 未安装依赖时，系统 Python 的 pytest 会因缺少 `python-dotenv` 在收集阶段失败；这不是仓库代码失败，已用隔离环境复核。

### Scriptify

- `npm install --no-package-lock --ignore-scripts` 后 `npm run build`：
  - TypeScript 编译：PASS
  - npm `postbuild`：FAIL，Windows 环境没有 `chmod` 命令
- `node dist/cli.js --help`：PASS，能列出 `init/spec/idea/outline/characters/scene/script/...` 命令
- 在新目录运行 `init --here --ai codex`：PASS，生成 `.scriptify/config.json`、`.codex/prompts/*`、`scripts/bash/*` 等项目骨架
- 在同一 Windows 环境运行 `spec`：FAIL，错误为 `spawn bash ENOENT`
- 结论：Scriptify 的模板/命令设计可读、可复用；当前 CLI 的执行层不是 Windows 原生可运行路径。

## 3. 值得吸收的设计

### A. Novel2Script：把小说改编拆成有契约的中间产物

它不是让模型一次性“小说直接变剧本”，而是明确拆成：

`章节分析 → 统一角色表 → 场景大纲 → 结构化剧本 → Schema 校验/自动修复`

可吸收点：

1. **章节、角色、场景、剧本分层**：每一层都有明确输入/输出，不把所有上下文塞进一次生成。
2. **稳定 ID**：`C001`、`CHAR001`、`S001` 这类 ID 让跨阶段引用可校验；这对现有 `episode_plan`、`shot contract` 的溯源很有价值。
3. **角色注册表**：统一姓名、别名、首次出场和关系，能减少镜头间角色漂移。
4. **场景大纲先行**：场景包含来源章节、地点、时间、出场角色、剧情目的、关键节拍和冲突，适合在进入逐镜生成前作为结构门。
5. **结构化输出 + 修复循环**：JSON Schema/YAML 校验失败时，把错误信息回传给修复阶段；不是静默接受脏输出。
6. **`adaptation_notes` + `open_questions`**：把改编决策和未决问题显式留在产物里，便于后续人工确认和审计。

关键参考：

- `C:\tmp\novel2script\schemas\script.schema.json`
- `C:\tmp\novel2script\prompts\01_chapter_analysis.txt`
- `C:\tmp\novel2script\prompts\02_character_extraction.txt`
- `C:\tmp\novel2script\prompts\03_scene_planning.txt`
- `C:\tmp\novel2script\prompts\04_script_generation.txt`
- `C:\tmp\novel2script\prompts\05_yaml_fix.txt`

### B. Scriptify：把创作流程变成可复用的命令协议

它的核心不是后端算法，而是“命令模板 + 项目状态文件 + 文件脚本”的组合：

- 用 `/import`、`/analyze`、`/extract`、`/compress`、`/visualize`、`/externalize`、`/script` 表达小说改编链路。
- 用 `/select-novel` 先做选题评估，输出评分和 A/B/C 改进方案，而不是一上来盲改。
- 用 `/adapt-comic` 先分析题材/节奏，再给风格、集数、模式选项；强调“先分析再提问”。
- 用 `/quality-check-comic` 把时长、对白数、开篇冲突、结尾钩子、禁止内容、口语化/动作细节列成检查清单。
- 每条命令以 Markdown frontmatter 声明描述、参数和脚本入口；这个形态适合挂接现有的 `research receipt` / `preflight` / `acceptance receipt`。

关键参考：

- `C:\tmp\scriptify\templates\commands\select-novel.md`
- `C:\tmp\scriptify\templates\commands\adapt-comic.md`
- `C:\tmp\scriptify\templates\commands\quality-check-comic.md`
- `C:\tmp\scriptify\src\cli.ts`
- `C:\tmp\scriptify\src\utils\yaml-parser.ts`

## 4. 与现有 ACE/Video Kingdom 的映射

不替换现有 `six_module_contract`，新增一个更上游、可选的“故事编译层”即可：

```text
local novel / original idea
  -> source_manifest (path, sha256, rights/evidence boundary)
  -> chapter_analysis[]
  -> character_registry
  -> scene_outline[]
  -> episode_plan + adaptation_notes + open_questions
  -> six_module_contract (measured TTS required)
  -> per-shot provider generation
  -> pacing / continuity / acceptance gates
```

建议映射：

| 上游研究产物 | 现有系统落点 | 规则 |
|---|---|---|
| `Cxxx` 章节 ID | `source_manifest` / `episode_plan.source_refs` | 保留原 ID，不靠标题匹配 |
| `CHARxxx` 角色表 | `assets/*_dossier.json` + `episode_plan.cast` | 角色名、别名、锚点图、首次出场均可追溯 |
| `Sxxx` 场景大纲 | `six_module_contract.modules[].scene_ref` | 先过场景结构门，再生成逐镜 |
| `adaptation_notes` | research receipt / decision record | 记录删改、外化、压缩依据 |
| `open_questions` | preflight 的 `UNKNOWN` / `REVIEW_REQUIRED` | 未决事项不能伪装成 PASS |
| Hook/节奏/禁词清单 | 现有 pacing + continuity + acceptance 证据 | 只把可测部分升级为硬门禁 |

## 5. 明确不照搬的部分

1. **不把 Scriptify 的“爆点密度/评分阈值”直接当成事实**：这些是创作 heuristics，必须标成策略或建议；只有经过本地样本验证后才可进入硬门禁。
2. **不把“前 5000 字足够”当通用规则**：它适合快速选题预览，不适合需要全局连续性的正式改编；正式流水线仍需记录完整来源范围和截断边界。
3. **不采用 Scriptify 的硬编码 Bash 执行路径**：当前 Windows 运行已实证 `spawn bash ENOENT`；现有控制面应优先使用 Python/PowerShell 原生入口。
4. **不让一次性剧本生成绕过逐镜 TTS、pacing、continuity 审计**：研究仓库的结构化剧本只能作为上游输入，不能替代当前已建立的媒体质量门。
5. **不把 README/PRD 的“已实现”描述当成运行证据**：以本地测试、构建和最小入口复现为准。

## 6. 当前结论

- **Novel2Script：可借鉴，偏工程化。** 最值得吸收的是分层中间产物、稳定 ID、角色/场景注册表、Schema 校验和修复循环。
- **Scriptify：可借鉴，偏工作流化。** 最值得吸收的是命令协议、先分析后选项、质量清单、`adaptation_notes/open_questions` 的显式留痕。
- **两者都不能直接作为现有视频生产替代品。** 前者没有现有的逐镜媒体连续性门；后者明确不负责分镜、资产、配音和渲染，且其 Windows CLI 执行路径存在缺口。
- **本轮执行产物是研究收据，不升级任何交付状态，也不重复提交 Provider 请求。**

## 7. 下一步（待纳入现有控制面）

1. 先实现只读 `novel_ingest`：生成 `source_manifest`、章节 ID、sha256 和证据边界。
2. 再实现 `character_registry` / `scene_outline` 的结构化编译器，输出兼容 `episode_plan` 的中间 JSON。
3. 将 `adaptation_notes`、`open_questions` 接入 preflight；任何未决问题默认 `UNKNOWN/REVIEW_REQUIRED`。
4. 只在这些中间产物稳定后，选择一条新题材跑完整的“实测 TTS → 逐镜生成 → pacing/continuity → acceptance”闭环。
