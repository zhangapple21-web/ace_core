"""Read-only, privacy-preserving reconciliation for exported provider usage CSVs.

The provider export is account-level telemetry.  It is valuable for observing
cost, availability and error patterns, but it is *not* request-level billing
proof for an ACE task: current task traces do not retain the provider export's
request identifiers or caller identity.  This module therefore deliberately
uses the status ``AGGREGATE_ONLY_UNATTRIBUTABLE`` and never writes a
``reconciled`` task billing record.

Raw CSV rows are processed in memory only.  Reports intentionally exclude raw
``api_key`` labels, request ids, prompts, responses, and source row contents.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


REQUIRED_COLUMNS = frozenset({
    "date",
    "local_date",
    "model",
    "api_key",
    "input_tokens",
    "cache_tokens",
    "output_tokens",
    "cost_usd",
    "total_charged_usd",
    "status",
    "status_code",
})
FILENAME_DATE_RANGE = re.compile(r"usage-(\d{8})-(\d{8})\.csv$", re.IGNORECASE)
KEY_LIKE_VALUE = re.compile(r"(?:^|[^a-z0-9])(?:sk|api)[-_][a-z0-9_-]{4,}", re.IGNORECASE)


def _number(value: Any) -> float:
    try:
        return float(value) if value not in (None, "") else 0.0
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _date_part(value: Any) -> str:
    value = str(value or "").strip()
    return value[:10] if len(value) >= 10 else ""


def _hour_part(value: Any) -> str:
    value = str(value or "").strip()
    if len(value) >= 13 and value[4:5] == "-" and value[7:8] == "-":
        return value[:13]
    return ""


def _safe_source_filename(path: Path) -> str:
    """Keep a useful display name without accidentally echoing a key-like name."""
    return "redacted_usage_csv" if KEY_LIKE_VALUE.search(path.name) else path.name


def safe_source_error_status(error: BaseException) -> str:
    """Classify parser failures without returning a source path or row value."""
    message = str(error)
    if message.startswith("UNSUPPORTED_SCHEMA"):
        return "UNSUPPORTED_SCHEMA"
    return "MALFORMED_SOURCE"


def _safe_route_class(raw_label: Any, model: str) -> str:
    """Map an untrusted provider label to a bounded, non-reversible class."""
    label = str(raw_label or "").strip().lower()
    model = str(model or "").strip().lower()
    if KEY_LIKE_VALUE.search(label):
        return "key_like_label"
    if "image" not in model:
        return "non_image"
    if "ace" in label:
        return "ace_image"
    if "canvas" in label or "画布" in label or "无限" in label:
        return "canvas_image"
    if "codex" in label:
        return "codex_image"
    if "专用" in label or "dedicated" in label:
        return "image_dedicated"
    if not label:
        return "image_label_missing"
    return "generic_image"


def _source_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _round_numbers(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {
        key: round(value, 10) if isinstance(value, float) else value
        for key, value in record.items()
    }


def _blank_metrics() -> Dict[str, Any]:
    return {
        "requests": 0,
        "completed_requests": 0,
        "failed_requests": 0,
        "input_tokens": 0.0,
        "cache_tokens": 0.0,
        "output_tokens": 0.0,
        "cost_usd": 0.0,
        "charged_usd": 0.0,
        "fallback_requests": 0,
    }


def _add_row(metrics: Dict[str, Any], row: Mapping[str, Any], completed: bool) -> None:
    metrics["requests"] += 1
    metrics["completed_requests" if completed else "failed_requests"] += 1
    metrics["input_tokens"] += _number(row.get("input_tokens"))
    metrics["cache_tokens"] += _number(row.get("cache_tokens"))
    metrics["output_tokens"] += _number(row.get("output_tokens"))
    metrics["cost_usd"] += _number(row.get("cost_usd"))
    metrics["charged_usd"] += _number(row.get("total_charged_usd"))
    if _truthy(row.get("fallback")):
        metrics["fallback_requests"] += 1


def _finalize_metrics(metrics: Mapping[str, Any]) -> Dict[str, Any]:
    result = dict(metrics)
    requests = int(result["requests"])
    context_tokens = float(result["input_tokens"]) + float(result["cache_tokens"])
    result["success_rate"] = round(result["completed_requests"] / requests, 8) if requests else 0.0
    result["cache_context_share"] = round(result["cache_tokens"] / context_tokens, 8) if context_tokens else 0.0
    return _round_numbers(result)


def _filename_range(path: Path) -> Optional[Dict[str, str]]:
    matched = FILENAME_DATE_RANGE.search(path.name)
    if not matched:
        return None
    start, end = matched.groups()
    return {
        "start": f"{start[:4]}-{start[4:6]}-{start[6:]}",
        "end": f"{end[:4]}-{end[4:6]}-{end[6:]}",
    }


def find_latest_usage_csv(downloads_dir: Path) -> Optional[Path]:
    """Return the newest exported usage CSV without reading or moving it."""
    directory = Path(downloads_dir)
    if not directory.exists() or not directory.is_dir():
        return None
    candidates = []
    for path in directory.glob("usage-*.csv"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if path.is_file():
            candidates.append((stat.st_mtime_ns, path.name, path))
    return max(candidates)[2] if candidates else None


def _safe_runtime_comparison(
    provider_by_date: Mapping[str, Mapping[str, Any]],
    runtime_daily_cost: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    runtime_daily_cost = runtime_daily_cost if isinstance(runtime_daily_cost, Mapping) else {}
    rows = []
    for date in sorted(set(provider_by_date) & set(runtime_daily_cost)):
        runtime = runtime_daily_cost.get(date)
        if not isinstance(runtime, Mapping):
            continue
        provider = provider_by_date[date]
        rows.append({
            "date": date,
            "provider_account_charged_usd": round(_number(provider.get("charged_usd")), 10),
            "ace_runtime_estimated_usd": round(_number(runtime.get("total_usd")), 10),
            "ace_runtime_total_calls": int(_number(runtime.get("total_calls"))),
        })
    return {
        "reconciliation_status": "AGGREGATE_ONLY_UNATTRIBUTABLE",
        "request_level_linkage": "MISSING",
        "scope_note": (
            "The provider export can include other applications and routes. "
            "No provider request identifier or caller mapping is persisted in ACE task traces."
        ),
        "overlapping_dates": rows,
    }


def build_usage_report(
    source_path: Path,
    *,
    runtime_daily_cost: Optional[Mapping[str, Any]] = None,
    minimum_failure_burst: int = 5,
) -> Dict[str, Any]:
    """Parse one provider export into a report that contains no sensitive rows.

    Raises ``ValueError`` for schema/row problems so the caller can fail
    closed without affecting the surrounding runtime loop.
    """
    source_path = Path(source_path)
    if minimum_failure_burst < 1:
        raise ValueError("minimum_failure_burst must be at least 1")
    if not source_path.is_file():
        raise FileNotFoundError(source_path)

    totals = _blank_metrics()
    by_model: Dict[str, Dict[str, Any]] = defaultdict(_blank_metrics)
    image_routes: Dict[str, Dict[str, Any]] = defaultdict(_blank_metrics)
    by_date: Dict[str, Dict[str, Any]] = defaultdict(_blank_metrics)
    failure_status_codes: Counter[str] = Counter()
    failure_hours: Counter[str] = Counter()
    business_failed_http_success = 0
    dates: set[str] = set()
    rows_read = 0

    try:
        handle = source_path.open("r", encoding="utf-8-sig", newline="")
    except UnicodeError as error:
        raise ValueError("MALFORMED_SOURCE: unable to decode UTF-8 CSV") from error

    with handle:
        reader = csv.DictReader(handle)
        fieldnames = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_COLUMNS - fieldnames)
        if missing_columns:
            raise ValueError("UNSUPPORTED_SCHEMA: missing " + ", ".join(missing_columns))
        for row in reader:
            if not isinstance(row, dict):
                continue
            rows_read += 1
            model = str(row.get("model") or "unknown").strip() or "unknown"
            status = str(row.get("status") or "").strip().lower()
            completed = status == "completed"
            observed_date = _date_part(row.get("local_date")) or _date_part(row.get("date")) or "unknown"
            if observed_date != "unknown":
                dates.add(observed_date)
            _add_row(totals, row, completed)
            _add_row(by_model[model], row, completed)
            _add_row(by_date[observed_date], row, completed)
            if "image" in model.lower():
                _add_row(image_routes[_safe_route_class(row.get("api_key"), model)], row, completed)
            if not completed:
                code = _integer(row.get("status_code"))
                code_label = str(code) if code is not None else "unknown"
                failure_status_codes[code_label] += 1
                hour = _hour_part(row.get("local_date")) or _hour_part(row.get("date"))
                if hour:
                    failure_hours[hour] += 1
                if code == 200:
                    business_failed_http_success += 1

    if not rows_read:
        raise ValueError("MALFORMED_SOURCE: CSV contains no data rows")

    filename_range = _filename_range(source_path)
    actual_coverage = {"start": min(dates), "end": max(dates)} if dates else None
    coverage_warning = None
    if filename_range and actual_coverage and filename_range != actual_coverage:
        coverage_warning = {
            "type": "FILENAME_DATE_RANGE_DIFFERS_FROM_ROW_COVERAGE",
            "filename_range": filename_range,
            "actual_row_coverage": actual_coverage,
        }

    finalized_by_date = {date: _finalize_metrics(metrics) for date, metrics in sorted(by_date.items())}
    return {
        "schema_version": "ProviderUsageReconciliation/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "mode": "READ_ONLY_PROVIDER_ACCOUNT_TELEMETRY",
        "source": {
            "source_filename": _safe_source_filename(source_path),
            "source_file_sha256": _source_sha256(source_path),
            "source_size_bytes": source_path.stat().st_size,
            "source_mtime_ns": source_path.stat().st_mtime_ns,
            "row_count": rows_read,
            "filename_date_range": filename_range,
            "actual_row_coverage": actual_coverage,
            "coverage_warning": coverage_warning,
        },
        "totals": _finalize_metrics(totals),
        "models": {model: _finalize_metrics(metrics) for model, metrics in sorted(by_model.items())},
        "image_route_classes": {
            route: _finalize_metrics(metrics) for route, metrics in sorted(image_routes.items())
        },
        "daily": finalized_by_date,
        "failures": {
            "status_code_counts": dict(sorted(failure_status_codes.items(), key=lambda item: item[0])),
            "http_200_business_failed_requests": business_failed_http_success,
            "hourly_failure_clusters": [
                {"hour": hour, "failed_requests": count}
                for hour, count in sorted(failure_hours.items())
                if count >= minimum_failure_burst
            ],
        },
        "ace_runtime_comparison": _safe_runtime_comparison(finalized_by_date, runtime_daily_cost),
        "privacy_contract": {
            "raw_api_key_stored": False,
            "raw_request_id_stored": False,
            "raw_csv_row_stored": False,
            "task_billing_reconciliation_written": False,
        },
    }


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def refresh_latest_usage_report(
    *,
    downloads_dir: Path,
    output_path: Path,
    runtime_daily_cost: Optional[Mapping[str, Any]] = None,
    previous_state: Optional[Mapping[str, Any]] = None,
    minimum_failure_burst: int = 5,
) -> Dict[str, Any]:
    """Refresh a persisted redacted report only when the source file changed."""
    source_path = find_latest_usage_csv(Path(downloads_dir))
    if source_path is None:
        return {
            "status": "NO_SOURCE",
            "state": {"status": "NO_SOURCE", "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")},
        }

    stat = source_path.stat()
    previous_state = previous_state if isinstance(previous_state, Mapping) else {}
    unchanged = (
        previous_state.get("source_size_bytes") == stat.st_size
        and previous_state.get("source_mtime_ns") == stat.st_mtime_ns
        and isinstance(previous_state.get("source_file_sha256"), str)
        and Path(output_path).is_file()
    )
    if unchanged:
        return {
            "status": "UNCHANGED",
            "state": {
                "status": "UNCHANGED",
                "source_file_sha256": previous_state["source_file_sha256"],
                "source_size_bytes": stat.st_size,
                "source_mtime_ns": stat.st_mtime_ns,
                "report_path": str(Path(output_path)),
                "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            },
        }

    report = build_usage_report(
        source_path,
        runtime_daily_cost=runtime_daily_cost,
        minimum_failure_burst=minimum_failure_burst,
    )
    _atomic_json_write(Path(output_path), report)
    source = report["source"]
    return {
        "status": "REFRESHED",
        "report": report,
        "state": {
            "status": "REFRESHED",
            "source_file_sha256": source["source_file_sha256"],
            "source_size_bytes": source["source_size_bytes"],
            "source_mtime_ns": source["source_mtime_ns"],
            "report_path": str(Path(output_path)),
            "refreshed_at": report["generated_at"],
        },
    }
