"""Read-only health evidence for local provider ports."""

from __future__ import annotations

from typing import Any, Dict, Iterable
from urllib.parse import urlparse

import requests


ENDPOINTS = ("/health", "/health/liveliness", "/v1/models", "/v1/responses")


def _error_class(error: Exception) -> str:
    text = str(error).lower()
    if isinstance(error, requests.ConnectionError) or "connection refused" in text:
        return "connection_refused"
    if isinstance(error, requests.Timeout) or "timed out" in text:
        return "timeout"
    return "request_error"


def _endpoint_result(base_url: str, endpoint: str, timeout_seconds: float) -> Dict[str, Any]:
    url = f"{base_url}{endpoint}"
    try:
        response = requests.get(url, timeout=timeout_seconds)
        status_code = int(response.status_code)
        return {
            "status_code": status_code,
            "status": "ok" if 200 <= status_code < 300 else "error",
            "error_class": "" if 200 <= status_code < 300 else f"http_{status_code}",
        }
    except Exception as error:
        return {
            "status_code": None,
            "status": "unavailable",
            "error_class": _error_class(error),
            "error": str(error)[:200],
        }


def probe_provider_ports(
    ports: Iterable[int],
    timeout_seconds: float = 3,
    evidence_dir: Any = None,
) -> Dict[str, Any]:
    """Probe local provider endpoints without writing evidence or runtime state."""
    del evidence_dir
    results: Dict[str, Any] = {}
    for port in ports:
        port_key = str(port)
        endpoints = {
            endpoint: _endpoint_result(
                f"http://127.0.0.1:{port}", endpoint, timeout_seconds
            )
            for endpoint in ENDPOINTS
        }
        successful = [item for item in endpoints.values() if item["status"] == "ok"]
        unavailable = all(item["status"] == "unavailable" for item in endpoints.values())
        results[port_key] = {
            "port": port,
            "status": "unavailable" if unavailable else ("ok" if successful else "degraded"),
            "error_class": next(
                (item["error_class"] for item in endpoints.values() if item["error_class"]),
                "",
            ),
            "endpoints": endpoints,
        }
    return {"ports": results, "side_effects": "none"}
