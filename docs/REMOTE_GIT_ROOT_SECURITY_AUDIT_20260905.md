# Remote Git Root Security Audit — 2026-09-05

## Verdict

`HIGH_PRIORITY_REMEDIATION_REQUIRED`

This finding remains open after a fresh remote-tip recheck. The local system
has completed the read-only inventory and generated a replayable remediation
record, but no claim is made that GitHub visibility, branch protection, or
history rotation changed.

The remote-recovery boundary is observable, but the repository that the local
architecture describes as a private credential store is currently public.
This is a security boundary failure, not a reason to widen ACE Runtime
authority.

## FACT

- A fresh public remote-tip probe reaches `zhangapple21-web/coze-assets`
  `main` at `6acbaff8f3c57ea87b6bea35354e8cda7d0ebfd3`.
- The last authenticated control-plane observation still showed
  `private=false`/`visibility=public` and no classic branch protection. The
  current REST probe cannot re-confirm settings because its unauthenticated
  rate limit is exhausted; protection is therefore `UNKNOWN_CONTROL_PLANE`,
  not silently treated as absent or fixed.
- The public tree contains operationally sensitive-looking paths including
  `.env.tpl`, `05_TOOLS/miner/miner_env.sh`, `02_miner_config/miner_env.sh`,
  `05_TOOLS/secret_syncer.py`, and `05_TOOLS/miner/free_api.env.tpl`.
- A metadata-only content scan found secret-assignment names and token-shaped
  strings in the two public `miner_env.sh` files. Values were not printed or
  copied by this audit.
- The repository's latest observed commit message includes
  `SEC-001: ... fix SECRET.md tracking`, which is provenance, not proof that
  historical or current secrets are absent.

## UNKNOWN

- Whether any token-shaped value is live, revoked, synthetic, or already
  rotated.
- Whether sensitive values exist in older Git history, forks, caches, release
  artifacts, or GitHub Actions logs.
- Whether the intended security policy changed after the local architecture
  documents were written.

## Automated closure status

The system has performed the safe, evidence-preserving portion itself:

1. Enumerated all nine `zhangapple21-web` remote repositories returned by the
   GitHub repository listing, and rechecked every `main` tip with
   `git ls-remote`.
2. Added `ops/remote_recovery_inventory.py`, which records remote-only,
   match-clean, match-dirty, and drift states without fetching, staging,
   committing, pushing, or mutating ACE Runtime state.
3. Replayed the public `coze-assets` tip and recorded secret-shaped paths only
   as metadata; no secret value was read into the report.
4. Prepared a minimal `main-recovery-boundary` ruleset in the authenticated
   GitHub page, targeting the default branch with deletion and force-push
   blocking only. The final Create action was not evidenced as submitted in
   this run, so the ruleset is **not claimed as active**.

The remaining control-plane mutation is kept as a machine-visible
`UNKNOWN_CONTROL_PLANE` state in
`research/remote_recovery_inventory_20260905.json`. This is an automated
fail-closed state, not an instruction that the user must perform routine
integration. When the authenticated control surface is available, the same
bounded action can be replayed and then independently rechecked.

No deletion, visibility change, credential rotation, or default-branch rewrite
is claimed. This report is evidence only and must not be converted into an
ACE TaskPool command by parsing it.
