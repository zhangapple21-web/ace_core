import json
from datetime import datetime, timezone

from core.public_sentiment_observation import PublicSentimentObservation
from core.stock_discovery_sources import StockDiscoverySources


class Observer:
    def record(self, *args, **kwargs):
        return None


def test_thin_public_pages_are_observation_only(tmp_path):
    collector = PublicSentimentObservation(
        str(tmp_path),
        fetcher=lambda _: "<html><title>页面</title><a>只有一个足够长的链接文字</a></html>",
    )
    report = collector.collect(window="morning_observation", observed_at=datetime(2026, 8, 25, 9, 0))

    assert report["status"] == "NO_OBSERVABLE_SENTIMENT_SOURCE"
    assert report["admission_ready"] is False
    assert all(item.get("snapshot_path") for item in report["sources"])


def test_independent_snapshots_form_existing_strategic_candidate(tmp_path):
    data = tmp_path / "06_RUNTIME" / "ace" / "data"
    data.mkdir(parents=True)
    report = {
        "date": datetime.now().date().isoformat(),
        "window": "morning_observation",
        "admission_ready": True,
        "sources": [
            {
                "name": name,
                "status": "observed",
                "lineage_observable": True,
                "headline_count": 3,
                "independence_group": group,
                "upstream_identity": identity,
                "source_ref": f"C:/evidence/{name}.html#sha256={name}",
                "title": name,
                "headlines": ["one", "two", "three"],
                "retrieved_at": "2026-08-25T09:00:00+08:00",
                "content_hash": name,
                "url": f"https://{name}.example",
            }
            for name, group, identity in (
                ("x", "xueqiu_community", "xueqiu"),
                ("e", "eastmoney_community", "eastmoney_guba"),
                ("s", "sina_finance_editorial", "sina_finance"),
            )
        ],
    }
    (data / "public_sentiment_latest.json").write_text(json.dumps(report), encoding="utf-8")
    source = StockDiscoverySources(Observer(), str(tmp_path), advisor_workspace=str(tmp_path / "missing"))
    candidates = source.public_sentiment_candidates()

    assert len(candidates) == 1
    assert candidates[0].task_type == "strategic"
    assert len(candidates[0].metadata["autonomous_maintenance"]["evidence"]) == 3
