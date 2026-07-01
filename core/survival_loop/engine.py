"""
Survival Loop Engine — 单循环执行内核（极简版）

笨但活得久。

规则：
  1. 固定顺序：glm → openrouter → nim → apiyi → sambanova → oneapi → github_models → modelscope → huggingface
  2. 成功即返回，失败直接跳过
  3. 无重试、无路由、无决策、无动态配置
  4. 永远有输出、不崩溃、不循环
  5. 所有错误静默吞掉，只记日志

调用：
  engine = SurvivalLoopEngine(coze_assets_path="...")
  result = engine.chat(messages=[...], system_prompt="...")

返回：
  {
    "success": bool,
    "content": str,
    "model": str,
    "provider": str,
    "usage": dict,
    "latency_ms": int,
    "error": str,
    "tried": [{"provider": str, "status": str, "error": str}],
  }
"""

import json
import re
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, List, Any, Optional


PROVIDER_ORDER = [
    "glm",
    "openrouter",
    "nim",
    "apiyi",
    "sambanova",
    "oneapi",
    "github_models",
    "modelscope",
    "huggingface",
    "ace_proxy",
]

DEFAULT_MODEL = {
    "glm": "glm-4-flash",
    "openrouter": "anthropic/claude-3.5-sonnet",
    "nim": "deepseek-ai/deepseek-v4-flash",
    "apiyi": "gemini-pro",
    "sambanova": "Meta-Llama-3.1-405B-Instruct",
    "oneapi": "gpt-4o",
    "github_models": "gpt-4o",
    "modelscope": "qwen-plus",
    "huggingface": "meta-llama/Meta-Llama-3-8B-Instruct",
    "ace_proxy": "gpt-4o",
}

DEFAULT_BASE_URL = {
    "glm": "https://open.bigmodel.cn/api/paas/v4",
    "openrouter": "https://openrouter.ai/api/v1",
    "nim": "https://integrate.api.nvidia.com/v1",
    "apiyi": "https://api.apiyi.com",
    "sambanova": "https://api.sambanova.ai/v1",
    "oneapi": "http://localhost:3000/v1",
    "github_models": "https://models.inference.ai.azure.com",
    "modelscope": "https://api-inference.modelscope.cn/v1",
    "huggingface": "https://api-inference.huggingface.co/v1",
    "ace_proxy": "http://localhost:3001/v1",
}


class SurvivalLoopEngine:
    """
    单循环执行内核 — 笨但活得久。

    一个 for 循环，挨个试，成功就回，全败就兜底。
    """

    def __init__(self, coze_assets_path: Optional[str] = None, state_dir: Optional[str] = None):
        self._providers: Dict[str, Dict[str, str]] = {}
        self._logs: List[Dict] = []
        self._coze_path: Optional[Path] = None
        self._state_dir: Optional[Path] = Path(state_dir) if state_dir else None
        self._ready = False

        try:
            if coze_assets_path:
                self._coze_path = Path(coze_assets_path)
            else:
                self._coze_path = self._find_coze_assets()

            if self._state_dir:
                self._state_dir.mkdir(parents=True, exist_ok=True)

            self._load_secret()
            self._ready = bool(self._providers)
        except Exception:
            self._ready = False

    def _find_coze_assets(self) -> Optional[Path]:
        home = Path.home()
        roots = [
            Path.cwd(),
            Path.cwd().parent,
            home / "Downloads",
            home / "Desktop",
            home / "Documents",
            home / "projects",
            home / "workspace",
            home / ".trae" / "work",
        ]
        for root in roots:
            if not root.exists():
                continue
            try:
                for p in root.rglob("coze-assets/01_credentials/SECRET.md"):
                    if p.is_file():
                        return p.parent.parent
            except Exception:
                pass
        return None

    def _load_secret(self):
        if not self._coze_path or not self._coze_path.exists():
            return
        secret_file = self._coze_path / "01_credentials" / "SECRET.md"
        if not secret_file.exists():
            return
        try:
            content = secret_file.read_text(encoding="utf-8")
        except Exception:
            return

        patterns = {
            "glm": {
                "key": r"智谱 GLM[\s\S]*?Key:\s*`?([\w\.\-]+)",
                "base": r"智谱 GLM[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            },
            "openrouter": {
                "key": r"OpenRouter[\s\S]*?Key:\s*`?(sk-or-v1-[\w]+)",
                "base": r"OpenRouter[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            },
            "nim": {
                "key": r"NVIDIA NIM[\s\S]*?Key:\s*`?([\w\-]+)",
                "base": r"NVIDIA NIM[\s\S]*?\*?\*?Base:\*?\*?\s*`?(https?://[^\s`]+)",
            },
            "apiyi": {
                "key": r"API易[\s\S]*?Key:\s*`?(sk-[\w]+)",
                "base": r"API易[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            },
            "sambanova": {
                "key": r"SambaNova[\s\S]*?Key:\s*`?([\w\-]+)",
                "base": r"SambaNova[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            },
            "oneapi": {
                "key": r"OneAPI[\s\S]*?Token-miner:\s*`?([\w]+)",
                "base": r"OneAPI[\s\S]*?地址:\s*`?(https?://[^\s`]+)",
                "append_v1": True,
            },
            "github_models": {
                "key": r"GitHub Models[\s\S]*?Token:\s*`?([\w\-_]+)",
                "base": r"GitHub Models[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            },
            "modelscope": {
                "key": r"魔搭 ModelScope[\s\S]*?Key:\s*`?([\w\-]+)",
                "base": r"魔搭 ModelScope[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            },
            "huggingface": {
                "key": r"HuggingFace[\s\S]*?Key:\s*`?([\w]+)",
                "base": None,
            },
            "ace_proxy": {
                "key": r"ACE OpenAI 代理[\s\S]*?Token:\s*`?([\w\-]+)",
                "base": r"ACE OpenAI 代理[\s\S]*?Base:\s*`?(https?://[^\s`]+)",
            },
        }

        for name, pat in patterns.items():
            try:
                m = re.search(pat["key"], content)
                if not m:
                    continue
                api_key = m.group(1).strip()
                if not api_key:
                    continue

                base_url = DEFAULT_BASE_URL.get(name, "")
                if pat.get("base"):
                    bm = re.search(pat["base"], content)
                    if bm:
                        base_url = bm.group(1).strip()

                if pat.get("append_v1") and base_url and not base_url.endswith("/v1"):
                    base_url = base_url.rstrip("/") + "/v1"

                self._providers[name] = {
                    "api_key": api_key,
                    "base_url": base_url,
                    "model": DEFAULT_MODEL.get(name, ""),
                }
            except Exception:
                continue

        if "nim" not in self._providers:
            self._try_nim_from_miner_env()

    def _try_nim_from_miner_env(self):
        if not self._coze_path:
            return
        env_file = self._coze_path / "02_miner_config" / "miner_env.sh"
        if not env_file.exists():
            return
        try:
            content = env_file.read_text(encoding="utf-8")
            keys = []
            for m in re.finditer(r'NIM_KEY_\d+="([^"]+)"', content):
                k = m.group(1)
                if k and k not in keys:
                    keys.append(k)
            if keys:
                base = DEFAULT_BASE_URL["nim"]
                bm = re.search(r'NIM_BASE="([^"]+)"', content)
                if bm:
                    base = bm.group(1)
                self._providers["nim"] = {
                    "api_key": keys[0],
                    "base_url": base,
                    "model": DEFAULT_MODEL["nim"],
                }
        except Exception:
            pass

    @property
    def is_initialized(self) -> bool:
        return self._ready

    def initialize(self) -> bool:
        """兼容旧接口 — 构造时已完成初始化，这里直接返回状态"""
        return self._ready

    @property
    def available_providers(self) -> List[str]:
        result = []
        for p in PROVIDER_ORDER:
            if p in self._providers:
                result.append(p)
        return result

    def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: str = "",
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 60,
        **kwargs,
    ) -> Dict[str, Any]:
        """
        单循环：按固定顺序挨个试，成功就回，全败就兜底。

        永远返回一个 dict，永远不抛异常。
        """
        tried: List[Dict] = []
        last_error = ""

        try:
            full_messages = []
            if system_prompt:
                full_messages.append({"role": "system", "content": system_prompt})
            full_messages.extend(messages)
        except Exception:
            full_messages = messages or []

        for name in PROVIDER_ORDER:
            if name not in self._providers:
                continue

            pdata = self._providers[name]
            use_model = model or pdata.get("model", "")

            try:
                ok, content, resp_model, usage, latency, err = self._call_one(
                    name=name,
                    base_url=pdata["base_url"],
                    api_key=pdata["api_key"],
                    messages=full_messages,
                    model=use_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=timeout,
                    **kwargs,
                )
            except Exception as e:
                ok, content, resp_model, usage, latency, err = (
                    False, "", use_model, {}, 0, str(e)
                )

            log_entry = {
                "provider": name,
                "status": "success" if ok else "fail",
                "latency_ms": latency,
                "error": err,
                "model": resp_model or use_model,
            }
            tried.append(log_entry)
            self._log(log_entry)

            if ok:
                return {
                    "success": True,
                    "content": content,
                    "model": resp_model or use_model,
                    "provider": name,
                    "usage": usage,
                    "latency_ms": latency,
                    "error": "",
                    "tried": tried,
                }
            else:
                last_error = err
                continue

        return self._safe_fallback(tried, last_error)

    def _call_one(
        self,
        name: str,
        base_url: str,
        api_key: str,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float,
        max_tokens: int,
        timeout: int,
        **kwargs,
    ):
        """调一个 provider。返回 (ok, content, model, usage, latency_ms, error)"""
        start = time.time()
        try:
            if not model:
                return False, "", model, {}, 0, "model is required"

            base_url = base_url.rstrip("/")
            if name == "apiyi":
                chat_url = base_url + "/v1/chat/completions"
            else:
                chat_url = base_url + "/chat/completions"

            payload = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            for k in ["top_p", "frequency_penalty", "presence_penalty", "stream"]:
                if k in kwargs:
                    payload[k] = kwargs[k]

            data = json.dumps(payload).encode("utf-8")

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            if name == "openrouter":
                headers["HTTP-Referer"] = "https://ace-runtime.local"
                headers["X-Title"] = "ACE Runtime"

            req = urllib.request.Request(chat_url, data=data, headers=headers, method="POST")

            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                resp_data = json.loads(body)
                latency = int((time.time() - start) * 1000)

                if resp_data.get("error"):
                    return False, "", model, {}, latency, str(resp_data["error"])

                choices = resp_data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    content = msg.get("content", "")
                    resp_model = resp_data.get("model", model)
                    usage = resp_data.get("usage", {})
                    return True, content, resp_model, usage, latency, ""
                else:
                    return False, "", model, {}, latency, "no choices in response"

        except urllib.error.HTTPError as e:
            latency = int((time.time() - start) * 1000)
            try:
                err_body = e.read().decode("utf-8", errors="replace")
                err_data = json.loads(err_body)
                err_msg = err_data.get("error", {}).get("message", f"HTTP {e.code}")
                return False, "", model, {}, latency, err_msg
            except Exception:
                return False, "", model, {}, latency, f"HTTP {e.code}: {e.reason}"
        except urllib.error.URLError as e:
            latency = int((time.time() - start) * 1000)
            return False, "", model, {}, latency, f"URL Error: {e.reason}"
        except Exception as e:
            latency = int((time.time() - start) * 1000)
            return False, "", model, {}, latency, str(e)

    def _safe_fallback(self, tried: List[Dict], last_error: str) -> Dict[str, Any]:
        """
        所有 provider 都挂了的兜底。

        保证永远有输出，不崩溃。
        """
        return {
            "success": False,
            "content": "",
            "model": "",
            "provider": "",
            "usage": {},
            "latency_ms": 0,
            "error": last_error or "all providers failed",
            "tried": tried,
            "fallback": True,
        }

    def _log(self, entry: Dict):
        """简单日志，内存里最多存 1000 条"""
        self._logs.append(entry)
        if len(self._logs) > 1000:
            self._logs = self._logs[-1000:]

    def get_logs(self, limit: int = 50) -> List[Dict]:
        return self._logs[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        total = len(self._logs)
        succ = sum(1 for l in self._logs if l["status"] == "success")
        fail = sum(1 for l in self._logs if l["status"] == "fail")
        rate = succ / total if total > 0 else 0.0
        by_provider: Dict[str, Dict] = {}
        for l in self._logs:
            p = l["provider"]
            if p not in by_provider:
                by_provider[p] = {"total": 0, "success": 0, "fail": 0, "latency_sum": 0}
            by_provider[p]["total"] += 1
            if l["status"] == "success":
                by_provider[p]["success"] += 1
            else:
                by_provider[p]["fail"] += 1
            by_provider[p]["latency_sum"] += l.get("latency_ms", 0)
        for p, s in by_provider.items():
            s["avg_latency_ms"] = s["latency_sum"] / s["total"] if s["total"] > 0 else 0
            s["success_rate"] = s["success"] / s["total"] if s["total"] > 0 else 0
            del s["latency_sum"]
        return {
            "initialized": self._ready,
            "providers": {
                "available": self.available_providers,
                "total_configured": len(self._providers),
            },
            "calls": {
                "total": total,
                "success": succ,
                "fail": fail,
                "success_rate": round(rate, 4),
                "by_provider": by_provider,
            },
        }
