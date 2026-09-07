# Runtime Boundary Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 已完成运行时权威边界收口：确认 `AceDaemon` 是唯一现代生产运行时，legacy Scheduler/TaskQueue/heartbeat 均 fail-closed，3000 与 3002 独立报告，并移除生产可用的 Admission bypass。

**Architecture:** `AceDaemon` 是唯一现代生产运行时，并与 `core/task.py` 的 TaskPool/Admission 共同承载生产生命周期。Legacy implementations 位于考古边界或 fail-closed 入口，不能从原生产路径启动。Heartbeat 由 daemon 独占，记录 `owner=ace_daemon` 和 `run_id`；`.workspace.write.lock` 由 daemon 生命周期获取和释放，冲突或 malformed lock 均 fail-closed。3000 LiteLLM/OneAPI 与 3002 Responses 兼容层独立报告，不可互相推断；`OneAPIProvider` 和 SurvivalLoop OneAPI 在 `/chat/completions` 前以 `/models` 预检未知模型，返回不可重试的 `model_unavailable`。测试构造边界不构成生产 Admission bypass。

## Closure status (2026-09-06)

本计划中的未勾选步骤是实施前历史清单，不再表示当前待处理项；下列结果已验证：

- [x] `AceDaemon` 为唯一现代生产运行时；`core.scheduler`、`core.task_queue`、`04_PROTOCOLS/heartbeat` 已 fail-closed。
- [x] 生产 heartbeat 为 `owner=ace_daemon` 并包含 `run_id`；旧 protocol heartbeat 不可形成第二循环。
- [x] `AceDaemon` 生命周期获取并释放 `.workspace.write.lock`；冲突返回 `workspace_write_locked`、`owner`、`run_id`、`lock_file`、`recommendation`，malformed lock fail-closed。
- [x] 3000 LiteLLM/OneAPI 与 3002 Responses 兼容层独立报告；两个 catalog 当前均包含 `gpt-5.6-sol`。
- [x] `OneAPIProvider` 与 SurvivalLoop OneAPI 均在 `/chat/completions` 前校验 `/models`；未知模型返回不可重试的 `model_unavailable`。
- [x] 全量 `pytest` 为 `744 passed`，`compileall` 通过；`git diff --check` 仅报告既有 EOF 空行和一处既有尾随空格。

明确剩余风险：这不是全仓库 syscall/ACL 级写入封锁证明；直接文件写入、未证明已接入 guard 的窗口工具，以及 3000/3002 各自后续健康变化，仍须独立审计。此文档收口不包含提交、推送、删除历史或改动代码/测试。

**Tech Stack:** Python 3.11, pathlib, pytest, PowerShell runtime probes, existing ACE daemon/TaskPool and local provider conventions.

---

### Task 1: Lock the legacy runtime boundary with failing tests

**Files:**
- Modify: `C:\tmp\ace_core\ops\test_runtime_authority_audit.py`
- Modify: `C:\tmp\ace_core\ops\test_legacy_cli_fail_closed.py`
- Test: `C:\tmp\ace_core\ops\test_runtime_authority_audit.py`

- [ ] **Step 1: Write the failing tests**

Add tests that assert the former production module paths cannot be imported as executable runtime modules, and that a legacy compatibility path cannot create a task or mutate a modern TaskPool. The tests must inspect the actual import behavior rather than only checking that the CLI does not call the modules.

```python
def test_legacy_runtime_modules_are_not_available_from_production_paths():
    with pytest.raises((ImportError, RuntimeError), match="legacy_runtime_deprecated"):
        importlib.import_module("core.scheduler")
    with pytest.raises((ImportError, RuntimeError), match="legacy_runtime_deprecated"):
        importlib.import_module("core.task_queue")


def test_legacy_runtime_cannot_write_modern_task_pool(tmp_path):
    pool = TaskPool(str(tmp_path / "pool"))
    before = list((tmp_path / "pool").glob("**/*"))
    with pytest.raises((ImportError, RuntimeError), match="legacy_runtime_deprecated"):
        importlib.import_module("core.scheduler")
    assert list((tmp_path / "pool").glob("**/*")) == before
```

Use isolated imports or remove the modules from `sys.modules` so the test cannot pass because another test imported them earlier. Preserve the existing CLI fail-closed assertions.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```powershell
python -m pytest -q ops/test_runtime_authority_audit.py ops/test_legacy_cli_fail_closed.py
```

Expected: the new import-boundary tests fail because the legacy source files are still importable or fail with a different error.

- [ ] **Step 3: Define the archive layout without changing modern imports**

Create an explicit archaeology package under `C:\tmp\ace_core\archaeology\legacy_runtime\` containing the old implementations, and add package markers only if the repository's existing import style requires them. The archived modules must not be imported by `ace.py`, `ace_daemon.py`, `core.task`, or any production role.

- [ ] **Step 4: Replace former production modules with fail-closed shims**

Replace `core/scheduler.py` and `core/task_queue.py` with minimal modules that raise `RuntimeError("legacy_runtime_deprecated")` before importing historical dependencies. Do not retain constructors, queue writes, or compatibility behavior in these shims.

- [ ] **Step 5: Run the focused tests and verify success**

Run:

```powershell
python -m pytest -q ops/test_runtime_authority_audit.py ops/test_legacy_cli_fail_closed.py
```

Expected: PASS, with no import of `nodes.*`, no TaskPool files created, and old CLI commands still returning exit code 2.

- [ ] **Step 6: Commit the isolated legacy boundary**

```powershell
git add core/scheduler.py core/task_queue.py archaeology/legacy_runtime ops/test_runtime_authority_audit.py ops/test_legacy_cli_fail_closed.py
git commit -m "refactor: isolate legacy runtime implementations"
```

### Task 2: Make heartbeat ownership single and explicit

**Files:**
- Modify: `C:\tmp\ace_core\core\heartbeat.py`
- Modify: `C:\tmp\ace_core\04_PROTOCOLS\heartbeat.py`
- Modify: `C:\tmp\ace_core\ace_daemon.py`
- Modify: `C:\tmp\ace_core\ops\test_runtime_continuity_repairs.py`
- Test: `C:\tmp\ace_core\ops\test_runtime_continuity_repairs.py`

- [ ] **Step 1: Write failing heartbeat ownership tests**

Add tests asserting that daemon heartbeat records contain a stable owner and run identifier, and that executing the historical protocol heartbeat does not start a loop or write old memory. The test should monkeypatch the old writer and assert it is never called.

```python
def test_daemon_heartbeat_has_single_owner_and_run_id(tmp_path):
    daemon = AceDaemon(tmp_path, minimal_config(tmp_path))
    daemon.run_id = "run-test"
    receipt = daemon._write_heartbeat()
    assert receipt["owner"] == "ace_daemon"
    assert receipt["run_id"] == "run-test"


def test_historical_heartbeat_is_non_executable(monkeypatch):
    import runpy
    writes = []
    monkeypatch.setattr(Path, "write_text", lambda *args, **kwargs: writes.append(args))
    with pytest.raises(RuntimeError, match="heartbeat_deprecated"):
        runpy.run_path(str(PROJECT_ROOT / "04_PROTOCOLS" / "heartbeat.py"), run_name="__main__")
    assert writes == []
```

Adapt helper names to the actual daemon heartbeat API after reading its current implementation; the assertions must remain owner, run_id, no legacy loop, and no legacy write.

- [ ] **Step 2: Run the heartbeat tests and verify failure**

Run:

```powershell
python -m pytest -q ops/test_runtime_continuity_repairs.py -k heartbeat
```

Expected: FAIL because the current records do not provide the complete owner/run identity or the historical script still executes.

- [ ] **Step 3: Add explicit daemon heartbeat identity**

Update `core/heartbeat.py` and the daemon call site so every production heartbeat record includes `owner="ace_daemon"`, `run_id`, timestamp, and the daemon state/health payload. Keep heartbeat limited to health/observation writes; it must not call TaskPool claim, renew, approve, archive, or completion methods.

- [ ] **Step 4: Convert the historical heartbeat into a fail-closed archive shim**

Move the old implementation to `archaeology/legacy_runtime/heartbeat.py`. Replace `04_PROTOCOLS/heartbeat.py` with a short executable guard that raises `RuntimeError("heartbeat_deprecated")` and performs no imports that can write files, call providers, send messages, or start a loop.

- [ ] **Step 5: Run focused heartbeat and continuation tests**

Run:

```powershell
python -m pytest -q ops/test_runtime_continuity_repairs.py ops/test_24h_runtime_mainline.py -k "heartbeat or continuation"
```

Expected: PASS; only the daemon-owned heartbeat writes current health data, and no historical heartbeat process is runnable.

- [ ] **Step 6: Commit the heartbeat boundary**

```powershell
git add core/heartbeat.py 04_PROTOCOLS/heartbeat.py ace_daemon.py archaeology/legacy_runtime/heartbeat.py ops/test_runtime_continuity_repairs.py
 git commit -m "refactor: make daemon heartbeat ownership explicit"
```

### Task 3: Add a read-only, side-effect-free 3000 health boundary

**Files:**
- Modify: `C:\tmp\ace_core\ace_daemon.py`
- Modify: `C:\tmp\ace_core\ops\test_runtime_authority_audit.py`
- Create: `C:\tmp\ace_core\ops\test_provider_health_boundary.py`
- Test: `C:\tmp\ace_core\ops\test_provider_health_boundary.py`

- [ ] **Step 1: Write failing port-separation and side-effect tests**

Add a test helper that probes 3000 and 3002 separately, records status and error class, and never invokes TaskPool methods. Add a test using a fake failing HTTP client to assert that a 3000 failure returns provider-unavailable health data while the TaskPool directory remains unchanged.

```python
def test_port_health_is_recorded_separately():
    result = probe_provider_health([3000, 3002])
    assert {entry["port"] for entry in result} == {3000, 3002}
    assert all("status" in entry and "side_effects" in entry for entry in result)


def test_3000_failure_cannot_mutate_task_pool(tmp_path, monkeypatch):
    daemon = AceDaemon(tmp_path, minimal_config(tmp_path))
    before = sorted(str(path) for path in daemon.task_pool.pool_dir.rglob("*"))
    monkeypatch.setattr(daemon, "_probe_provider", lambda port: {"port": port, "status": "unavailable"})
    result = daemon.check_provider_health(3000)
    after = sorted(str(path) for path in daemon.task_pool.pool_dir.rglob("*"))
    assert result["status"] == "unavailable"
    assert result["side_effects"] == []
    assert after == before
```

Use the repository's actual health/configuration helpers if they already exist; do not add a second HTTP client dependency.

- [ ] **Step 2: Run the provider boundary tests and verify failure**

Run:

```powershell
python -m pytest -q ops/test_provider_health_boundary.py
```

Expected: FAIL because there is no independent 3000/3002 result contract or side-effect assertion.

- [ ] **Step 3: Implement the read-only provider health adapter**

Add the smallest existing-style helper, preferably in `ace_daemon.py` if no provider health module exists, that probes each configured port independently and returns `{port, status, endpoint, error_class, side_effects}`. Catch connection, timeout, HTTP 5xx, and malformed response errors as `status="unavailable"`; do not create observations that look like tasks and do not call TaskPool mutation methods.

- [ ] **Step 4: Wire health information into daemon state without changing task state**

Store the per-port result only in daemon health/state output. A failed 3000 probe must not fall back to 3002, must not be treated as a successful model route, and must not alter admission, claim, lease, approval, or archive state.

- [ ] **Step 5: Run focused tests and live probes**

Run:

```powershell
python -m pytest -q ops/test_provider_health_boundary.py ops/test_runtime_authority_audit.py
```

Then run the existing PowerShell probes for `3000` and `3002` separately and record the actual `/health`, `/health/liveliness`, `/v1/models`, and `/v1/responses` results. Expected: each port has independent evidence; a 3000 failure remains visible and has zero ACE task side effects.

- [ ] **Step 6: Commit the provider boundary**

```powershell
git add ace_daemon.py ops/test_provider_health_boundary.py ops/test_runtime_authority_audit.py
git commit -m "feat: isolate provider health from task mutation"
```

### Task 4: Remove the public test admission bypass

**Files:**
- Modify: `C:\tmp\ace_core\core\task.py`
- Modify: `C:\tmp\ace_core\ops\test_task_admission.py`
- Modify: affected test fixtures under `C:\tmp\ace_core\ops\`
- Test: `C:\tmp\ace_core\ops\test_task_admission.py`

- [ ] **Step 1: Write the failing API-boundary test**

Add a test proving that `TaskPool.__init__` no longer accepts `allow_test_creator_without_admission`, and that `creator="test"` without a valid admission fails exactly like every other creator.

```python
def test_task_pool_does_not_expose_public_admission_bypass(tmp_path):
    with pytest.raises(TypeError):
        TaskPool(str(tmp_path), allow_test_creator_without_admission=True)
    pool = TaskPool(str(tmp_path / "strict"))
    with pytest.raises(ValueError, match="task_admission_required"):
        pool.create_task("test task", creator="test")
```

- [ ] **Step 2: Run the admission tests and verify failure**

Run:

```powershell
python -m pytest -q ops/test_task_admission.py
```

Expected: FAIL because the public keyword still exists.

- [ ] **Step 3: Replace the flag with a test-only construction boundary**

Remove the public constructor flag and unconditional creator-based bypass. Add a test-only factory in the existing test support location, or a private capability object that cannot be created by production configuration. The factory must construct a TaskPool with an explicit internal test capability and must be imported only from test modules.

The production path must remain equivalent to:

```python
admission = validate_admission(admission)
```

No environment variable, config key, creator string, or CLI option may enable missing admission.

- [ ] **Step 4: Migrate test fixtures to the test-only boundary**

Replace every `allow_test_creator_without_admission=True` use with the test factory or with valid admission metadata. Search the whole repository and fail the test if the public flag string remains outside an intentional migration assertion.

- [ ] **Step 5: Run focused and adjacent admission tests**

Run:

```powershell
python -m pytest -q ops/test_task_admission.py ops/test_24h_runtime_mainline.py ops/test_model_pool_mainline.py ops/test_daily_growth.py ops/test_daily_shift.py ops/test_model_work_discovery.py
```

Expected: PASS, with production-style calls always requiring admission and test fixtures using an explicit test-only boundary.

- [ ] **Step 6: Commit the test boundary**

```powershell
git add core/task.py ops/test_task_admission.py ops/test_24h_runtime_mainline.py ops/test_model_pool_mainline.py ops/test_daily_growth.py ops/test_daily_shift.py ops/test_model_work_discovery.py
 git commit -m "refactor: remove public task admission bypass"
```

### Task 5: Synchronize runtime state documentation and execute regression

**Files:**
- Modify: `C:\tmp\ace_core\README.md`
- Modify: `C:\tmp\ace_core\CURRENT_STATE.md`
- Modify: `C:\tmp\ace_core\research\runtime_authority_write_entry_matrix.v1.md`
- Modify: `C:\tmp\ace_core\research\runtime_authority_audit.v1.md`

- [ ] **Step 1: Add documentation tests or static assertions first**

Add assertions to the existing authority audit test that current docs do not advertise old CLI commands as runnable, identify `AceDaemon` as the heartbeat owner, state that 3000 and 3002 are independent, and state that test admission cannot be enabled by production configuration.

- [ ] **Step 2: Run the documentation assertions and verify failure**

Run:

```powershell
python -m pytest -q ops/test_runtime_authority_audit.py
```

Expected: FAIL where README or CURRENT_STATE still presents legacy runtime behavior as current.

- [ ] **Step 3: Update the current-state documents**

Describe only verified behavior: modern `ace daemon/runtime` entry points, fail-closed legacy paths, daemon-owned heartbeat, independent 3000/3002 health evidence, and strict admission. Preserve unresolved external-service diagnostics as unresolved instead of describing 3000 as healthy.

- [ ] **Step 4: Run the complete verification suite**

Run:

```powershell
python -m pytest -q
```

Then run the repository's available lint and type-check commands discovered from its configuration. If no project command exists, report that explicitly and run the applicable Python syntax/import checks instead.

Expected: all tests pass; no test imports `nodes.*`; no public admission bypass remains; old runtime modules are fail-closed; heartbeat has one production owner; 3000 and 3002 evidence remains separate.

- [ ] **Step 5: Commit the verified closure**

```powershell
git add README.md CURRENT_STATE.md research/runtime_authority_write_entry_matrix.v1.md research/runtime_authority_audit.v1.md ops/test_runtime_authority_audit.py
git commit -m "docs: record closed runtime authority boundaries"
```

## Self-Review Checklist

- Legacy Scheduler/TaskQueue are covered by Task 1, including import, construction, and mutation boundaries.
- Historical heartbeat and daemon owner are covered by Task 2, including no-loop and no-write behavior.
- Independent 3000/3002 health evidence and zero TaskPool side effects are covered by Task 3.
- Public test bypass removal and fixture migration are covered by Task 4.
- Documentation and full regression are covered by Task 5.
- All production changes begin with a failing test and use existing Python/pytest conventions.
- No step depends on 3002 success to infer 3000 health.
