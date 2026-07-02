"""
Failure Taxonomy（故障分类体系）

核心职责：
    对 Provider 故障进行结构化分类。
    不再只有 "fail"，而是精确到：
        - 401 AUTH_INVALID
        - 404 MODEL_NOT_FOUND
        - 429 RATE_LIMITED
        - 500 SERVER_ERROR
        - TIMEOUT
        - NETWORK_DNS
        - NETWORK_SSL
        - NETWORK_CONNECTION_REFUSED
        - RESPONSE_PARSE_ERROR
        - CONFIG_INCOMPLETE
        - MODEL_DEPRECATED (410)

    每种故障都有：
        - category: 大类（auth / model / network / server / config / parse）
        - severity: 严重程度（critical / warning / info）
        - actionable: 是否可行动（true/false）
        - recommended_fix: 建议修复方向
        - known_pattern: 是否已知故障模式

    目的：
        让 Runtime 长记性，
        遇到同样的错误，
        直接从 Failure Memory 取答案，
        而不是每次重新调查。
"""

import re
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class FailureClassification:
    """故障分类结果"""
    code: str                    # 故障代码，如 AUTH_INVALID, MODEL_NOT_FOUND
    category: str                # 大类: auth / model / network / server / config / parse / unknown
    severity: str                # critical / warning / info
    actionable: bool             # 是否可主动修复
    recommended_fix: str         # 建议修复方向
    description: str             # 人类可读描述
    http_status: int = 0         # HTTP 状态码（如果有）
    raw_error: str = ""          # 原始错误信息
    is_known: bool = False       # 是否为已知故障模式


class FailureTaxonomy:
    """
    故障分类器

    将原始错误信息映射到结构化的故障分类。
    """

    # 已知故障模式定义
    PATTERNS = [
        # === 认证类 ===
        (r"(invalid.*api.?key|api.?key.*invalid|unauthorized|bad credentials|user not found|authentication failed)",
         "AUTH_INVALID", "auth", "critical", True,
         "检查 API Key 是否有效，可能过期或被吊销"),

        (r"(insufficient.*quota|quota.*exceeded|out of quota|rate.*limit.*exceeded|429)",
         "RATE_LIMITED", "auth", "warning", True,
         "触发速率限制或额度用尽，等待或切换 Key"),

        # === 模型类 ===
        (r"(model.*not.*found|not.*found.*model|invalid model|model.*invalid|does not exist|no such model)",
         "MODEL_NOT_FOUND", "model", "critical", True,
         "模型名称错误或已下线，检查模型 ID"),

        (r"(model.*deprecated|deprecated.*model|no longer available|not available on)",
         "MODEL_DEPRECATED", "model", "critical", True,
         "模型已下线，需要替换为新模型"),

        (r"(model.*max.*length|context.*length.*exceeded|maximum context length)",
         "MODEL_CONTEXT_EXCEEDED", "model", "warning", True,
         "上下文长度超限，减少输入 token 数"),

        # === 网络类 ===
        (r"(getaddrinfo failed|name or service not known|dns.*resolv|nodename nor servname)",
         "NETWORK_DNS", "network", "critical", False,
         "DNS 解析失败，检查网络连接或域名"),

        (r"(connection refused|connection reset|connection.*timed.*out|connect.*timeout)",
         "NETWORK_CONNECTION", "network", "warning", False,
         "连接失败，服务可能宕机或网络不通"),

        (r"(ssl.*error|certificate.*verify|tls.*handshake)",
         "NETWORK_SSL", "network", "warning", False,
         "SSL/TLS 证书问题，检查系统时间和证书链"),

        (r"(timeout|timed out)",
         "TIMEOUT", "network", "warning", False,
         "请求超时，可能是网络慢或服务响应慢"),

        # === 服务端 ===
        (r"(5\d{2}|internal server error|server error|service.*unavailable|bad gateway)",
         "SERVER_ERROR", "server", "warning", False,
         "服务端错误，稍后重试"),

        # === 配置类 ===
        (r"(config.*incomplete|invalid.*config|configuration.*error)",
         "CONFIG_ERROR", "config", "critical", True,
         "配置错误，检查配置文件"),

        # === 解析类 ===
        (r"(json.*decode|expecting value|response.*parse|parse.*error)",
         "RESPONSE_PARSE_ERROR", "parse", "warning", True,
         "响应解析失败，可能返回非 JSON 或 HTML 错误页"),
    ]

    @classmethod
    def classify(cls, error_msg: str, http_status: int = 0,
                 status: str = "") -> FailureClassification:
        """
        对错误进行分类

        Args:
            error_msg: 原始错误信息
            http_status: HTTP 状态码
            status: 状态码（PASS/FAIL/TIMEOUT/ERROR）

        Returns:
            FailureClassification
        """
        error_lower = error_msg.lower() if error_msg else ""

        # 特殊处理：TIMEOUT 状态
        if status == "TIMEOUT":
            return FailureClassification(
                code="TIMEOUT",
                category="network",
                severity="warning",
                actionable=False,
                recommended_fix="请求超时，可能是网络慢或服务响应慢，可重试",
                description="请求超时",
                http_status=http_status,
                raw_error=error_msg,
                is_known=True,
            )

        # 先按 HTTP 状态码快速分类
        if http_status == 401 or http_status == 403:
            if "quota" in error_lower or "rate" in error_lower:
                code = "RATE_LIMITED"
                fix = "触发速率限制或额度用尽"
            else:
                code = "AUTH_INVALID"
                fix = "认证失败，检查 API Key"
            return FailureClassification(
                code=code,
                category="auth",
                severity="critical",
                actionable=True,
                recommended_fix=fix,
                description=f"HTTP {http_status} 认证错误",
                http_status=http_status,
                raw_error=error_msg,
                is_known=True,
            )

        if http_status == 404:
            return FailureClassification(
                code="MODEL_NOT_FOUND",
                category="model",
                severity="critical",
                actionable=True,
                recommended_fix="模型不存在，检查模型 ID 是否正确",
                description="模型未找到 (HTTP 404)",
                http_status=http_status,
                raw_error=error_msg,
                is_known=True,
            )

        if http_status == 410:
            return FailureClassification(
                code="MODEL_DEPRECATED",
                category="model",
                severity="critical",
                actionable=True,
                recommended_fix="模型已下线，需要替换为新模型",
                description="模型已弃用 (HTTP 410)",
                http_status=http_status,
                raw_error=error_msg,
                is_known=True,
            )

        if http_status == 429:
            return FailureClassification(
                code="RATE_LIMITED",
                category="auth",
                severity="warning",
                actionable=True,
                recommended_fix="触发速率限制，等待后重试或切换 Key",
                description="速率限制 (HTTP 429)",
                http_status=http_status,
                raw_error=error_msg,
                is_known=True,
            )

        if 500 <= http_status < 600:
            return FailureClassification(
                code="SERVER_ERROR",
                category="server",
                severity="warning",
                actionable=False,
                recommended_fix="服务端错误，稍后重试",
                description=f"服务端错误 (HTTP {http_status})",
                http_status=http_status,
                raw_error=error_msg,
                is_known=True,
            )

        # 正则匹配
        for pattern, code, category, severity, actionable, fix in cls.PATTERNS:
            if re.search(pattern, error_lower):
                return FailureClassification(
                    code=code,
                    category=category,
                    severity=severity,
                    actionable=actionable,
                    recommended_fix=fix,
                    description=f"匹配模式: {code}",
                    http_status=http_status,
                    raw_error=error_msg,
                    is_known=True,
                )

        # 未匹配到已知模式
        return FailureClassification(
            code="UNKNOWN_ERROR",
            category="unknown",
            severity="warning",
            actionable=False,
            recommended_fix="未知错误，需要进一步调查",
            description="未分类的错误",
            http_status=http_status,
            raw_error=error_msg,
            is_known=False,
        )

    @classmethod
    def get_all_categories(cls) -> Dict[str, str]:
        """获取所有故障大类"""
        return {
            "auth": "认证/权限",
            "model": "模型相关",
            "network": "网络问题",
            "server": "服务端错误",
            "config": "配置错误",
            "parse": "响应解析",
            "unknown": "未知错误",
        }
