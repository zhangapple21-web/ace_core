import hashlib
import json
import os
import multiprocessing
import re
import sys
import threading
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as clock_time, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


DEFAULT_SYMBOLS = {
    "sh_main": "600000",
    "sz_main": "000001",
    "chinext": "300750",
    "star": "688001",
    "bse": "430047",
}
CRITICAL_QUOTE_FIELDS = ("price", "change_pct", "volume")
CRITICAL_DAILY_FIELDS = ("date", "open", "close", "high", "low", "volume")
BENCHMARK_OPERATIONS = (
    "quote",
    "daily_kline",
    "minute_kline_1m",
    "minute_kline_5m",
    "index",
    "stock_pool",
    "etf",
    "fund_flow",
)


def benchmark_operations() -> Tuple[str, ...]:
    return BENCHMARK_OPERATIONS


@dataclass(frozen=True)
class StockDataCandidate:
    candidate_id: str
    repository: str
    license: str
    license_evidence: str
    language: str
    maintenance: str
    maintenance_evidence: str
    layer: str
    upstream_identity: str
    independence_group: str
    capabilities: Tuple[str, ...]
    evidence_status: str
    production_role: str


def candidate_registry() -> Dict[str, StockDataCandidate]:
    return {
        "akshare": StockDataCandidate(
            "akshare", "installed:akshare==1.18.64", "MIT", "installed LICENSE", "Python",
            "installed_version_observed", "akshare/_version.py", "sdk_library", "EastMoney per audited A-share adapters",
            "eastmoney_public_http", ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index", "stock_pool", "etf", "fund_flow"),
            "SOURCE_AUDITED_INSTALLED", "BENCHMARK_REQUIRED",
        ),
        "baostock": StockDataCandidate(
            "baostock", "installed:baostock==0.9.3", "BSD_DECLARED_UNVERIFIED_TEXT", "installed METADATA; license text absent", "Python",
            "installed_version_observed", "baostock/common/contants.py", "sdk_library", "BaoStock public API",
            "baostock_tcp", ("daily_kline", "minute_kline_5m", "index", "stock_pool", "etf"),
            "SOURCE_AUDITED_INSTALLED", "BENCHMARK_REQUIRED",
        ),
        "pytdx": StockDataCandidate(
            "pytdx", "installed:pytdx==1.72", "UNVERIFIED", "installed metadata/license text not verified", "Python",
            "installed_version_observed", "pytdx/hq.py", "sdk_library", "TDX quotation protocol host pool",
            "tdx_tcp_protocol", ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index", "stock_pool"),
            "SOURCE_AUDITED_INSTALLED", "BENCHMARK_REQUIRED",
        ),
        "pytdx3": StockDataCandidate(
            "pytdx3", "UNVERIFIED", "UNVERIFIED", "repository/source not locked", "Python", "UNVERIFIED", "repository/source not locked",
            "sdk_library", "UNVERIFIED", "UNVERIFIED", (), "UNVERIFIED", "RESEARCH_ONLY",
        ),
        "efinance": StockDataCandidate(
            "efinance", "guoht/efinance", "UNVERIFIED", "not installed; license text not locally verified", "Python", "UNVERIFIED", "source audit incomplete",
            "sdk_library", "EastMoney for audited A-share adapters", "eastmoney_public_http", (), "SOURCE_AUDITED_REMOTE_PARTIAL", "RESEARCH_ONLY",
        ),
        "finshare": StockDataCandidate(
            "finshare", "installed:finshare==2.1.0", "MIT", "installed finshare-2.1.0.dist-info/METADATA", "Python",
            "installed_version_observed", "finshare/config/settings.py and finshare/sources", "wrapper",
            "UNVERIFIED_AGGREGATE", "UNVERIFIED_AGGREGATE", (), "SOURCE_AUDITED_INSTALLED", "RESEARCH_ONLY",
        ),
        "tencent_direct": StockDataCandidate(
            "tencent_direct", "existing:stock_query.StockQuery", "NOT_APPLICABLE", "existing local adapter", "Python", "local_adapter_observed", "StockDataBenchmark._tencent_probes",
            "data_supplier", "Tencent public quotation endpoints", "tencent_public_http", ("quote", "daily_kline", "minute_kline_5m", "fund_flow"),
            "SOURCE_AUDITED_LOCAL", "BENCHMARK_REQUIRED",
        ),
        "sina_direct": StockDataCandidate(
            "sina_direct", "direct:https://hq.sinajs.cn and https://quotes.sina.cn", "NOT_APPLICABLE",
            "public HTTP data supplier; no bundled library", "Python", "live_endpoint_observed",
            "StockDataBenchmark._sina_probes", "data_supplier", "Sina public quotation endpoints",
            "sina_public_http", ("quote", "minute_kline_1m", "index"), "SOURCE_AUDITED_LOCAL",
            "BENCHMARK_REQUIRED",
        ),
        "pyqauto_astock_source_router": StockDataCandidate(
            "pyqauto_astock_source_router", "tabman2026/pyqauto", "UNVERIFIED", "source audit incomplete", "Python", "UNVERIFIED", "source audit incomplete",
            "gateway_router", "UNVERIFIED_AGGREGATE", "UNVERIFIED_AGGREGATE", (), "SOURCE_AUDITED_REMOTE_PARTIAL", "RESEARCH_ONLY",
        ),
        "open_stock_data": StockDataCandidate(
            "open_stock_data", "UNVERIFIED", "UNVERIFIED", "repository identity ambiguous", "UNVERIFIED", "UNVERIFIED", "repository identity ambiguous",
            "UNVERIFIED", "UNVERIFIED", "UNVERIFIED", (), "UNVERIFIED", "RESEARCH_ONLY",
        ),
        "stock_data_mcp": StockDataCandidate(
            "stock_data_mcp", "UNVERIFIED", "UNVERIFIED", "repository/source audit incomplete", "UNVERIFIED", "UNVERIFIED", "repository/source audit incomplete",
            "mcp_skill", "UNVERIFIED_AGGREGATE", "UNVERIFIED_AGGREGATE", (), "UNVERIFIED", "RESEARCH_ONLY",
        ),
        "a_stock_data": StockDataCandidate(
            "a_stock_data", "UNVERIFIED", "UNVERIFIED", "repository identity ambiguous", "UNVERIFIED", "UNVERIFIED", "repository identity ambiguous",
            "UNVERIFIED", "UNVERIFIED", "UNVERIFIED", (), "UNVERIFIED", "RESEARCH_ONLY",
        ),
        "stock_data": StockDataCandidate(
            "stock_data", "UNVERIFIED", "UNVERIFIED", "repository identity ambiguous", "UNVERIFIED", "UNVERIFIED", "repository identity ambiguous",
            "UNVERIFIED", "UNVERIFIED", "UNVERIFIED", (), "UNVERIFIED", "RESEARCH_ONLY",
        ),
    }


@dataclass
class ProbeResult:
    source: str
    supplier: str
    data_type: str
    symbol: str
    started_at: str
    latency_ms: int
    success: bool
    fields: Dict[str, Any]
    expected_fields: List[str]
    evidence_hash: str
    operation: str = ""
    upstream_identity: str = ""
    independence_group: str = ""
    error_type: str = ""
    error_message: str = ""
    freshness_at: str = ""
    lineage_observable: bool = True
    endpoint: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SafetyDecision:
    action: str
    reason: str
    selected_source: str = ""
    conflicts: List[str] = None
    missing_fields: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MarketState(str, Enum):
    TRADING_DAY = "trading_day"
    HOLIDAY = "holiday"
    WEEKEND = "weekend"
    PRE_MARKET = "pre_market"
    TRADING = "trading"
    LUNCH = "lunch"
    POST_MARKET = "post_market"


@dataclass(frozen=True)
class MarketStateResult:
    state: MarketState
    market_date: str
    reason: str


@dataclass
class DataQualityDecision:
    data_quality_status: str
    recommendation_eligibility: str
    reason: str
    selected_source: str = ""
    market_state: str = ""
    protocol_steps: List[str] = None
    conflicts: List[str] = None
    missing_fields: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


A_SHARE_HOLIDAYS = {
    date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3),
    date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18), date(2026, 2, 19), date(2026, 2, 20), date(2026, 2, 21), date(2026, 2, 22),
    date(2026, 4, 4), date(2026, 4, 5), date(2026, 4, 6),
    date(2026, 5, 1), date(2026, 5, 2), date(2026, 5, 3), date(2026, 5, 4), date(2026, 5, 5),
    date(2026, 6, 19), date(2026, 6, 20), date(2026, 6, 21),
    date(2026, 9, 25), date(2026, 9, 26), date(2026, 9, 27),
    date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3), date(2026, 10, 4), date(2026, 10, 5), date(2026, 10, 6), date(2026, 10, 7),
}


def _to_china_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone(timedelta(hours=8)))
    return value.astimezone(timezone(timedelta(hours=8)))


def assess_market_state(now: datetime) -> MarketStateResult:
    current = _to_china_time(now)
    market_date = current.date()
    if market_date in A_SHARE_HOLIDAYS:
        return MarketStateResult(MarketState.HOLIDAY, market_date.isoformat(), "configured_a_share_holiday")
    if current.weekday() >= 5:
        return MarketStateResult(MarketState.WEEKEND, market_date.isoformat(), "weekend")
    local_time = current.time()
    if local_time < clock_time(9, 15):
        return MarketStateResult(MarketState.PRE_MARKET, market_date.isoformat(), "before_auction")
    if local_time < clock_time(11, 30):
        return MarketStateResult(MarketState.TRADING, market_date.isoformat(), "morning_session")
    if local_time < clock_time(13, 0):
        return MarketStateResult(MarketState.LUNCH, market_date.isoformat(), "lunch_break")
    if local_time <= clock_time(15, 0):
        return MarketStateResult(MarketState.TRADING, market_date.isoformat(), "afternoon_session")
    return MarketStateResult(MarketState.POST_MARKET, market_date.isoformat(), "after_close")


def _probe_age_seconds(probe: Dict[str, Any], now: datetime) -> Optional[float]:
    timestamp = probe.get("freshness_at") or probe.get("started_at")
    if not timestamp:
        return None
    try:
        measured = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
    except ValueError:
        return None
    if measured.tzinfo is None:
        measured = measured.replace(tzinfo=timezone.utc)
    return max(0.0, (now.astimezone(timezone.utc) - measured.astimezone(timezone.utc)).total_seconds())


def _provider_degraded(source: str, health: Dict[str, Dict[str, Any]]) -> bool:
    metrics = health.get(source, {})
    return any(metrics.get(field, 0.0) < threshold for field, threshold in {
        "availability": 0.8,
        "field_completeness": 0.8,
        "coverage": 0.8,
        "consistency": 0.7,
    }.items())


def evaluate_data_quality(
    market: MarketStateResult,
    primary: Dict[str, Any],
    standby: Dict[str, Any],
    provider_health: Dict[str, Dict[str, Any]],
    now: datetime,
    freshness_seconds: int = 120,
) -> DataQualityDecision:
    if market.state != MarketState.TRADING:
        return DataQualityDecision("MARKET_CLOSED", "research_only", market.reason, market_state=market.state.value, protocol_steps=["market_state_gate"])
    primary_source = primary.get("source", "primary")
    standby_source = standby.get("source", "standby")
    active_sources = [standby_source] if not primary.get("success") else [primary_source, standby_source]
    if any(_provider_degraded(source, provider_health) for source in active_sources):
        return DataQualityDecision("DEGRADED", "do_not_recommend", "provider_health_below_runtime_threshold", market_state=market.state.value, protocol_steps=["market_state_gate", "provider_health_check"])
    active_probes = [standby] if not primary.get("success") else [primary, standby]
    ages = [_probe_age_seconds(probe, now) for probe in active_probes if probe.get("success")]
    if any(age is None or age > freshness_seconds for age in ages):
        return DataQualityDecision("STALE", "do_not_recommend", "quote_freshness_exceeds_runtime_limit", market_state=market.state.value, protocol_steps=["market_state_gate", "provider_health_check", "freshness_check"])
    decision = decide_safe_fallback(primary, standby)
    if decision.action == "do_not_recommend":
        status = "CONFLICT" if decision.conflicts else "UNAVAILABLE"
        return DataQualityDecision(status, "do_not_recommend", decision.reason, market_state=market.state.value, protocol_steps=["market_state_gate", "provider_health_check", "field_validation", "consistency_check"], conflicts=decision.conflicts or [], missing_fields=decision.missing_fields or [])
    steps = ["primary_health_check"]
    if decision.action == "use_hot_standby":
        steps.append("standby_field_validation")
    else:
        steps.append("cross_source_consistency_check")
    steps.append("recommendation_eligible")
    return DataQualityDecision("READY", "eligible", decision.reason, decision.selected_source, market.state.value, steps, [], [])


class DataQualityProtocol:
    def evaluate(
        self,
        now: datetime,
        primary: Dict[str, Any],
        standby: Dict[str, Any],
        provider_health: Dict[str, Dict[str, Any]],
        freshness_seconds: int = 120,
    ) -> DataQualityDecision:
        return evaluate_data_quality(assess_market_state(now), primary, standby, provider_health, now, freshness_seconds)


def _run_source_batch(source: str, advisor_dir: str, symbol: str, connection) -> None:
    try:
        benchmark = StockDataBenchmark(".", advisor_dir or None)
        factories = {
            "akshare": benchmark._akshare_probes,
            "baostock": benchmark._baostock_probes,
            "finshare": benchmark._finshare_probes,
            "pytdx": benchmark._pytdx_probes,
            "tencent": benchmark._tencent_probes,
            "sina": benchmark._sina_probes,
        }
        probes = benchmark._market_probes() if source == "market" else factories[source](symbol)
        connection.send({"ok": True, "probes": [probe.to_dict() for probe in probes]})
    except BaseException as exc:
        connection.send({"ok": False, "error_type": type(exc).__name__, "error_message": str(exc)[:500]})
    finally:
        connection.close()


def _json_safe(value: Any) -> Any:
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if hasattr(value, "model_dump"):
        return _json_safe(value.model_dump())
    if hasattr(value, "to_dict"):
        return _json_safe(value.to_dict())
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if hasattr(value, "item"):
        return value.item()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _hash_evidence(value: Any) -> str:
    encoded = json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_number(value: Any) -> Optional[float]:
    try:
        if value in (None, "", "-", "null"):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _quote_code(symbol: str) -> str:
    if symbol.startswith(("4", "8")):
        return f"bj{symbol}"
    return ("sh" if symbol.startswith("6") else "sz") + symbol


def _normalize_quote(value: Any) -> Dict[str, Any]:
    raw = _json_safe(value)
    if isinstance(raw, list):
        raw = raw[0] if raw else {}
    if not isinstance(raw, dict):
        raw = getattr(value, "__dict__", {})
    aliases = {
        "price": ("price", "last_price", "最新价", "close"),
        "change_pct": ("change_pct", "change_percent", "涨跌幅", "pct_chg"),
        "volume": ("volume", "vol", "成交量"),
        "name": ("name", "名称"),
        "time": ("time", "servertime", "timestamp", "更新时间", "datetime"),
    }
    normalized = {}
    for target, choices in aliases.items():
        for choice in choices:
            if choice in raw:
                normalized[target] = raw[choice]
                break
    for field in ("price", "change_pct", "volume"):
        if field in normalized:
            normalized[field] = _safe_number(normalized[field])
    time_value = str(normalized.get("time", ""))
    if re.fullmatch(r"\d{1,2}:\d{2}:\d{2}(?:\.\d+)?", time_value):
        current = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        normalized["time"] = f"{current}T{time_value}+08:00"
    if normalized.get("change_pct") is None:
        previous_close = _safe_number(raw.get("prev_close", raw.get("last_close")))
        if normalized.get("price") is not None and previous_close and previous_close > 0:
            normalized["change_pct"] = (normalized["price"] - previous_close) / previous_close * 100
    return normalized


def _normalize_rows(value: Any, expected: Iterable[str]) -> Dict[str, Any]:
    raw = _json_safe(value)
    if hasattr(value, "to_dict"):
        try:
            rows = value.to_dict("records")
        except TypeError:
            rows = value.to_dict()
        raw = _json_safe(rows)
    if isinstance(raw, list):
        row = raw[-1] if raw else {}
        count = len(raw)
    elif isinstance(raw, dict):
        row = raw
        count = len(raw)
    else:
        row = {}
        count = 0
    if not isinstance(row, dict):
        row = {}
    aliases = {
        "date": ("datetime", "date", "day", "日期", "time"),
        "open": ("open", "开盘"),
        "close": ("close", "收盘", "price"),
        "high": ("high", "最高"),
        "low": ("low", "最低"),
        "volume": ("volume", "vol", "成交量"),
        "main_inflow": ("main_inflow", "main_net_inflow", "主力净流入", "total_main_inflow"),
        "index_value": ("index_value", "price", "最新价", "close"),
    }
    normalized = {"record_count": count}
    for field in expected:
        for alias in aliases.get(field, (field,)):
            if alias in row:
                normalized[field] = row[alias]
                break
    for field in ("open", "close", "high", "low", "volume", "main_inflow", "index_value"):
        if field in normalized:
            normalized[field] = _safe_number(normalized[field])
    return normalized


def _parse_quote_time(fields: Dict[str, Any]) -> str:
    value = fields.get("time", fields.get("date"))
    if value is None:
        return ""
    return str(value)


class StockDataBenchmark:
    def __init__(self, evidence_dir: str, advisor_dir: Optional[str] = None):
        self.evidence_dir = Path(evidence_dir)
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        self.advisor_dir = Path(advisor_dir) if advisor_dir else self._find_advisor_dir()
        self._tencent_query = None

    @staticmethod
    def _find_advisor_dir() -> Optional[Path]:
        configured = os.environ.get("ACE_ADVISOR_WORKSPACE", "").strip()
        roots = [Path(configured)] if configured else []
        roots.append(Path.home() / "ace_workspace" / "mine-seed")
        for root in roots:
            candidate = root / "05_TOOLS" / "advisor"
            if candidate.exists():
                return candidate
        return None

    def _tencent(self):
        if self._tencent_query is not None:
            return self._tencent_query
        if not self.advisor_dir:
            raise RuntimeError("advisor_stock_query_unavailable")
        path = str(self.advisor_dir)
        if path not in sys.path:
            sys.path.insert(0, path)
        from stock_query import StockQuery
        self._tencent_query = StockQuery()
        return self._tencent_query

    def _probe(
        self,
        source: str,
        supplier: str,
        data_type: str,
        symbol: str,
        expected_fields: Iterable[str],
        operation: Callable[[], Any],
        endpoint: str,
        lineage_observable: bool = True,
        normalizer: Callable[[Any], Dict[str, Any]] = None,
        timeout_seconds: int = 20,
        operation_name: str = "",
    ) -> ProbeResult:
        candidate = candidate_registry().get({
            "tencent": "tencent_direct",
            "sina": "sina_direct",
        }.get(source, source))
        operation_name = operation_name or {
            "daily_k": "daily_kline",
            "minute_k": "minute_kline_5m",
        }.get(data_type, data_type)
        started = datetime.now(timezone.utc).isoformat()
        tick = time.perf_counter()
        result = []
        failure = []

        def invoke():
            try:
                result.append(operation())
            except Exception as exc:
                failure.append(exc)

        thread = threading.Thread(target=invoke, daemon=True)
        thread.start()
        thread.join(timeout_seconds)
        try:
            if thread.is_alive():
                raise TimeoutError(f"probe_timeout_after_{timeout_seconds}s")
            if failure:
                raise failure[0]
            raw = result[0]
            fields = (normalizer or (lambda value: _normalize_rows(value, expected_fields)))(raw)
            if raw is None or not fields or fields.get("record_count") == 0:
                raise RuntimeError("empty_or_unparseable_response")
            return ProbeResult(
                source=source,
                supplier=supplier,
                data_type=data_type,
                symbol=symbol,
                started_at=started,
                latency_ms=round((time.perf_counter() - tick) * 1000),
                success=True,
                fields=fields,
                expected_fields=list(expected_fields),
                evidence_hash=_hash_evidence(raw),
                operation=operation_name,
                upstream_identity=candidate.upstream_identity if candidate else "UNVERIFIED",
                independence_group=candidate.independence_group if candidate else "UNVERIFIED",
                freshness_at=_parse_quote_time(fields),
                lineage_observable=lineage_observable,
                endpoint=endpoint,
            )
        except Exception as exc:
            return ProbeResult(
                source=source,
                supplier=supplier,
                data_type=data_type,
                symbol=symbol,
                started_at=started,
                latency_ms=round((time.perf_counter() - tick) * 1000),
                success=False,
                fields={},
                expected_fields=list(expected_fields),
                evidence_hash="",
                operation=operation_name,
                upstream_identity=candidate.upstream_identity if candidate else "UNVERIFIED",
                independence_group=candidate.independence_group if candidate else "UNVERIFIED",
                error_type=type(exc).__name__,
                error_message=str(exc)[:500],
                lineage_observable=lineage_observable,
                endpoint=endpoint,
            )

    def _akshare_probes(self, symbol: str) -> List[ProbeResult]:
        import akshare as ak
        market = "sh" if symbol.startswith("6") or symbol.startswith("688") else "sz"
        return [
            self._probe("akshare", "akshare_aggregate", "quote", symbol, CRITICAL_QUOTE_FIELDS,
                        lambda: ak.stock_zh_a_spot_em().query("代码 == @symbol").to_dict("records"),
                        "ak.stock_zh_a_spot_em", normalizer=_normalize_quote),
            self._probe("akshare", "akshare_aggregate", "daily_k", symbol, CRITICAL_DAILY_FIELDS,
                        lambda: ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date="20260801", end_date="20260821", adjust="qfq"),
                        "ak.stock_zh_a_hist"),
            self._probe("akshare", "akshare_aggregate", "minute_k", symbol, ("date", "open", "close", "high", "low", "volume"),
                        lambda: ak.stock_zh_a_hist_min_em(symbol=symbol, period="1", adjust="qfq"),
                        "ak.stock_zh_a_hist_min_em", operation_name="minute_kline_1m"),
            self._probe("akshare", "akshare_aggregate", "minute_k", symbol, ("date", "open", "close", "high", "low", "volume"),
                        lambda: ak.stock_zh_a_hist_min_em(symbol=symbol, period="5", adjust="qfq"),
                        "ak.stock_zh_a_hist_min_em", operation_name="minute_kline_5m"),
            self._probe("akshare", "akshare_aggregate", "fund_flow", symbol, ("main_inflow",),
                        lambda: ak.stock_individual_fund_flow(stock=symbol, market=market),
                        "ak.stock_individual_fund_flow"),
        ]

    @staticmethod
    def _baostock_code(symbol: str) -> str:
        return ("sh." if symbol.startswith("6") else "sz.") + symbol

    @staticmethod
    def _pytdx_market(symbol: str) -> int:
        return 1 if symbol.startswith("6") else 0

    @staticmethod
    def _pytdx_hosts() -> Tuple[Tuple[str, str, int], ...]:
        from pytdx.config.hosts import hq_hosts

        # The installed pytdx registry is the audited host pool.  Keep failover
        # bounded so an unavailable pool cannot consume the whole source-batch
        # timeout, while avoiding the former single-host availability verdict.
        unique = []
        seen = set()
        for host in hq_hosts:
            endpoint = (host[1], host[2])
            if endpoint in seen:
                continue
            seen.add(endpoint)
            unique.append(host)
            if len(unique) == 8:
                break
        return tuple(unique)

    @staticmethod
    def _baostock_rows(result: Any) -> List[Dict[str, Any]]:
        rows = []
        while result.error_code == "0" and result.next():
            rows.append(dict(zip(result.fields, result.get_row_data())))
        if result.error_code != "0":
            raise RuntimeError(f"baostock_query_failed:{result.error_code}:{result.error_msg}")
        return rows

    def _baostock_probes(self, symbol: str) -> List[ProbeResult]:
        import baostock as bs

        code = self._baostock_code(symbol)
        login = bs.login()
        if login.error_code != "0":
            raise RuntimeError(f"baostock_login_failed:{login.error_code}:{login.error_msg}")
        try:
            return [
                self._probe("baostock", "baostock", "daily_k", symbol, CRITICAL_DAILY_FIELDS,
                            lambda: self._baostock_rows(bs.query_history_k_data_plus(
                                code, "date,open,high,low,close,volume", "2026-08-01", "2026-08-21", "d", "3"
                            )), "baostock://public-api/history/daily"),
                self._probe("baostock", "baostock", "minute_k", symbol, CRITICAL_DAILY_FIELDS,
                            lambda: self._baostock_rows(bs.query_history_k_data_plus(
                                code, "date,time,open,high,low,close,volume", "2026-08-20", "2026-08-21", "5", "3"
                            )), "baostock://public-api/history/5m", operation_name="minute_kline_5m"),
            ]
        finally:
            bs.logout()

    def _pytdx_probes(self, symbol: str) -> List[ProbeResult]:
        from pytdx.hq import TdxHq_API

        api = None
        selected = None
        attempted = []
        initial_quote = None
        market = self._pytdx_market(symbol)
        for host_name, host, port in self._pytdx_hosts():
            candidate_api = TdxHq_API()
            attempted.append(f"{host}:{port}")
            if candidate_api.connect(host, port, time_out=3):
                quote = candidate_api.get_security_quotes([(market, symbol)])
                if quote:
                    api = candidate_api
                    initial_quote = quote
                    selected = (host_name, host, port)
                    break
            candidate_api.disconnect()
        if api is None or selected is None:
            raise RuntimeError(f"pytdx_host_pool_exhausted:{','.join(attempted)}")

        host_name, host, port = selected
        endpoint = f"tdx://{host}:{port}"
        try:
            return [
                self._probe("pytdx", "pytdx", "quote", symbol, CRITICAL_QUOTE_FIELDS,
                            lambda: initial_quote, endpoint, normalizer=_normalize_quote),
                self._probe("pytdx", "pytdx", "daily_k", symbol, CRITICAL_DAILY_FIELDS,
                            lambda: api.get_security_bars(9, market, symbol, 0, 15), endpoint),
                self._probe("pytdx", "pytdx", "minute_k", symbol, CRITICAL_DAILY_FIELDS,
                            lambda: api.get_security_bars(8, market, symbol, 0, 120), endpoint, operation_name="minute_kline_1m"),
                self._probe("pytdx", "pytdx", "minute_k", symbol, CRITICAL_DAILY_FIELDS,
                            lambda: api.get_security_bars(0, market, symbol, 0, 120), endpoint, operation_name="minute_kline_5m"),
                self._probe("pytdx", "pytdx", "index", "000001", ("index_value",),
                            lambda: api.get_index_bars(8, 1, "000001", 0, 15), endpoint,
                            normalizer=lambda value: _normalize_rows(value, ("index_value", "date"))),
                self._probe("pytdx", "pytdx", "stock_pool", "all", ("record_count",),
                            lambda: api.get_security_list(market, 0), endpoint),
            ]
        finally:
            api.disconnect()

    def _tencent_minute(self, symbol: str, interval: str) -> List[Dict[str, Any]]:
        code = _quote_code(symbol)
        key = f"m{interval}"
        url = f"https://web.ifzq.gtimg.cn/appstock/app/kline/mkline?param={code},{key},,,120"
        with urllib.request.urlopen(url, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        rows = payload.get("data", {}).get(code, {}).get(key, [])
        return [
            {"date": row[0], "open": row[1], "close": row[2], "high": row[3], "low": row[4], "volume": row[5]}
            for row in rows if len(row) >= 6
        ]

    def _tencent_probes(self, symbol: str) -> List[ProbeResult]:
        query = self._tencent()
        quote_code = _quote_code(symbol)
        return [
            self._probe("tencent", "tencent", "quote", symbol, CRITICAL_QUOTE_FIELDS,
                        lambda: query.get_quote([quote_code]), "qt.gtimg.cn/q", normalizer=_normalize_quote),
            self._probe("tencent", "tencent", "daily_k", symbol, CRITICAL_DAILY_FIELDS,
                        lambda: query.get_hist_kline(symbol, days=15), "web.ifzq.gtimg.cn/app/fqkline"),
            self._probe("tencent", "tencent", "minute_k", symbol, ("date", "open", "close", "high", "low", "volume"),
                        lambda: self._tencent_minute(symbol, "1"), "web.ifzq.gtimg.cn/app/kline/mkline", operation_name="minute_kline_1m"),
            self._probe("tencent", "tencent", "minute_k", symbol, ("date", "open", "close", "high", "low", "volume"),
                        lambda: self._tencent_minute(symbol, "5"), "web.ifzq.gtimg.cn/app/kline/mkline", operation_name="minute_kline_5m"),
            self._probe("tencent", "tencent", "fund_flow", symbol, ("main_inflow",),
                        lambda: query.get_fund_flow(symbol), "qt.gtimg.cn/q=ff_"),
        ]

    @staticmethod
    def _sina_request(url: str, encoding: str = "utf-8") -> str:
        request = urllib.request.Request(url, headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(request, timeout=12) as response:
            return response.read().decode(encoding, errors="replace")

    @staticmethod
    def _require_current_sina_date(value: str) -> None:
        current = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        if value != current:
            raise RuntimeError(f"sina_stale_or_nontrading_date:{value or 'missing'}:{current}")

    def _sina_quote_code(self, code: str) -> Dict[str, Any]:
        body = self._sina_request(f"https://hq.sinajs.cn/list={code}", "gbk")
        match = re.search(r'="(.*)";', body)
        values = match.group(1).split(",") if match else []
        if len(values) < 32:
            raise RuntimeError("sina_quote_unparseable")
        self._require_current_sina_date(values[30])
        price = _safe_number(values[3])
        previous_close = _safe_number(values[2])
        volume = _safe_number(values[8])
        if not price or not previous_close or volume is None:
            raise RuntimeError("sina_quote_missing_critical_fields")
        return {
            "price": price,
            "prev_close": previous_close,
            "volume": volume,
            "time": f"{values[30]}T{values[31]}+08:00",
        }

    def _sina_quote(self, symbol: str) -> Dict[str, Any]:
        return self._sina_quote_code(_quote_code(symbol))

    def _sina_minute(self, symbol: str) -> List[Dict[str, Any]]:
        code = _quote_code(symbol)
        url = (
            "https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_data=/"
            "CN_MarketDataService.getKLineData"
            f"?symbol={code}&scale=1&ma=no&datalen=120"
        )
        body = self._sina_request(url)
        start, end = body.find("["), body.rfind("]")
        if start < 0 or end < start:
            raise RuntimeError("sina_minute_unparseable")
        rows = json.loads(body[start:end + 1])
        if not rows:
            raise RuntimeError("sina_minute_empty")
        self._require_current_sina_date(str(rows[-1].get("day", ""))[:10])
        return rows

    def _sina_index(self) -> Dict[str, Any]:
        quote = self._sina_quote_code("sh000001")
        return {"index_value": quote["price"], "time": quote["time"]}

    def _sina_probes(self, symbol: str) -> List[ProbeResult]:
        return [
            self._probe("sina", "sina", "quote", symbol, CRITICAL_QUOTE_FIELDS,
                        lambda: self._sina_quote(symbol), "hq.sinajs.cn/list", normalizer=_normalize_quote),
            self._probe("sina", "sina", "minute_k", symbol, CRITICAL_DAILY_FIELDS,
                        lambda: self._sina_minute(symbol), "quotes.sina.cn/CN_MarketDataService.getKLineData",
                        operation_name="minute_kline_1m"),
            self._probe("sina", "sina", "index", "000001", ("index_value",),
                        self._sina_index, "hq.sinajs.cn/list=sh000001",
                        normalizer=lambda value: _normalize_rows(value, ("index_value", "time"))),
        ]

    def _finshare_probes(self, symbol: str) -> List[ProbeResult]:
        import finshare as fs
        code = symbol + (".BJ" if symbol.startswith(("4", "8")) else ".SH" if symbol.startswith("6") else ".SZ")
        supplier = "finshare_auto_router"
        return [
            self._probe("finshare", supplier, "quote", symbol, CRITICAL_QUOTE_FIELDS,
                        lambda: fs.get_snapshot_data(code), "finshare.get_snapshot_data", False, _normalize_quote),
            self._probe("finshare", supplier, "daily_k", symbol, CRITICAL_DAILY_FIELDS,
                        lambda: fs.get_historical_data(code, start="2026-08-01", end="2026-08-21", period="daily", adjust="qfq"),
                        "finshare.get_historical_data", False, timeout_seconds=10),
            self._probe("finshare", supplier, "fund_flow", symbol, ("main_inflow",),
                        lambda: fs.get_money_flow(code), "finshare.get_money_flow", False),
        ]

    def _source_probes(self, source: str, symbol: str, timeout_seconds: int = 35) -> List[ProbeResult]:
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        process = context.Process(
            target=_run_source_batch,
            args=(source, str(self.advisor_dir or ""), symbol, child),
        )
        started = datetime.now(timezone.utc).isoformat()
        tick = time.perf_counter()
        process.start()
        child.close()
        process.join(timeout_seconds)
        if process.is_alive():
            process.terminate()
            process.join(5)
            if process.is_alive():
                process.kill()
                process.join(5)
            return [self._source_failure(source, symbol, started, tick, "ProbeTimeout", f"source_batch_terminated_after_{timeout_seconds}s")]
        try:
            payload = parent.recv() if parent.poll() else {}
        finally:
            parent.close()
        if payload.get("ok"):
            return [ProbeResult(**probe) for probe in payload.get("probes", [])]
        return [self._source_failure(
            source,
            symbol,
            started,
            tick,
            payload.get("error_type", "SourceBatchFailure"),
            payload.get("error_message", "source_batch_returned_no_evidence"),
        )]

    @staticmethod
    def _source_failure(source: str, symbol: str, started: str, tick: float, error_type: str, error_message: str) -> ProbeResult:
        suppliers = {
            "akshare": "akshare_aggregate",
            "baostock": "baostock",
            "finshare": "finshare_auto_router",
            "pytdx": "pytdx",
            "sina": "sina",
            "tencent": "tencent",
            "market": "market_aggregate",
        }
        candidate = candidate_registry().get({
            "tencent": "tencent_direct",
            "sina": "sina_direct",
        }.get(source, source))
        return ProbeResult(
            source=source,
            supplier=suppliers[source],
            data_type="source_batch",
            symbol=symbol,
            started_at=started,
            latency_ms=round((time.perf_counter() - tick) * 1000),
            success=False,
            fields={},
            expected_fields=[],
            evidence_hash="",
            upstream_identity=candidate.upstream_identity if candidate else "UNVERIFIED",
            independence_group=candidate.independence_group if candidate else "UNVERIFIED",
            error_type=error_type,
            error_message=error_message[:500],
            lineage_observable=source != "finshare",
            endpoint="isolated_source_batch",
        )

    def _market_probes(self) -> List[ProbeResult]:
        import akshare as ak
        results = [
            self._probe("akshare", "akshare_aggregate", "index", "000001", ("index_value",),
                        lambda: ak.stock_zh_index_spot_em().query("代码 == '000001'").to_dict("records"),
                        "ak.stock_zh_index_spot_em", normalizer=lambda value: _normalize_rows(value, ("index_value",))),
            self._probe("akshare", "akshare_aggregate", "stock_pool", "all", ("record_count",),
                        lambda: ak.stock_zh_a_spot_em(), "ak.stock_zh_a_spot_em"),
            self._probe("akshare", "akshare_aggregate", "etf", "510300", ("record_count",),
                        lambda: ak.fund_etf_spot_em().query("代码 == '510300'").to_dict("records"),
                        "ak.fund_etf_spot_em"),
        ]
        try:
            import finshare as fs
            results.extend([
                self._probe("finshare", "finshare_auto_router", "stock_pool", "all", ("record_count",),
                            lambda: fs.get_stock_list(), "finshare.get_stock_list", False),
                self._probe("finshare", "finshare_auto_router", "index", "market_overview", ("index_value",),
                            lambda: fs.get_market_overview(), "finshare.get_market_overview", False),
            ])
        except ImportError:
            pass
        results.append(ProbeResult(
            source="tencent", supplier="tencent", data_type="stock_pool", symbol="all",
            started_at=datetime.now(timezone.utc).isoformat(), latency_ms=0, success=False, fields={"coverage_limit": 600},
            expected_fields=["record_count"], evidence_hash="", error_type="CapabilityGap",
            error_message="production adapter uses a bounded hardcoded hot-stock pool; no full-market endpoint is implemented",
            endpoint="stock_advisor._get_spot_from_tencent",
        ))
        return results

    def run(self, rounds: int = 3, symbols: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        symbols = symbols or DEFAULT_SYMBOLS
        run = {
            "schema_version": 1,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "rounds": rounds,
            "symbols": symbols,
            "source_lineage": {
                "akshare": "aggregation SDK; upstream varies by endpoint and is not independent by package name",
                "baostock": "direct BaoStock TCP login and historical-query protocol; operation support must be evidenced per probe",
                "finshare": "multi-provider routing wrapper; automatic route is not independent and may select Tencent/EastMoney/Sina/TDX/BaoStock",
                "pytdx": "direct TDX quotation protocol connection; each probe records the selected host and port",
                "tencent": "direct Tencent endpoints used by current fallback adapter",
            },
            "probes": [],
        }
        for round_number in range(1, rounds + 1):
            for symbol in symbols.values():
                for source in ("akshare", "finshare", "tencent", "baostock", "pytdx", "sina"):
                    for probe in self._source_probes(source, symbol):
                        item = probe.to_dict()
                        item["round"] = round_number
                        run["probes"].append(item)
            market_probes = self._source_probes("market", "all", timeout_seconds=40)
            for probe in market_probes:
                item = probe.to_dict()
                item["round"] = round_number
                run["probes"].append(item)
        run["completed_at"] = datetime.now(timezone.utc).isoformat()
        run["summary"] = evaluate_health(run["probes"])
        self._persist_run(run)
        return run

    def refresh_live_operations(
        self,
        *,
        rounds: int = 1,
        symbols: Optional[Dict[str, str]] = None,
        sources: Tuple[str, ...] = ("pytdx", "sina"),
        operations: Tuple[str, ...] = ("quote", "minute_kline_1m", "index"),
        batch_timeout_seconds: int = 25,
    ) -> Dict[str, Any]:
        """Refresh live-operation evidence without discarding historical gates.

        Daily/5m evidence remains attached to its original probes.  Only the
        selected live operations for the selected direct sources are replaced,
        preserving explicit lineage and the parent benchmark timestamp.
        """
        latest_path = self.evidence_dir / "stock_data_benchmark_latest.json"
        try:
            previous = json.loads(latest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("baseline_benchmark_required_for_live_refresh") from exc
        if not isinstance(previous, dict) or not isinstance(previous.get("probes"), list):
            raise RuntimeError("baseline_benchmark_required_for_live_refresh")

        symbols = symbols or DEFAULT_SYMBOLS
        source_set = set(sources)
        operation_set = set(operations)
        retained = [
            probe for probe in previous["probes"]
            if not (
                probe.get("source") in source_set
                and (
                    probe.get("operation") in operation_set
                    or probe.get("data_type") == "source_batch"
                )
            )
        ]
        refreshed = []
        started_at = datetime.now(timezone.utc).isoformat()
        for round_number in range(1, rounds + 1):
            for symbol in symbols.values():
                for source in sources:
                    for probe in self._source_probes(
                        source,
                        symbol,
                        timeout_seconds=batch_timeout_seconds,
                    ):
                        item = probe.to_dict()
                        if (
                            item.get("data_type") == "source_batch"
                            and not item.get("operation")
                        ):
                            for operation in operations:
                                operation_failure = dict(item)
                                operation_failure["operation"] = operation
                                operation_failure["round"] = round_number
                                refreshed.append(operation_failure)
                            continue
                        if item.get("operation") not in operation_set:
                            continue
                        item["round"] = round_number
                        refreshed.append(item)

        run = {
            "schema_version": 1,
            "started_at": started_at,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "rounds": rounds,
            "symbols": symbols,
            "source_lineage": previous.get("source_lineage", {}),
            "probes": retained + refreshed,
            "incremental_refresh": {
                "kind": "trading_window_live_operations",
                "parent_completed_at": previous.get("completed_at"),
                "sources": list(sources),
                "operations": list(operations),
                "retained_probe_count": len(retained),
                "refreshed_probe_count": len(refreshed),
            },
        }
        run["summary"] = evaluate_health(run["probes"])
        self._persist_run(run)
        return run

    def _persist_run(self, run: Dict[str, Any]) -> None:
        matrix = build_capability_matrix(candidate_registry(), run)
        run["capability_matrix_path"] = str(self.evidence_dir / "A_SHARE_DATA_CAPABILITY_MATRIX.json")
        stamped = datetime.now().strftime("%Y%m%d_%H%M%S")
        raw_path = self.evidence_dir / f"stock_data_benchmark_{stamped}.json"
        latest_path = self.evidence_dir / "stock_data_benchmark_latest.json"
        payload = json.dumps(run, ensure_ascii=False, indent=2)
        matrix_path = self.evidence_dir / "A_SHARE_DATA_CAPABILITY_MATRIX.json"
        raw_path.write_text(payload, encoding="utf-8")
        latest_temporary = latest_path.with_suffix(latest_path.suffix + ".tmp")
        latest_temporary.write_text(payload, encoding="utf-8")
        latest_temporary.replace(latest_path)
        matrix_temporary = matrix_path.with_suffix(matrix_path.suffix + ".tmp")
        matrix_temporary.write_text(
            json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        matrix_temporary.replace(matrix_path)


def _complete(probe: Dict[str, Any]) -> bool:
    if not probe.get("success"):
        return False
    fields = probe.get("fields", {})
    expected = probe.get("expected_fields", [])
    return all(fields.get(field) not in (None, "") for field in expected if field != "record_count")


def evaluate_health(probes: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    probes = list(probes)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for probe in probes:
        grouped[probe["source"]].append(probe)
    sources = {}
    for source, entries in grouped.items():
        success = [entry for entry in entries if entry.get("success")]
        latency = sorted(entry["latency_ms"] for entry in success)
        complete = [entry for entry in entries if _complete(entry)]
        types = Counter(entry["data_type"] for entry in success)
        failures = Counter(entry.get("error_type") or "unknown" for entry in entries if not entry.get("success"))
        consistency = _consistency(entries, probes)
        availability = len(success) / len(entries) if entries else 0.0
        completeness = len(complete) / len(entries) if entries else 0.0
        median_latency = latency[len(latency) // 2] if latency else None
        p95_latency = latency[max(0, (len(latency) * 95 + 99) // 100 - 1)] if latency else None
        coverage = _coverage(entries)
        operation_coverage = _operation_coverage(entries)
        operation_quality = _operation_quality(entries, probes)
        timeout_rate = sum(
            1 for entry in entries
            if "timeout" in str(entry.get("error_type", "")).lower()
        ) / len(entries) if entries else 0.0
        lineage_observable = all(entry.get("lineage_observable", True) for entry in entries)
        upstream_identities = {
            str(entry.get("upstream_identity", "")).strip()
            for entry in entries
            if str(entry.get("upstream_identity", "")).strip()
        }
        independence_groups = {
            str(entry.get("independence_group", "")).strip()
            for entry in entries
            if str(entry.get("independence_group", "")).strip()
        }
        upstream_identity = (
            next(iter(upstream_identities))
            if len(upstream_identities) == 1
            else "UNVERIFIED"
        )
        independence_group = (
            next(iter(independence_groups))
            if len(independence_groups) == 1
            else "UNVERIFIED"
        )
        score = round(100 * (0.30 * availability + 0.20 * completeness + 0.15 * coverage + 0.20 * consistency + 0.15 * (1 if median_latency is not None and median_latency <= 5000 else 0)), 1)
        sources[source] = {
            "availability": round(availability, 3),
            "latency_ms_median": median_latency,
            "p95_latency_ms": p95_latency,
            "timeout_rate": round(timeout_rate, 3),
            "operation_coverage": operation_coverage,
            "operation_quality": operation_quality,
            "freshness": "endpoint timestamp captured only for quote; historical freshness must be assessed against market calendar",
            "coverage": round(coverage, 3),
            "field_completeness": round(completeness, 3),
            "consistency": round(consistency, 3),
            "error_rate": round(1 - availability, 3),
            "stability": round(availability * completeness, 3),
            "successful_data_types": dict(types),
            "failure_reasons": dict(failures),
            "lineage_observable": lineage_observable,
            "upstream_identity": upstream_identity,
            "independence_group": independence_group,
            "health_score": score,
            "recommended_role": _role(source, availability, completeness, coverage, consistency, lineage_observable),
        }
    return {"generated_at": datetime.now(timezone.utc).isoformat(), "sources": sources}


def _operation_coverage(entries: List[Dict[str, Any]]) -> Dict[str, float]:
    declared = {entry.get("operation") or entry.get("data_type") for entry in entries}
    return {
        operation: float(any(
            entry.get("success")
            and (entry.get("operation") or entry.get("data_type")) == operation
            for entry in entries
        ))
        for operation in sorted(declared)
        if operation
    }


def _coverage(entries: List[Dict[str, Any]]) -> float:
    market = [entry for entry in entries if entry["data_type"] == "stock_pool"]
    if not market:
        return 0.0
    success = [entry for entry in market if entry.get("success") and entry.get("fields", {}).get("record_count", 0) >= 1000]
    return len(success) / len(market)


def _fresh_probe(entry: Dict[str, Any], max_age_seconds: int = 300) -> bool:
    value = str(entry.get("freshness_at", "")).strip()
    if not value:
        return False
    try:
        observed = datetime.fromisoformat(value)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone(timedelta(hours=8)))
        sampled = datetime.fromisoformat(entry["started_at"])
        if sampled.tzinfo is None:
            sampled = sampled.replace(tzinfo=timezone.utc)
        age = (sampled.astimezone(timezone.utc) - observed.astimezone(timezone.utc)).total_seconds()
        return -90 <= age <= max_age_seconds
    except (KeyError, TypeError, ValueError):
        return False


def _operation_quality(entries: List[Dict[str, Any]], all_probes: List[Dict[str, Any]]) -> Dict[str, Dict[str, float]]:
    operations = sorted({entry.get("operation") for entry in entries if entry.get("operation")})
    quality = {}
    for operation in operations:
        samples = [entry for entry in entries if entry.get("operation") == operation]
        successes = [entry for entry in samples if entry.get("success")]
        expected_keys = {(entry.get("symbol"), entry.get("round")) for entry in samples}
        covered_keys = {(entry.get("symbol"), entry.get("round")) for entry in successes}
        quality[operation] = {
            "availability": round(len(successes) / len(samples), 3) if samples else 0.0,
            "coverage": round(len(covered_keys) / len(expected_keys), 3) if expected_keys else 0.0,
            "field_completeness": round(sum(_complete(entry) for entry in samples) / len(samples), 3) if samples else 0.0,
            "freshness": round(sum(_fresh_probe(entry) for entry in samples) / len(samples), 3) if samples else 0.0,
            "consistency": round(_operation_consistency(entries, all_probes, operation), 3),
            "sample_count": len(samples),
        }
    return quality


def _operation_consistency(entries: List[Dict[str, Any]], all_entries: List[Dict[str, Any]], operation: str) -> float:
    fields = {"quote": "price", "index": "index_value"}
    field = fields.get(operation, "close")
    checks = matches = 0
    for entry in entries:
        if not entry.get("success") or entry.get("operation") != operation:
            continue
        entry_group = entry.get("independence_group", "UNVERIFIED")
        peers = [candidate for candidate in all_entries if (
            candidate.get("success")
            and candidate.get("operation") == operation
            and candidate.get("symbol") == entry.get("symbol")
            and candidate.get("round") == entry.get("round")
            and candidate.get("source") != entry.get("source")
            and candidate.get("independence_group", "UNVERIFIED") not in {entry_group, "UNVERIFIED", "UNVERIFIED_AGGREGATE"}
        )]
        left = _safe_number(entry.get("fields", {}).get(field))
        for peer in peers:
            right = _safe_number(peer.get("fields", {}).get(field))
            if left is None or right is None or left == 0:
                continue
            checks += 1
            if abs(left - right) / abs(left) <= 0.02:
                matches += 1
    return matches / checks if checks else 0.0


def _consistency(entries: List[Dict[str, Any]], all_probes: Iterable[Dict[str, Any]]) -> float:
    checks = 0
    matches = 0
    all_entries = list(all_probes)
    for entry in entries:
        if not entry.get("success") or entry["data_type"] not in {"quote", "daily_k"}:
            continue
        key = (entry["data_type"], entry["symbol"], entry.get("round"))
        entry_group = entry.get("independence_group", "UNVERIFIED")
        peers = [
            candidate for candidate in all_entries
            if (candidate["data_type"], candidate["symbol"], candidate.get("round")) == key
            and candidate.get("success")
            and candidate["source"] != entry["source"]
            and candidate.get("independence_group", "UNVERIFIED") not in {entry_group, "UNVERIFIED", "UNVERIFIED_AGGREGATE"}
        ]
        for peer in peers:
            field = "price" if entry["data_type"] == "quote" else "close"
            left = _safe_number(entry.get("fields", {}).get(field))
            right = _safe_number(peer.get("fields", {}).get(field))
            if left is None or right is None or left == 0:
                continue
            checks += 1
            if abs(left - right) / abs(left) <= 0.02:
                matches += 1
    return matches / checks if checks else 0.0


def _role(source: str, availability: float, completeness: float, coverage: float, consistency: float, lineage_observable: bool) -> str:
    if source == "finshare" and not lineage_observable:
        return "研究源"
    if availability < 0.6 or completeness < 0.6:
        return "淘汰源"
    if coverage >= 0.8 and consistency >= 0.8 and availability >= 0.9:
        return "生产主源"
    if consistency >= 0.7 and availability >= 0.8:
        return "热备源"
    return "交叉验证源"


def decide_safe_fallback(primary: Dict[str, Any], standby: Dict[str, Any], critical_fields: Iterable[str] = CRITICAL_QUOTE_FIELDS, tolerance: float = 0.02) -> SafetyDecision:
    fields = tuple(critical_fields)
    primary_fields = primary.get("fields", {}) if primary.get("success") else {}
    standby_fields = standby.get("fields", {}) if standby.get("success") else {}
    primary_missing = [field for field in fields if primary_fields.get(field) in (None, "")]
    standby_missing = [field for field in fields if standby_fields.get(field) in (None, "")]
    if not primary.get("success"):
        if standby.get("success") and not standby_missing:
            return SafetyDecision("use_hot_standby", "primary_unavailable_and_standby_complete", standby.get("source", ""), [], [])
        return SafetyDecision("do_not_recommend", "primary_unavailable_and_standby_incomplete", "", [], standby_missing)
    if primary_missing:
        return SafetyDecision("do_not_recommend", "primary_missing_critical_fields", "", [], primary_missing)
    if not standby.get("success"):
        return SafetyDecision("use_primary", "standby_unavailable_but_primary_complete", primary.get("source", ""), [], [])
    if standby_missing:
        return SafetyDecision("do_not_recommend", "standby_missing_critical_fields_prevents_consensus", "", [], standby_missing)
    conflicts = []
    for field in fields:
        left = _safe_number(primary_fields.get(field))
        right = _safe_number(standby_fields.get(field))
        if left is None or right is None:
            conflicts.append(field)
        elif left == 0 or abs(left - right) / abs(left) > tolerance:
            conflicts.append(field)
    if conflicts:
        return SafetyDecision("do_not_recommend", "critical_field_conflict", "", conflicts, [])
    return SafetyDecision("use_primary", "cross_source_consensus", primary.get("source", ""), [], [])


def audit_stock_data_paths(workspace: Path) -> Dict[str, Any]:
    known_observability_only = {
        "core/environment_sensor.py": {
            "source": "tencent_direct",
            "operation": "provider_liveness_probe",
            "classification": "observability_only",
            "excluded_from": ["health_aggregation", "cross_validation", "recommendation_eligibility"],
        },
    }
    unregistered_runtime_calls = []
    exceptions = []
    for path in (workspace / "core").rglob("*.py"):
        relative = path.relative_to(workspace).as_posix()
        content = path.read_text(encoding="utf-8")
        has_stock_endpoint = any(endpoint in content for endpoint in (
            "qt.gtimg.cn", "ifzq.gtimg.cn", "eastmoney.com", "baostock.com",
        ))
        if not has_stock_endpoint or relative == "core/stock_data_reliability.py":
            continue
        if relative in known_observability_only:
            exceptions.append({"path": relative, **known_observability_only[relative]})
        else:
            unregistered_runtime_calls.append(relative)
    return {
        "unregistered_runtime_calls": sorted(unregistered_runtime_calls),
        "exceptions": sorted(exceptions, key=lambda item: item["path"]),
    }


def _matrix_decision(candidate: StockDataCandidate, metrics: Dict[str, Any]) -> str:
    if candidate.evidence_status == "UNVERIFIED" or candidate.production_role == "RESEARCH_ONLY":
        return "RESEARCH"
    if not metrics:
        return "RESEARCH"
    if metrics.get("availability", 0.0) < 0.6 or metrics.get("field_completeness", 0.0) < 0.6:
        return "REJECT"
    if metrics.get("coverage", 0.0) >= 0.8 and metrics.get("consistency", 0.0) >= 0.8:
        return "REUSE"
    return "ADAPT"


def build_capability_matrix(
    registry: Dict[str, StockDataCandidate],
    benchmark_result: Dict[str, Any],
) -> Dict[str, Any]:
    sources = benchmark_result.get("summary", {}).get("sources", {})
    rows = []
    groups = {"REUSE": [], "ADAPT": [], "RESEARCH": [], "REJECT": []}
    source_keys = {"tencent_direct": "tencent", "sina_direct": "sina"}
    candidate_metrics = {}
    for candidate_id, candidate in registry.items():
        metrics = sources.get(source_keys.get(candidate_id, candidate_id), {})
        candidate_metrics[candidate_id] = metrics
        decision = _matrix_decision(candidate, metrics)
        groups[decision].append(candidate_id)
        for capability in candidate.capabilities or ("UNVERIFIED",):
            rows.append({
                "Source": candidate_id,
                "Capability": capability,
                "Available": metrics.get("operation_coverage", {}).get(capability, 0.0),
                "Freshness": metrics.get("freshness", "UNMEASURED"),
                "Coverage": metrics.get("coverage", 0.0),
                "Stability": metrics.get("stability", 0.0),
                "Upstream": candidate.upstream_identity,
                "Independence": candidate.independence_group,
                "Production Role": metrics.get("recommended_role", candidate.production_role),
                "Decision": decision,
            })
    core_operations = {}
    for operation in ("quote", "daily_kline", "minute_kline_1m", "minute_kline_5m", "index"):
        production_sources = []
        independence_groups = []
        for candidate_id, candidate in registry.items():
            metrics = candidate_metrics[candidate_id]
            operation_metrics = metrics.get("operation_quality", {}).get(operation, {})
            production_eligible = (
                candidate.evidence_status != "UNVERIFIED"
                and candidate.production_role != "RESEARCH_ONLY"
                and metrics.get("lineage_observable") is True
                and metrics.get("availability", 0.0) >= 0.8
                and metrics.get("field_completeness", 0.0) >= 0.8
                and metrics.get("operation_coverage", {}).get(operation) == 1.0
            )
            if operation in {"quote", "minute_kline_1m", "index"}:
                production_eligible = production_eligible and all(
                    operation_metrics.get(metric, 0.0) >= 0.8
                    for metric in ("availability", "coverage", "field_completeness", "freshness", "consistency")
                )
            if production_eligible:
                production_sources.append(candidate_id)
                independence_groups.append(candidate.independence_group)
        valid_groups = sorted({
            group for group in independence_groups
            if group not in {"UNVERIFIED", "UNVERIFIED_AGGREGATE"}
        })
        core_operations[operation] = {
            "production_sources": production_sources,
            "independence_groups": valid_groups,
            "has_independent_cross_validation": len(valid_groups) >= 2,
            "quality_gate": {
                "availability": 0.8,
                "coverage": 0.8,
                "field_completeness": 0.8,
                "freshness": 0.8,
                "consistency": 0.8,
            } if operation in {"quote", "minute_kline_1m", "index"} else {},
        }
    admitted = all(
        details["production_sources"] and details["has_independent_cross_validation"]
        for details in core_operations.values()
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "columns": ["Source", "Capability", "Available", "Freshness", "Coverage", "Stability", "Upstream", "Independence", "Production Role"],
        "rows": rows,
        "decision_groups": groups,
        "phase_two_admission": {
            "status": "ADMITTED" if admitted else "NOT_ADMITTED",
            "core_operations": core_operations,
        },
    }


def load_latest_health(evidence_dir: str) -> Dict[str, Any]:
    path = Path(evidence_dir) / "stock_data_benchmark_latest.json"
    if not path.exists():
        return {"available": False, "reason": "benchmark_evidence_missing"}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return {"available": True, "path": str(path), "summary": payload.get("summary", {}), "completed_at": payload.get("completed_at", "")}
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"benchmark_evidence_invalid:{type(exc).__name__}"}


if __name__ == "__main__":
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    root = Path(__file__).resolve().parent.parent
    benchmark = StockDataBenchmark(str(root / "06_RUNTIME" / "ace" / "data" / "stock_data_evidence"))
    result = benchmark.run(rounds=rounds)
    print(json.dumps({"completed_at": result["completed_at"], "summary": result["summary"]}, ensure_ascii=False))
