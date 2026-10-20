"""Backfill the lane onto artifacts written before the field existed.

Same shape as the tombstoning backfill, and for the same reason: the fix makes
future writes attributed, but the artifacts already on disk are still anonymous,
and a substrate that names its writers only from today onward is half-answered.

Nothing else in any record is touched, and re-running is a no-op. The capability
card hash is deliberately NOT recomputed - the field sits outside it by design,
so rewriting a card to add a lane must leave its identity exactly as it was.
"""
import json
import os
from pathlib import Path

ROOT = Path(r"C:\tmp/ace_core/09_KNOWLEDGE")

TARGETS = [
    # (directory, filename prefix, lane)
    #
    # Only writers whose attribution can be established from the artifacts
    # themselves. The deposition path's historical records are deliberately
    # NOT here: labelling 1125 August-September patterns "daemon-archivist"
    # would be inventing provenance, which is the exact failure this whole
    # change is meant to remove. They stay visibly unattributed, and that is
    # the honest state - a reader can see the field is absent and knows not
    # to draw a conclusion about who wrote them.
    ("capability_cards", "CAP-", "learning-return-bridge"),
    ("skills", "SKILL-", "skill-generator"),
    ("mission_rounds", "round_", "steward_window_A"),
]


def _rewrite(path: Path, lane: str) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data["depositing_lane"] = lane
    temporary = path.with_suffix(".json.tmp")
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def main(apply: bool = False) -> dict:
    labelled, already, unreadable = [], [], []
    for directory, prefix, lane in TARGETS:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.glob(f"{prefix}*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                unreadable.append(path.name)
                continue
            if data.get("depositing_lane"):
                already.append(path.name)
                continue
            if apply:
                _rewrite(path, lane)
            labelled.append((directory, lane, path.name))

    by_lane = {}
    for directory, lane, _name in labelled:
        key = f"{directory}->{lane}"
        by_lane[key] = by_lane.get(key, 0) + 1
    return {
        "apply": apply,
        "labelled": len(labelled),
        "already_labelled": len(already),
        "unreadable": unreadable,
        "by_target": by_lane,
    }


if __name__ == "__main__":
    import sys

    print(json.dumps(main("--apply" in sys.argv), ensure_ascii=False, indent=2))
