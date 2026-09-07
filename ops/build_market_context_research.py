"""Build a research-only market-context record from already retained evidence.

This command never fetches a URL, calls a model, changes data admission, or
creates a candidate.  It is intended as the safe post-processing phase of an
existing finance observation window.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.market_context_research import build_market_context_research, write_market_context_research


def _read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _file_ref(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return f"{path}#sha256={digest}"


def build(data_dir: Path) -> dict:
    window_path = data_dir / "finance_work_windows_latest.json"
    sentiment_path = data_dir / "public_sentiment_latest.json"
    window = _read(window_path)
    sentiment = _read(sentiment_path)
    observed_at = str(sentiment.get("observed_at") or window.get("observed_at") or datetime.now().astimezone().isoformat())
    market_date = str(sentiment.get("date") or window.get("date") or observed_at[:10])
    sources = sentiment.get("sources") if isinstance(sentiment.get("sources"), list) else []
    if not window or not sentiment or not sources or not window_path.exists():
        return {
            "contract_version": "ace.market_context_research.v1",
            "market_date": market_date,
            "observed_at": observed_at,
            "research_status": "NO_CONTEXT_EVIDENCE",
            "recommendation_authority": False,
            "market_data_admission_changed": False,
            "reason": "Existing finance-window facts and retained public snapshots are both required; no fetch was attempted.",
        }
    fact = {
        "source_ref": _file_ref(window_path),
        "observed_at": str(window.get("observed_at", observed_at)),
        "summary": f"Finance window={window.get('window_status')}; finance status={window.get('finance_status')}; recommendation allowed={window.get('recommendation_allowed')}",
        "upstream_identity": "ace_finance_window",
        "lineage_observable": True,
    }
    context = []
    for item in sources:
        if not isinstance(item, dict) or item.get("status") != "observed":
            continue
        role = "community_discussion" if "community" in str(item.get("independence_group", "")) else "sector_news"
        if not item.get("source_ref") or not item.get("content_hash"):
            continue
        context.append({
            "source_role": role,
            "source_ref": item["source_ref"],
            "observed_at": item.get("retrieved_at", observed_at),
            "summary": item.get("description") or item.get("title") or "Retained public market-context snapshot.",
            "content_hash": item["content_hash"],
            "upstream_identity": item.get("upstream_identity", "UNVERIFIED"),
            "lineage_observable": item.get("lineage_observable") is True,
        })
    if not context:
        return {
            "contract_version": "ace.market_context_research.v1",
            "market_date": market_date,
            "observed_at": observed_at,
            "research_status": "NO_CONTEXT_EVIDENCE",
            "recommendation_authority": False,
            "market_data_admission_changed": False,
            "reason": "No retained public snapshots met the traceability requirement; no fetch was attempted.",
        }
    return build_market_context_research(market_date=market_date, observed_at=observed_at, market_facts=[fact], context_evidence=context)


def main() -> int:
    data_dir = ROOT / "06_RUNTIME" / "ace" / "data"
    record = build(data_dir)
    target = data_dir / "market_context_latest.json"
    # Use the same atomic write discipline even when no context is available.
    # A failed/partial write must never be mistaken for an observed snapshot by
    # a later Daily Shift run.
    if record["research_status"] == "RESEARCH_ONLY":
        write_market_context_research(target, record)
    else:
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temporary.replace(target)
    print(json.dumps({"status": record["research_status"], "path": str(target)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

