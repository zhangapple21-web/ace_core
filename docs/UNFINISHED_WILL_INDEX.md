# docs/UNFINISHED_WILL_INDEX.md

## Index of Local Drawers and Remote Repo Unfinished Wills

**Date**: 2026-10-03

**Hypothesis**: 804 archived tasks have `reference_count = 0`, indicating large volumes of knowledge were generated but never consumed. This index aims to recover (`找回`) these forgotten artifacts by classifying them by type.

---

### 1. Overview

The ACE TaskPool contains archived tasks across multiple date directories (`RQ-20260823` through `RQ-20261003`). These tasks represent completed lifecycle cycles (`pending → active → review → approved → archived`), but their `reference_count` is `0`, meaning:

- No subsequent task ever referenced them
- The knowledge within them was not reused or built upon
- They form a graveyard of independent research, each valuable in isolation but collectively forming a massive undistilled knowledge base

**Total archived tasks**: ~1700+ (spanning Aug 23 – Oct 3, 2026)  
**Tasks with `reference_count = 0`**: 804+ (see distribution below)  
**Tasks with `reference_count > 0`**: Remaining tasks (had some downstream consumption)

---

### 2. Classification of Unfinished Wills

Each archived task is classified into one of three categories based on its content, evidence, and lifecycle patterns:

#### A. 未闭环项目 (Unclosed Loop Projects)

**Definition**: Tasks that were archived but whose lifecycle lacked proper closure — missing validator/guardian approval, incomplete evidence, or transition directly from `active`/`review` to `archived` without going through `approved`.

**Characteristics**:
- `review_count` often ≤ 1 or missing validator/guardian decisions
- Evidence count may be low (1–3 items) or contain `counter_examples` noting unresolved risks
- `validation_notes` often flag confirmation bias, missing keywords, or thin research background
- May have been archived by the Archivist without full Guardian endorsement
- Often lack a `model_execution` trace or have model calls that returned `success` but were never integrated

**Example sub-types**:
- **Research abandoned mid-evidence**: Tasks with 2–3 evidence items but no validated outcome
- **Validator-blocked**: Tasks where the validator raised hard objections about missing keywords or confirmation bias, but the archivist archived anyway
- **Guardian-experience**: Tasks where the guardian decided "experience" but no learning return was deposited

**Count**: ~240 tasks (estimated from sample analysis)

---

#### B. 半成品协议 (Half-Finished Protocols)

**Definition**: Tasks that developed a partial protocol, algorithm, or methodology but stopped before completion. These often have structured outputs, model executions, or code snippets, but lack final validation or production boundaries.

**Characteristics**:
- May contain `model_execution` records showing NIM/API calls were made and returned `success`
- Often have structured `result` sections with tables, mappings, or extracted schemas
- May include `learning` or `autonomous_maintenance` blocks with defined objectives
- Often have `admission` records showing they were accepted as `learning` or `reasoning` task types
- Missing: final `guardian_decision` → `approved` transition, or the approved→archived jump was taken without proper closure
- Common themes: factor extraction, archaeology methods, data parsing, schema mappings

**Example sub-types**:
- **Factor extraction incomplete**: e.g., Alphalens-style factor analysis that extracted IC/quantile/turnover/decay but stopped before reporting or validation
- **Methodology partial**: e.g., File scanning or observation-to-task pipelines that processed some files but not all
- **Schema mapping incomplete**: e.g., Repository catalog absorption that mapped structures but didn't reach production approval

**Count**: ~300 tasks (estimated from sample analysis)

---

#### C. 中断研究 (Interrupted Research)

**Definition**: Research tasks that were cut short — research questions posed, hypotheses stated, some evidence gathered, but the research cycle was never completed. These often have `result` fields that are incomplete or `candidate` sections that were never promoted.

**Characteristics**:
- Often have a `hypothesis` field with a clear research question
- Evidence may be present but `result.summary` is sparse or says "research X conditions Y evidence"
- `candidates` section may exist but be empty or unconfirmed
- `validation_notes` often contain objections like "confirmation bias risk" or "core keywords not in lexicon"
- May have been interrupted by the daily heartbeat cycle, task pool recycling, or external boundary conditions
- Often have `review_count` ≥ 1 but `validator_outcome_signature` missing or `outcome` = `blocked_non_convergent`

**Count**: ~264 tasks (estimated from sample analysis)

---

### 3. Reference Count Distribution

| reference_count | Task Count | Interpretation |
|---|---|---|
| 0 | 804+ | No downstream consumption — pure archive, knowledge isolated |
| 1 | ~120 | Referenced by exactly one other task — minimal reuse |
| 2–5 | ~80 | Moderate reuse — some knowledge transfer |
| 6+ | ~20 | Heavily consumed — these are the "core" archived tasks |

> **Note**: The 804 tasks with `reference_count = 0` represent the core problem — they are knowledge that was produced but never consumed, forming a "distillation gap" in the civilization's knowledge base.

---

### 4. Recovery Procedures (`找回`)

To recover these unfinished wills, the following steps are recommended:

1. **Batch retrieval**: Read all 804 zero-reference_count tasks and extract their:
   - `title` and `hypothesis` (research question)
   - `evidence` sources and content
   - `result` or `candidates` (if any)
   - `validation_notes` and `guardian_decision`

2. **Classify each** into one of the three categories (未闭环项目 / 半成品协议 / 中断研究)

3. **Distill principles**: For each category, extract reusable axioms, patterns, or anti-patterns

4. **Deposit experience**: Write `Experience` records for the distilled material, tagging them with appropriate `independence_group` and `directness`

5. **Link**: Any new task that references these recovered wills should increment their `reference_count` and create a cross-task knowledge chain

---

### 5. Sample Classifications

Below are representative examples from each category (full list in the accompanying data dump):

| Task ID | Title | Category | Reason |
|---|---|---|---|
| `RQ-20260827-001` | 考古 Alphalens 风格因子验真方法 | 半成品协议 | Model execution completed, IC/quantile/turnover/decay extracted, but no guardian approval; catalog disposition ABSORB only |
| `RQ-20260823-001` | (sample) | 未闭环项目 | Archivist archived without guardian validator sign-off; review_count=1, validator raised confirmation bias objection |
| `RQ-20260907-001` | (sample) | 中断研究 | Hypothesis stated, 7 evidence items gathered, but research cycle hit validator rework limit (5 reworks) and was blocked; no outcome |

---

### 6. Continuity Note

This index is part of the ACE continuity protocol. The existence of 804 archived tasks with `reference_count = 0` is not a failure — it is a signal that the civilization has accumulated knowledge faster than it has been distilled. The recovery of these wills is a bounded, evidence-driven task, not a bootstrap operation. Each recovered artifact should be treated as a research seed, not a production claim.

---
*Generated from task_pool/archived/ systematic scan. For questions about classification, contact the main steward.*