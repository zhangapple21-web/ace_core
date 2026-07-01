"""
Provider Watchdog — Provider 健康看门狗

遵循协议：OPS-001 Provider 健康检查与自动切换

职责：
  - 实时监控各 Provider 健康状态
  - 故障时自动切换到备用 Provider
  - 记录切换事件，供审计和优化
  - 提供健康查询接口

设计原则：
  - 看门狗自身故障不得影响主循环
  - 状态持久化，重启不丢历史
  - 失败静默降级，不抛异常
"""

import json
import time
import socket
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime


HEALTHY = "HEALTHY"
DEGRADED = "DEGRADED"
UNHEALTHY = "UNHEALTHY"
OFFLINE = "OFFLINE"
RECOVERING = "RECOVERING"


@dataclass
class ProviderHealth:
    """单个 Provider 的健康状态"""
    provider: str
    base_url: str = ""
    status: str = UNHEALTHY
    last_check: float = 0.0
    last_success: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    latency_ms: int = 0
    total_calls: int = 0
    failed_calls: int = 0
    error_message: str = ""

    def to_dict(self) -> Dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "status": self.status,
            "last_check": self.last_check,
            "last_success": self.last_success,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "latency_ms": self.latency_ms,
            "total_calls": self.total_calls,
            "failed_calls": self.failed_calls,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, d: Dict) -> "ProviderHealth":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class SwitchEvent:
    """Provider 切换事件"""
    event_id: str
    timestamp: float
    provider_type: str
    from_provider: str
    to_provider: str
    trigger_reason: str
    from_status: str
    to_status: str
    operator: str = "watchdog"
    status: str = "completed"

    def to_dict(self) -> Dict:
        return self.__dict__


class ProviderWatchdog:
    """
    Provider 健康看门狗

    使用方式：
        watchdog = ProviderWatchdog(state_dir="path/to/state")
        watchdog.register_provider("glm", "https://...", "api_key")

        # 调用前快速检查
        if watchdog.is_healthy("glm"):
            # 调用 glm
            watchdog.record_success("glm", 150)
        else:
            # 切换到备用
            backup = watchdog.get_best_provider()
            # ...

        # 失败时
        watchdog.record_failure("glm", "connection_timeout")
    """

    def __init__(self, state_dir: Optional[str] = None):
        self._providers: Dict[str, ProviderHealth] = {}
        self._api_keys: Dict[str, str] = {}
        self._switch_events: List[SwitchEvent] = []
        self._state_dir = Path(state_dir) if state_dir else None
        self._loaded = False

        if self._state_dir:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            self._load_state()

    def _load_state(self):
        """从磁盘加载状态"""
        if not self._state_dir:
            return
        try:
            state_file = self._state_dir / "watchdog_state.json"
            if state_file.exists():
                data = json.loads(state_file.read_text(encoding="utf-8"))
                for pname, pdata in data.get("providers", {}).items():
                    self._providers[pname] = ProviderHealth.from_dict(pdata)
                self._switch_events = [
                    SwitchEvent(**e) for e in data.get("switch_events", [])[-100:]
                ]
            self._loaded = True
        except Exception:
            self._loaded = False

    def _save_state(self):
        """保存状态到磁盘"""
        if not self._state_dir:
            return
        try:
            data = {
                "providers": {k: v.to_dict() for k, v in self._providers.items()},
                "switch_events": [e.to_dict() for e in self._switch_events[-200:]],
                "last_updated": time.time(),
            }
            state_file = self._state_dir / "watchdog_state.json"
            state_file.write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
        except Exception:
            pass

    def register_provider(self, name: str, base_url: str, api_key: str = ""):
        """注册一个 Provider"""
        if name not in self._providers:
            self._providers[name] = ProviderHealth(
                provider=name,
                base_url=base_url,
                status=UNHEALTHY,
            )
        else:
            self._providers[name].base_url = base_url
        if api_key:
            self._api_keys[name] = api_key
        self._save_state()

    def is_healthy(self, provider_name: str) -> bool:
        """快速检查 Provider 是否健康（不发起网络请求）"""
        p = self._providers.get(provider_name)
        if not p:
            return False
        return p.status in (HEALTHY, RECOVERING, DEGRADED)

    def get_best_provider(self, exclude: List[str] = None) -> Optional[str]:
        """获取当前最佳可用 Provider"""
        exclude = set(exclude or [])
        candidates = []
        for name, p in self._providers.items():
            if name in exclude:
                continue
            if p.status in (HEALTHY, RECOVERING, DEGRADED):
                score = self._health_score(p)
                candidates.append((name, score))
        if not candidates:
            return None
        candidates.sort(key=lambda x: x[1], reverse=True)
        return candidates[0][0]

    @staticmethod
    def _health_score(p: ProviderHealth) -> float:
        """计算健康分数（越高越好）"""
        status_scores = {
            HEALTHY: 100,
            RECOVERING: 70,
            DEGRADED: 50,
            UNHEALTHY: 20,
            OFFLINE: 0,
        }
        score = status_scores.get(p.status, 0)
        # 成功率加成
        if p.total_calls > 10:
            success_rate = (p.total_calls - p.failed_calls) / p.total_calls
            score += success_rate * 10
        # 延迟惩罚
        if p.latency_ms > 0:
            if p.latency_ms > 5000:
                score -= 20
            elif p.latency_ms > 2000:
                score -= 10
        return score

    def quick_check(self, provider_name: str) -> bool:
        """
        L1 快速检查：TCP 连通性
        耗时 < 3s，用于调用前探活
        """
        p = self._providers.get(provider_name)
        if not p:
            return False

        try:
            from urllib.parse import urlparse
            parsed = urlparse(p.base_url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            if not host:
                return False
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((host, port))
            sock.close()
            p.last_check = time.time()
            return True
        except Exception:
            return False

    def deep_check(self, provider_name: str, test_model: str = "gpt-4o") -> Dict:
        """
        L3/L4 深度检查：HTTP + 功能验证
        """
        p = self._providers.get(provider_name)
        if not p:
            return {"status": "unknown", "error": "provider not found"}

        api_key = self._api_keys.get(provider_name, "")
        base_url = p.base_url.rstrip("/")
        result = {
            "tcp": False,
            "http": False,
            "models_endpoint": False,
            "chat_completion": False,
            "latency_ms": 0,
            "error": "",
        }

        # TCP
        try:
            from urllib.parse import urlparse
            parsed = urlparse(base_url)
            host = parsed.hostname
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            sock.connect((host, port))
            sock.close()
            result["tcp"] = True
        except Exception as e:
            result["error"] = f"tcp_failed: {str(e)[:60]}"
            self._update_status(p, OFFLINE, result["error"])
            return result

        # HTTP /v1/models
        try:
            models_url = base_url
            if not models_url.endswith("/v1"):
                models_url = base_url + "/v1"
            models_url += "/models"
            r = requests.get(
                models_url,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            result["http"] = True
            if r.status_code == 200:
                result["models_endpoint"] = True
            else:
                result["error"] = f"models_{r.status_code}: {r.text[:80]}"
        except Exception as e:
            result["error"] = f"http_failed: {str(e)[:60]}"

        # Chat Completion
        if result["models_endpoint"]:
            try:
                start = time.time()
                chat_url = base_url
                if not chat_url.endswith("/v1"):
                    chat_url = base_url + "/v1"
                chat_url += "/chat/completions"
                r = requests.post(
                    chat_url,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": test_model,
                        "messages": [{"role": "user", "content": "hi"}],
                        "max_tokens": 10,
                    },
                    timeout=30,
                )
                elapsed = int((time.time() - start) * 1000)
                result["latency_ms"] = elapsed
                if r.status_code == 200:
                    result["chat_completion"] = True
                else:
                    result["error"] = f"chat_{r.status_code}: {r.text[:80]}"
            except Exception as e:
                result["error"] = f"chat_failed: {str(e)[:60]}"

        # 更新状态
        p.last_check = time.time()
        if result["chat_completion"]:
            p.latency_ms = result["latency_ms"]
            if p.status in (UNHEALTHY, OFFLINE):
                p.status = RECOVERING
                p.consecutive_successes = 1
            elif p.status == RECOVERING:
                p.consecutive_successes += 1
                if p.consecutive_successes >= 5:
                    p.status = HEALTHY
            else:
                p.status = HEALTHY
                p.consecutive_successes += 1
            p.last_success = time.time()
        elif result["models_endpoint"]:
            p.status = DEGRADED
        elif result["http"]:
            p.status = UNHEALTHY
        else:
            p.status = OFFLINE
            p.consecutive_failures += 1

        self._save_state()
        return result

    def record_success(self, provider_name: str, latency_ms: int):
        """记录一次成功调用"""
        p = self._providers.get(provider_name)
        if not p:
            return
        p.total_calls += 1
        p.last_success = time.time()
        p.latency_ms = latency_ms
        p.consecutive_failures = 0
        p.consecutive_successes += 1

        if p.status == OFFLINE or p.status == UNHEALTHY:
            p.status = RECOVERING
        elif p.status == RECOVERING and p.consecutive_successes >= 5:
            p.status = HEALTHY
        elif p.status == DEGRADED:
            p.status = HEALTHY

        self._save_state()

    def record_failure(self, provider_name: str, error: str = ""):
        """记录一次失败调用，触发自动切换判断"""
        p = self._providers.get(provider_name)
        if not p:
            return

        p.total_calls += 1
        p.failed_calls += 1
        p.consecutive_failures += 1
        p.consecutive_successes = 0
        p.error_message = error

        # 连续失败则降级
        if p.consecutive_failures >= 3:
            if p.status == HEALTHY:
                p.status = DEGRADED
            elif p.status == DEGRADED:
                p.status = UNHEALTHY
            elif p.status == UNHEALTHY:
                p.status = OFFLINE

        self._save_state()

        # 自动切换
        if p.status in (UNHEALTHY, OFFLINE):
            backup = self.get_best_provider(exclude=[provider_name])
            if backup:
                self._record_switch(
                    from_provider=provider_name,
                    to_provider=backup,
                    reason=f"consecutive_failures_{p.consecutive_failures}",
                    from_status=p.status,
                    to_status=self._providers[backup].status,
                )

    def _record_switch(self, from_provider: str, to_provider: str,
                       reason: str, from_status: str, to_status: str):
        """记录切换事件"""
        event = SwitchEvent(
            event_id=f"SWITCH-{int(time.time())}",
            timestamp=time.time(),
            provider_type="llm",
            from_provider=from_provider,
            to_provider=to_provider,
            trigger_reason=reason,
            from_status=from_status,
            to_status=to_status,
        )
        self._switch_events.append(event)
        self._save_state()

    def list_providers(self) -> List[Dict]:
        """列出所有 Provider 状态"""
        return [
            {
                "name": name,
                "status": p.status,
                "latency_ms": p.latency_ms,
                "total_calls": p.total_calls,
                "failed_calls": p.failed_calls,
                "consecutive_failures": p.consecutive_failures,
            }
            for name, p in self._providers.items()
        ]

    def get_stats(self) -> Dict:
        """获取统计信息"""
        providers = self.list_providers()
        healthy = sum(1 for p in providers if p["status"] == HEALTHY)
        degraded = sum(1 for p in providers if p["status"] == DEGRADED)
        unhealthy = sum(1 for p in providers if p["status"] == UNHEALTHY)
        offline = sum(1 for p in providers if p["status"] == OFFLINE)
        recovering = sum(1 for p in providers if p["status"] == RECOVERING)

        total_calls = sum(p["total_calls"] for p in providers)
        total_failed = sum(p["failed_calls"] for p in providers)
        success_rate = (total_calls - total_failed) / total_calls if total_calls > 0 else 0

        return {
            "total_providers": len(providers),
            "healthy": healthy,
            "recovering": recovering,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "offline": offline,
            "total_calls": total_calls,
            "total_failed": total_failed,
            "success_rate": round(success_rate, 4),
            "switch_count": len(self._switch_events),
            "recent_switches": [e.to_dict() for e in self._switch_events[-10:]],
        }

    def run_full_check(self, test_models: Dict[str, str] = None) -> Dict:
        """执行所有 Provider 的深度检查"""
        test_models = test_models or {}
        results = {}
        for name in self._providers:
            model = test_models.get(name, "gpt-4o")
            results[name] = self.deep_check(name, test_model=model)
        return results


# 全局单例
_watchdog: Optional[ProviderWatchdog] = None


def get_provider_watchdog(state_dir: Optional[str] = None) -> ProviderWatchdog:
    """获取全局 Watchdog 单例"""
    global _watchdog
    if _watchdog is None:
        _watchdog = ProviderWatchdog(state_dir=state_dir)
    return _watchdog
