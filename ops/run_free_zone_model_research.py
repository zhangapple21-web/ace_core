#!/usr/bin/env python3
"""Run one explicitly selected Free Zone semantic seed through existing MinerPool."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.free_zone_model_research import FreeZoneModelResearch
from core.miner_pool.miner_pool import MinerPool
from core.semantic_seed import normalize_semantic_seed


def main():
    p = argparse.ArgumentParser()
    p.add_argument("seed")
    p.add_argument("--max-tokens", type=int, default=1024)
    p.add_argument("--receipt-dir", default=str(ROOT / "07_SANDBOX" / "free_research" / "reports" / "model_turns"))
    a = p.parse_args()
    seed = normalize_semantic_seed(json.loads(Path(a.seed).read_text(encoding="utf-8")))
    cfg = json.loads((ROOT / "ace_config.json").read_text(encoding="utf-8"))
    pool = MinerPool(coze_assets_path=cfg.get("runtime", {}).get("miner_pool_assets_path"), state_dir=str(ROOT / "06_RUNTIME" / "ace" / "data" / "miner_pool"))
    receipt = FreeZoneModelResearch(pool).run(seed, max_tokens=a.max_tokens)
    out = Path(a.receipt_dir); out.mkdir(parents=True, exist_ok=True)
    target = out / f"{seed['seed_hash'][:16]}-{receipt['recorded_at'].replace(':','').replace('+','_')}.json"
    target.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(target), "outcome": receipt["outcome"], "provider": receipt["provider"], "model": receipt["model"]}, ensure_ascii=False))

if __name__ == '__main__': main()

