# ACE 24H Host And Resource Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy one durable Windows-hosted ACE daemon and prove that its required runtime resources can be backed up, restored, and used after restart.

**Architecture:** Windows Task Scheduler owns one `ACE_Daemon_Boot` task that starts `python ace.py daemon --serve` in `C:\tmp\ace_core`. The daemon performs periodic, manifest-backed data snapshots through a narrow backup helper; snapshots are restored only into isolated temporary directories for validation. Observation signatures prevent identical persistent states from being appended each daemon cycle while retaining recovery generations.

**Tech Stack:** Python 3.11, Windows Task Scheduler PowerShell cmdlets, JSON/JSONL runtime state, pytest.

---

### Task 1: Converge task-scheduler ownership

**Files:**
- Modify: `ops/install_tasks.ps1`
- Modify: `ops/install_tasks.py`
- Test: `ops/test_24h_runtime_mainline.py`

- [ ] Add a structural test that asserts the installer defines only `ACE_Daemon_Boot` as an ACE production task and uses `ace.py daemon --serve`.
- [ ] Run the structural test and verify it fails against the multi-task installers.
- [ ] Make each installer install/check/remove only `ACE_Daemon_Boot`, use the active Python executable, set the current repository as working directory, run under the interactive host user, use unlimited execution time, and configure restart-on-failure.
- [ ] Disable, without deleting, legacy `ACE_Heartbeat` and `ACE_DailyDiscovery`; register the current-workspace boot task; start it once and inspect action, account, restart settings, and running process.
- [ ] Run the structural test and the focused host suite.

### Task 2: Add periodic snapshot and isolated restore verification

**Files:**
- Modify: `ops/backup_data.py`
- Modify: `ace_daemon.py`
- Test: `ops/test_24h_runtime_mainline.py`

- [ ] Add a failing test that creates representative runtime files and asserts a backup manifest contains task pool, daily-learning state, discovery state, memory, knowledge, daemon state, and runtime metadata.
- [ ] Add a failing test that restores a snapshot into a temporary target and validates the manifest and copied paths without overwriting production data.
- [ ] Extend the backup helper with explicit source entries, secret/token exclusion, a versioned manifest with checksums, and a restore-to-target validation operation.
- [ ] Add a daemon-owned periodic backup call controlled by a conservative interval and record the last successful manifest in daemon state.
- [ ] Run focused backup and daemon tests, then perform a real isolated restore rehearsal from a generated snapshot.

### Task 3: Make persistent observations state-idempotent

**Files:**
- Modify: `core/observation.py`
- Test: `ops/test_24h_runtime_mainline.py`

- [ ] Add a failing test recording the same observation signature twice and assert only one active record is appended.
- [ ] Add a failing recovery test showing a resolved signature can produce a new generation when it recurs.
- [ ] Persist signature lifecycle state (`active`, `recovered`, `cooldown`) next to observation records and make `record()` return the active observation for an identical active signature.
- [ ] Run observer-specific and full focused runtime tests.

### Task 4: Repair narrow runtime continuity links and audit sources

**Files:**
- Modify: `ace_daemon.py`
- Test: `ops/test_24h_runtime_mainline.py`

- [ ] Add a failing test for fragment backlog extraction from the actual `FragmentIndex.get_stats()` shape.
- [ ] Correct the daemon's fragment backlog read without changing Discovery policy.
- [ ] Search workspace, archives, backups, and configured sibling repositories for Telegram raw exports, cursors, parsers, and indexes. If none exist, record a non-sensitive `TELEGRAM_FAVORITES_SOURCE_NOT_FOUND` observation; do not create a reader.
- [ ] Run the resource audit and focused suite.

### Task 5: Verify the deployed runtime and report readiness

**Files:**
- Verify only: Windows Task Scheduler configuration, `06_RUNTIME/ace/data`, `task_pool`, `09_KNOWLEDGE`, backup manifest, Git remote

- [ ] Observe multiple daemon cycles through the installed task and verify heartbeat advancement, no duplicate process, no stale daemon lock, no unleased active tasks, and no forbidden automation switches.
- [ ] Stop the running daemon process once and verify Task Scheduler restart behavior; then verify it resumes normal heartbeat updates.
- [ ] Produce the resource continuity matrix with existence, readability, real data, main-chain reference, and recoverability.
- [ ] Declare `24H READY` only if host, resources, continuity, and persistent runtime evidence are all present.
