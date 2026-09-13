# ACE vs R1 端口边界 / 远程仓 / 本地抽屉 — 2026-09-12

> 用户把 R1「端口即边界」发来对照。本文只记录判断，不重开 8001/8003/1443，不改 3000/3002，不启 daemon。

## 判断

R1 那套职责还在，但已经不是 TCP 端口。ACE 把同一条边界做成了代码/治理，不是监听口。

现场只在听两个环回口：

- `127.0.0.1:3000` → `local_oneapi_gateway_launcher.py`（LiteLLM/OneAPI）
- `127.0.0.1:3002` → `shenwen_responses_compat_proxy.py`（Responses 兼容层）

`8001` / `8003` / `1443` 本机未监听，`ace_core` 代码里也搜不到。不要为了「像以前」把它们重新立起来。

## 对照

| R1 端口 | 当时职责 | 现在 ACE 对应 | 现状 |
|---|---|---|---|
| 8001 外网/生产 | 只展示、加密、受控、不泄露内核 | `AceDaemon` + Admission + CoreSyncer 母板 allowlist + Telegram 出口 | 职责在代码里；daemon 心跳停在 2026-09-08，当前没在跑 |
| 8003 内网/实验 | 完全自由、纯学习 | `07_SANDBOX/free_research` | 还在写蒸馏/提案；默认不得进生产 |
| 1443 仲裁/桥接 | 内外网唯一穿透，证据核验 | `08_GOVERNANCE/free_zone_bridge` 收据（`MAPPED_SHADOW` / `HOLD_FOR_EVIDENCE`） | 桥是文件收据，不是端口；2026-09-07 最近一张仍是 HOLD |
| 3000 模型网关 | 统一模型入口 | 3000 LiteLLM + 3002 Responses 兼容层，独立报告、不可互相掩盖 | 活着；2026-09-06 Runtime Boundary 已收口 |

穿透路径现在是：实验产物 → 桥接收据 → Admission/Experience 审阅 → 才可能进 Runtime。不是 8003 直出、也不是 8001 直写内网。

旧文档不要当现场：`mine-seed/06_RUNTIME/ACE_RUNTIME_TOPOLOGY.md`（2026-07-13）和 `07_GUARDIAN/NETWORK_BRIDGE.md`（2026-06-25 zrok）描述的是前世拓扑。

## 远程 git（公开扫描 2026-09-12，未认证，看不到 private）

| 仓 | 角色 | 远程上次 push | 本地抽屉 |
|---|---|---|---|
| ace_core | Runtime Core | 9/11 | `C:\tmp\ace_core`（git 可用，但停在 9/8 刷机快照分支）；干净克隆 `C:\tmp\ace_core_remote_sync` |
| mine-seed | Civilization Seed | 9/8，3d Critical | `C:\tmp\mine-seed`（有 `.git`，对象库坏，remote 读不出） |
| r1-archaeology | Civilization Memory | 9/6 | `C:\tmp\r1-archaeology`（同上，git 对象坏） |
| `-` | 视频王国公开资产 | 9/1 | `C:\tmp\ace_video_kingdom_assets_public`；备份 remote 指向这个异常名 |
| R1_continuity_archive | 连续性档案 | 8/19 | 本地未见独立目录 |
| R1 | 哲学仓 | 7/19 Abandoned | `C:\tmp\R1`（基本只剩 README） |
| aum-protocol | 未知 | 7/14 Abandoned | 本地未见 |
| r1-open-source-seed | 开源种子 | 7/8 Abandoned | `C:\tmp\r1-open-source-seed` |
| coze-assets | 私有密钥仓 | 扫描看不见 | 不在公开地图里，也不该上公共远程 |

备份 `MANIFEST.json`（2026-09-08）里还有扫描器没标角色的仓：

- `claw-soul` → 本地 `C:\tmp\claw-soul`
- `mine-seed-credentials` → 本地 `C:\tmp\mine-seed-credentials`（凭据，禁止公共推送）
- `ace-video-kingdom` → `D:\tmp\ace-video-kingdom`
- `infinite-canvas` / `zola` → 第三方 clone，不是 ACE 母板

本地-only 抽屉（备份标明无 remote）：`continue_gate_runtime`、`runtime`、`agnes-js`、`coze-mirror`。

## 本地抽屉分层（PR-001）

1. **Runtime**：3000/3002 在；ACE daemon 不在。`memory_index` 停在 9/8。
2. **Workspace**：`C:\tmp` 是工作抽屉，`D:\tmp\ACE_SYSTEM_BACKUP_20260908_200634` 是更晚的刷机备份。
3. **GitHub**：公开仓如上；多数本地 clone 的 `.git/objects` 坏了，不能当推送端。
4. **Telegram / Archive / Internet**：本轮不翻。

## 故意没做

- 不监听 8001/8003/1443。
- 不改 `local_oneapi_config.yaml` / 3000 / 3002。
- 不启 ACE daemon，不扩 CoreSyncer，不 `git add .`。
- 不修全部坏 git 对象库。
- 不把 claw-soul / credentials / 视频王国塞进文明地图扫描器（那会扩生产工具）。

## 以后若要补，最小顺序

1. 继续只用收据/Admission 当 1443，不要端口化。
2. 文明地图扫描器补「备份有、扫描器没有」的仓名（claw-soul 等），仍保持未认证、private 不可见。
3. 推送只走 `ace_core_remote_sync` 这类干净克隆，且只推已分类 `docs/`。
