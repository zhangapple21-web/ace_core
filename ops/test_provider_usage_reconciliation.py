import csv
import json
import os
import sys
import time
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.provider_usage_reconciliation import (
    build_usage_report,
    find_latest_usage_csv,
    refresh_latest_usage_report,
    safe_source_error_status,
)


HEADER = [
    "request_id", "date", "local_date", "timezone", "model", "api_key",
    "input_tokens", "cache_tokens", "output_tokens", "web_search_calls",
    "web_search_cost_usd", "total_tokens", "cost_usd", "total_charged_usd",
    "status", "status_code", "fallback",
]


def _write_usage_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)


def _row(**overrides):
    row = {
        "request_id": "request-private-001",
        "date": "2026-08-27T07:00:00Z",
        "local_date": "2026-08-27T15:00:00+08:00",
        "timezone": "Asia/Shanghai",
        "model": "gpt-5.6-terra",
        "api_key": "normal route label",
        "input_tokens": "100",
        "cache_tokens": "50",
        "output_tokens": "20",
        "web_search_calls": "0",
        "web_search_cost_usd": "0",
        "total_tokens": "170",
        "cost_usd": "0.01",
        "total_charged_usd": "0.02",
        "status": "completed",
        "status_code": "200",
        "fallback": "false",
    }
    row.update(overrides)
    return row


def test_report_aggregates_models_errors_routes_and_never_leaks_sensitive_cells(tmp_path):
    source = tmp_path / "usage-20260727-20260827.csv"
    secret_like_label = "sk-test-not-a-real-key-12345"
    _write_usage_csv(source, [
        _row(),
        _row(
            request_id="request-private-002",
            model="gpt-image-2",
            api_key="ACE image route",
            local_date="2026-08-27T15:01:00+08:00",
            status="failed",
            status_code="502",
            cost_usd="0",
            total_charged_usd="0",
        ),
        _row(
            request_id="request-private-003",
            model="gpt-image-2",
            api_key=secret_like_label,
            local_date="2026-08-27T15:02:00+08:00",
            status="failed",
            status_code="400",
            cost_usd="0",
            total_charged_usd="0",
            fallback="true",
        ),
        _row(
            request_id="request-private-004",
            model="gpt-image-2",
            api_key="Canvas image route",
            local_date="2026-08-27T15:03:00+08:00",
            status="failed",
            status_code="200",
            cost_usd="0",
            total_charged_usd="0",
        ),
        _row(
            request_id="request-private-005",
            local_date="2026-08-27T15:04:00+08:00",
            status="failed",
            status_code="503",
            cost_usd="0",
            total_charged_usd="0",
        ),
    ])

    report = build_usage_report(
        source,
        runtime_daily_cost={"2026-08-27": {"total_usd": 0.0129, "total_calls": 4}},
        minimum_failure_burst=1,
    )

    assert report["totals"]["requests"] == 5
    assert report["totals"]["completed_requests"] == 1
    assert report["totals"]["failed_requests"] == 4
    assert report["totals"]["fallback_requests"] == 1
    assert report["models"]["gpt-image-2"]["failed_requests"] == 3
    assert report["image_route_classes"]["ace_image"]["failed_requests"] == 1
    assert report["image_route_classes"]["canvas_image"]["failed_requests"] == 1
    assert report["image_route_classes"]["key_like_label"]["failed_requests"] == 1
    assert report["failures"]["status_code_counts"] == {"200": 1, "400": 1, "502": 1, "503": 1}
    assert report["failures"]["http_200_business_failed_requests"] == 1
    assert report["failures"]["hourly_failure_clusters"] == [
        {"hour": "2026-08-27T15", "failed_requests": 4}
    ]
    assert report["ace_runtime_comparison"]["reconciliation_status"] == "AGGREGATE_ONLY_UNATTRIBUTABLE"
    assert report["ace_runtime_comparison"]["request_level_linkage"] == "MISSING"
    assert report["ace_runtime_comparison"]["overlapping_dates"][0]["ace_runtime_estimated_usd"] == 0.0129
    assert report["privacy_contract"]["task_billing_reconciliation_written"] is False

    serialized = json.dumps(report, ensure_ascii=False)
    assert secret_like_label not in serialized
    assert "request-private-001" not in serialized
    assert "normal route label" not in serialized
    assert '"api_key"' not in serialized
    assert '"request_id"' not in serialized


def test_report_detects_filename_coverage_mismatch_and_preserves_actual_rows(tmp_path):
    source = tmp_path / "usage-20260727-20260827.csv"
    _write_usage_csv(source, [_row(local_date="2026-08-21T09:30:00+08:00")])

    report = build_usage_report(source)

    warning = report["source"]["coverage_warning"]
    assert warning["type"] == "FILENAME_DATE_RANGE_DIFFERS_FROM_ROW_COVERAGE"
    assert warning["filename_range"] == {"start": "2026-07-27", "end": "2026-08-27"}
    assert warning["actual_row_coverage"] == {"start": "2026-08-21", "end": "2026-08-21"}


def test_refresh_reuses_unchanged_export_without_reparsing(tmp_path):
    downloads = tmp_path / "Downloads"
    source = downloads / "usage-20260821-20260827.csv"
    output = tmp_path / "out" / "shenwen_usage_latest.json"
    _write_usage_csv(source, [_row()])

    first = refresh_latest_usage_report(downloads_dir=downloads, output_path=output)
    second = refresh_latest_usage_report(
        downloads_dir=downloads,
        output_path=output,
        previous_state=first["state"],
    )

    assert first["status"] == "REFRESHED"
    assert output.is_file()
    assert second["status"] == "UNCHANGED"
    assert second["state"]["source_file_sha256"] == first["state"]["source_file_sha256"]


def test_no_source_and_unsupported_schema_fail_closed_without_writing(tmp_path):
    downloads = tmp_path / "Downloads"
    output = tmp_path / "out" / "usage.json"
    no_source = refresh_latest_usage_report(downloads_dir=downloads, output_path=output)
    assert no_source["status"] == "NO_SOURCE"
    assert not output.exists()

    bad_source = downloads / "usage-20260827-20260827.csv"
    bad_source.parent.mkdir(parents=True)
    bad_source.write_text("request_id,date\nanything,2026-08-27\n", encoding="utf-8")
    try:
        build_usage_report(bad_source)
    except ValueError as error:
        assert str(error).startswith("UNSUPPORTED_SCHEMA")
    else:
        raise AssertionError("missing columns must not become a partial report")

    key_like_missing_path = downloads / "usage-sk-test-not-a-real-key-12345.csv"
    try:
        build_usage_report(key_like_missing_path)
    except OSError as error:
        assert safe_source_error_status(error) == "MALFORMED_SOURCE"
        assert "sk-test" not in safe_source_error_status(error)
    else:
        raise AssertionError("missing source must not produce a report")


def test_latest_usage_csv_is_selected_by_mtime(tmp_path):
    downloads = tmp_path / "Downloads"
    older = downloads / "usage-20260821-20260826.csv"
    newer = downloads / "usage-20260821-20260827.csv"
    _write_usage_csv(older, [_row()])
    _write_usage_csv(newer, [_row()])
    future = time.time() + 5
    os.utime(older, (future, future))

    assert find_latest_usage_csv(downloads) == older


def test_daemon_refresh_stores_only_safe_report_metadata(monkeypatch, tmp_path):
    from ace_daemon import AceDaemon

    captured = {}

    def fake_refresh(**kwargs):
        captured.update(kwargs)
        return {
            "status": "REFRESHED",
            "state": {
                "status": "REFRESHED",
                "source_file_sha256": "safe-digest",
                "source_size_bytes": 12,
                "source_mtime_ns": 34,
                "report_path": str(tmp_path / "provider_billing" / "shenwen_usage_latest.json"),
            },
        }

    monkeypatch.setattr("ace_daemon.refresh_latest_usage_report", fake_refresh)
    daemon = AceDaemon.__new__(AceDaemon)
    daemon.base_dir = tmp_path
    daemon.state = {"shenwen_daily_cost": {"2026-08-27": {"total_usd": 0.01}}}
    daemon._log_error = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError(args))

    result = daemon._refresh_provider_usage_billing()

    assert result["status"] == "REFRESHED"
    assert captured["runtime_daily_cost"] == daemon.state["shenwen_daily_cost"]
    assert captured["previous_state"] == {}
    assert captured["output_path"] == tmp_path / "06_RUNTIME" / "ace" / "data" / "provider_billing" / "shenwen_usage_latest.json"
    assert daemon.state["shenwen_provider_usage_billing"] == result["state"]
