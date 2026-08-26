"""Bounded, auditable observation of public finance-discussion landing pages.

This is deliberately an observation adapter, not a recommendation engine or a
scraper for authenticated/private feeds.  It stores the exact public response
used as evidence and reports whether there is enough *observable content* for
the existing Discovery -> Admission path to consider a research task.
"""

import hashlib
import html
import json
import re
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


DEFAULT_SOURCES = (
    {
        "name": "xueqiu_hq",
        "url": "https://xueqiu.com/hq",
        "upstream_identity": "xueqiu",
        "independence_group": "xueqiu_community",
    },
    {
        "name": "eastmoney_guba",
        "url": "https://guba.eastmoney.com/",
        "upstream_identity": "eastmoney_guba",
        "independence_group": "eastmoney_community",
    },
    {
        "name": "sina_finance",
        "url": "https://finance.sina.com.cn/",
        "upstream_identity": "sina_finance",
        "independence_group": "sina_finance_editorial",
    },
)


class _HeadlineParser(HTMLParser):
    """Extract conservative, human-visible headline candidates from HTML."""

    TAGS = {"a", "h1", "h2", "h3"}

    def __init__(self):
        super().__init__()
        self._depth = 0
        self._parts: List[str] = []
        self.items: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.TAGS:
            if self._depth == 0:
                self._parts = []
            self._depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.TAGS and self._depth:
            self._depth -= 1
            if self._depth == 0:
                value = " ".join("".join(self._parts).split())
                if 8 <= len(value) <= 160 and value not in self.items:
                    self.items.append(value)

    def handle_data(self, data):
        if self._depth:
            self._parts.append(data)


class PublicSentimentObservation:
    """Fetch a tiny public-source snapshot once per existing finance window."""

    def __init__(
        self,
        data_dir: str,
        *,
        sources=DEFAULT_SOURCES,
        fetcher: Optional[Callable[[str], str]] = None,
    ):
        self.data_dir = Path(data_dir)
        self.sources = tuple(sources)
        self.fetcher = fetcher or self._fetch
        self.report_path = self.data_dir / "public_sentiment_latest.json"
        self.snapshot_dir = self.data_dir / "public_sentiment_evidence"

    @staticmethod
    def _fetch(url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ACE-PublicObservation/1.0 (+auditable research)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        with urllib.request.urlopen(request, timeout=12) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
        return raw.decode(charset, errors="replace")

    @staticmethod
    def _metadata(markup: str) -> Dict[str, Any]:
        title = re.search(r"<title[^>]*>(.*?)</title>", markup, re.I | re.S)
        description = re.search(
            r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\']([^"\']+)',
            markup,
            re.I | re.S,
        )
        parser = _HeadlineParser()
        parser.feed(markup)
        # Navigation labels are not enough evidence for a sentiment conclusion.
        headlines = [item for item in parser.items if not re.fullmatch(r"[\W\d_]+", item)][:12]
        return {
            "title": html.unescape(title.group(1)).strip() if title else "",
            "description": html.unescape(description.group(1)).strip() if description else "",
            "headlines": headlines,
        }

    def collect(self, *, window: str, observed_at: datetime) -> Dict[str, Any]:
        """Collect public snapshots and explicitly report insufficient evidence."""
        day = observed_at.date().isoformat()
        collected: List[Dict[str, Any]] = []
        for source in self.sources:
            item = {
                "name": source["name"],
                "url": source["url"],
                "upstream_identity": source["upstream_identity"],
                "independence_group": source["independence_group"],
                "lineage_observable": True,
            }
            try:
                markup = self.fetcher(source["url"])
                digest = hashlib.sha256(markup.encode("utf-8")).hexdigest()
                snapshot = self.snapshot_dir / day / window / f"{source['name']}-{digest[:16]}.html"
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                snapshot.write_text(markup, encoding="utf-8")
                metadata = self._metadata(markup)
                item.update({
                    "status": "observed",
                    "retrieved_at": observed_at.isoformat(),
                    "content_hash": digest,
                    "snapshot_path": str(snapshot),
                    "source_ref": f"{snapshot}#sha256={digest}",
                    "title": metadata["title"],
                    "description": metadata["description"],
                    "headlines": metadata["headlines"],
                    "headline_count": len(metadata["headlines"]),
                })
            except Exception as exc:
                item.update({"status": "unavailable", "reason": type(exc).__name__})
            collected.append(item)

        groups = {
            item["independence_group"] for item in collected
            if item["status"] == "observed" and item.get("headline_count", 0) >= 3
        }
        # A strategic route requires three independently identified refs.  This
        # prevents landing-page metadata or a single community from becoming a
        # synthetic model workload.
        admission_ready = len(groups) >= 3
        report = {
            "schema_version": 1,
            "observed_at": observed_at.isoformat(),
            "date": day,
            "window": window,
            "sources": collected,
            "independent_content_source_count": len(groups),
            "admission_ready": admission_ready,
            "status": "OBSERVED" if admission_ready else "NO_OBSERVABLE_SENTIMENT_SOURCE",
            "reason": (
                "three independent public sources preserved at least three observable headline items"
                if admission_ready else
                "fewer than three independent sources exposed sufficient public, timestamped content; research remains observation-only"
            ),
        }
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return report
