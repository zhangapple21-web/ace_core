# Remote Git Root Security Audit — 2026-09-05

## Verdict

`HIGH_PRIORITY_REMEDIATION_REQUIRED`

The remote-recovery boundary is observable, but the repository that the local
architecture describes as a private credential store is currently public.
This is a security boundary failure, not a reason to widen ACE Runtime
authority.

## FACT

- GitHub's unauthenticated repository metadata for
  `zhangapple21-web/coze-assets` currently reports `private=false` and
  `visibility=public`.
- Its `main` branch is not protected (`protected=false`) and the latest
  observed tip is `6acbaff8f3c57ea87b6bea35354e8cda7d0ebfd3`.
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

## Required owner action (not executed here)

1. Confirm the intended visibility with the repository owner.
2. If it is a credential store, make it private and protect `main` through the
   GitHub control plane; do not rely on a local `.gitignore`.
3. Treat every credential-shaped value ever committed there as compromised
   until independently verified otherwise: revoke/rotate, then scan history
   and forks with the appropriate GitHub security tooling.
4. Replace public operational files with redacted templates only after the
   rotation boundary is complete.
5. Re-run `ops/remote_git_root_audit.py` and record the new remote tip; do not
   claim recovery completeness while local dirty or divergent material remains.

No deletion, visibility change, rotation, push, or account action was taken by
this audit. The finding must not be converted into an ACE TaskPool command by
parsing this document.
