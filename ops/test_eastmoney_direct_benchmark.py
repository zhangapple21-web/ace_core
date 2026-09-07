import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ops.eastmoney_direct_benchmark import EastMoneyDirectIsolationBenchmark


def test_isolation_benchmark_records_direct_lineage_and_does_not_claim_admission(tmp_path):
    responses = {
        "quote:1.600000": {"f43": 9.13, "f47": 100, "f57": "600000", "f58": "浦发银行", "f60": 9.08, "f86": 1787718732},
        "minute_kline_1m:1.600000": {"klines": ["2026-08-26 10:00,9.1,9.13,9.14,9.09,100,1000"]},
        "index:1.000001": {"f43": 3916.83, "f47": 100, "f57": "000001", "f58": "上证指数", "f60": 3889.44, "f86": 1787718732},
    }

    benchmark = EastMoneyDirectIsolationBenchmark(
        str(tmp_path),
        symbols=("1.600000",),
        index_secid="1.000001",
        fetch=lambda operation, secid: responses[f"{operation}:{secid}"],
        now_epoch=lambda: 1787718740,
    )

    result = benchmark.run(rounds=1)

    assert result["candidate"]["upstream_identity"] == "EastMoney direct public quotation endpoints"
    assert result["candidate"]["independence_group"] == "eastmoney_public_http"
    assert result["candidate"]["lineage_observable"] is True
    assert result["admission"] == "RESEARCH_ONLY"
    assert result["production_integration"] is False
    assert result["candidate_disposition"] == "CANDIDATE_REQUIRES_CROSS_SOURCE_VALIDATION"
    assert {probe["operation"] for probe in result["probes"]} == {"quote", "minute_kline_1m", "index"}
    assert all(probe["success"] for probe in result["probes"])
    assert all(probe["endpoint"].startswith("https://") for probe in result["probes"])
    assert result["summary"]["quote"]["availability"] == 1.0
    assert result["summary"]["quote"]["freshness_observable"] is True
    assert json.loads((tmp_path / "eastmoney_direct_isolation_latest.json").read_text(encoding="utf-8"))["admission"] == "RESEARCH_ONLY"


def test_isolation_benchmark_retains_failure_as_evidence(tmp_path):
    def fetch(operation, secid):
        if operation == "minute_kline_1m":
            raise TimeoutError("bounded test timeout")
        return {"f43": 1, "f47": 1, "f57": "x", "f58": "x", "f60": 1, "f86": 1787718732}

    result = EastMoneyDirectIsolationBenchmark(
        str(tmp_path),
        symbols=("1.600000",),
        index_secid="1.000001",
        fetch=fetch,
        now_epoch=lambda: 1787718740,
    ).run(rounds=1)

    minute = next(probe for probe in result["probes"] if probe["operation"] == "minute_kline_1m")
    assert minute["success"] is False
    assert minute["error_type"] == "TimeoutError"
    assert result["summary"]["minute_kline_1m"]["availability"] == 0.0
    assert result["candidate_disposition"] == "A_SHARE_DATA_SOURCE_NOT_FOUND"
    assert result["admission"] == "RESEARCH_ONLY"


