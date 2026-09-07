# Provider Catalog and Workspace Lock Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate duplicate OneAPI model-catalog validation, make the workspace write lock safer to use and more resistant to stale Windows PID reuse, and close oversized continuation and image transport boundaries.

**Architecture:** Put the OneAPI `/models` preflight in a small shared module used by both `OneAPIProvider` and `SurvivalLoopEngine`; it exposes an explicit fail-closed result and short-lived in-process cache. Extend `WorkspaceWriteLock` with a context-manager protocol and a process-start fingerprint; a lock is reclaimable only when its recorded owner is verified dead or its PID fingerprint differs from the current process with the same PID. Keep the 3002 compatibility proxy ingress budget separate from its normalized upstream budget, project oversized continuation history or fail into a fresh task, and treat HTTP 413 as terminal. Enforce a global image boundary: reject Data URI and forwarded Base64, materialize provider output locally as real WebP below 500KB, and pass only path, SHA-256, and size metadata across local boundaries; URL-only providers accept only public URLs.

**Tech Stack:** Python standard library (`json`, `os`, `time`, `urllib.request`, `ctypes` on Windows), pytest, existing `BaseProvider` adapter and `AceDaemon` lifecycle.

---

## File Structure

- Create: `C:\tmp\ace_core\core\oneapi_model_catalog.py`
  - Owns OneAPI model-catalog fetch, parsing, bounded cache, and fail-closed validation.
- Modify: `C:\tmp\ace_core\core\miner_pool\providers\openai_compatible.py`
  - Makes `OneAPIProvider.chat()` delegate its preflight to the shared catalog boundary.
- Modify: `C:\tmp\ace_core\core\survival_loop\engine.py`
  - Makes the OneAPI branch delegate its preflight to the same boundary.
- Modify: `C:\tmp\ace_core\core\workspace_write_lock.py`
  - Adds process-start fingerprinting, consistent conflict responses, and context-manager cleanup.
- Modify: `C:\tmp\ace_core\ops\test_oneapi_model_catalog.py`
  - Covers shared validation, fail-closed catalog errors, and shared cache behavior.
- Modify: `C:\tmp\ace_core\ops\test_workspace_write_lock.py`
  - Covers context-manager release, PID fingerprint mismatch reclamation, and complete conflict diagnostics.

### Task 1: Shared OneAPI Catalog Boundary

**Files:**
- Create: `C:\tmp\ace_core\core\oneapi_model_catalog.py`
- Test: `C:\tmp\ace_core\ops\test_oneapi_model_catalog.py`

- [ ] **Step 1: Write failing tests for the shared preflight contract**

```python
def test_catalog_validation_reuses_a_fresh_cache(monkeypatch):
    from core.oneapi_model_catalog import OneAPIModelCatalog

    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return b'{"data": [{"id": "gpt-5.6-terra"}]}'

    def urlopen(request, timeout):
        calls.append((request.method, request.full_url))
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    catalog = OneAPIModelCatalog(cache_ttl_seconds=60)

    assert catalog.validate("http://provider.test/v1", "key", "gpt-5.6-terra", 3) is None
    assert catalog.validate("http://provider.test/v1", "key", "gpt-5.6-terra", 3) is None
    assert calls == [("GET", "http://provider.test/v1/models")]


def test_catalog_validation_fails_closed_when_catalog_request_errors(monkeypatch):
    from core.oneapi_model_catalog import OneAPIModelCatalog
    import urllib.error

    def urlopen(request, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)

    error = OneAPIModelCatalog().validate(
        "http://provider.test/v1",
        "key",
        "gpt-5.6-terra",
        3,
    )

    assert error == "model_unavailable"
```

- [ ] **Step 2: Run the catalog tests to verify they fail**

Run:

```powershell
python -m pytest -q ops/test_oneapi_model_catalog.py
```

Expected: FAIL because `core.oneapi_model_catalog` does not exist.

- [ ] **Step 3: Implement the shared catalog boundary**

```python
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
        cached = self._cache.get(cache_key)
        now = time.monotonic()
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
```

- [ ] **Step 4: Run the catalog tests to verify they pass**

Run:

```powershell
python -m pytest -q ops/test_oneapi_model_catalog.py
```

Expected: PASS.

### Task 2: Migrate Both OneAPI Call Paths

**Files:**
- Modify: `C:\tmp\ace_core\core\miner_pool\providers\openai_compatible.py:309-346`
- Modify: `C:\tmp\ace_core\core\survival_loop\engine.py:386-402`
- Test: `C:\tmp\ace_core\ops\test_oneapi_model_catalog.py`

- [ ] **Step 1: Extend the existing call-path tests to assert no POST occurs after a failed shared preflight**

```python
assert calls == [("GET", "http://provider.test/v1/models")]
```

Keep this assertion in both the `OneAPIProvider` and `SurvivalLoopEngine` unknown-model tests. Add a positive case that returns a catalog containing the requested model, then returns one chat-completion response, and assert calls are `GET /models` followed by `POST /chat/completions`.

- [ ] **Step 2: Run the call-path tests to verify the currently duplicated implementation still satisfies only existing behavior**

Run:

```powershell
python -m pytest -q ops/test_oneapi_model_catalog.py
```

Expected: PASS before refactor; this establishes behavioral coverage before moving implementation.

- [ ] **Step 3: Replace `OneAPIProvider` inline catalog logic with the shared boundary**

```python
from core.oneapi_model_catalog import OneAPIModelCatalog


class OneAPIProvider(OpenAICompatibleProvider):
    provider_name = "oneapi"

    def __init__(self, api_key: str, base_url: str = "http://localhost:3000/v1", **kwargs):
        super().__init__(api_key, base_url, provider_name="oneapi", **kwargs)
        self._model_catalog = OneAPIModelCatalog()

    def chat(self, messages, model="", temperature=0.7, max_tokens=1024, timeout=60, extra_headers=None, **kwargs):
        error = self._model_catalog.validate(self.base_url, self.api_key, model, timeout)
        if error:
            return {
                "success": False,
                "content": "",
                "model": model,
                "usage": {},
                "error": error,
                "latency_ms": 0,
                "provider": self.provider_name,
            }
        return super().chat(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout=timeout,
            extra_headers=extra_headers,
            **kwargs,
        )
```

- [ ] **Step 4: Replace `SurvivalLoopEngine` inline OneAPI catalog request with the shared boundary**

Add a module-level instance:

```python
from core.oneapi_model_catalog import OneAPIModelCatalog

_ONEAPI_MODEL_CATALOG = OneAPIModelCatalog()
```

Replace the inline `if name == "oneapi":` block with:

```python
if name == "oneapi":
    error = _ONEAPI_MODEL_CATALOG.validate(base_url, api_key, model, timeout)
    if error:
        return False, "", model, {}, int((time.time() - start) * 1000), error
```

- [ ] **Step 5: Run the focused model-routing regression**

Run:

```powershell
python -m pytest -q ops/test_oneapi_model_catalog.py ops/test_oneapi_model_resolution.py ops/test_model_pool_mainline.py
```

Expected: PASS.

### Task 3: Workspace Lock Lifecycle and PID Reuse Defense

**Files:**
- Modify: `C:\tmp\ace_core\core\workspace_write_lock.py`
- Test: `C:\tmp\ace_core\ops\test_workspace_write_lock.py`

- [ ] **Step 1: Write failing tests for context-manager cleanup and PID fingerprint mismatch**

```python
def test_workspace_write_lock_context_manager_releases_on_exception(tmp_path):
    from core.workspace_write_lock import WorkspaceWriteLock

    try:
        with WorkspaceWriteLock(tmp_path, owner_id="window-a"):
            assert (tmp_path / ".workspace.write.lock").exists()
            raise RuntimeError("abort")
    except RuntimeError:
        pass

    assert not (tmp_path / ".workspace.write.lock").exists()


def test_workspace_write_lock_reclaims_a_reused_pid(tmp_path, monkeypatch):
    from core.workspace_write_lock import WorkspaceWriteLock

    lock_file = tmp_path / ".workspace.write.lock"
    lock_file.write_text(
        json.dumps({
            "pid": 42,
            "owner_id": "stale-window",
            "run_id": "old-run",
            "process_started_at": 1.0,
            "token": "stale-token",
            "created_at": 1.0,
        }),
        encoding="utf-8",
    )
    current = WorkspaceWriteLock(tmp_path, owner_id="window-a")
    monkeypatch.setattr(current, "_owner_alive", lambda owner: True)
    monkeypatch.setattr(current, "_process_started_at", lambda pid: 2.0)

    result = current.acquire()

    assert result["acquired"] is True
```

- [ ] **Step 2: Run the workspace-lock tests to verify they fail**

Run:

```powershell
python -m pytest -q ops/test_workspace_write_lock.py
```

Expected: FAIL because the lock has no context manager and does not evaluate `process_started_at`.

- [ ] **Step 3: Add process-start metadata, fingerprint-aware liveness, and context-manager methods**

```python
class WorkspaceWriteLock:
    def __enter__(self):
        result = self.acquire()
        if not result.get("acquired"):
            raise RuntimeError(result["reason"])
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.release()
        return False

    def _new_owner(self, token: str) -> Dict[str, Any]:
        pid = os.getpid()
        return {
            "pid": pid,
            "owner_id": self.owner_id,
            "run_id": self.run_id or None,
            "process_started_at": self._process_started_at(pid),
            "token": token,
            "created_at": time.time(),
        }

    def _is_reclaimable(self, owner: Dict[str, Any]) -> bool:
        if not self._owner_alive(owner):
            return True
        started_at = owner.get("process_started_at")
        if not isinstance(started_at, (float, int)):
            return False
        current_started_at = self._process_started_at(owner["pid"])
        return isinstance(current_started_at, (float, int)) and current_started_at != started_at
```

In `acquire()`, replace the direct `_owner_alive()` decision with `_is_reclaimable()` and build the owner through `_new_owner(token)`. Implement `_process_started_at(pid)` using `GetProcessTimes` on Windows and return `None` on platforms where this repository does not have a safe standard-library equivalent. A missing fingerprint must fail closed for an alive process.

Create a single `_conflict(owner)` method and use it both in the primary collision return and the retry-exhausted return:

```python
def _conflict(self, owner: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "acquired": False,
        "reason": "workspace_write_locked",
        "owner": owner,
        "lock_file": str(self.lock_file),
        "recommendation": "wait_for_current_owner_or_verify_stale_lock",
    }
```

- [ ] **Step 4: Run the workspace-lock regression**

Run:

```powershell
python -m pytest -q ops/test_workspace_write_lock.py ops/test_24h_runtime_mainline.py
```

Expected: PASS.

### Task 4: 3002 Request and Continuation Boundary

**Files:**
- Modify: `C:\tmp\local_responses_compat_proxy.py`
- Modify: `C:\tmp\local_oneapi_watchdog.ps1` only if effective environment propagation is incomplete
- Test: `C:\tmp\responses_compat_regression_test.py`

- [ ] **Step 1: Keep raw ingress and normalized upstream budgets distinct**

The proxy must allow a bounded oversized continuation body to enter local history projection while enforcing a smaller normalized upstream payload budget. A raw body above the ingress cap returns 413 with a fresh-task/shorten-history hint and is not forwarded.

- [ ] **Step 2: Make continuation projection explicit and bounded**

When inline history or `previous_response_id` recovery would exceed the replay budget, retain only the bounded tail and required task context. If the request still cannot be normalized under the upstream budget, return terminal 413 with telemetry distinguishing raw overflow from normalized overflow; do not retry or silently replay the full continuation.

- [ ] **Step 3: Keep 413 terminal and non-retryable**

Unsupported-key retry is permitted only for HTTP 400 responses. HTTP 413 must return unchanged, must not invoke a retry callback, and must emit a distinct rejection reason.

- [ ] **Step 4: Verify the running 3002 instance and watchdog chain**

Confirm the listener is owned by `local_responses_compat_proxy.py`, `/healthz` is 200, and the watchdog or parent startup path preserves the effective ingress and upstream budget environment after restart. Do not alter the 3000 gateway role.

### Task 5: Global Image Transport Boundary

**Files:**
- Modify: `C:\tmp\ace_video_kingdom_git\runtime\shot_core.py`
- Modify: `C:\tmp\ace_video_kingdom_git\tools\run_idea_pipeline.py`
- Modify: `C:\tmp\ace_video_kingdom_git\tools\generate_episode007_anchors.py`
- Modify: `C:\tmp\ace_video_kingdom_git\tools\generate_episode007_scene_action_anchors.py`
- Audit: `C:\tmp\infinite-canvas\`, `C:\tmp\zola-pages\`
- Test: `C:\tmp\ace_video_kingdom_git\tests\test_shot_core_hardening.py`, `C:\tmp\ace_video_kingdom_git\tests\test_future_hardening.py`

- [ ] **Step 1: Reject inline image transport at provider and proxy boundaries**

Data URI, `base64`, `b64_json`, and image-context `data` fields must not be forwarded to providers or the compatibility proxy. Provider response `b64_json` may be decoded only inside a local materialization helper.

- [ ] **Step 2: Materialize images as bounded WebP artifacts**

Every generated image must be a real WebP with `size_bytes < 500 * 1024`, written atomically. Downstream references carry `path`, `sha256`, and `size_bytes`; legacy string path fields remain only for compatibility with existing renderers.

- [ ] **Step 3: Enforce local asset verification in Shot Core**

Local references must point to an existing, valid WebP below the size limit, with matching SHA-256 and `size_bytes`. Data URI references are blocked. Public HTTP/HTTPS references remain accepted for URL-capable providers.

- [ ] **Step 4: Fail closed at URL-only provider adapters**

A URL-only adapter must reject local paths or metadata dictionaries rather than passing them through. A provider-compatible conversion must be explicit and produce a public URL before admission.

- [ ] **Step 5: Audit browser and worker image paths**

Classify remaining Data URI usage as preview-only, local materialization input, or provider-bound transport. Remove or block provider-bound forwarding and add body/image budget checks at the earliest boundary without modifying unrelated dirty worktree content.

### Task 6: Full Verification and Documentation Alignment

**Files:**
- Modify only if behavior wording changed: `C:\tmp\ace_core\research\runtime_authority_audit.v1.md`

- [ ] **Step 1: Run targeted regressions**

Run:

```powershell
python -m pytest -q ops/test_oneapi_model_catalog.py ops/test_oneapi_model_resolution.py ops/test_model_pool_mainline.py ops/test_workspace_write_lock.py ops/test_24h_runtime_mainline.py ops/test_runtime_authority_audit.py
```

Expected: PASS.

- [ ] **Step 2: Run the full verification suite**

Run:

```powershell
python -m pytest -q
python -m compileall -q core ace_daemon.py ops
git diff --check
```

Expected: pytest and compileall pass. Report pre-existing global diff whitespace separately rather than reformatting unrelated files.

- [ ] **Step 3: Update the audit only when the implemented behavior changes documented claims**

Record these facts in `research/runtime_authority_audit.v1.md`:

```markdown
- OneAPI `/models` validation is shared by MinerPool's `OneAPIProvider` and SurvivalLoopEngine.
- The catalog cache is process-local and bounded by a short TTL; cache miss or catalog error remains fail-closed as `model_unavailable`.
- Workspace lock records include a Windows process-start fingerprint when available; an alive PID with a mismatched fingerprint is reclaimable as PID reuse.
- `WorkspaceWriteLock` supports `with` usage and releases on exceptional exits.
```

- [ ] **Step 4: Commit only the scoped optimization after verifying ownership of every staged diff**

```powershell
git add core/oneapi_model_catalog.py core/miner_pool/providers/openai_compatible.py core/survival_loop/engine.py core/workspace_write_lock.py ops/test_oneapi_model_catalog.py ops/test_workspace_write_lock.py research/runtime_authority_audit.v1.md
git diff --cached --check
git diff --cached --name-only
```

Expected: only the scoped files appear. Do not commit if any other-window change appears in the staged diff.
