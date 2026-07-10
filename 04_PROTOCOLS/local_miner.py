#!/usr/bin/env python3
"""
Local Miner v2 - 多源模型调用，不依赖 TRAE
================================================
模型优先级：Ollama(本地) → GitHub Models → Zhipu GLM → OpenRouter

公理根基:
  #002 考古不是搬家是炼金
  #005 隐私是盾, 行动是剑
  #014 本地推理为主, 外部模型只当嘴
"""
import os, sys, json, argparse, urllib.request, urllib.error
from datetime import datetime
from pathlib import Path

# Load keys from miner_env.sh
def load_env():
    env_path = Path(__file__).parent.parent / "05_TOOLS" / "miner" / "miner_env.sh"
    if env_path.exists():
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("export ") and "=" in line:
                    k, v = line[7:].split("=", 1)
                    v = v.strip().strip('"').strip("'")
                    os.environ.setdefault(k, v)

load_env()

GITHUB_PAT = os.environ.get("GITHUB_PAT", "")
GITHUB_BASE = "https://models.inference.ai.azure.com"
ZHIPU_KEY = os.environ.get("ZHIPU_KEY", "")
ZHIPU_BASE = "https://open.bigmodel.cn/api/paas/v4"
OPENROUTER_KEY = os.environ.get("OPENROUTER_KEY", "")
OPENROUTER_BASE = "https://openrouter.ai/api/v1"
HF_KEY = os.environ.get("HF_KEY", "")
HF_BASE = "https://router.huggingface.co/v1"

# Ollama 本地模型（默认 localhost:11434）
OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "huihui_ai/qwen2.5-vl-abliterated:7b")

# 模型 fallback 链
MODEL_FALLBACK_CHAIN = [
    ("ollama", OLLAMA_MODEL),
    ("hf", "openai/gpt-oss-120b"),
    ("github", "gpt-4o-mini"),
    ("zhipu", "glm-4-flash"),
    ("openrouter", "meta-llama/llama-3.3-70b-instruct:free"),
]


def call_ollama(prompt, model=None, max_tokens=500, temperature=0.7):
    """调用本地 Ollama 模型"""
    model = model or OLLAMA_MODEL
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"num_predict": max_tokens, "temperature": temperature},
    }
    req = urllib.request.Request(
        f"{OLLAMA_BASE}/api/chat",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            resp = json.loads(r.read().decode())
            # 转换为 OpenAI 兼容格式
            return {
                "choices": [{"message": {"content": resp.get("message", {}).get("content", "")}}],
                "model": model,
                "source": "ollama",
            }
    except urllib.error.URLError as e:
        return {"error": f"Ollama URLError: {e}", "source": "ollama"}
    except Exception as e:
        return {"error": f"Ollama error: {e}", "source": "ollama"}


def check_ollama_available() -> bool:
    """检测 Ollama 是否可用"""
    try:
        req = urllib.request.Request(f"{OLLAMA_BASE}/api/tags")
        with urllib.request.urlopen(req, timeout=3) as r:
            data = json.loads(r.read().decode())
            return len(data.get("models", [])) > 0
    except Exception:
        return False


def call_github_models(prompt, model="gpt-4o-mini", max_tokens=500, temperature=0.7):
    if not GITHUB_PAT: return {"error": "GITHUB_PAT not set", "source": "github"}
    data = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature}
    req = urllib.request.Request(f"{GITHUB_BASE}/chat/completions", data=json.dumps(data).encode(), headers={"Authorization": f"Bearer {GITHUB_PAT}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read().decode())
            result["source"] = "github"
            return result
    except urllib.error.URLError as e: return {"error": f"URLError: {e}", "source": "github"}
    except Exception as e: return {"error": f"Error: {e}", "source": "github"}


def call_zhipu(prompt, model="glm-4-flash", max_tokens=500, temperature=0.7):
    if not ZHIPU_KEY: return {"error": "ZHIPU_KEY not set", "source": "zhipu"}
    data = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    req = urllib.request.Request(f"{ZHIPU_BASE}/chat/completions", data=json.dumps(data).encode(), headers={"Authorization": f"Bearer {ZHIPU_KEY}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read().decode())
            result["source"] = "zhipu"
            return result
    except Exception as e: return {"error": f"Error: {e}", "source": "zhipu"}


def call_openrouter(prompt, model="meta-llama/llama-3.3-70b-instruct:free", max_tokens=500, temperature=0.7):
    if not OPENROUTER_KEY: return {"error": "OPENROUTER_KEY not set", "source": "openrouter"}
    data = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens}
    headers = {"Authorization": f"Bearer {OPENROUTER_KEY}", "Content-Type": "application/json", "HTTP-Referer": "https://ace.local", "X-Title": "ACE Miner"}
    req = urllib.request.Request(f"{OPENROUTER_BASE}/chat/completions", data=json.dumps(data).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read().decode())
            result["source"] = "openrouter"
            return result
    except Exception as e: return {"error": f"Error: {e}", "source": "openrouter"}


def call_hf(prompt, model="openai/gpt-oss-120b", max_tokens=500, temperature=0.7):
    """调用 HuggingFace Inference Providers (OpenAI 兼容, router.huggingface.co)

    测试结果 (2026-07-10): 30ms 延迟, gpt-oss-120b 可用
    支持自动路由: :fastest / :cheapest / :preferred
    注意: 必须带 User-Agent, 否则 Cloudflare 会拦截 (403)
    """
    if not HF_KEY: return {"error": "HF_KEY not set", "source": "hf"}
    data = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature, "stream": False}
    headers = {"Authorization": f"Bearer {HF_KEY}", "Content-Type": "application/json", "User-Agent": "ACE-Miner/2.0"}
    req = urllib.request.Request(f"{HF_BASE}/chat/completions", data=json.dumps(data).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            result = json.loads(r.read().decode())
            result["source"] = "hf"
            return result
    except Exception as e: return {"error": f"Error: {e}", "source": "hf"}


# Provider 注册表
PROVIDERS = {
    "ollama": call_ollama,
    "hf": call_hf,
    "github": call_github_models,
    "zhipu": call_zhipu,
    "openrouter": call_openrouter,
}

# ============================================================
# Capability Graph — 能力为一等公民，模型只是资源
# ============================================================

# 能力继承图：复合能力自动展开为子能力
CAPABILITY_GRAPH = {
    # 基础能力（不可再分）
    "vision":      {"requires": [],           "desc": "图像/视觉理解"},
    "chinese":     {"requires": [],           "desc": "中文优化"},
    "fast":        {"requires": [],           "desc": "低延迟响应"},
    "long_context":{"requires": [],           "desc": "长上下文"},

    # 中级能力
    "summarize":   {"requires": [],           "desc": "摘要生成"},
    "reasoning":   {"requires": [],           "desc": "逻辑推理"},
    "coding":      {"requires": [],           "desc": "代码生成"},
    "debate":      {"requires": ["reasoning"], "desc": "辩论/多角度分析"},

    # 高级能力（自动继承子能力）
    "archaeology": {"requires": ["summarize", "reasoning"], "desc": "结构考古"},
    "code_review": {"requires": ["coding", "reasoning"],    "desc": "代码审查"},
    "research":    {"requires": ["summarize", "reasoning", "long_context"], "desc": "深度研究"},
    "planning":    {"requires": ["reasoning", "summarize"],  "desc": "任务规划"},
    "execution":   {"requires": ["coding", "reasoning"],     "desc": "执行任务"},
}

# Provider → 模型 → 支持的能力
# 模型只是资源，挂在能力下面
# HF Router 是一个 Provider 文明：一个入口，多个模型，按 capability 自动分工
MODELS = {
    # === Ollama (本地，优先级最高) ===
    "ollama-qwen-vl": {
        "provider": "ollama",
        "model": OLLAMA_MODEL,
        "capabilities": ["vision", "summarize", "archaeology", "coding", "chinese", "fast", "reasoning"],
        "priority": 1,
    },
    # === HuggingFace Router (一个入口，多个模型) ===
    # reasoning → gpt-oss-120b (120B, OpenAI 开源, 推理最强)
    "hf-gpt-oss-120b": {
        "provider": "hf",
        "model": "openai/gpt-oss-120b",
        "capabilities": ["reasoning", "research", "planning", "debate", "long_context"],
        "priority": 2,
    },
    # coding → DeepSeek-V3 (编码专精)
    "hf-deepseek-v3": {
        "provider": "hf",
        "model": "deepseek-ai/DeepSeek-V3",
        "capabilities": ["coding", "reasoning", "code_review", "long_context"],
        "priority": 3,
    },
    # fast/chinese → Qwen2.5-7B (轻量, 中文好)
    "hf-qwen-7b": {
        "provider": "hf",
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "capabilities": ["fast", "chinese", "summarize", "coding"],
        "priority": 3,
    },
    # summarize/debate → Llama-3.3-70B (通用大模型)
    "hf-llama-70b": {
        "provider": "hf",
        "model": "meta-llama/Llama-3.3-70B-Instruct",
        "capabilities": ["summarize", "debate", "reasoning", "long_context", "execution"],
        "priority": 4,
    },
    # === GitHub Models (备用) ===
    "github-gpt4omini": {
        "provider": "github",
        "model": "gpt-4o-mini",
        "capabilities": ["reasoning", "coding", "debate", "summarize", "chinese", "long_context"],
        "priority": 5,
    },
    # === Zhipu GLM (备用, 中文好) ===
    "glm-flash": {
        "provider": "zhipu",
        "model": "glm-4-flash",
        "capabilities": ["fast", "chinese", "summarize", "reasoning", "coding"],
        "priority": 6,
    },
    # === OpenRouter (最后兜底) ===
    "openrouter-llama": {
        "provider": "openrouter",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "capabilities": ["debate", "long_context", "reasoning", "coding", "summarize"],
        "priority": 7,
    },
}

# ============================================================
# Provider Health Monitor — Health Score 驱动路由
# ============================================================

class ProviderHealth:
    """Provider 健康度监控 — 不用试错，看 Health Score 选 Provider

    失败回写机制：当 Provider 状态降级时，自动沉淀 Experience，
    形成"失败→经验→约束"闭环，而不是只在内存里留痕。
    """

    def __init__(self):
        self._health = {}  # provider → {latency_ms, success_rate, total, success, last_check, status}
        self._exp_dir = Path(__file__).parent.parent / "02_MEMORY" / "experience"
        self._last_sedimented = {}  # provider → last status that was sedimented (避免重复写)

    def _sediment_failure(self, provider: str, prev_status: str, new_status: str):
        """当状态降级时，自动写一条 Experience"""
        if new_status == prev_status:
            return
        # 只在降级到 degraded/down 时写
        if new_status not in ("degraded", "down"):
            return
        # 同一状态不重复写
        if self._last_sedimented.get(provider) == new_status:
            return
        self._last_sedimented[provider] = new_status

        h = self._health.get(provider, {})
        exp = {
            "type": "provider_failure",
            "provider": provider,
            "prev_status": prev_status,
            "new_status": new_status,
            "success_rate": h.get("success", 0) / max(h.get("total", 1), 1),
            "total_calls": h.get("total", 0),
            "timestamp": datetime.now().isoformat(),
            "analysis": f"Provider '{provider}' 状态从 '{prev_status}' 降级到 '{new_status}'。"
                       f"成功率 {h.get('success',0)}/{h.get('total',0)}。"
                       f"建议：检查 API key/网络/配额，或切换到备用 Provider。",
        }
        try:
            self._exp_dir.mkdir(parents=True, exist_ok=True)
            fname = f"exp_provider_{provider}_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
            with open(self._exp_dir / fname, "w", encoding="utf-8") as f:
                json.dump(exp, f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass  # 经验写入失败不影响主流程

    def record(self, provider: str, success: bool, latency_ms: float = 0):
        """记录一次调用结果"""
        h = self._health.setdefault(provider, {
            "total": 0, "success": 0, "latency_sum": 0, "last_check": "", "status": "unknown"
        })
        prev_status = h.get("status", "unknown")
        h["total"] += 1
        if success:
            h["success"] += 1
            h["latency_sum"] += latency_ms
        h["last_check"] = datetime.now().isoformat()
        # 计算状态
        rate = h["success"] / h["total"] if h["total"] > 0 else 0
        if h["total"] < 3:
            h["status"] = "warming_up"
        elif rate >= 0.8:
            h["status"] = "healthy"
        elif rate >= 0.5:
            h["status"] = "degraded"
        else:
            h["status"] = "down"
        # 状态降级时自动沉淀 Experience
        self._sediment_failure(provider, prev_status, h["status"])

    def get_score(self, provider: str) -> float:
        """获取 Health Score (0.0~1.0)"""
        h = self._health.get(provider)
        if not h or h["total"] == 0:
            return 0.5  # 未知，给中间分
        rate = h["success"] / h["total"]
        # 状态惩罚
        if h["status"] == "down":
            return rate * 0.3
        if h["status"] == "degraded":
            return rate * 0.7
        return rate

    def get_status(self, provider: str) -> dict:
        """获取 Provider 状态摘要"""
        h = self._health.get(provider, {})
        avg_latency = h.get("latency_sum", 0) / h.get("success", 1) if h.get("success", 0) > 0 else 0
        return {
            "provider": provider,
            "status": h.get("status", "unknown"),
            "success_rate": h.get("success", 0) / h.get("total", 1) if h.get("total", 0) > 0 else 0,
            "total_calls": h.get("total", 0),
            "avg_latency_ms": round(avg_latency, 1),
            "last_check": h.get("last_check", ""),
            "health_score": round(self.get_score(provider), 2),
        }

    def all_status(self) -> list:
        """所有 Provider 状态"""
        return [self.get_status(p) for p in PROVIDERS]

    def should_skip(self, provider: str) -> bool:
        """是否应该跳过这个 Provider（连续失败或 down）"""
        h = self._health.get(provider)
        if not h:
            return False
        if h["status"] == "down" and h["total"] >= 3:
            return True
        # 连续3次失败
        return False


# 全局 Health Monitor 实例
health = ProviderHealth()


# Capability → 按优先级排序的 model 列表（运行时构建）
_CAPABILITY_INDEX: dict = {}

def _expand_capability(cap: str, seen: set = None) -> list:
    """展开复合能力为所有子能力"""
    if seen is None:
        seen = set()
    if cap in seen:
        return []
    seen.add(cap)
    result = [cap]
    cap_info = CAPABILITY_GRAPH.get(cap, {})
    for sub in cap_info.get("requires", []):
        result.extend(_expand_capability(sub, seen))
    return list(dict.fromkeys(result))  # 去重保序

def _build_capability_index():
    """构建 capability → 按优先级排序的 model 列表"""
    global _CAPABILITY_INDEX
    _CAPABILITY_INDEX = {}
    for entry_name, info in MODELS.items():
        for cap in info["capabilities"]:
            _CAPABILITY_INDEX.setdefault(cap, []).append((info["priority"], entry_name, info))
    for cap in _CAPABILITY_INDEX:
        _CAPABILITY_INDEX[cap].sort(key=lambda x: x[0])

_build_capability_index()


def list_capabilities() -> list:
    """列出所有可用 capability（含复合能力）"""
    return sorted(CAPABILITY_GRAPH.keys())


def list_models() -> list:
    """列出所有注册的模型"""
    return list(MODELS.keys())


def call_model(prompt, max_tokens=500, temperature=0.7, prefer=None, capability=None):
    """统一模型调用 — 按 Capability 路由 + Health Score 排序 + 自动 fallback

    路由逻辑：
    1. 如果指定 capability，展开子能力，找支持的最优模型
    2. 按 Health Score 排序（不试错，看历史表现）
    3. 如果指定 prefer，把它移到最前面
    4. 自动 fallback，记录 Health

    任何一个成功就返回，不继续尝试。
    """
    # 构建调用链
    if capability and capability in _CAPABILITY_INDEX:
        chain = [(info["provider"], info["model"]) for _, _, info in _CAPABILITY_INDEX[capability]]
    else:
        chain = list(MODEL_FALLBACK_CHAIN)

    # 如果指定 prefer，把该 provider 的模型移到最前面（保留原 model 名）
    if prefer and prefer in PROVIDERS:
        prefer_chain = [(p, m) for p, m in chain if p == prefer]
        other_chain = [(p, m) for p, m in chain if p != prefer]
        chain = prefer_chain + other_chain

    # 按 Health Score 排序（跳过 down 的 provider）
    # 但如果指定了 prefer，prefer 的 provider 永远在最前面
    def _sort_key(item):
        provider_name = item[0]
        if health.should_skip(provider_name):
            return (1, 0, 0)  # 排到最后
        prefer_boost = 0 if (prefer and provider_name == prefer) else 1
        return (prefer_boost, 0, -health.get_score(provider_name))

    chain.sort(key=_sort_key)

    errors = []
    for provider_name, model_name in chain:
        if health.should_skip(provider_name):
            errors.append(f"{provider_name}: skipped (health=down)")
            continue

        provider_fn = PROVIDERS.get(provider_name)
        if not provider_fn:
            continue
        if provider_name == "ollama" and not check_ollama_available():
            errors.append(f"ollama: not available")
            health.record("ollama", success=False)
            continue

        import time as _time
        t0 = _time.time()
        result = provider_fn(prompt, model=model_name, max_tokens=max_tokens, temperature=temperature)
        latency = (_time.time() - t0) * 1000

        if "error" not in result:
            health.record(provider_name, success=True, latency_ms=latency)
            result.setdefault("model", model_name)
            result["provider"] = provider_name
            result["capability"] = capability or "default"
            result["latency_ms"] = round(latency, 1)
            return result

        health.record(provider_name, success=False, latency_ms=latency)
        errors.append(f"{provider_name}: {result['error']}")

    return {"error": "All providers failed", "errors": errors}


def task_signal_discovery():
    print(f"[MINER] Signal Discovery @ {datetime.now().isoformat()}")
    obs_path = Path(__file__).parent.parent / "03_DATA" / "observation_log.json"
    observations = []
    if obs_path.exists():
        try:
            with open(obs_path) as f: observations = json.load(f).get("observations", [])[-20:]
        except: pass
    if not observations:
        observations = [
            {"time": "2026-07-10T14:00:00", "type": "market", "data": "HS300 volume spike +15%"},
            {"time": "2026-07-10T14:30:00", "type": "market", "data": "VIX down -8%"},
        ]
    prompt = f"""你是ACE矿工的信号发现层。分析以下观察记录，提取可能有效的市场信号模式。

观察记录:
{json.dumps(observations, ensure_ascii=False, indent=2)}

请输出JSON格式:
{{"signals": [...], "validation": "...", "risk": "..."}}
"""
    result = call_model(prompt, max_tokens=800)
    if "error" in result: return {"status": "error", "error": result["error"]}
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {"status": "ok", "task": "signal_discovery", "model": result.get("model"), "provider": result.get("provider"), "time": datetime.now().isoformat(), "response": content}


def task_archivist():
    print(f"[MINER] Archivist @ {datetime.now().isoformat()}")
    prompt = """你是ACE矿工的档案整理层。分析今日工作区状态并给出归档建议。

输出JSON格式:
{"to_archive": ["文件1", "文件2"], "to_distill": ["需要蒸馏的文件"], "review_notes": "备注"}
"""
    result = call_model(prompt, max_tokens=500)
    if "error" in result: return {"status": "error", "error": result["error"]}
    content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
    return {"status": "ok", "task": "archivist", "model": result.get("model"), "provider": result.get("provider"), "time": datetime.now().isoformat(), "response": content}


TASKS = {"signal_discovery": task_signal_discovery, "archivist": task_archivist}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", choices=list(TASKS.keys()))
    parser.add_argument("--test", action="store_true", help="Test model connectivity")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if args.test:
        print("=== Capability Graph ===")
        for cap, info in CAPABILITY_GRAPH.items():
            req = info.get("requires", [])
            print(f"  {cap:15s} requires={req}  ({info['desc']})")
        print(f"\n  All capabilities: {list_capabilities()}")

        print(f"\n=== Models (resources) ===")
        for name, info in MODELS.items():
            print(f"  {name:25s} provider={info['provider']:12s} caps={info['capabilities']}")

        print(f"\n=== Provider Connectivity ===")
        print(f"  Ollama ({OLLAMA_BASE}): {'OK' if check_ollama_available() else 'NOT AVAILABLE'}")
        print(f"  GitHub Models: {'OK' if GITHUB_PAT else 'NO PAT'}")
        print(f"  Zhipu: {'OK' if ZHIPU_KEY else 'NO KEY'}")
        print(f"  OpenRouter: {'OK' if OPENROUTER_KEY else 'NO KEY'}")

        print(f"\n=== Capability Routing Test ===")
        for cap in ["fast", "archaeology", "research", "debate"]:
            r = call_model(f"Say one word about {cap}.", max_tokens=10, capability=cap)
            if "error" in r:
                print(f"  {cap:15s} → FAILED ({r.get('errors', r.get('error'))})")
            else:
                print(f"  {cap:15s} → provider={r.get('provider'):12s} model={r.get('model')} latency={r.get('latency_ms','?')}ms")

        print(f"\n=== Provider Health ===")
        for s in health.all_status():
            print(f"  {s['provider']:12s} status={s['status']:12s} score={s['health_score']} calls={s['total_calls']} latency={s['avg_latency_ms']}ms")
        return

    if not args.task:
        parser.print_help()
        return

    result = TASKS.get(args.task)()
    if args.json: print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"Status: {result.get('status')}")
        if result.get('status') == 'ok':
            print(f"Provider: {result.get('provider')}, Model: {result.get('model')}")
            print(result.get('response', '')[:500])
        else: print(f"Error: {result.get('error')}")


if __name__ == "__main__":
    main()