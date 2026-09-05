# Remote Git Recovery Root Protocol v1

## Scope

This protocol makes a narrow claim: a configured remote branch is a recovery
root only for the committed content that is present at that remote tip. It is
not a second ACE Runtime, TaskPool, Scheduler, Router, owner registry, or
admission system.

The read-only auditor is `ops/remote_git_root_audit.py`. It does not fetch,
stage, commit, push, repair, or change Runtime state. Its output is evidence
for a human/main steward and must not be reinterpreted as a Runtime command.

## States

| State | Meaning | Recovery claim |
| --- | --- | --- |
| `MATCH_CLEAN` | local branch tip equals remote branch tip and the worktree is clean | committed checkout is recoverable from the remote tip |
| `MATCH_DIRTY` | branch tips match but local uncommitted entries exist | only the committed subset is recoverable; local evidence is not in the root |
| `DRIFT` | reachable remote branch tip differs from local tip | no complete root claim; review divergence before sync |
| `REMOTE_BRANCH_MISSING` | remote is reachable but the selected branch is absent | no root claim for that branch |
| `REMOTE_UNAVAILABLE` | local remote lookup failed | no root claim |
| `NO_REMOTE` / `DETACHED` | no stable remote/branch identity | fail closed |

## Current bounded observation (2026-09-05)

The public GitHub API lists nine repositories under `zhangapple21-web`:
`-`, `ace_core`, `mine-seed`, `R1`, `R1_continuity_archive`,
`r1-archaeology`, `r1-open-source-seed`, `coze-assets`, and `aum-protocol`.
The local checkout scan found six matching owned repositories: `ace_core`,
`mine-seed`, `R1`, `r1-archaeology`, `r1-open-source-seed`, and `-` (checked
out locally as `ace_video_kingdom_assets_public`). The other three are not
locally present in this scan; this is a missing local mirror, not proof that
the remotes are unused.

For the sampled owned checkouts, `mine-seed`, `R1`, `r1-archaeology`,
`r1-open-source-seed`, and `-` matched their remote `main` tips. Before this
audit, `ace_core` was `DRIFT` (`local=9095f0c`, remote=`22f4f8f`); the five
already-reviewed commits were pushed to `origin/main`, which now matches
`9095f0c`. The checkout still has substantial local uncommitted material, so
it is now `MATCH_DIRTY`: the committed root is recoverable, but the current
working state is still only partially represented remotely.

## Authority boundary

Remote Git can restore source, contracts, and deliberately committed
provenance. It cannot by itself establish current TaskPool state, owner/lease
validity, heartbeat thread attribution, gateway health, or production
authorization. Those remain runtime/evidence questions and stay fail-closed
when unproven.

No commit, push, deletion, merge, or daemon restart is implied by this
protocol. A future push must use an explicit, reviewed source pack; never use
`git add .` on a dirty ACE checkout.

## 2026-09-05 remote-root recheck

`ops/remote_recovery_inventory.py` rechecked all nine public remote `main`
refs associated with `zhangapple21-web`. Every remote was reachable. The
current observations are persisted in
`research/remote_recovery_inventory_20260905.json`:

- `ace_core` and `mine-seed`: `MATCH_DIRTY` (the committed tip is recoverable;
  uncommitted local material is not).
- `R1`, `r1-archaeology`, and `r1-open-source-seed`: `MATCH_CLEAN`.
- `-`, `R1_continuity_archive`, `coze-assets`, and `aum-protocol`:
  `REMOTE_ONLY` because no local mirror was present in this scan.

Remote visibility and branch protection remain separate control-plane fields.
For `coze-assets`, public visibility was previously observed and a fresh
remote-tip probe still reaches `main`; protection is intentionally retained as
`UNKNOWN_CONTROL_PLANE` until an authenticated control-plane read confirms it.
The inventory tool does not infer protection from successful Git transport and
does not promote remote metadata into ACE Runtime authority.
