"""Register Grok candidates in ACE Provider Registry as shadow-only models."""

import argparse
from pathlib import Path

from core.governance.provider_registry import ProviderRegistry


def register(data_dir: str) -> Path:
    registry = ProviderRegistry(data_dir)
    registry.register_shadow_catalog(
        provider="shenwen_grok",
        base_url="https://api.shenwenai.com/v1",
        description="Shenwen Grok Heavy channel; shadow evaluation only",
        models={
            "grok-4.5": {"display_name": "Grok 4.5"},
            "grok-4.6": {"display_name": "Grok 4.6"},
        },
    )
    return registry.registry_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", default=str(Path(__file__).resolve().parents[1] / "08_GOVERNANCE"))
    args = parser.parse_args()
    print(register(args.data_dir))
