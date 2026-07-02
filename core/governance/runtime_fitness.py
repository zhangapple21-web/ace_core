"""
Runtime Fitness（运行时健康度）

核心职责：
    持续验证 Runtime 的执行能力是否退化。

    文明可以每天成长，但 Runtime 不允许每天退化。

    每次启动或每日节律时，自动跑一遍所有 Provider，
    输出 Runtime Fitness Score。

    如果 Fitness 下降到阈值以下，
    Governor 应该优先恢复执行能力，
    禁止继续新增功能。

设计原则：
    - 不假设原因，只验证事实
    - 每个 Provider 至少发一个真实请求
    - 记录历史基线，检测退化
    - 结果可追溯，每次检查都有证据
"""

import json
import logging
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class ProviderCheckResult:
    """单个 Provider 检查结果"""
    provider_name: str
    model: str
    base_url: str
    passed: bool
    status: str  # PASS / FAIL / TIMEOUT / ERROR
    latency_ms: int = 0
    error: str = ""
    response_preview: str = ""
    timestamp: str = ""
    request_body: Dict = field(default_factory=dict)
    response_status: int = 0
    failure_code: str = ""  # 故障分类代码（来自 FailureTaxonomy）


@dataclass
class RuntimeFitnessReport:
    """Runtime Fitness 报告"""
    timestamp: str = ""
    total_providers: int = 0
    passed: int = 0
    failed: int = 0
    fitness_score: float = 0.0  # 0~100
    previous_score: float = 0.0  # 上一次的分数
    score_change: float = 0.0   # 变化量
    is_regression: bool = False  # 是否退化
    results: List[ProviderCheckResult] = field(default_factory=list)
    baseline_date: str = ""      # 基线日期
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total_providers": self.total_providers,
            "passed": self.passed,
            "failed": self.failed,
            "fitness_score": self.fitness_score,
            "previous_score": self.previous_score,
            "score_change": self.score_change,
            "is_regression": self.is_regression,
            "baseline_date": self.baseline_date,
            "results": [
                {
                    "provider_name": r.provider_name,
                    "model": r.model,
                    "base_url": r.base_url,
                    "passed": r.passed,
                    "status": r.status,
                    "latency_ms": r.latency_ms,
                    "error": r.error[:200] if r.error else "",
                    "response_preview": r.response_preview[:200],
                    "timestamp": r.timestamp,
                    "response_status": r.response_status,
                    "failure_code": r.failure_code,
                }
                for r in self.results
            ],
            "details": self.details,
        }


class RuntimeFitnessChecker:
    """
    Runtime Fitness 检查器

    核心逻辑：
        1. 遍历所有已配置的 Provider
        2. 每个发一个最小请求（max_tokens=5）
        3. 记录成功/失败/延迟
        4. 计算 Fitness Score = pass/total * 100
        5. 与历史基线对比，检测退化
    """

    def __init__(self, ace_runtime_dir: str):
        self.ace_runtime_dir = Path(ace_runtime_dir)
        self.data_dir = self.ace_runtime_dir / "08_GOVERNANCE" / "runtime_fitness"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.data_dir / "fitness_history.jsonl"
        self.baseline_file = self.data_dir / "baseline.json"

        self._providers_config: Optional[Dict] = None

    def _load_providers_from_engine(self) -> Dict[str, Dict]:
        """从 SurvivalLoopEngine 加载 Provider 配置"""
        try:
            import sys
            sys.path.insert(0, str(self.ace_runtime_dir))
            from core.survival_loop.engine import SurvivalLoopEngine

            engine = SurvivalLoopEngine()
            return engine._providers
        except Exception as e:
            logger.warning(f"从 SurvivalLoopEngine 加载 Provider 失败: {e}")
            return {}

    def get_providers(self) -> Dict[str, Dict]:
        """获取所有 Provider 配置"""
        if self._providers_config is None:
            self._providers_config = self._load_providers_from_engine()
        return self._providers_config

    # 不同 Provider 的超时时间（秒）
    PROVIDER_TIMEOUTS = {
        "nim": 60,
        "oneapi": 45,
        "openrouter": 45,
        "sambanova": 30,
    }

    def check_provider(self, name: str, provider_config: Dict,
                       timeout: int = 30) -> ProviderCheckResult:
        """
        检查单个 Provider

        Args:
            name: Provider 名称
            provider_config: Provider 配置（base_url, api_key, model 等）
            timeout: 超时时间（秒）

        Returns:
            ProviderCheckResult
        """
        base_url = provider_config.get("base_url", "")
        api_key = provider_config.get("api_key", "")
        model = provider_config.get("model", "")

        # 按 Provider 使用不同的超时时间
        effective_timeout = self.PROVIDER_TIMEOUTS.get(name, timeout)

        result = ProviderCheckResult(
            provider_name=name,
            model=model,
            base_url=base_url,
            passed=False,
            status="ERROR",
            timestamp=datetime.now().isoformat(),
        )

        if not base_url or not api_key or not model:
            result.status = "ERROR"
            result.error = f"配置不完整: base_url={bool(base_url)}, api_key={bool(api_key)}, model={bool(model)}"
            return result

        chat_url = base_url.rstrip("/") + "/chat/completions"

        payload = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5,
            "temperature": 0.1,
        }
        result.request_body = payload

        req = urllib.request.Request(
            chat_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )

        start = time.time()
        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                latency = int((time.time() - start) * 1000)

                result.latency_ms = latency
                result.response_status = resp.status

                try:
                    data = json.loads(body)
                    if "choices" in data and len(data["choices"]) > 0:
                        result.passed = True
                        result.status = "PASS"
                        content = data["choices"][0].get("message", {}).get("content", "")
                        result.response_preview = content
                    else:
                        result.status = "FAIL"
                        result.error = "响应格式异常，无 choices 字段"
                        result.response_preview = body[:200]
                except Exception as e:
                    result.status = "FAIL"
                    result.error = f"响应解析失败: {e}"
                    result.response_preview = body[:200]

        except urllib.error.HTTPError as e:
            latency = int((time.time() - start) * 1000)
            result.latency_ms = latency
            result.response_status = e.code
            result.status = "FAIL"
            try:
                err_body = e.read().decode("utf-8", errors="replace")
                result.error = f"HTTP {e.code}: {err_body[:150]}"
                result.response_preview = err_body[:200]
            except Exception:
                result.error = f"HTTP {e.code}"

        except urllib.error.URLError as e:
            latency = int((time.time() - start) * 1000)
            result.latency_ms = latency
            result.status = "FAIL"
            result.error = f"URL Error: {e.reason}"

        except TimeoutError:
            result.latency_ms = int((time.time() - start) * 1000)
            result.status = "TIMEOUT"
            result.error = f"请求超时（>{effective_timeout}s）"

        except Exception as e:
            latency = int((time.time() - start) * 1000)
            result.latency_ms = latency
            result.status = "ERROR"
            result.error = f"{type(e).__name__}: {str(e)[:100]}"

        # Failure Taxonomy 分类（仅失败时）
        if not result.passed:
            try:
                from core.governance.failure_taxonomy import FailureTaxonomy
                classification = FailureTaxonomy.classify(
                    error_msg=result.error,
                    http_status=result.response_status,
                    status=result.status,
                )
                result.failure_code = classification.code
            except Exception:
                pass
        else:
            result.failure_code = "PASS"

        return result

    def check_all(self, timeout_per_provider: int = 30) -> RuntimeFitnessReport:
        """
        检查所有 Provider，生成 Fitness 报告

        Args:
            timeout_per_provider: 每个 Provider 的超时时间（秒）

        Returns:
            RuntimeFitnessReport
        """
        providers = self.get_providers()
        results: List[ProviderCheckResult] = []

        logger.info(f"开始 Runtime Fitness 检查，共 {len(providers)} 个 Provider")

        for name, config in providers.items():
            logger.info(f"  检查 {name}...")
            result = self.check_provider(name, config, timeout=timeout_per_provider)
            results.append(result)
            status_icon = "✅" if result.passed else "❌"
            logger.info(f"    {status_icon} {result.status} ({result.latency_ms}ms)")

        passed = sum(1 for r in results if r.passed)
        total = len(results)
        score = round((passed / total) * 100, 1) if total > 0 else 0.0

        # 获取上一次分数
        prev_score = self._get_previous_score()
        score_change = round(score - prev_score, 1)
        is_regression = score < prev_score - 5  # 下降超过 5% 视为退化

        report = RuntimeFitnessReport(
            timestamp=datetime.now().isoformat(),
            total_providers=total,
            passed=passed,
            failed=total - passed,
            fitness_score=score,
            previous_score=prev_score,
            score_change=score_change,
            is_regression=is_regression,
            results=results,
            baseline_date=self._get_baseline_date(),
        )

        # 保存历史
        self._save_history(report)

        # 如果是第一次或分数更高，更新基线
        if prev_score == 0 or score > prev_score:
            self._update_baseline(report)

        logger.info(
            f"Runtime Fitness 完成: {passed}/{total} = {score}% "
            f"(上次: {prev_score}%, 变化: {score_change:+.1f}%)"
        )

        if is_regression:
            logger.warning(f"⚠️  Runtime 退化检测: 分数下降 {abs(score_change)}%")

        return report

    def _get_previous_score(self) -> float:
        """获取上一次的 Fitness 分数"""
        if not self.history_file.exists():
            return 0.0
        try:
            last_line = ""
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last_line = line
            if last_line:
                data = json.loads(last_line)
                return data.get("fitness_score", 0.0)
        except Exception as e:
            logger.warning(f"读取历史 Fitness 失败: {e}")
        return 0.0

    def _get_baseline_date(self) -> str:
        """获取基线日期"""
        if self.baseline_file.exists():
            try:
                with open(self.baseline_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("timestamp", "")[:10]
            except Exception:
                pass
        return ""

    def _save_history(self, report: RuntimeFitnessReport):
        """保存历史记录"""
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存 Fitness 历史失败: {e}")

    def _update_baseline(self, report: RuntimeFitnessReport):
        """更新基线（新高时更新）"""
        try:
            baseline_data = report.to_dict()
            baseline_data["updated_at"] = datetime.now().isoformat()
            with open(self.baseline_file, "w", encoding="utf-8") as f:
                json.dump(baseline_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Fitness 基线已更新: {report.fitness_score}%")
        except Exception as e:
            logger.error(f"更新基线失败: {e}")

    def get_history(self, days: int = 7) -> List[Dict]:
        """获取最近 N 天的历史记录"""
        if not self.history_file.exists():
            return []

        records = []
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        try:
            with open(self.history_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        if data.get("timestamp", "") >= cutoff:
                            records.append(data)
                    except Exception:
                        continue
        except Exception as e:
            logger.warning(f"读取 Fitness 历史失败: {e}")

        return records

    def get_baseline(self) -> Optional[Dict]:
        """获取基线数据"""
        if not self.baseline_file.exists():
            return None
        try:
            with open(self.baseline_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def generate_markdown_report(self, report: RuntimeFitnessReport) -> str:
        """生成 Markdown 格式的报告"""
        lines = []

        lines.append("# Runtime Fitness Report")
        lines.append("")
        lines.append(f"**时间**: {report.timestamp}")
        lines.append(f"**基线日期**: {report.baseline_date or '无'}")
        lines.append("")

        # 总体评分
        lines.append("## 总体评分")
        lines.append("")

        if report.is_regression:
            lines.append(f"> ⚠️  **Runtime 退化检测**：分数较上次下降 {abs(report.score_change)}%")
            lines.append("")
        elif report.score_change > 0:
            lines.append(f"> ✅  **Runtime 能力提升**：分数较上次上升 {report.score_change}%")
            lines.append("")

        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| Fitness Score | **{report.fitness_score}%** |")
        lines.append(f"| 上次分数 | {report.previous_score}% |")
        lines.append(f"| 变化 | {report.score_change:+.1f}% |")
        lines.append(f"| 通过 Provider | {report.passed}/{report.total_providers} |")
        lines.append(f"| 失败 Provider | {report.failed}/{report.total_providers} |")
        lines.append("")

        # 详细结果
        lines.append("## Provider 详细结果")
        lines.append("")
        lines.append("| Provider | Model | 状态 | 延迟 | 错误 | Failure Code |")
        lines.append("|----------|-------|------|------|------|--------------|")

        for r in report.results:
            status_icon = "✅ PASS" if r.passed else f"❌ {r.status}"
            error_display = r.error[:50] if r.error else "-"
            model_short = r.model.split("/")[-1] if "/" in r.model else r.model
            failure_code = getattr(r, 'failure_code', '')
            lines.append(
                f"| {r.provider_name} | {model_short} | {status_icon} | "
                f"{r.latency_ms}ms | {error_display} | {failure_code} |"
            )

        lines.append("")

        # 退化的 Provider（与基线对比）
        baseline = self.get_baseline()
        if baseline and baseline.get("results"):
            baseline_passed = {r["provider_name"] for r in baseline["results"] if r["passed"]}
            now_failed = {r.provider_name for r in report.results if not r.passed}
            regressed = baseline_passed & now_failed

            if regressed:
                lines.append("## 退化 Provider 列表")
                lines.append("")
                lines.append("基线时通过，现在失败的 Provider：")
                lines.append("")
                for name in sorted(regressed):
                    result = next((r for r in report.results if r.provider_name == name), None)
                    if result:
                        failure_code = getattr(result, 'failure_code', 'UNKNOWN')
                        lines.append(f"- **{name}**: {result.status} [{failure_code}] - {result.error[:80]}")
                lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("> **文明可以每天成长，但 Runtime 不允许每天退化。**")

        return "\n".join(lines)


# ============================================================================
# 扩展：完整 Runtime Fitness 体系（PART 1-6 + TASK A-F）
# ============================================================================

class RuntimeFitnessSuite:
    """
    Runtime Fitness 完整套件

    整合：
        - Provider Fitness Engine (PART 1)
        - Fitness Score (PART 2)
        - Regression Detection (PART 3)
        - Evidence Chain (PART 4)
        - Forensics Integration (PART 5)
        - Runtime Constitution (PART 6)
        - Provider Registry (TASK-A)
        - Model Verification (TASK-B)
        - Capability Matrix (TASK-C)
        - Key Health (TASK-D)
        - Weighted Routing (TASK-E) - 数据支持
        - Failure Memory (TASK-F)
    """

    def __init__(self, ace_runtime_dir: str):
        self.ace_runtime_dir = Path(ace_runtime_dir)
        self.governance_dir = self.ace_runtime_dir / "08_GOVERNANCE"
        self.governance_dir.mkdir(parents=True, exist_ok=True)

        # 子模块
        self.checker = RuntimeFitnessChecker(str(ace_runtime_dir))
        self.registry = None  # 延迟加载
        self.model_verifier = None
        self.failure_memory = None
        self.key_health = None

    def _lazy_init(self):
        """延迟初始化子模块"""
        from core.governance.provider_registry import ProviderRegistry
        from core.governance.model_verifier import ModelVerifier
        from core.governance.failure_memory import FailureMemory
        from core.governance.key_health import KeyHealthManager

        if not self.registry:
            self.registry = ProviderRegistry(str(self.governance_dir))
        if not self.failure_memory:
            self.failure_memory = FailureMemory(str(self.governance_dir))
        if not self.key_health:
            self.key_health = KeyHealthManager(str(self.governance_dir))
        if not self.model_verifier:
            self.model_verifier = ModelVerifier(str(self.ace_runtime_dir))

    def run_full_check(self) -> Dict[str, Any]:
        """
        运行完整的 Runtime Fitness 检查

        Returns:
            包含所有报告的字典
        """
        self._lazy_init()

        results = {
            "timestamp": datetime.now().isoformat(),
            "fitness": None,
            "model_verification": None,
            "failure_stats": None,
            "key_health": None,
            "registry_summary": None,
            "capability_matrix": None,
        }

        # 1. Provider Fitness
        fitness_report = self.checker.check_all()
        results["fitness"] = fitness_report.to_dict()

        # 同步 Key Health 和 Failure Memory
        from core.governance.failure_taxonomy import FailureTaxonomy
        for r in fitness_report.results:
            providers = self.checker.get_providers()
            api_key = providers.get(r.provider_name, {}).get("api_key", "")

            if r.passed:
                if api_key:
                    self.key_health.record_success(
                        provider=r.provider_name,
                        api_key=api_key,
                        latency_ms=r.latency_ms,
                    )
            else:
                classification = FailureTaxonomy.classify(
                    error_msg=r.error,
                    http_status=getattr(r, 'response_status', 0),
                    status=r.status,
                )
                # 写入 failure_code 到 result
                r.failure_code = classification.code
                if api_key:
                    self.key_health.record_failure(
                        provider=r.provider_name,
                        api_key=api_key,
                        latency_ms=r.latency_ms,
                        reason=r.error,
                    )
                # 写入 Failure Memory
                self.failure_memory.record_failure(
                    classification=classification,
                    provider=r.provider_name,
                    model=r.model,
                    evidence={
                        "url": providers.get(r.provider_name, {}).get("base_url", "") + "/chat/completions",
                        "model": r.model,
                        "error": r.error[:200],
                        "http_status": getattr(r, 'response_status', 0),
                    },
                )

        # 2. Model Verification
        try:
            verify_report = self.model_verifier.verify_all()
            results["model_verification"] = verify_report.to_dict()
        except Exception as e:
            results["model_verification"] = {"error": str(e)}

        # 3. Failure Memory 统计
        results["failure_stats"] = self.failure_memory.get_failure_stats()

        # 4. Key Health 摘要
        results["key_health"] = self.key_health.get_health_summary()

        # 5. Registry 摘要
        results["registry_summary"] = {
            "total_providers": len(self.registry.list_providers()),
            "total_models": len(self.registry.list_models(status=None)),
            "verified_models": len(self.registry.list_models(verified_only=True)),
        }

        # 6. Capability Matrix
        results["capability_matrix"] = self.registry.get_capability_matrix()

        return results

    def generate_full_report_markdown(self, results: Dict = None) -> str:
        """生成完整的 Markdown 报告"""
        if results is None:
            results = self.run_full_check()

        lines = []
        lines.append("# Runtime Fitness Suite — 完整报告")
        lines.append("")
        lines.append(f"**生成时间**: {results['timestamp']}")
        lines.append("")

        # 一、Runtime Fitness Score
        fitness = results.get("fitness", {})
        score = fitness.get("fitness_score", 0)
        prev_score = fitness.get("previous_score", 0)
        change = fitness.get("score_change", 0)
        is_regression = fitness.get("is_regression", False)
        passed = fitness.get("passed", 0)
        total = fitness.get("total_providers", 0)

        lines.append("## 一、Runtime Fitness Score")
        lines.append("")

        if is_regression:
            lines.append(f"> ⚠️  **Runtime Capability Regression** — 分数下降 {abs(change)}%")
            lines.append("")

        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| **Fitness Score** | **{score}%** |")
        lines.append(f"| 上次分数 | {prev_score}% |")
        lines.append(f"| 变化 | {change:+.1f}% |")
        lines.append(f"| Provider 通过 | {passed}/{total} |")
        lines.append("")

        # 二、Provider 详细结果
        lines.append("## 二、Provider 详细结果")
        lines.append("")
        lines.append("| Provider | 状态 | 延迟 | Failure Code |")
        lines.append("|----------|------|------|--------------|")

        for r in fitness.get("results", []):
            status = "✅" if r["passed"] else "❌"
            lines.append(
                f"| {r['provider_name']} | {status} {r['status']} | "
                f"{r['latency_ms']}ms | {r.get('failure_code', 'N/A')} |"
            )

        lines.append("")

        # 三、模型验证
        mv = results.get("model_verification", {})
        if mv and "error" not in mv:
            lines.append("## 三、模型验证")
            lines.append("")
            lines.append(f"总模型: {mv.get('total_models', 0)} | "
                        f"通过: {mv.get('passed', 0)} | "
                        f"失败: {mv.get('failed', 0)}")
            lines.append("")

            nf = mv.get("not_found_404", [])
            if nf:
                lines.append("### ⚠️  404 模型")
                lines.append("")
                for m in nf:
                    lines.append(f"- ❌ `{m}`")
                lines.append("")

            unauth = mv.get("unauthorized", [])
            if unauth:
                lines.append("### 🔒 认证失败")
                lines.append("")
                for m in unauth:
                    lines.append(f"- `{m}`")
                lines.append("")

        # 四、Failure Memory
        fm = results.get("failure_stats", {})
        if fm:
            lines.append("## 四、Failure Memory")
            lines.append("")
            lines.append(f"| 指标 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| 故障种类 | {fm.get('total_failures', 0)} |")
            lines.append(f"| 总发生次数 | {fm.get('total_occurrences', 0)} |")
            lines.append(f"| 关键故障 | {fm.get('critical_count', 0)} |")
            lines.append(f"| 未修复 | {fm.get('open_count', 0) + fm.get('investigating_count', 0)} |")
            lines.append("")

            lines.append("### 按分类")
            lines.append("")
            for cat, count in fm.get("by_category", {}).items():
                cat_name = {"auth": "认证", "model": "模型", "network": "网络",
                           "server": "服务端", "config": "配置", "parse": "解析",
                           "unknown": "未知"}.get(cat, cat)
                lines.append(f"- **{cat_name}**: {count} 种")
            lines.append("")

        # 五、Key Health
        kh = results.get("key_health", {})
        if kh and kh.get("total_keys", 0) > 0:
            lines.append("## 五、Key Health")
            lines.append("")
            lines.append(f"| 指标 | 值 |")
            lines.append(f"|------|-----|")
            lines.append(f"| Key 总数 | {kh.get('total_keys', 0)} |")
            lines.append(f"| 平均健康度 | {kh.get('avg_health', 0)}% |")
            lines.append(f"| 总成功率 | {kh.get('overall_success_rate', 0)}% |")
            lines.append(f"| healthy | {kh.get('by_status', {}).get('healthy', 0)} |")
            lines.append(f"| degraded | {kh.get('by_status', {}).get('degraded', 0)} |")
            lines.append(f"| unhealthy | {kh.get('by_status', {}).get('unhealthy', 0)} |")
            lines.append(f"| suspended | {kh.get('by_status', {}).get('suspended', 0)} |")
            lines.append("")

        # 六、Registry 摘要
        rs = results.get("registry_summary", {})
        if rs:
            lines.append("## 六、Provider Registry")
            lines.append("")
            lines.append(f"- Provider 数: {rs.get('total_providers', 0)}")
            lines.append(f"- 模型总数: {rs.get('total_models', 0)}")
            lines.append(f"- 已验证模型: {rs.get('verified_models', 0)}")
            lines.append("")

        lines.append("---")
        lines.append("")
        lines.append("## 宪法原则")
        lines.append("")
        lines.append("> **Runtime Capability Non-Regression**")
        lines.append(">")
        lines.append("> 任何 Runtime 在进入下一阶段演化之前，")
        lines.append("> 必须保持不少于上一版本的 Provider 可用能力。")
        lines.append("> 若 Runtime Fitness 下降，")
        lines.append("> 优先恢复执行能力，")
        lines.append("> 禁止继续新增功能。")
        lines.append("")
        lines.append("> 文明可以每天成长，但 Runtime 不允许每天退化。")

        return "\n".join(lines)

    def save_full_report(self, output_dir: str = None):
        """保存完整报告到文件"""
        results = self.run_full_check()

        if output_dir is None:
            output_dir = self.ace_runtime_dir / "08_ARCHAEOLOGY" / "ops"
        else:
            output_dir = Path(output_dir)

        output_dir.mkdir(parents=True, exist_ok=True)

        # JSON 原始数据
        json_file = output_dir / f"runtime_fitness_suite_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # Markdown 报告
        md_content = self.generate_full_report_markdown(results)
        md_file = output_dir / "RUNTIME_FITNESS_REPORT.md"
        with open(md_file, "w", encoding="utf-8") as f:
            f.write(md_content)

        # 最新报告（symlink 替代：直接覆盖 latest）
        latest_md = output_dir / "runtime_fitness_latest.md"
        with open(latest_md, "w", encoding="utf-8") as f:
            f.write(md_content)

        return md_file, json_file
