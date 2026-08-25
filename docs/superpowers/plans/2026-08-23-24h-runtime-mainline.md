# ACE 24H Runtime Mainline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect ACE's existing autonomy components into one startable, persistent, recoverable `AceDaemon` production chain.

**Architecture:** Remove the daemon's dependency on the legacy Scheduler and make `AceDaemon` the only TaskPool lifecycle owner. Add durable file-backed task leases and atomic state commits, then wire failure classification, daily learning, knowledge governance, and local market/data gates into its lifecycle without invoking external production effects.

**Tech Stack:** Python standard library, existing ACE core task/discovery/governance/learning/data-health modules, Windows Task Scheduler configuration.

---

## File Structure

- Modify `ace_daemon.py`: direct runtime context, startup recovery, lifecycle claim/failure/governance/learning/data gate orchestration.
- Modify `ace.py`: explicit `daemon --serve` command behavior and one-shot separation.
- Modify `ops/install_tasks.py` and `ops/install_tasks.ps1`: explicit persistent boot command and execution policy.
- Modify `core/task.py`: durable task metadata, lock, atomic commits, claim/renew/reclaim/failure/block APIs.
- Modify `core/task_roles.py`: TaskPool claim/renew/failure integration.
- Modify `core/daily_learning.py`: resumable daily checkpoints and idempotent evidence/deposition stages.
- Modify `core/observation_to_task.py` and `core/stock_discovery_sources.py`: source-specific task worthiness for qualifying medium events.
- Modify `core/stock_data_reliability.py`: local runtime decision API with no network execution.
- Modify `ops/clear_review_queue.py`, `ops/auto_archive_approved.py`, `ops/cleanup_expired_tasks.py`: read-only or formal-lifecycle delegation.
- Create `ops/test_24h_runtime_mainline.py`: full temporary-directory runtime safety regression.

### Task 1: Make the Daemon Independently Importable and Bootable

**Files:**
- Modify: `ace_daemon.py`
- Modify: `ace.py`
- Modify: `ops/install_tasks.py`
- Modify: `ops/install_tasks.ps1`
- Test: `ops/test_24h_runtime_mainline.py`

- [ ] Add a failing test that imports `ace_daemon`, constructs `AceDaemon` with a temporary base directory, and asserts that `run_daemon` is available without importing `core.scheduler`.
- [ ] Run `python ops/test_24h_runtime_mainline.py` and verify the current missing `nodes` import failure.
- [ ] Remove `Scheduler` construction/import from `AceDaemon`; initialize only the daemon-owned dependencies directly.
- [ ] Keep `ace.py run` as the legacy Scheduler entrypoint, but route `ace.py daemon --serve` only to `AceDaemon.run_daemon()`.
- [ ] Update both Windows installers to invoke `python ace.py daemon --serve`; remove the two-hour execution limit and configure restart-on-failure behavior.
- [ ] Run the isolated test and `python -c "import ace_daemon"`; expect successful import.

### Task 2: Add Durable Atomic Task Ownership

**Files:**
- Modify: `core/task.py`
- Test: `ops/test_24h_runtime_mainline.py`

- [ ] Add failing tests for two simultaneous consumers, lease renewal, stale lease reclamation, and a simulated interruption before old-state cleanup.
- [ ] Run the isolated test and verify duplicate claim/current delete-before-write behavior fails the assertions.
- [ ] Extend `Task` serialization with `lease_owner`, `lease_expires_at`, `claim_id`, `fencing_token`, and `block_type`.
- [ ] Add TaskPool transaction locking using a lock file created exclusively with a bounded timeout.
- [ ] Implement `claim_task(task_id, owner, lease_seconds)`, `renew_lease(task_id, owner, claim_id, lease_seconds)`, and `reclaim_stale_leases(now)`.
- [ ] Replace delete-then-write transitions with write-temp, fsync, atomic replace, then remove the prior state copy only after the replacement is durable. Maintain a recovery scan for duplicate state copies after interruption.
- [ ] Run the ownership tests; assert exactly one consumer obtains a claim and stale work returns to pending/retryable state.

### Task 3: Integrate Claim, Block, Failure, and Restart Semantics

**Files:**
- Modify: `core/task_roles.py`
- Modify: `ace_daemon.py`
- Modify: `core/task.py`
- Test: `ops/test_24h_runtime_mainline.py`

- [ ] Add failing tests for external-condition blocks remaining blocked, retryable worker errors reaching graveyard after bounded attempts, and restart recovery preserving a valid lease while reclaiming an expired lease.
- [ ] Implement role claim through `TaskPool.claim_task()` only; renew the lease before/after task work and require claim credentials for active task transitions.
- [ ] Implement failure classification: retryable -> delayed pending; credential/permission -> `manual_gate_blocked`; external condition -> `external_condition_blocked`; permanent -> graveyard.
- [ ] Restrict automatic unblock to `dependency_blocked` tasks with satisfied dependencies.
- [ ] Invoke lease reclaim and pending archive/deposition compensation at daemon startup and every lifecycle round.
- [ ] Run failure/restart tests and assert no exception is only logged without a task outcome.

### Task 4: Wire Formal Governance and Resumable Daily Learning

**Files:**
- Modify: `ace_daemon.py`
- Modify: `core/daily_learning.py`
- Test: `ops/test_24h_runtime_mainline.py`
- Test: `ops/test_daily_autonomous_learning.py`

- [ ] Add failing tests proving DailyLearningLoop runs once on an idle runtime day, does not run while higher-priority work exists, and resumes an interrupted daily checkpoint without duplicate evidence or deposition.
- [ ] Assemble `DailyLearningLoop` in `AceDaemon` with existing TaskPool, converter, registry, governor, lifecycle, archivist, and deposition components.
- [ ] Add checkpoint stages `candidate_selected`, `evidence_registered`, `governed`, `archived`, `deposited`, and `terminal` to the existing daily result directory; resume each stage from persisted identifiers and hashes.
- [ ] Route learning adoption only through `KnowledgeGovernor`; record Validator/Guardian outputs as workflow evidence, not adoption.
- [ ] Ensure normal daemon archive/deposition creates a compensatable pending-deposition marker before archive and clears it only after successful deposition.
- [ ] Run daily-learning and runtime tests; expect same-day idempotency and no duplicated registry/deposition output.

### Task 5: Add Local Data-Health and Source-Worthiness Decisions

**Files:**
- Modify: `core/stock_data_reliability.py`
- Modify: `ace_daemon.py`
- Modify: `core/observation_to_task.py`
- Modify: `core/stock_discovery_sources.py`
- Test: `ops/test_24h_runtime_mainline.py`
- Test: `ops/test_stock_data_reliability.py`

- [ ] Add failing tests showing a market-tagged task cannot be claimed unless the injected policy is `READY`, while non-market research remains claimable for `MARKET_CLOSED` and `STALE`.
- [ ] Add a no-network runtime decision method returning `MARKET_CLOSED`, `READY`, `DEGRADED`, `CONFLICT`, `STALE`, or `UNAVAILABLE` from existing benchmark evidence and time context.
- [ ] Apply the decision at claim time, not merely during discovery.
- [ ] Add source-specific `task_worthy` metadata for known valuable medium-severity stock discovery events; converter accepts only that explicit upgrade, preserving the general high-severity threshold.
- [ ] Run stock health and mainline tests; assert no real data client is called.

### Task 6: Retire TaskPool Bypass Consumers and Fix Boot Resilience

**Files:**
- Modify: `ops/clear_review_queue.py`
- Modify: `ops/auto_archive_approved.py`
- Modify: `ops/cleanup_expired_tasks.py`
- Modify: `ops/install_tasks.py`
- Modify: `ops/install_tasks.ps1`
- Test: `ops/test_24h_runtime_mainline.py`

- [ ] Add static tests ensuring these scripts neither call `move_task` for production transitions nor delete live TaskPool task files.
- [ ] Convert review/archive scripts to diagnostics that report candidate ids and instruct the daemon lifecycle to process them; retain their files and command names for compatibility.
- [ ] Restrict cleanup to terminal artifacts confirmed unreferenced by archival/deposition records; it must never change pending/active/review/approved work.
- [ ] Add Task Scheduler failure restart configuration and explicit service-style daemon command verification.
- [ ] Run static and lifecycle tests; expect no direct bypass state transitions.

### Task 7: Make the Actual Router Explicit and Perform Reverse Audit

**Files:**
- Modify: `ace_daemon.py`
- Modify: `core/miner_pool/__init__.py`
- Modify: `04_PROTOCOLS/local_miner.py`
- Modify: `04_PROTOCOLS/awareness_loop.py`
- Test: `ops/test_24h_runtime_mainline.py`

- [ ] Add tests asserting daemon task roles call only the selected runtime routing adapter and that compatibility routers do not create or claim TaskPool tasks.
- [ ] Add an explicit daemon role routing adapter mapping strategic reasoning, execution, Free Zone fallback, and FA quality gate to production profiles without requesting providers during tests.
- [ ] Mark unused miner-pool and protocol consumer entrypoints compatibility-only through exported metadata and prevent them from mutating TaskPool unless explicitly invoked in compatibility mode.
- [ ] Run a reverse-audit test that traces boot -> daemon -> discovery -> claim -> worker -> validation -> governance -> archive -> daily learning -> restart through injected deterministic fixtures.
- [ ] Run all existing isolated regressions, compilation, diff check, and the new mainline test. Do not commit.

## Self-Review

- Clean daemon startup and persistent boot path: Task 1 and Task 6.
- Atomic ownership, transition safety, lease renewal and stale recovery: Task 2.
- Retry, block types, graveyard, restart behavior: Task 3.
- Daily Learning integration, governance admission, interrupted recovery and deposition compensation: Task 4.
- Data health gate and medium discovery worthiness: Task 5.
- Bypass consumer removal by compatibility delegation: Task 6.
- One actual routing chain and reverse audit: Task 7.
- Production safety: all tests use temporary directories and injected fixtures; no live data/recommendation/notification/push behavior is enabled.
