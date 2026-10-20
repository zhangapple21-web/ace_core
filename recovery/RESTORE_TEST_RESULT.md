# Restore Test Result

更新日期：2026-10-01

## 结论

状态：`PARTIAL`。远程回执证明 core 分支和私有 state 白名单可在隔离目录中取回并完成 hash 校验；不证明整机、跨文件事务一致性、历史行为连续性、daemon 每日迭代、外部 Provider 或完整宿主工作流可恢复。

## 当前远程 ref 对账（非恢复重跑）

Observed-at：2026-10-01T06:02:34Z–2026-10-01T06:02:37Z；非交互 `git ls-remote --heads` 查得 core `core/daemon-lifecycle-resilience-20260912` 为 `4d40191b539dfcc0e651504437e20d07daa5dd4e`，state `main` 为 `a40340bf1329b3789773ce09d2cd11a50676f5da`，video `main` 为 `27da48891ac778e88689fd1e33cdc058472f9b90`，均 `EXISTS`、exit=0。16/16 optional refs 同样 `EXISTS`，SHA 未变；没有 ACCESS_BLOCKED 或 BRANCH_MISSING。本次只查询 ref，当前 core HEAD 的完整恢复、health、业务结果为 `UNVERIFIED`；下文 PARTIAL/FAIL 是各自历史 checkout 结果，不能作为当前 HEAD 的重跑结果。

从既有隔离 state checkout 的当前远程 SHA 对象复核 `STATE_MANIFEST.json`：SHA-256 `829b2278b5ca15fe4275a62253782eb87619933fc5f637db0fb3dbe5e33a97f2`，1674 entries，counts 与下文一致；未读取凭据仓，未重推 state，也未重新逐项校验 state 内容。

## 历史远程恢复证据

- core：`https://github.com/zhangapple21-web/ace_core.git`，branch `core/daemon-lifecycle-resilience-20260912`，远程/checkout SHA `4414401034b1040351b45f60cbbbb8afdb8ef434`，`ref_match=true`。
- state：`https://github.com/zhangapple21-web/ace-civilization-backup.git`，branch `main`，远程/checkout SHA `a40340bf1329b3789773ce09d2cd11a50676f5da`，`ref_match=true`，private verification PASS；没有读取 secret repo 内容。
- state manifest `829b2278b5ca15fe4275a62253782eb87619933fc5f637db0fb3dbe5e33a97f2`；1674 个文件逐项 bytes/SHA PASS，包含 task_pool 796、09_KNOWLEDGE 686、06_RUNTIME/ace 192、evidence files 65、37960831 bytes。
- manifest 仅声明“两次匹配盘点”，不是跨文件事务快照。恢复的知识文件/records、runtime、memory index 数量分别为 686/612、192、7457；这些是恢复计数，不是行为连续性证明。
- 回执：`C:\tmp\ace_remote_state_final_20261001\ACE_REMOTE_RESTORE_RECEIPT.json`；SHA-256 `e029cb275f17c9685f6d2d5489e7bbfbf13978c7aed3495d74cf8e72b00d9739`。

## 实际验证记录

- 远程 bootstrap 实际 `PARTIAL`，exit code `3`，且使用 `--skip-tests`。
- 远程 health 实际 overall `error`，exit `2`，`errors=1`、`warnings=1`；daemon heartbeat 为 `status=born, pid=None`。WARN/ERROR 不能折算 PASS。
- `ace.py status` 返回 `0`，展示恢复后的 796 tasks、612 knowledge records、7457 memory index records；这是 smoke/status，不是 daemon E2E。
- 隔离 integrated bootstrap tests：`153 passed`；cleanvenv：`103 passed, 3 blocked`；`18 unittest` 通过。
- 历史隔离 integrated bootstrap 为 `PARTIAL`、exit `3`；health `exit=2`、1 error/3 warnings。这些是旧验证记录，不替代历史远程 state 演练，更不代表当前 core HEAD 已重跑；恢复演练的 core SHA 见上文。
- cleanvenv Python `3.11.9`；历史 `pip check` PASS。`recovery/requirements-recovery.lock` 仅覆盖该测试集，不能视为全系统依赖锁。
- 视频域历史演练：`36 passed` 离线测试及 dry-run；`provider_submission=NOT_PERFORMED`，不出片、不提交真实 Provider。
- `business_validation.json` 总体为 `FAIL`：股票 `time` 字段误取价格变化值 `0.30`；真实报价非空但没有模拟单或成交。5 个 Skill 的 loadable/frontmatter 检查和一次纯 helper 调用不是宿主 E2E。

## Fresh Reinstall 验证（2026-10-01）

- 在新的空路径 `C:\tmp\ace_recovery_fresh_20261001_subverify` 从 core 远程 clone canonical branch；checkout 与 `git ls-remote` 均为 `919768e353459011f22ebfde1cd1056bffa75fdd`。没有复用已存在的 `C:\tmp\ace_recovery_fresh_20261001`，没有复制 venv 或包缓存。
- 使用 `py -3.11 -m venv .recovery-venv` 创建新环境：Python `3.11.9`，Windows AMD64，`pyvenv.cfg` 的 `include-system-site-packages=false`，`site.ENABLE_USER_SITE=False`，`sys.prefix != sys.base_prefix`；pip `24.0`，未升级 pip。
- 新 venv 执行 `python -m pip install --no-cache-dir -r recovery/requirements-recovery.lock`，exit `0`，22 个锁定包安装成功；`python -m pip check` exit `0`，输出 `No broken requirements found.`。
- 同一 venv 执行 `python -m pytest -q -p no:cacheprovider recovery/test_recovery.py recovery/test_state_snapshot.py`，exit `0`，`29 passed, 28 subtests passed in 1.66s`。仅 focused recovery 验证，不重跑全业务 behavior，也不将历史 103/153/18/36 计数冒充本次结果。
- **bootstrap 边界**：读取 `bootstrap.py` 确认它使用调用者的 Python 准备目录/配置并执行检查，根本不创建隔离 venv 或安装 lock。因此 code-only bootstrap 不能视为完整 dependency rebuild；本次为人工显式执行的在线 recovery 测试集 dependency rebuild，不修改 bootstrap，不改变任何锁定版本或模型；仅同步 lock 的验证状态注释，具体证据以 manifest 本节对应字段为准。
- **网络与依赖局限**：本次在线包下载成功，`pytdx==1.72` 通过隔离构建产生 wheel，pip 临时构建缓存未迁移。lock 未锁定构建工具，也不含包制品 hash 或离线 wheelhouse；未来包源可用性、断网恢复、其他 Python/平台、PyYAML registry 工具和完整 ACE 依赖/业务仍未验证。未审计包源基础设施，成功安装不能推断长期可恢复。
- **安全边界**：未 clone 私有 state，focused tests 仅使用合成临时 fixtures/模拟调用；未启动 daemon、provider、交易或真实视频任务，未执行继承 epoch 行为。仅使用既有 Git 认证，生产目录和发布仓库无关 dirty 未改动。整机恢复结论仍为 `PARTIAL`。

## 快照排除和边界

- 排除统计已复核：15152 个 backup/cache/test/validation/claim，5 个 source/transient process state，300 个 raw external HTML。HTML 仅保留 hash，正文未上传，不能从 state snapshot 恢复；credential configuration 被排除，secret scan fail-closed。
- C/D 文件系统盘点仍截断：C 159268、D 138394，`truncated=true`；X/Y 只是 D 子目录映射，不是独立介质。整机资产覆盖 `UNKNOWN/PARTIAL`。
- 未恢复保证：Provider 密钥、用户密钥、`mine-seed-credentials` 内容、CosyVoice 权重/参考音频、私有媒体/缓存、白名单之外资产、计划任务动作值。历史连续性、继承 epoch 行为、跨文件事务一致性均 UNKNOWN。
- daemon 未启动；heartbeat、每日迭代、计划任务动作未验。旧 `3000/3002`、legacy scheduler/heartbeat 不由恢复链启动，也不作为健康门槛。
- 不做继承 epoch 行为验证、daemon 视频交易或真实视频任务。

## 可选仓库检查

`restore_from_remote.py` 的全部 16 个 OPTIONAL_REPOS 已于 2026-10-01 以无交互 `git ls-remote` 检查，16/16 唯一 requested ref exit=0；这只证明分支 ref 可查询，不证明内容 clone、测试通过或运行时加载。完整 URL、branch、SHA 见 `REPOSITORY_MAP.md`；凭据仓未查询，UNKNOWN 不假设。

## 严格 PASS 条件

只有扫描未截断且范围明确、行为关键依赖和历史状态有具事务边界的可验证快照、bootstrap/restore/health 全部 PASS 且 exit code 0、daemon heartbeat/每日迭代/计划任务动作实际验证、Skill 宿主 E2E 和模拟单有证据时，才可改写为 PASS。当前保持 `PARTIAL`。
