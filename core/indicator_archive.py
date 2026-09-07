"""Metadata-only bridge for a local TongdaXin ``.tn6`` indicator archive.

``.tn6`` files are proprietary/binary formula packages.  ACE does not have a
licensed formula parser in this checkout, so this bridge deliberately reads
only file metadata (name, size, SHA-256) and maps filename semantics to the
existing research factors.  It never executes, decrypts, or treats an
indicator hit as market evidence.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping


CONTRACT_VERSION = "ace.tn6_indicator_bridge.v1"
_FACTOR_KEYS = (
    "market_sentiment_index_environment",
    "sector_strength_rotation",
    "auction_opening_support",
    "intraday_volume_price_turnover",
    "flow_continuity_1_3d",
    "next_day_path_exit",
)

_KEYWORD_TAGS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("auction", ("竞价",)),
    ("intraday_orderflow", ("分时", "盘口", "主买", "大单频率", "笔均额", "异动")),
    ("flow_turnover", ("资金", "大单", "换手", "游资", "筹码")),
    ("sector_rotation", ("板块", "热点", "概念")),
    ("breakout_momentum", ("启动", "起爆", "突破", "发射", "涨停", "疯牛", "龙头", "成妖")),
    ("early_structure", ("低位", "底部", "回踩", "抄底", "反转", "反攻", "N字", "N型", "W底")),
    ("trend_technical", ("趋势", "均线", "MACD", "CCI", "RSI", "多周期", "角度")),
    ("market_regime", ("大盘", "指数", "逃顶", "避风港")),
    ("opaque_model", ("AI", "LSTM", "量化", "智能")),
)

_TAG_TO_FACTORS: dict[str, tuple[str, ...]] = {
    "auction": ("auction_opening_support",),
    "intraday_orderflow": ("intraday_volume_price_turnover",),
    "flow_turnover": ("flow_continuity_1_3d", "intraday_volume_price_turnover"),
    "sector_rotation": ("sector_strength_rotation",),
    "breakout_momentum": ("intraday_volume_price_turnover",),
    "early_structure": ("intraday_volume_price_turnover",),
    "trend_technical": ("intraday_volume_price_turnover",),
    "market_regime": ("market_sentiment_index_environment",),
    # Opaque labels are not promoted to a factor merely because they contain
    # "AI" or "量化"; they remain a question for later formula extraction.
    "opaque_model": (),
}


@dataclass(frozen=True)
class TN6Entry:
    relative_path: str
    file_name: str
    size_bytes: int
    sha256: str
    semantic_tags: tuple[str, ...]
    mapped_factors: tuple[str, ...]
    parse_status: str = "BINARY_FORMULA_UNPARSED"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {
            "semantic_tags": list(self.semantic_tags),
            "mapped_factors": list(self.mapped_factors),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_indicator_name(name: str) -> dict[str, list[str]]:
    """Classify a filename only; no formula bytes are interpreted."""

    text = str(name)
    tags: list[str] = []
    for tag, keywords in _KEYWORD_TAGS:
        if any(keyword.lower() in text.lower() for keyword in keywords):
            tags.append(tag)
    factors = sorted({factor for tag in tags for factor in _TAG_TO_FACTORS[tag]})
    return {"semantic_tags": tags, "mapped_factors": factors}


def inventory_tn6(root: str | Path) -> list[TN6Entry]:
    """Inventory ``.tn6`` files below ``root`` with stable hashes."""

    base = Path(root)
    if not base.exists() or not base.is_dir():
        raise ValueError("tn6_root_must_be_existing_directory")
    entries: list[TN6Entry] = []
    for path in sorted(base.rglob("*.tn6"), key=lambda item: item.as_posix().lower()):
        if not path.is_file():
            continue
        classification = classify_indicator_name(path.name)
        entries.append(TN6Entry(
            relative_path=path.relative_to(base).as_posix(),
            file_name=path.name,
            size_bytes=path.stat().st_size,
            sha256=_sha256(path),
            semantic_tags=tuple(classification["semantic_tags"]),
            mapped_factors=tuple(classification["mapped_factors"]),
        ))
    return entries


def build_indicator_bridge_record(
    *,
    root: str | Path,
    observed_at: str,
    veteran_principles: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create a research-only, metadata-bound bridge record."""

    parsed = datetime.fromisoformat(str(observed_at))
    if parsed.tzinfo is None:
        raise ValueError("observed_at_requires_timezone")
    entries = inventory_tn6(root)
    tag_counts = Counter(tag for entry in entries for tag in entry.semantic_tags)
    factor_counts = Counter(factor for entry in entries for factor in entry.mapped_factors)
    missing_factor_coverage = [factor for factor in _FACTOR_KEYS if not factor_counts.get(factor)]
    inventory_hash = hashlib.sha256(
        json.dumps([entry.to_dict() for entry in entries], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    record = {
        "contract_version": CONTRACT_VERSION,
        "observed_at": parsed.isoformat(),
        "root": str(Path(root)),
        "entry_count": len(entries),
        "entries": [entry.to_dict() for entry in entries],
        "semantic_tag_counts": dict(sorted(tag_counts.items())),
        "mapped_factor_counts": dict(sorted(factor_counts.items())),
        "missing_factor_coverage": missing_factor_coverage,
        "inventory_hash": inventory_hash,
        "parse_status": "BINARY_FORMULA_UNPARSED",
        "can_consume_as_market_signal": False,
        "research_status": "RESEARCH_ONLY",
        "production_integration": False,
        "recommendation_authority": False,
        "next_action": "obtain_licensed_formula_export_or_replay_indicator_hits_against_point_in_time_data",
    }
    # Keep structural learning attached to the same hash-bound bridge. This
    # remains research context only; it never feeds a market score or signal.
    from .tn6_experience_fusion import (
        DEFAULT_VETERAN_PRINCIPLES,
        build_tn6_experience_prior,
    )

    principles = (
        DEFAULT_VETERAN_PRINCIPLES
        if veteran_principles is None
        else tuple(veteran_principles)
    )
    record["experience_prior"] = build_tn6_experience_prior(
        record,
        veteran_principles=principles,
    )
    return record


def write_indicator_bridge_record(path: str | Path, record: Mapping[str, Any]) -> Path:
    """Atomically write a validated metadata-only bridge record."""

    if record.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("unsupported_tn6_bridge_contract")
    if record.get("research_status") != "RESEARCH_ONLY" or record.get("can_consume_as_market_signal") is not False:
        raise ValueError("tn6_bridge_must_remain_research_only")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(target)
    return target
