# A_SHARE_DATA_SUPPLY_DECISION_001

**Status:** `DATA_SUPPLY_BLOCKER_OPEN`  
**Decision time:** 2026-08-27  
**Scope:** evidence-led data-supply continuity; no daemon integration, no Advisor/Risk/TG activation.

## Persisted capability truth

| Operation | Observed usable sources | Current limitation | Role |
| --- | --- | --- | --- |
| quote | pytdx, Sina | multi-source admission is still incomplete across the full contract | research / controlled cross-check |
| minute 1m | pytdx, Sina | reliability and coverage remain insufficient for the complete Phase 2 contract | research / controlled cross-check |
| index | pytdx, Sina | stable independent cross-validation not yet proven at contract level | research / controlled cross-check |
| daily K | pytdx, BaoStock | freshness and cross-source consistency gaps | historical / cross-check |
| minute 5m | pytdx, BaoStock | freshness and cross-source consistency gaps | historical / cross-check |

Evidence source: `06_RUNTIME/ace/data/stock_data_evidence/stock_data_benchmark_latest.json`, generated 2026-08-27T09:35:06+08:00.

## Source decisions

| Source / group | Disposition | Evidence-led reason |
| --- | --- | --- |
| pytdx / `tdx_tcp_protocol` | `CROSS_CHECK_ONLY` | broad operation coverage, but its benchmark coverage is 0.5 and its health score alone does not constitute independent admission. |
| Sina / `sina_public_http` | `CROSS_CHECK_ONLY` | quote, 1m and index were observed, but it has only one public source group and cannot independently close the full Phase 2 contract. |
| BaoStock / `baostock_tcp` | `CROSS_CHECK_ONLY` | useful daily/5m historical comparison; it is not a live 1m answer. |
| Tencent / `tencent_public_http` | `REJECT_FOR_PHASE_2` | observed 1m and 5m coverage were zero in the current benchmark. |
| AKShare / `eastmoney_public_http` | `REJECT_FOR_PHASE_2` | current indirect benchmark failed all sampled operations. |
| Direct EastMoney isolation | `RESEARCH_ONLY` | isolated quote 8/8 and index 2/2 succeeded, but 1m was only 2/8 (0.25) with repeated `RemoteDisconnected`; no production wiring. |
| FinShare / `UNVERIFIED_AGGREGATE` | `RESEARCH_ONLY` | upstream lineage is not observable, so it cannot count as an independent source. |

## Supply contract before production consideration

An authorized candidate must provide all of the following before any adapter is considered:

1. `quote`, `minute_kline_1m`, and `index`, with source timestamps, coverage and required field completeness.
2. Observable upstream identity and an independence group distinct from the existing source used for cross-checking.
3. Multi-symbol, multi-window, multi-day isolated benchmark evidence with each required quality dimension meeting the existing gate.
4. Cross-source agreement evidence retained alongside each snapshot and feature calculation.
5. A lawful owner-authorized account, credential/config declaration, and cost decision. ACE must not buy, sign up for, or infer this authority.

## Continuity while the blocker is open

The unresolved dependency is not reset every day. Daily Shift must carry:

- `DATA_SUPPLY_BLOCKER_OPEN`;
- last benchmark timestamp and precise failed operation;
- the next scheduled proof point;
- research that remains valid without live recommendation: historical replay, technical-feature research, source-comparison and data-quality work.

`Phase 2 = NOT_ADMITTED`, `Finance = DEGRADED`, `Advisor = BLOCKED`, `Risk = NOT_READY`, and `Owner TG = OFF` remain unchanged. No degraded research result may be presented as a live recommendation.

## Owner decision required

No active authorized paid/vendor source was found in current local config or environment-name archaeology. This means **no evidence of an enabled credential**, not proof that the owner has no account. The next material step is an owner-authorized provider choice or explicit existing provider declaration; only then can ACE perform an isolated benchmark under the unchanged admission gate.
