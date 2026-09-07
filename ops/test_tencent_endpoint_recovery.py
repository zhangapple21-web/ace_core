"""Regression checks for the Tencent minute-host correction."""

import json

from core.stock_data_reliability import StockDataBenchmark, build_capability_matrix, candidate_registry


def test_tencent_minute_uses_non_web_ifzq_host(monkeypatch, tmp_path):
    seen = []

    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self):
            return json.dumps({"data": {"sz000001": {"m1": [["2026-08-27 09:31", "1", "2", "3", "0.5", "9"]]}}}).encode()

    def fake_open(request, timeout):
        seen.append(request.full_url)
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    rows = StockDataBenchmark(tmp_path)._tencent_minute("000001", "1")
    assert rows[0]["close"] == "2"
    assert seen[0].startswith("https://ifzq.gtimg.cn/appstock/app/kline/mkline")
    assert "web.ifzq" not in seen[0]


def test_capability_matrix_keeps_healthy_tencent_quote_when_other_operation_fails():
    source = {"availability": 0.56, "field_completeness": 0.56, "coverage": 0.0, "consistency": 1.0, "stability": 0.31, "freshness": "observed", "lineage_observable": True, "recommended_role": "淘汰源", "operation_coverage": {"quote": 1.0, "minute_kline_5m": 0.0}, "operation_quality": {"quote": {"availability": 1.0, "field_completeness": 1.0}, "minute_kline_5m": {"availability": 0.0, "field_completeness": 0.0}}}
    matrix = build_capability_matrix(candidate_registry(), {"summary": {"sources": {"tencent": source}}})
    rows = [row for row in matrix["rows"] if row["Source"] == "tencent_direct"]
    assert next(row for row in rows if row["Capability"] == "quote")["Decision"] == "ADAPT"
    assert next(row for row in rows if row["Capability"] == "minute_kline_5m")["Decision"] == "REJECT"


