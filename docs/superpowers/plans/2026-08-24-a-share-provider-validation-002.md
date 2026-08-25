# A-Share Provider Validation 002 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add auditable BaoStock and PyTDX probes to the existing stock-data benchmark and classify both candidates without enabling a production data path.

**Architecture:** Extend only `StockDataBenchmark` and its existing isolated source-batch dispatch. Probe outputs retain the existing `ProbeResult` schema, with source-specific host, port, protocol, and operation details in endpoint/upstream evidence. The benchmark keeps the same symbols, per-operation timeout, five rounds, health aggregation, matrix builder, and admission thresholds already used in Phase 1.

**Tech Stack:** Python 3.11, installed `baostock==0.9.3`, installed `pytdx==1.72`, standard library, pytest.

---

### Task 1: Define source-specific probe contracts

**Files:**
- Modify: `C:\tmp\ace_core\ops\test_stock_data_reliability.py`
- Modify: `C:\tmp\ace_core\core\stock_data_reliability.py`

- [ ] **Step 1: Add failing probe-factory tests**

```python
def test_baostock_probes_only_claim_supported_operations(monkeypatch, tmp_path):
    benchmark = StockDataBenchmark(str(tmp_path))
    probes = benchmark._baostock_probes("600000")

    assert {probe.operation for probe in probes} == {
        "daily_kline", "minute_kline_5m"
    }
    assert all(probe.source == "baostock" for probe in probes)
    assert all(probe.independence_group == "baostock_tcp" for probe in probes)


def test_pytdx_probe_evidence_includes_selected_tdx_host(monkeypatch, tmp_path):
    benchmark = StockDataBenchmark(str(tmp_path))
    probes = benchmark._pytdx_probes("600000")

    assert {probe.operation for probe in probes} == {
        "quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index", "stock_pool"
    }
    assert all("tdx://" in probe.endpoint for probe in probes)
    assert all(probe.independence_group == "tdx_tcp_protocol" for probe in probes)
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: FAIL because the BaoStock and PyTDX factories do not exist.

- [ ] **Step 3: Implement minimal probe factories**

Add `_baostock_probes()` and `_pytdx_probes()` to `StockDataBenchmark`. BaoStock probes only `daily_kline` and `minute_kline_5m`; it must emit explicit unsupported-operation evidence for quote, 1-minute bars, and index rather than synthetic values. PyTDX connects only to a locally audited `pytdx.config.hosts.hq_hosts` entry, performs all supported core probes through one selected connection, and records the selected `tdx://<host>:<port>` endpoint on every result. Add normalizers only for actually returned rows and quote fields.

- [ ] **Step 4: Run focused tests and confirm pass**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: PASS.

### Task 2: Preserve source batch isolation and candidate lineage

**Files:**
- Modify: `C:\tmp\ace_core\ops\test_stock_data_reliability.py`
- Modify: `C:\tmp\ace_core\core\stock_data_reliability.py`

- [ ] **Step 1: Add failing dispatch and lineage tests**

```python
def test_source_batch_supports_baostock_and_pytdx():
    factories = StockDataBenchmark.source_factories()

    assert {"baostock", "pytdx"} <= set(factories)


def test_pytdx_success_carries_observable_protocol_lineage(tmp_path):
    benchmark = StockDataBenchmark(str(tmp_path))
    probe = benchmark._source_failure(
        "pytdx", "600000", "2026-08-24T00:00:00+00:00", 0, "ProbeTimeout", "test"
    )

    assert probe.upstream_identity == "TDX quotation protocol host pool"
    assert probe.independence_group == "tdx_tcp_protocol"
    assert probe.lineage_observable is True
```

- [ ] **Step 2: Run focused tests and confirm failure**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: FAIL because the isolated dispatcher and failure helper do not recognize both sources.

- [ ] **Step 3: Extend existing source dispatcher**

Add `baostock` and `pytdx` to `_run_source_batch`, `StockDataBenchmark.source_factories()`, and `_source_failure()` supplier handling. Add their source-lineage descriptions to `run()`. Do not modify `DataQualityProtocol`, environment flags, recommendation code, or runtime routing.

- [ ] **Step 4: Run focused tests and confirm pass**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: PASS.

### Task 3: Execute the fixed five-round benchmark and rebuild evidence

**Files:**
- Modify: `C:\tmp\ace_core\core\stock_data_reliability.py`
- Output: `C:\tmp\ace_core\06_RUNTIME\ace\data\stock_data_evidence\stock_data_benchmark_latest.json`
- Output: `C:\tmp\ace_core\06_RUNTIME\ace\data\stock_data_evidence\A_SHARE_DATA_CAPABILITY_MATRIX.json`

- [ ] **Step 1: Extend the fixed benchmark source list**

Change the `run()` source sequence from:

```python
("akshare", "finshare", "tencent")
```

to:

```python
("akshare", "finshare", "tencent", "baostock", "pytdx")
```

Do not alter `DEFAULT_SYMBOLS`, `BENCHMARK_OPERATIONS`, operation timeouts, or the five-round invocation.

- [ ] **Step 2: Execute the five-round benchmark**

Run:

```powershell
python core/stock_data_reliability.py 5
```

Expected: a new stamped raw evidence file, refreshed latest evidence, and a capability matrix containing BaoStock and PyTDX metrics or explicit failures.

- [ ] **Step 3: Assert the matrix retains the strict admission gate**

Run:

```powershell
python -c "import json; from pathlib import Path; p=Path('06_RUNTIME/ace/data/stock_data_evidence/A_SHARE_DATA_CAPABILITY_MATRIX.json'); m=json.loads(p.read_text(encoding='utf-8')); assert set(m['phase_two_admission']['core_operations']) == {'quote','daily_kline','minute_kline_1m','minute_kline_5m','index'}; print(m['phase_two_admission']['status'])"
```

Expected: `NOT_ADMITTED` unless every core operation has eligible sources across at least two valid independence groups.

### Task 4: Reverse-audit and verify the result

**Files:**
- Test: `C:\tmp\ace_core\ops\test_stock_data_reliability.py`
- Inspect: `C:\tmp\ace_core\core\stock_data_reliability.py`
- Inspect: `C:\tmp\ace_core\core\environment_sensor.py`

- [ ] **Step 1: Run reliability regression suite**

Run:

```powershell
python -m pytest ops/test_stock_data_reliability.py -q
```

Expected: PASS.

- [ ] **Step 2: Run source-bypass audit**

Run:

```powershell
python -c "from pathlib import Path; from core.stock_data_reliability import audit_stock_data_paths; findings=audit_stock_data_paths(Path.cwd()); assert findings['unregistered_runtime_calls'] == []; print(findings)"
```

Expected: no unregistered runtime calls; only the existing observability-only Tencent liveness exception.

- [ ] **Step 3: Compile modified modules**

Run:

```powershell
python -m compileall core ops
```

Expected: successful compilation.

- [ ] **Step 4: Classify candidates and stop at the evidence gate**

Read the refreshed matrix and raw benchmark artifact. Report `REUSE`, `ADAPT`, `RESEARCH`, or `REJECT` for BaoStock and PyTDX. Report `NO_PRODUCTION_SOURCE_FOUND` and retain `PHASE_2_NOT_ADMITTED` unless a full core-operation production candidate and independent cross-validation group are established. Do not create a gateway, connect `financial_analysis`, run recommendation logic, send messages, enable `AUTO_RUN`/`AUTO_PUSH`, or commit changes.
