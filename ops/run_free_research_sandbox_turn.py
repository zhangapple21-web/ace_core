"""Run one bounded local free-research sandbox society turn."""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.sandbox_society import SandboxSociety


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="07_SANDBOX/free_research")
    arguments = parser.parse_args()
    result = SandboxSociety(Path(arguments.root)).run_turn()
    print(json.dumps(result, ensure_ascii=False, indent=2))

