"""Small, auditable market-data adapters for the research sandbox.

The adapter keeps provider payloads and normalized fields together.  It does
not cache, rank, recommend, or write production state.  A caller may inject an
opener in tests; the default opener is the public Tencent quote/K-line endpoint.
"""

from __future__ import annotations

import json
import re
import urllib.request
from typing import Any, Callable, Mapping


_SYMBOL_RE = re.compile(r"^(?P<market>sh|sz|bj)?(?P<code>\d{6})$", re.I)


def normalize_symbol(symbol: str) -> str:
    match = _SYMBOL_RE.match(str(symbol).strip().lower())
    if not match:
        raise ValueError("unsupported_symbol")
    market = match.group("market")
    code = match.group("code")
    if market:
        return market + code
    if code.startswith(("0", "3")):
        return "sz" + code
    if code.startswith("6"):
        return "sh" + code
    if code.startswith(("4", "8")):
        return "bj" + code
    raise ValueError("market_prefix_required")


def _number(value: Any) -> float | None:
    try:
        return float(value) if str(value).strip() else None
    except (TypeError, ValueError):
        return None


def _request(url: str, opener: Callable[..., Any] = urllib.request.urlopen, timeout: int = 8) -> str:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ACE-research-sandbox/1.0", "Accept": "*/*"},
    )
    with opener(request, timeout=timeout) as response:
        raw = response.read()
    # Tencent quotes are commonly GBK while fixtures and some edges are UTF-8.
    # A strict attempt prevents a lossy UTF-8 replacement from winning over a
    # valid GBK payload.
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk", errors="replace")


def _parse_quote_line(line: str) -> dict[str, Any] | None:
    if "=" not in line:
        return None
    raw_symbol, raw_value = line.split("=", 1)
    symbol = raw_symbol.removeprefix("v_").strip()
    fields = raw_value.strip().strip('";').split("~")
    if len(fields) < 40 or not fields[1] or _number(fields[3]) is None:
        return None
    return {
        "provider": "tencent",
        "symbol": symbol,
        "code": fields[2],
        "name": fields[1],
        "price": _number(fields[3]),
        "previous_close": _number(fields[4]),
        "open": _number(fields[5]),
        "volume": _number(fields[6]),
        "timestamp": fields[30] if len(fields) > 30 else None,
        "change": _number(fields[31]) if len(fields) > 31 else None,
        "change_pct": _number(fields[32]) if len(fields) > 32 else None,
        "high": _number(fields[33]) if len(fields) > 33 else None,
        "low": _number(fields[34]) if len(fields) > 34 else None,
        "turnover": _number(fields[37]) if len(fields) > 37 else None,
        "turnover_rate": _number(fields[38]) if len(fields) > 38 else None,
        "evidence_status": "VERIFIED",
    }


def fetch_tencent_quote(symbol: str, *, opener: Callable[..., Any] = urllib.request.urlopen) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    payload = _request(f"https://qt.gtimg.cn/q={normalized}", opener=opener)
    for line in payload.splitlines():
        parsed = _parse_quote_line(line)
        if parsed and parsed["symbol"] == normalized:
            return parsed
    raise ValueError("quote_payload_unparseable")


def fetch_tencent_daily(
    symbol: str,
    *,
    days: int = 90,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    normalized = normalize_symbol(symbol)
    if days < 1 or days > 1000:
        raise ValueError("days_out_of_range")
    url = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        f"?_var=ace_kline&param={normalized},day,,,{days},qfq"
    )
    payload = _request(url, opener=opener)
    raw = payload.removeprefix("ace_kline=").strip().rstrip(";")
    data = json.loads(raw)
    rows = data.get("data", {}).get(normalized, {}).get("qfqday", [])
    normalized_rows = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        values = [_number(value) for value in row[1:6]]
        if any(value is None for value in values):
            continue
        normalized_rows.append(
            {
                "date": row[0],
                "open": values[0],
                "close": values[1],
                "high": values[2],
                "low": values[3],
                "volume": values[4],
            }
        )
    if not normalized_rows:
        raise ValueError("daily_payload_empty")
    return {
        "provider": "tencent",
        "symbol": normalized,
        "frequency": "1d",
        "adjustment": "qfq",
        "rows": normalized_rows,
        "evidence_status": "VERIFIED",
    }
