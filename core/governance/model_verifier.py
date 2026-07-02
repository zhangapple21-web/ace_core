"""
Model Verification Pipeline（模型验证管道）

核心职责：
    自动遍历所有模型，发送最小请求，
    验证是否存在、是否有权限、响应是否正常。

    任何 404 直接进入文明警报。

    验证维度：
        1. 模型存在性（404 = 不存在）
        2. 权限（401/403 = 无权限）
        3. 响应格式（是否有 choices 字段）
        4. 延迟（响应时间）
        5. 速率限制（429 = 限流）

    输出：
        - 每个模型的验证结果
        - 404 模型列表（直接告警）
        - 验证报告
"""

import json
import logging
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from core.governance.provider_registry import ProviderRegistry, ProviderModel
from core.governance.failure_taxonomy import FailureTaxonomy, FailureClassification
from core.governance.failure_memory import FailureMemory

logger = logging.getLogger(__name__)


@dataclass
class ModelVerificationResult:
    """单个模型的验证结果"""
    provider: str
    model_id: str
    passed: bool = False
    status: str = ""  # PASS / NOT_FOUND / UNAUTHORIZED / RATE_LIMITED / SERVER_ERROR / TIMEOUT / PARSE_ERROR / UNKNOWN
    latency_ms: int = 0
    http_status: int = 0
    error: str = ""
    response_preview: str = ""
    failure_code: str = ""  # 对应 FailureTaxonomy 的 code
    verified_at: str = ""
    evidence: Dict = field(default_factory=dict)


@dataclass
class VerificationReport:
    """验证报告"""
    timestamp: str = ""
    total_models: int = 0
    passed: int = 0
    failed: int = 0
    not_found_404: List[str] = field(default_factory=list)  # 404 模型（直接告警）
    unauthorized: List[str] = field(default_factory=list)   # 401 模型
    results: List[ModelVerificationResult] = field(default_factory=list)
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "total_models": self.total_models,
            "passed": self.passed,
            "failed": self.failed,
            "not_found_404": self.not_found_404,
            "unauthorized": self.unauthorized,
            "results": [
                {
                    "provider": r.provider,
                    "model_id": r.model_id,
                    "passed": r.passed,
                    "status": r.status,
                    "latency_ms": r.latency_ms,
                    "http_status": r.http_status,
                    "error": r.error[:200] if r.error else "",
                    "failure_code": r.failure_code,
                    "verified_at": r.verified_at,
                }
                for r in self.results
            ],
            "details": self.details,
        }


class ModelVerifier:
    """
    模型验证器

    自动遍历所有模型，验证其可用性。
    404 模型直接告警。
    """

    def __init__(self, ace_runtime_dir: str):
        self.ace_runtime_dir = Path(ace_runtime_dir)
        self.data_dir = self.ace_runtime_dir / "08_GOVERNANCE"
        self.verification_dir = self.data_dir / "model_verification"
        self.verification_dir.mkdir(parents=True, exist_ok=True)
        self.history_file = self.verification_dir / "verification_history.jsonl"

        self.registry = ProviderRegistry(str(self.data_dir))
        self.failure_memory = FailureMemory(str(self.data_dir))

    def _get_api_key(self, provider: str) -> str:
        """获取 Provider 的 API Key"""
        try:
            import sys
            sys.path.insert(0, str(self.ace_runtime_dir))
            from core.survival_loop.engine import SurvivalLoopEngine

            engine = SurvivalLoopEngine()
            if provider in engine._providers:
                return engine._providers[provider].get("api_key", "")
        except Exception as e:
            logger.warning(f"获取 {provider} API Key 失败: {e}")
        return ""

    def verify_model(self, provider: str, model_id: str,
                     api_key: str = "", base_url: str = "",
                     timeout: int = 15) -> ModelVerificationResult:
        """
        验证单个模型

        Args:
            provider: Provider 名称
            model_id: 模型 ID
            api_key: API Key
            base_url: Base URL
            timeout: 超时时间

        Returns:
            ModelVerificationResult
        """
        result = ModelVerificationResult(
            provider=provider,
            model_id=model_id,
            verified_at=datetime.now().isoformat(),
        )

        if not api_key:
            api_key = self._get_api_key(provider)

        if not base_url:
            p = self.registry.get_provider(provider)
            if p:
                base_url = p.base_url

        if not api_key or not base_url:
            result.status = "CONFIG_ERROR"
            result.error = f"配置不完整: api_key={bool(api_key)}, base_url={bool(base_url)}"
            return result

        chat_url = base_url.rstrip("/") + "/chat/completions"

        payload = {
            "model": model_id,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 5,
            "temperature": 0.1,
        }

        result.evidence = {
            "url": chat_url,
            "request_body": payload,
            "api_key_prefix": api_key[:10] + "..." if api_key else "",
        }

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
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                latency = int((time.time() - start) * 1000)

                result.latency_ms = latency
                result.http_status = resp.status
                result.response_preview = body[:200]

                try:
                    data = json.loads(body)
                    if "choices" in data and len(data["choices"]) > 0:
                        result.passed = True
                        result.status = "PASS"
                    else:
                        result.status = "PARSE_ERROR"
                        result.error = "响应格式异常，无 choices 字段"
                except Exception as e:
                    result.status = "PARSE_ERROR"
                    result.error = f"响应解析失败: {e}"

        except urllib.error.HTTPError as e:
            latency = int((time.time() - start) * 1000)
            result.latency_ms = latency
            result.http_status = e.code

            try:
                err_body = e.read().decode("utf-8", errors="replace")
                result.error = f"HTTP {e.code}: {err_body[:150]}"
                result.response_preview = err_body[:200]
            except Exception:
                result.error = f"HTTP {e.code}"

            # 状态码分类
            if e.code == 404:
                result.status = "NOT_FOUND"
            elif e.code in (401, 403):
                result.status = "UNAUTHORIZED"
            elif e.code == 429:
                result.status = "RATE_LIMITED"
            elif 500 <= e.code < 600:
                result.status = "SERVER_ERROR"
            else:
                result.status = "HTTP_ERROR"

        except urllib.error.URLError as e:
            result.latency_ms = int((time.time() - start) * 1000)
            result.status = "NETWORK_ERROR"
            result.error = f"URL Error: {e.reason}"

        except TimeoutError:
            result.latency_ms = int((time.time() - start) * 1000)
            result.status = "TIMEOUT"
            result.error = f"请求超时（>{timeout}s）"

        except Exception as e:
            result.latency_ms = int((time.time() - start) * 1000)
            result.status = "UNKNOWN"
            result.error = f"{type(e).__name__}: {str(e)[:100]}"

        # 故障分类
        classification = FailureTaxonomy.classify(
            result.error, result.http_status, result.status
        )
        result.failure_code = classification.code

        # 写入 Failure Memory
        if not result.passed:
            self.failure_memory.record_failure(
                classification=classification,
                provider=provider,
                model=model_id,
                evidence=result.evidence,
            )

        # 更新 Registry 中的验证状态
        self.registry.update_model_verification(
            provider=provider,
            model_id=model_id,
            passed=result.passed,
            result=result.status,
        )

        return result

    def verify_all(self, timeout_per_model: int = 20) -> VerificationReport:
        """
        验证所有模型

        Args:
            timeout_per_model: 每个模型的超时时间

        Returns:
            VerificationReport
        """
        report = VerificationReport(
            timestamp=datetime.now().isoformat(),
        )

        all_models = self.registry.list_models(status=None)
        report.total_models = len(all_models)

        logger.info(f"开始模型验证，共 {len(all_models)} 个模型")

        for model in all_models:
            logger.info(f"  验证 {model.provider}:{model.model_id}...")

            result = self.verify_model(
                provider=model.provider,
                model_id=model.model_id,
                timeout=timeout_per_model,
            )
            report.results.append(result)

            if result.passed:
                report.passed += 1
            else:
                report.failed += 1
                if result.status == "NOT_FOUND":
                    report.not_found_404.append(f"{model.provider}:{model.model_id}")
                elif result.status == "UNAUTHORIZED":
                    report.unauthorized.append(f"{model.provider}:{model.model_id}")

            icon = "✅" if result.passed else "❌"
            logger.info(f"    {icon} {result.status} ({result.latency_ms}ms)")

        # 保存历史
        self._save_history(report)

        logger.info(
            f"模型验证完成: {report.passed}/{report.total_models} 通过, "
            f"404: {len(report.not_found_404)}, "
            f"401: {len(report.unauthorized)}"
        )

        if report.not_found_404:
            logger.warning(
                f"⚠️  发现 {len(report.not_found_404)} 个 404 模型: {', '.join(report.not_found_404)}"
            )

        return report

    def _save_history(self, report: VerificationReport):
        """保存历史记录"""
        try:
            with open(self.history_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(report.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存验证历史失败: {e}")

    def generate_markdown_report(self, report: VerificationReport) -> str:
        """生成 Markdown 格式的验证报告"""
        lines = []

        lines.append("# Model Verification Report")
        lines.append("")
        lines.append(f"**时间**: {report.timestamp}")
        lines.append("")

        # 404 告警
        if report.not_found_404:
            lines.append("## ⚠️  404 模型告警")
            lines.append("")
            lines.append("以下模型不存在（404），请立即处理：")
            lines.append("")
            for m in report.not_found_404:
                lines.append(f"- ❌ `{m}`")
            lines.append("")
            lines.append("> **这些模型已被标记为 deprecated，请从任务配置中移除。**")
            lines.append("")

        # 401 告警
        if report.unauthorized:
            lines.append("## ⚠️  认证失败模型")
            lines.append("")
            for m in report.unauthorized:
                lines.append(f"- 🔒 `{m}`")
            lines.append("")

        # 总体统计
        lines.append("## 总体统计")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 模型总数 | {report.total_models} |")
        lines.append(f"| 通过 | {report.passed} |")
        lines.append(f"| 失败 | {report.failed} |")
        lines.append(f"| 404 不存在 | {len(report.not_found_404)} |")
        lines.append(f"| 401 无权限 | {len(report.unauthorized)} |")
        lines.append("")

        # 详细结果
        lines.append("## 详细结果")
        lines.append("")
        lines.append("| Provider | Model | 状态 | 延迟 | HTTP | Failure Code |")
        lines.append("|----------|-------|------|------|------|--------------|")

        for r in report.results:
            status_icon = "✅ PASS" if r.passed else f"❌ {r.status}"
            model_short = r.model_id.split("/")[-1] if "/" in r.model_id else r.model_id
            lines.append(
                f"| {r.provider} | `{model_short}` | {status_icon} | "
                f"{r.latency_ms}ms | {r.http_status or '-'} | {r.failure_code} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("> **任何 404 模型都必须立即处理。模型不存在是配置错误，不是网络问题。**")

        return "\n".join(lines)
