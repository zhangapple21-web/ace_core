import json
import time
import urllib.request
from typing import Dict, Optional, Set, Tuple


class OneAPIModelCatalog:
    def __init__(self, cache_ttl_seconds: float = 30.0):
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: Dict[Tuple[str, str], Tuple[float, Set[str]]] = {}

    def validate(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: int,
    ) -> Optional[str]:
        if model in self._models(base_url, api_key, timeout):
            return None
        return "model_unavailable"

    def _models(self, base_url: str, api_key: str, timeout: int) -> Set[str]:
        normalized_url = base_url.rstrip("/")
        cache_key = (normalized_url, api_key)
        now = time.monotonic()
        cached = self._cache.get(cache_key)
        if cached and now - cached[0] < self.cache_ttl_seconds:
            return cached[1]

        request = urllib.request.Request(
            f"{normalized_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            return set()

        models = {
            item.get("id")
            for item in payload.get("data", [])
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        }
        self._cache[cache_key] = (now, models)
        return models
