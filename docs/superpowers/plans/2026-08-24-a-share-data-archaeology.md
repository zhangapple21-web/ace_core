# A-Share Data Archaeology Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing stock-data reliability layer with auditable A-share candidate lineage, repeatable no-credential benchmarks, a capability matrix, and a bypass audit without enabling production market analysis.

**Architecture:** Retain `core.stock_data_reliability.StockDataBenchmark`, `evaluate_health`, and `DataQualityProtocol` as the only runtime reliability mechanism. Add registry-backed metadata and operation-level probe coverage to that module, persist raw evidence and a generated matrix in the existing evidence directory, and test the distinction between a supplier, SDK, wrapper, gateway, and MCP. This phase does not create `finance_data.py`, a gateway, task type, scheduler, or production source selection.

**Tech Stack:** Python 3.11, standard library, installed `akshare`, `baostock`, `pytdx`, existing Tencent adapter, pytest.

---

### Task 1: Define the candidate registry and lineage contract

**Files:**
- Modify: `C:\tmp\ace_core\core\stock_data_reliability.py`
- Modify: `C:\tmp\ace_core\ops\test_stock_data_reliability.py`

- [ ] **Step 1: Write registry classification tests**

```python
def test_candidate_registry_separates_layers_and_independence():
    registry = candidate_registry()
    assert registry["akshare"].layer == "sdk_library"
    assert registry["tencent_direct"].layer == "data_supplier"
    assert registry["finshare"].layer == "wrapper"
    assert registry["akshare"].upstream_identity != "akshare"
    assert registry["finshare"].production_role == "RESEARCH_ONLY"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: FAIL because no typed candidate registry exists.

- [ ] **Step 3: Add static, source-auditable candidate metadata**

Define records for `akshare`, `baostock`, `pytdx`, `pytdx3`, `efinance`, `finshare`, `tencent_direct`, `pyqauto_astock_source_router`, `open_stock_data`, `stock_data_mcp`, `a_stock_data`, and generic `stock_data`. Each record must include repository reference, license, language, maintenance state, layer, upstream identity, independence group, supported capabilities, evidence status, and provisional production role. Unknown ultimate upstreams stay `UNVERIFIED_AGGREGATE` and cannot be a production candidate.

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: PASS.

### Task 2: Extend benchmark operation coverage without a second reliability system

**Files:**
- Modify: `C:\tmp\ace_core\core\stock_data_reliability.py`
- Modify: `C:\tmp\ace_core\ops\test_stock_data_reliability.py`

- [ ] **Step 1: Write failing operation-coverage tests**

```python
def test_benchmark_declares_required_phase_one_operations():
    operations = benchmark_operations()
    assert {"quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index", "stock_pool", "etf", "fund_flow"} <= set(operations)


def test_probe_carries_lineage_and_operation_fields():
    probe = ProbeResult(...)
    assert probe.operation == "quote"
    assert probe.upstream_identity
    assert probe.independence_group
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: FAIL because probes lack operation-level lineage fields and 1m/ETF coverage.

- [ ] **Step 3: Add only tested, installed-source probes**

Expand the existing AKShare and direct-Tencent probe factories to distinguish 1m and 5m bars, the four required indices, stock pool scope, ETF coverage, and fund-flow response completeness. Use BaoStock and pytdx only when their tested public interfaces return normalized evidence; otherwise record an explicit capability gap rather than a synthetic success. Keep each source batch process-isolated and keep timeout failures as evidence.

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: PASS.

### Task 3: Compute repeat-sample health, freshness, and source-independent consistency

**Files:**
- Modify: `C:\tmp\ace_core\core\stock_data_reliability.py`
- Modify: `C:\tmp\ace_core\ops\test_stock_data_reliability.py`

- [ ] **Step 1: Write failing health aggregation tests**

```python
def test_health_reports_p95_timeout_rate_and_operation_coverage():
    source = evaluate_health(sample_probes)["sources"]["tencent_direct"]
    assert source["p95_latency_ms"] == 300
    assert source["timeout_rate"] == 0.25
    assert source["operation_coverage"]["quote"] == 1.0


def test_same_independence_group_does_not_count_as_cross_validation():
    source = evaluate_health(same_upstream_probes)["sources"]["akshare"]
    assert source["consistency"] == 0.0
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: FAIL because p95, timeout rate, and independence-aware consistency are absent.

- [ ] **Step 3: Implement deterministic operation-level aggregation**

Calculate availability, median and p95 latency, freshness classification, coverage by declared scope, field completeness, cross-group value consistency, timeout rate, and error rate. Classify readiness as `READY`, `PARTIAL`, `RESEARCH_ONLY`, or `UNAVAILABLE`; derive production roles only from measured evidence plus observable lineage. A package sharing an upstream group cannot satisfy an independent cross-validation requirement.

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: PASS.

### Task 4: Execute isolated multi-round benchmark and produce the capability matrix

**Files:**
- Modify: `C:\tmp\ace_core\core\stock_data_reliability.py`
- Test: `C:\tmp\ace_core\ops\test_stock_data_reliability.py`
- Output: `C:\tmp\ace_core\06_RUNTIME\ace\data\stock_data_evidence\stock_data_benchmark_latest.json`
- Output: `C:\tmp\ace_core\06_RUNTIME\ace\data\stock_data_evidence\A_SHARE_DATA_CAPABILITY_MATRIX.json`

- [ ] **Step 1: Write a failing matrix-generation test**

```python
def test_matrix_exposes_reuse_adapt_research_reject_decisions(tmp_path):
    matrix = build_capability_matrix(candidate_registry(), benchmark_result)
    assert {"REUSE", "ADAPT", "RESEARCH", "REJECT"} <= set(matrix["decision_groups"])
    assert matrix["columns"] == ["Source", "Capability", "Available", "Freshness", "Coverage", "Stability", "Upstream", "Independence", "Production Role"]
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: FAIL because no matrix is generated.

- [ ] **Step 3: Implement matrix construction and run five isolated rounds**

Generate the capability matrix from candidate metadata plus benchmark evidence. Run five rounds against current no-credential candidates, retain per-call raw records, and emit a production recommendation only when stable evidence and an independently grouped cross-validation result exist. Do not install dependencies, create `finance_data.py`, invoke models, send notifications, or change environment flags.

Run:

```powershell
python core/stock_data_reliability.py 5
```

Expected: JSON evidence and matrix files are created; operational failures remain visible rather than becoming defaults.

- [ ] **Step 4: Run the focused test and verify it passes**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: PASS.

### Task 5: Reverse-audit data access and complete regression verification

**Files:**
- Inspect: `C:\tmp\ace_core\core\stock_data_reliability.py`
- Inspect: `C:\tmp\ace_core\core\environment_sensor.py`
- Inspect: `C:\tmp\ace_core\core\stock_discovery_sources.py`
- Test: `C:\tmp\ace_core\ops\test_stock_data_reliability.py`

- [ ] **Step 1: Add a bypass-audit regression test**

```python
def test_stock_data_runtime_paths_are_registered_or_observability_only():
    findings = audit_stock_data_paths(REPO_ROOT)
    assert findings["unregistered_runtime_calls"] == []
    assert all(item["classification"] == "observability_only" for item in findings["exceptions"])
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: FAIL until runtime calls are classified and current direct Tencent health check is explicitly marked observability-only.

- [ ] **Step 3: Implement audit-only call classification**

Scan runtime Python modules for direct stock endpoints and installed stock-library imports. Report a finding for every path that is neither a `StockDataBenchmark` adapter nor an explicit observability-only environment sensor. Do not redirect production calls in this phase; report any actual bypass as a blocking result.

- [ ] **Step 4: Run the complete verification suite**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
python -m compileall core
python -c "from core.stock_data_reliability import load_latest_health; print(load_latest_health('06_RUNTIME/ace/data/stock_data_evidence')['available'])"
git status --short
```

Expected: tests pass, compilation succeeds, evidence loads, and no commit is created.

- [ ] **Step 5: Assess second-phase admission**

Read the matrix and raw benchmark evidence. Mark second phase `ADMITTED` only when quote, daily kline, minute kline, and index each have a production-capable source plus a distinct `independence_group` cross-validation source. Otherwise record `NOT_ADMITTED` with the exact unmet condition and stop after the first-phase report.
