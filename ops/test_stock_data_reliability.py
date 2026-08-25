import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.discovery import DiscoveryMode
from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.stock_data_reliability import (
    CRITICAL_QUOTE_FIELDS,
    DataQualityProtocol,
    MarketState,
    ProbeResult,
    StockDataBenchmark,
    assess_market_state,
    audit_stock_data_paths,
    benchmark_operations,
    build_capability_matrix,
    candidate_registry,
    decide_safe_fallback,
    evaluate_data_quality,
    evaluate_health,
)
from core.stock_discovery_sources import StockDiscoverySources
from core.task import TaskPool


def quote(source, success=True, fields=None, started_at="2026-08-24T02:00:00+00:00"):
    return {
        "source": source,
        "supplier": source,
        "data_type": "quote",
        "symbol": "600000",
        "round": 1,
        "success": success,
        "latency_ms": 100,
        "fields": fields if fields is not None else {"price": 10.0, "change_pct": 1.0, "volume": 1000},
        "expected_fields": list(CRITICAL_QUOTE_FIELDS),
        "lineage_observable": True,
        "started_at": started_at,
    }


def healthy_metrics():
    return {
        "availability": 1.0,
        "field_completeness": 1.0,
        "coverage": 1.0,
        "consistency": 1.0,
        "error_rate": 0.0,
    }


def trading_time():
    return datetime(2026, 8, 24, 2, 0, tzinfo=timezone.utc)


def test_candidate_registry_separates_layers_and_independence():
    registry = candidate_registry()

    assert registry["akshare"].layer == "sdk_library"
    assert registry["tencent_direct"].layer == "data_supplier"
    assert registry["finshare"].layer == "wrapper"
    assert registry["akshare"].upstream_identity != "akshare"
    assert registry["finshare"].production_role == "RESEARCH_ONLY"
    assert registry["sina_direct"].upstream_identity == "Sina public quotation endpoints"
    assert registry["sina_direct"].independence_group == "sina_public_http"


def test_finshare_registry_uses_installed_source_evidence():
    candidate = candidate_registry()["finshare"]

    assert candidate.repository == "installed:finshare==2.1.0"
    assert candidate.license == "MIT"
    assert candidate.evidence_status == "SOURCE_AUDITED_INSTALLED"


def test_benchmark_declares_required_phase_one_operations():
    assert {
        "quote",
        "daily_kline",
        "minute_kline_1m",
        "minute_kline_5m",
        "index",
        "stock_pool",
        "etf",
        "fund_flow",
    } <= set(benchmark_operations())


def _captured_probe_calls(monkeypatch, benchmark):
    captured = []

    def capture(source, supplier, data_type, symbol, expected_fields, operation, endpoint, **kwargs):
        operation_name = kwargs.get("operation_name") or {"daily_k": "daily_kline", "minute_k": "minute_kline_5m"}.get(data_type, data_type)
        captured.append((source, data_type, endpoint, operation_name))
        return ProbeResult(
            source=source, supplier=supplier, data_type=data_type, symbol=symbol,
            started_at="2026-08-24T02:00:00+00:00", latency_ms=1, success=True,
            fields={"record_count": 1}, expected_fields=list(expected_fields), evidence_hash="test",
            operation=operation_name,
            upstream_identity=candidate_registry()[{"sina": "sina_direct"}.get(source, source)].upstream_identity,
            independence_group=candidate_registry()[{"sina": "sina_direct"}.get(source, source)].independence_group,
            endpoint=endpoint,
        )

    monkeypatch.setattr(benchmark, "_probe", capture)
    return captured


def test_baostock_probes_only_claim_supported_operations(monkeypatch, tmp_path):
    import baostock as bs

    benchmark = StockDataBenchmark(str(tmp_path))
    captured = _captured_probe_calls(monkeypatch, benchmark)
    monkeypatch.setattr(bs, "login", lambda: type("Login", (), {"error_code": "0", "error_msg": ""})())
    monkeypatch.setattr(bs, "logout", lambda: None)
    probes = benchmark._baostock_probes("600000")

    assert {probe.operation for probe in probes} == {"daily_kline", "minute_kline_5m"}
    assert {source for source, _, _, _ in captured} == {"baostock"}
    assert {operation for _, _, _, operation in captured} == {"daily_kline", "minute_kline_5m"}
    assert {probe.independence_group for probe in probes} == {"baostock_tcp"}


def test_pytdx_probes_declare_tdx_protocol_lineage(monkeypatch, tmp_path):
    from pytdx.hq import TdxHq_API

    benchmark = StockDataBenchmark(str(tmp_path))
    _captured_probe_calls(monkeypatch, benchmark)
    monkeypatch.setattr(TdxHq_API, "connect", lambda self, host, port, time_out=12: True)
    monkeypatch.setattr(TdxHq_API, "get_security_quotes", lambda self, symbols: [{"price": 10, "volume": 1}])
    monkeypatch.setattr(TdxHq_API, "disconnect", lambda self: None)
    probes = benchmark._pytdx_probes("600000")

    assert {probe.operation for probe in probes} == {
        "quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index", "stock_pool"
    }
    assert {probe.source for probe in probes} == {"pytdx"}
    assert {probe.independence_group for probe in probes} == {"tdx_tcp_protocol"}
    assert all(probe.endpoint.startswith("tdx://") for probe in probes)


def test_pytdx_probes_fall_back_within_audited_host_pool(monkeypatch, tmp_path):
    from pytdx.hq import TdxHq_API

    benchmark = StockDataBenchmark(str(tmp_path))
    _captured_probe_calls(monkeypatch, benchmark)
    hosts = (
        ("unreachable", "192.0.2.1", 7709),
        ("reachable", "198.51.100.2", 7709),
    )
    attempts = []

    monkeypatch.setattr(benchmark, "_pytdx_hosts", lambda: hosts)

    def connect(self, host, port, time_out=12):
        attempts.append((host, port, time_out))
        return host == "198.51.100.2"

    monkeypatch.setattr(TdxHq_API, "connect", connect)
    monkeypatch.setattr(TdxHq_API, "get_security_quotes", lambda self, symbols: [{"price": 10, "volume": 1}])
    monkeypatch.setattr(TdxHq_API, "disconnect", lambda self: None)

    probes = benchmark._pytdx_probes("600000")

    assert attempts == [
        ("192.0.2.1", 7709, 3),
        ("198.51.100.2", 7709, 3),
    ]
    assert all(probe.endpoint == "tdx://198.51.100.2:7709" for probe in probes)


def test_source_batch_failure_preserves_provider_lineage():
    probe = StockDataBenchmark._source_failure(
        "pytdx", "600000", "2026-08-24T02:00:00+00:00", 0, "ProbeTimeout", "test"
    )

    assert probe.upstream_identity == "TDX quotation protocol host pool"
    assert probe.independence_group == "tdx_tcp_protocol"
    assert probe.lineage_observable is True


def test_benchmark_runs_direct_sources_in_each_symbol_round(monkeypatch, tmp_path):
    benchmark = StockDataBenchmark(str(tmp_path))
    sources = []

    def source_probes(source, symbol, timeout_seconds=35):
        sources.append(source)
        return []

    monkeypatch.setattr(benchmark, "_source_probes", source_probes)
    benchmark.run(rounds=1, symbols={"sh_main": "600000"})

    assert sources == ["akshare", "finshare", "tencent", "baostock", "pytdx", "sina", "market"]


def test_sina_probes_declare_direct_supplier_lineage(monkeypatch, tmp_path):
    benchmark = StockDataBenchmark(str(tmp_path))
    _captured_probe_calls(monkeypatch, benchmark)

    probes = benchmark._sina_probes("600000")

    assert {probe.operation for probe in probes} == {"quote", "minute_kline_1m", "index"}
    assert {probe.source for probe in probes} == {"sina"}
    assert {probe.independence_group for probe in probes} == {"sina_public_http"}


def test_sina_index_uses_shanghai_index_code(monkeypatch, tmp_path):
    benchmark = StockDataBenchmark(str(tmp_path))
    requested = []
    current = datetime.now(timezone.utc).astimezone().date().isoformat()
    values = ["上证指数", "3860", "3861", "3862", "3863", "3850", "0", "0", "1", "1"]
    values.extend(["0"] * 20)
    values.extend([current, "10:00:00", "00", ""])

    def request(url, encoding="utf-8"):
        requested.append(url)
        return f'var hq_str_sh000001="{",".join(values)}";'

    monkeypatch.setattr(benchmark, "_sina_request", request)

    result = benchmark._sina_index()

    assert requested == ["https://hq.sinajs.cn/list=sh000001"]
    assert result["index_value"] == 3862.0


def test_probe_carries_lineage_and_operation_fields():
    probe = ProbeResult(
        source="akshare",
        supplier="akshare_aggregate",
        data_type="quote",
        operation="quote",
        symbol="600000",
        started_at="2026-08-24T02:00:00+00:00",
        latency_ms=1,
        success=True,
        fields={},
        expected_fields=[],
        evidence_hash="evidence",
        upstream_identity="EastMoney",
        independence_group="eastmoney_public_http",
    )

    assert probe.operation == "quote"
    assert probe.upstream_identity == "EastMoney"
    assert probe.independence_group == "eastmoney_public_http"


def test_safety_decisions():
    primary = quote("akshare", success=False)
    standby = quote("tencent")
    assert decide_safe_fallback(primary, standby).action == "use_hot_standby"
    assert decide_safe_fallback(quote("akshare"), quote("tencent", fields={"price": 10.5, "change_pct": 1.0, "volume": 1000})).action == "do_not_recommend"
    assert decide_safe_fallback(quote("akshare", fields={"price": 10.0, "change_pct": None, "volume": 1000}), quote("tencent")).action == "do_not_recommend"
    assert decide_safe_fallback(quote("akshare", success=False), quote("tencent", fields={"price": None, "change_pct": 1.0, "volume": 1000})).action == "do_not_recommend"


def test_normalize_quote_derives_change_pct_from_previous_close():
    from core.stock_data_reliability import _normalize_quote

    fields = _normalize_quote({
        "last_price": 10.5,
        "prev_close": 10.0,
        "volume": 1000,
        "timestamp": "2026-08-24T02:00:00+00:00",
    })

    assert fields == {
        "price": 10.5,
        "change_pct": 5.0,
        "volume": 1000.0,
        "time": "2026-08-24T02:00:00+00:00",
    }


def test_normalize_quote_preserves_pytdx_quote_fields():
    from core.stock_data_reliability import _normalize_quote

    fields = _normalize_quote({
        "price": 9.16,
        "last_close": 9.22,
        "vol": 156491,
        "servertime": "09:46:19.110",
    })

    assert fields == {
        "price": 9.16,
        "change_pct": (9.16 - 9.22) / 9.22 * 100,
        "volume": 156491.0,
        "time": f"{datetime.now(timezone.utc).astimezone().date().isoformat()}T09:46:19.110+08:00",
    }


def test_normalize_rows_preserves_pytdx_bar_volume():
    from core.stock_data_reliability import _normalize_rows

    fields = _normalize_rows([{
        "datetime": "2026-08-25 09:46",
        "open": 9.15,
        "close": 9.16,
        "high": 9.17,
        "low": 9.14,
        "vol": 1234,
    }], ("date", "open", "close", "high", "low", "volume"))

    assert fields["volume"] == 1234.0


def test_quote_code_uses_bj_prefix_for_bse_symbols():
    from core.stock_data_reliability import _quote_code

    assert _quote_code("430047") == "bj430047"


def test_health_model():
    probes = [
        quote("akshare"),
        {
            "source": "akshare", "supplier": "akshare", "data_type": "stock_pool", "symbol": "all", "round": 1,
            "success": True, "latency_ms": 100, "fields": {"record_count": 5000}, "expected_fields": ["record_count"], "lineage_observable": True,
        },
        quote("tencent", success=False),
        {
            "source": "tencent", "supplier": "tencent", "data_type": "stock_pool", "symbol": "all", "round": 1,
            "success": False, "latency_ms": 100, "fields": {}, "expected_fields": ["record_count"], "lineage_observable": True,
        },
    ]
    health = evaluate_health(probes)["sources"]
    assert health["akshare"]["availability"] == 1.0
    assert health["tencent"]["recommended_role"] == "淘汰源"


def test_health_reports_p95_timeout_rate_and_operation_coverage():
    probes = [
        {**quote("tencent", success=True), "operation": "quote", "latency_ms": 100, "independence_group": "tencent_public_http"},
        {**quote("tencent", success=True), "operation": "quote", "latency_ms": 200, "independence_group": "tencent_public_http"},
        {**quote("tencent", success=True), "operation": "quote", "latency_ms": 300, "independence_group": "tencent_public_http"},
        {**quote("tencent", success=False), "operation": "quote", "latency_ms": 400, "independence_group": "tencent_public_http", "error_type": "TimeoutError"},
    ]

    source = evaluate_health(probes)["sources"]["tencent"]
    assert source["p95_latency_ms"] == 300
    assert source["timeout_rate"] == 0.25
    assert source["operation_coverage"]["quote"] == 1.0


def test_same_independence_group_does_not_count_as_cross_validation():
    probes = [
        {**quote("akshare"), "independence_group": "eastmoney_public_http"},
        {**quote("efinance"), "independence_group": "eastmoney_public_http"},
    ]

    assert evaluate_health(probes)["sources"]["akshare"]["consistency"] == 0.0


def test_matrix_exposes_evidence_derived_decision_groups():
    benchmark = {
        "summary": {
            "sources": {
                "akshare": {"availability": 1.0, "field_completeness": 1.0, "coverage": 1.0, "consistency": 1.0, "lineage_observable": True, "operation_coverage": {"quote": 1.0}},
                "tencent": {"availability": 0.0, "field_completeness": 0.0, "coverage": 0.0, "consistency": 0.0, "lineage_observable": True, "operation_coverage": {"quote": 0.0}},
            }
        }
    }

    matrix = build_capability_matrix(candidate_registry(), benchmark)
    assert {"REUSE", "ADAPT", "RESEARCH", "REJECT"} <= set(matrix["decision_groups"])
    assert matrix["columns"] == ["Source", "Capability", "Available", "Freshness", "Coverage", "Stability", "Upstream", "Independence", "Production Role"]
    assert matrix["phase_two_admission"]["status"] == "NOT_ADMITTED"
    assert matrix["phase_two_admission"]["core_operations"]["daily_kline"]["production_sources"] == []


def test_matrix_requires_per_operation_freshness_and_consistency():
    metrics = {
        "availability": 1.0,
        "field_completeness": 1.0,
        "coverage": 1.0,
        "consistency": 1.0,
        "lineage_observable": True,
        "operation_coverage": {"quote": 1.0},
        "operation_quality": {
            "quote": {
                "availability": 1.0,
                "coverage": 1.0,
                "field_completeness": 1.0,
                "freshness": 0.0,
                "consistency": 1.0,
            }
        },
    }

    matrix = build_capability_matrix(candidate_registry(), {"summary": {"sources": {"pytdx": metrics}}})

    assert "pytdx" not in matrix["phase_two_admission"]["core_operations"]["quote"]["production_sources"]


def test_stock_data_runtime_bypass_is_observability_only():
    findings = audit_stock_data_paths(Path(__file__).resolve().parent.parent)

    assert findings["unregistered_runtime_calls"] == []
    assert findings["exceptions"] == [{
        "path": "core/environment_sensor.py",
        "source": "tencent_direct",
        "operation": "provider_liveness_probe",
        "classification": "observability_only",
        "excluded_from": ["health_aggregation", "cross_validation", "recommendation_eligibility"],
    }]


def test_market_state_rules():
    assert assess_market_state(datetime(2026, 8, 24, 0, 30, tzinfo=timezone.utc)).state == MarketState.PRE_MARKET
    assert assess_market_state(trading_time()).state == MarketState.TRADING
    assert assess_market_state(datetime(2026, 8, 24, 4, 0, tzinfo=timezone.utc)).state == MarketState.LUNCH
    assert assess_market_state(datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc)).state == MarketState.POST_MARKET
    assert assess_market_state(datetime(2026, 8, 23, 2, 0, tzinfo=timezone.utc)).state == MarketState.WEEKEND
    assert assess_market_state(datetime(2026, 5, 4, 2, 0, tzinfo=timezone.utc)).state == MarketState.HOLIDAY


def test_runtime_protocol_normal_trading_is_ready():
    result = DataQualityProtocol().evaluate(
        now=trading_time(),
        primary=quote("akshare"),
        standby=quote("tencent"),
        provider_health={"akshare": healthy_metrics(), "tencent": healthy_metrics()},
    )
    assert result.data_quality_status == "READY"
    assert result.recommendation_eligibility == "eligible"
    assert result.selected_source == "akshare"


def test_runtime_protocol_uses_standby_only_after_primary_failure():
    result = DataQualityProtocol().evaluate(
        now=trading_time(),
        primary=quote("akshare", success=False),
        standby=quote("tencent"),
        provider_health={"akshare": {**healthy_metrics(), "availability": 0.0}, "tencent": healthy_metrics()},
    )
    assert result.data_quality_status == "READY"
    assert result.recommendation_eligibility == "eligible"
    assert result.selected_source == "tencent"
    assert result.protocol_steps == ["primary_health_check", "standby_field_validation", "recommendation_eligible"]


def test_runtime_protocol_rejects_incomplete_standby():
    result = DataQualityProtocol().evaluate(
        now=trading_time(),
        primary=quote("akshare", success=False),
        standby=quote("tencent", fields={"price": None, "change_pct": 1.0, "volume": 1000}),
        provider_health={"akshare": {**healthy_metrics(), "availability": 0.0}, "tencent": healthy_metrics()},
    )
    assert result.data_quality_status == "UNAVAILABLE"
    assert result.recommendation_eligibility == "do_not_recommend"


def test_runtime_protocol_blocks_conflict_and_stale_data():
    conflict = DataQualityProtocol().evaluate(
        now=trading_time(),
        primary=quote("akshare"),
        standby=quote("tencent", fields={"price": 11.0, "change_pct": 1.0, "volume": 1000}),
        provider_health={"akshare": healthy_metrics(), "tencent": healthy_metrics()},
    )
    assert conflict.data_quality_status == "CONFLICT"
    assert conflict.recommendation_eligibility == "do_not_recommend"
    stale = DataQualityProtocol().evaluate(
        now=trading_time(),
        primary=quote("akshare", started_at="2026-08-24T00:00:00+00:00"),
        standby=quote("tencent", started_at="2026-08-24T00:00:00+00:00"),
        provider_health={"akshare": healthy_metrics(), "tencent": healthy_metrics()},
    )
    assert stale.data_quality_status == "STALE"
    assert stale.recommendation_eligibility == "do_not_recommend"


def test_runtime_protocol_routes_closed_market_to_research_only():
    for closed_at in (datetime(2026, 8, 23, 2, 0, tzinfo=timezone.utc), datetime(2026, 8, 24, 4, 0, tzinfo=timezone.utc)):
        result = DataQualityProtocol().evaluate(
            now=closed_at,
            primary=quote("akshare"),
            standby=quote("tencent"),
            provider_health={"akshare": healthy_metrics(), "tencent": healthy_metrics()},
        )
        assert result.data_quality_status == "MARKET_CLOSED"
        assert result.recommendation_eligibility == "research_only"


def test_data_quality_classifies_provider_degradation_separately_from_empty_data():
    degraded = evaluate_data_quality(
        market=assess_market_state(trading_time()),
        primary=quote("akshare"),
        standby=quote("tencent"),
        provider_health={"akshare": {**healthy_metrics(), "availability": 0.5}, "tencent": healthy_metrics()},
        now=trading_time(),
    )
    assert degraded.data_quality_status == "DEGRADED"
    assert degraded.recommendation_eligibility == "do_not_recommend"


def test_advisor_status_and_lexicon_candidate_rules():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        workspace = root / "workspace"
        advisor = workspace / "05_TOOLS" / "advisor"
        advisor.mkdir(parents=True)
        (advisor / "daily_runner.py").write_text("", encoding="utf-8")
        output = workspace / "05_TOOLS" / "mine_output" / "advisor"
        output.mkdir(parents=True)
        (workspace / "02_MEMORY").mkdir()
        (workspace / "02_MEMORY" / "advisor_delivery.json").write_text(json.dumps({"reports": {}}), encoding="utf-8")
        (output / "runner_status.json").write_text(json.dumps({"last_run_success": False, "steps": {"report": "failed"}}), encoding="utf-8")
        sources = StockDiscoverySources(observer, str(root), advisor_workspace=str(workspace))
        previous_auto_run = os.environ.pop("ACE_STOCK_ADVISOR_AUTO_RUN", None)
        try:
            assert sources.advisor_status_candidates() == []
            os.environ["ACE_STOCK_ADVISOR_AUTO_RUN"] = "true"
            candidate = sources.advisor_status_candidates()[0]
            assert candidate.candidate_source == "advisor_system_status"
            assert candidate.priority == "critical"
        finally:
            if previous_auto_run is None:
                os.environ.pop("ACE_STOCK_ADVISOR_AUTO_RUN", None)
            else:
                os.environ["ACE_STOCK_ADVISOR_AUTO_RUN"] = previous_auto_run

        lexicon_path = root / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
        lexicon_path.parent.mkdir(parents=True)
        lexicon_path.write_text(json.dumps({
            "updated_at": "2026-08-22T00:00:00Z",
            "categories": {
                "stock": ["600000"], "industry": ["bank"], "concept": [],
                "risk_event": ["halt"], "new_term": ["term"],
            },
        }), encoding="utf-8")
        candidate = sources.lexicon_gap_candidates()[0]
        assert candidate.candidate_source == "stock_lexicon_gap"
        assert candidate.priority == "medium"
        lexicon_path.write_text(json.dumps({
            "categories": {
                "stock": ["600000"], "industry": ["bank"], "concept": ["value"],
                "risk_event": ["halt"], "new_term": ["term"],
            },
        }), encoding="utf-8")
        assert sources.lexicon_gap_candidates() == []


def test_discovery_candidate_rules():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        evidence = root / "evidence"
        evidence.mkdir()
        normal = {
            "summary": {"sources": {"akshare": {"availability": 1, "field_completeness": 1, "consistency": 1, "coverage": 1}}}
        }
        (evidence / "stock_data_benchmark_latest.json").write_text(json.dumps(normal), encoding="utf-8")
        sources = StockDiscoverySources(observer, str(root), evidence_dir=str(evidence))
        assert sources.data_health_candidates() == []
        assert len(observer.get_recent()) == 1

        degraded = {
            "summary": {"sources": {"tencent": {"availability": 0.5, "field_completeness": 1, "consistency": 1, "coverage": 0}}}
        }
        (evidence / "stock_data_benchmark_latest.json").write_text(json.dumps(degraded), encoding="utf-8")
        discovery = DiscoveryMode(pool, observer, str(root), candidate_sources=[sources.data_health_candidates])
        first = discovery.discover()
        assert first["status"] == "observed"
        unprocessed_before = len(observer.get_unprocessed())
        converter = ObservationToTaskConverter(observer, pool)
        conversion = converter.convert()
        assert conversion["candidate_count"] == 1
        assert conversion["eligible_count"] == 0
        assert conversion["rejected_count"] == 1
        assert conversion["tasks_created"] == 0
        assert conversion["outcome"] == "NO_VALID_MODEL_TASK_TARGET"
        assert pool.list_tasks(status="pending", limit=1) == []
        assert len(observer.get_unprocessed()) == unprocessed_before


def test_discovery_cooldown_recovery_and_restart_state():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        evidence = root / "evidence"
        evidence.mkdir()
        degraded = {"summary": {"sources": {"tencent": {"availability": 0.5, "field_completeness": 1, "consistency": 1, "coverage": 0}}}}
        normal = {"summary": {"sources": {"tencent": {"availability": 1, "field_completeness": 1, "consistency": 1, "coverage": 1}}}}
        path = evidence / "stock_data_benchmark_latest.json"
        path.write_text(json.dumps(degraded), encoding="utf-8")
        sources = StockDiscoverySources(observer, str(root), evidence_dir=str(evidence))
        first = sources.data_health_candidates()[0]
        assert sources.data_health_candidates() == []
        path.write_text(json.dumps(normal), encoding="utf-8")
        assert sources.data_health_candidates() == []
        path.write_text(json.dumps(degraded), encoding="utf-8")
        restarted = StockDiscoverySources(observer, str(root), evidence_dir=str(evidence))
        second = restarted.data_health_candidates()[0]
        assert first.fingerprint != second.fingerprint


def test_degraded_multi_source_candidate_can_create_reasoning_work_with_local_backlog():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "task_pool"))
        pool.create_task("existing local work", tags=["archaeology"], admission={
            "source_type": "archaeology",
            "source_ref": "local-fragment",
            "why_now": "Existing local work is pending.",
            "evidence": [{"source": "local", "content": "fragment"}],
            "expected_result": "Review the local fragment.",
            "verification_method": "Reinspect the fragment.",
            "risk": "local only",
            "estimated_scope": "one local fragment",
        })
        evidence = root / "evidence"
        evidence.mkdir()
        degraded = {
            "summary": {"sources": {
                "source_a": {"availability": 0.5, "field_completeness": 1.0, "coverage": 1.0, "consistency": 1.0},
                "source_b": {"availability": 1.0, "field_completeness": 0.5, "coverage": 1.0, "consistency": 1.0},
            }}
        }
        (evidence / "stock_data_benchmark_latest.json").write_text(json.dumps(degraded), encoding="utf-8")
        sources = StockDiscoverySources(observer, str(root), evidence_dir=str(evidence))
        discovery = DiscoveryMode(pool, observer, str(root), candidate_sources=[sources.data_health_candidates])
        converter = ObservationToTaskConverter(observer, pool)

        found = discovery.discover(allow_existing_work=True, allowed_priorities={"high"})
        converted = converter.convert(allowed_priorities={"high"})

        assert found["status"] == "observed"
        assert converted["reasoning_tasks_created"] == 1
        reasoning = [task for task in pool.list_tasks(status="pending", limit=10) if "task_type:reasoning" in task.tags]
        assert len(reasoning) == 1
        decision = reasoning[0].outputs["model_task_admission"]
        assert decision["eligible"] is True
        assert len(decision["evidence_refs"]) == 2


def main():
    test_safety_decisions()
    test_health_model()
    test_market_state_rules()
    test_runtime_protocol_normal_trading_is_ready()
    test_runtime_protocol_uses_standby_only_after_primary_failure()
    test_runtime_protocol_rejects_incomplete_standby()
    test_runtime_protocol_blocks_conflict_and_stale_data()
    test_runtime_protocol_routes_closed_market_to_research_only()
    test_data_quality_classifies_provider_degradation_separately_from_empty_data()
    test_advisor_status_and_lexicon_candidate_rules()
    test_discovery_candidate_rules()
    test_discovery_cooldown_recovery_and_restart_state()
    print("stock data reliability isolated tests passed")


if __name__ == "__main__":
    main()
