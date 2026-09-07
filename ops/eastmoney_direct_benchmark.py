"""Bounded, evidence-only benchmark for EastMoney's direct public endpoints.

This module deliberately does not register a provider, modify the production
capability matrix, or decide Phase-2 admission.  It exists to collect a
repeatable evidence packet before any adapter is considered.
"""

import hashlib
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional


UPSTREAM_IDENTITY = "EastMoney direct public quotation endpoints"
INDEPENDENCE_GROUP = "eastmoney_public_http"
QUOTE_ENDPOINT = "https://push2.eastmoney.com/api/qt/stock/get"
MINUTE_ENDPOINT = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
QUOTE_FIELDS = ("f43", "f47", "f57", "f58", "f60", "f86")


class EastMoneyDirectIsolationBenchmark:
    """Collect direct-endpoint evidence without creating a production path."""

    def __init__(
        self,
        evidence_dir: str,
        *,
        symbols: Iterable[str] = ("1.600000", "0.000001", "0.300750", "1.688001"),
        index_secid: str = "1.000001",
        fetch: Optional[Callable[[str, str], Dict[str, Any]]] = None,
        now_epoch: Optional[Callable[[], float]] = None,
    ) -> None:
        self.evidence_dir = Path(evidence_dir)
        self.symbols = tuple(symbols)
        self.index_secid = index_secid
        self.fetch = fetch or self._fetch_direct
        self.now_epoch = now_epoch or time.time

    @staticmethod
    def _load_json(url: str) -> Dict[str, Any]:
        request = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        })
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict) or payload.get("rc") != 0:
            raise RuntimeError("eastmoney_direct_unusable_response")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise RuntimeError("eastmoney_direct_missing_data")
        return data

    @classmethod
    def _fetch_direct(cls, operation: str, secid: str) -> Dict[str, Any]:
        if operation in {"quote", "index"}:
            url = (
                f"{QUOTE_ENDPOINT}?invt=2&fltt=2&ut=fa5fd1943c7b386f172d6893dbfba10b"
                f"&secid={secid}&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f86"
            )
            return cls._load_json(url)
        if operation == "minute_kline_1m":
            url = (
                f"{MINUTE_ENDPOINT}?secid={secid}&klt=1&fqt=0&lmt=120&end=20500101"
                "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
            )
            return cls._load_json(url)
        raise ValueError(f"unsupported_operation:{operation}")

    @staticmethod
    def _endpoint(operation: str) -> str:
        return MINUTE_ENDPOINT if operation == "minute_kline_1m" else QUOTE_ENDPOINT

    @staticmethod
    def _sha256(value: Dict[str, Any]) -> str:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    def _probe(self, operation: str, secid: str, round_number: int) -> Dict[str, Any]:
        started = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()
        base = {
            "source": "eastmoney_direct_isolation",
            "operation": operation,
            "secid": secid,
            "round": round_number,
            "started_at": started,
            "upstream_identity": UPSTREAM_IDENTITY,
            "independence_group": INDEPENDENCE_GROUP,
            "lineage_observable": True,
            "endpoint": self._endpoint(operation),
        }
        try:
            data = self.fetch(operation, secid)
            if operation == "minute_kline_1m":
                rows = data.get("klines") if isinstance(data, dict) else None
                last = rows[-1].split(",") if isinstance(rows, list) and rows else []
                valid = len(last) >= 6
                fields = {"row_count": len(rows or []), "last_bar": last[0] if last else "", "last_close": last[2] if len(last) > 2 else ""}
                freshness_observable = bool(last and last[0])
                missing = [] if valid else ["klines"]
            else:
                fields = {key: data.get(key) for key in QUOTE_FIELDS}
                missing = [key for key in QUOTE_FIELDS if fields.get(key) in (None, "", 0)]
                valid = not missing
                freshness_observable = isinstance(fields.get("f86"), (int, float)) and fields["f86"] > 0
                if freshness_observable:
                    fields["freshness_age_seconds"] = round(max(0.0, self.now_epoch() - float(fields["f86"])), 3)
            return {
                **base,
                "latency_ms": round((time.monotonic() - clock) * 1000),
                "success": bool(valid and freshness_observable),
                "fields": fields,
                "missing_fields": missing,
                "freshness_observable": freshness_observable,
                "evidence_hash": self._sha256(data),
                "error_type": "" if valid and freshness_observable else "ValidationError",
                "error_message": "" if valid and freshness_observable else "direct_response_missing_required_fields_or_timestamp",
            }
        except Exception as error:  # failure is retained as evidence
            return {
                **base,
                "latency_ms": round((time.monotonic() - clock) * 1000),
                "success": False,
                "fields": {},
                "missing_fields": [],
                "freshness_observable": False,
                "evidence_hash": "",
                "error_type": type(error).__name__,
                "error_message": str(error)[:500],
            }

    @staticmethod
    def _summary(probes: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        output: Dict[str, Dict[str, Any]] = {}
        for operation in ("quote", "minute_kline_1m", "index"):
            selected = [probe for probe in probes if probe["operation"] == operation]
            success_count = sum(bool(probe["success"]) for probe in selected)
            output[operation] = {
                "sample_count": len(selected),
                "success_count": success_count,
                "availability": round(success_count / len(selected), 3) if selected else 0.0,
                "field_completeness": round(sum(not probe["missing_fields"] for probe in selected) / len(selected), 3) if selected else 0.0,
                "freshness_observable": bool(selected) and all(probe["freshness_observable"] for probe in selected),
                "consistency": "NOT_MEASURED_IN_ISOLATION",
                "coverage": "MEASURED_SAMPLE_ONLY",
            }
        return output

    def run(self, *, rounds: int = 3) -> Dict[str, Any]:
        if rounds < 1:
            raise ValueError("rounds_must_be_positive")
        probes: List[Dict[str, Any]] = []
        for round_number in range(1, rounds + 1):
            for secid in self.symbols:
                probes.append(self._probe("quote", secid, round_number))
                probes.append(self._probe("minute_kline_1m", secid, round_number))
            probes.append(self._probe("index", self.index_secid, round_number))
        report = {
            "schema_version": 1,
            "started_at": probes[0]["started_at"] if probes else datetime.now(timezone.utc).isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "rounds": rounds,
            "candidate": {
                "upstream_identity": UPSTREAM_IDENTITY,
                "independence_group": INDEPENDENCE_GROUP,
                "lineage_observable": True,
                "kind": "direct_public_http",
            },
            "probes": probes,
            "summary": self._summary(probes),
            "admission": "RESEARCH_ONLY",
            "production_integration": False,
            "not_a_phase_two_decision": True,
            "reason": "isolated direct-source evidence requires existing full quality and cross-source admission before any production use",
        }
        required = ("quote", "minute_kline_1m", "index")
        report["candidate_disposition"] = (
            "CANDIDATE_REQUIRES_CROSS_SOURCE_VALIDATION"
            if all(
                report["summary"][operation]["availability"] >= 0.8
                and report["summary"][operation]["freshness_observable"]
                for operation in required
            )
            else "A_SHARE_DATA_SOURCE_NOT_FOUND"
        )
        report["candidate_disposition_scope"] = "eastmoney_direct_isolation"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        target = self.evidence_dir / "eastmoney_direct_isolation_latest.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, target)
        return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    result = EastMoneyDirectIsolationBenchmark(args.evidence_dir).run(rounds=args.rounds)
    print(json.dumps({"path": str(Path(args.evidence_dir) / "eastmoney_direct_isolation_latest.json"), "summary": result["summary"], "admission": result["admission"]}, ensure_ascii=False))

