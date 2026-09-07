# ACE Open-Source Candidate Triage — 2026-08-26

## Method and boundary

This is a read-only design review. Repository identity and public metadata were
checked through the GitHub API on 2026-08-26; star counts are observations, not
quality evidence. Nothing here is installed, invoked, added to the Runtime, or
added to the automatic learning backlog. ACE's sole daily-learning path remains
the existing one-item governed backlog.

## Decisions

| Candidate | Verified identity | Decision | ACE lesson or reason |
| --- | --- | --- | --- |
| OpenClaw | `openclaw/openclaw` | REJECT | A broad personal-assistant runtime would duplicate ACE's daemon and expand execution authority before continuity controls are complete. |
| AutoGPT | `Significant-Gravitas/AutoGPT` | REJECT | Generic autonomous task decomposition is already represented by ACE TaskPool/admission; importing its autonomy model would weaken ACE's evidence-first work conservation. |
| n8n | `n8n-io/n8n` | ADAPT LATER | Its trigger, retry, and visual workflow concepts are useful references, but it must not become a second scheduler. Revisit only after `runtime_claim` establishes at-most-once execution. |
| Dify | `langgenius/dify` | REJECT | A full AI application platform is out of scope. At most, its human-review UI patterns can be studied later; no platform dependency is justified. |
| OpenHands / former OpenDevin | canonical repository resolves to `OpenHands/OpenHands` | REJECT | This is a software-engineering agent, not a reliable basis for ACE continuity or market research. The claimed “memory capsule” feature was not treated as verified. |
| Codex Harness | no confirmed official OpenAI repository under that exact name | REJECT AS CLAIM | Do not create a learning task from an unverified name. A future candidate needs an official canonical URL and a scoped engineering question. |
| LocalLLM Runtime (LLR) | no canonical GitHub repository confirmed for the supplied name | REJECT AS CLAIM | Hardware/local-inference ideas are not a current bottleneck; a source identity is required before any archaeology. |
| llama.cpp | `ggml-org/llama.cpp` | DEFER | A valid local-inference reference, but provider resilience and data correctness are the current constraints. Revisit only with hardware, model, licensing, latency, and operational-owner evidence. |
| OpenBB | `OpenBB-finance/OpenBB` | ADAPT LATER | Study source-contract and analyst-research organization only after the A-share source archaeology closes. It cannot bypass ACE lineage, freshness, coverage, completeness, or independent-consistency gates. |
| Qlib | `microsoft/qlib` | ALREADY QUEUED | Retain the existing research-only catalogue item: absorb experiment/data/feature version records after reliable data exists. |
| vn.py Alpha | `vnpy/vnpy` | ALREADY QUEUED | Retain only offline research organization. Never adopt Gateway, broker, order, or live-trading components. |
| Alphalens Reloaded | `stefan-jansen/alphalens-reloaded` | ALREADY QUEUED | Retain IC, quantile, turnover, decay, and out-of-sample reporting concepts. |
| Backtrader / Zipline | `mementum/backtrader`; `quantopian/zipline` | REDUNDANT | Event-driven replay concepts are useful, but Qlib plus ACE's frozen-case replay work cover the near-term research need. |
| codebase-memory-mcp | `DeusData/codebase-memory-mcp` | DEFER | Persistent code-graph retrieval is interesting, but adding another MCP is a continuity/attack-surface decision. Consider only after an explicit local benchmark against `rg`, current repository maps, and memory retrieval. |

## Ordered learning plan

1. Finish the independent A-share `quote / 1m / index` source archaeology and
   the local `runtime_claim` continuity boundary. These are prerequisites, not
   items to be bypassed by an external platform.
2. Let the existing one-at-a-time backlog complete its Qlib, vn.py, Alphalens,
   and QuantaAlpha archaeology. Each needs a repository-specific evidence
   report before any classification changes.
3. Create a separate OpenBB source-contract study only if the source
   archaeology produces a concrete adapter question. Its outcome is allowed to
   be `REJECT` or `RESEARCH_ONLY`; it cannot alter the production matrix.
4. Revisit n8n concepts only as documentation for scheduling/recovery after
   `runtime_claim` has tests and an owning daemon integration. Do not deploy
   n8n or create a second scheduler.

## Explicit non-actions

- no package installation or external repository clone;
- no runtime, data-health, Advisor, Risk, Telegram, broker, or automatic
  recommendation change;
- no new background Worker or queue item created from this catalogue;
- no claim that a repository's popularity, README, or SDK name supplies an
  independent market-data source.
