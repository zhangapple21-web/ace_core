"""
分诊工作者（Triage Worker）— 从 android-reverse-engineering-skill 考古提取

对应 Phase 0: Fingerprint（快速指纹识别）

核心设计：
- 在深入分析之前，先做快速分类
- 判断文件类型、框架、混淆级别、可能的分析策略
- 避免在错误的方向上浪费时间

来源：
- android-reverse-engineering-skill 的 fingerprint.sh 设计
- ReVa 的 binary-triage skill
"""

from typing import Any, Dict, List, Optional
import hashlib
import os
from pathlib import Path

from .analysis_worker import AnalysisWorker


# 已知的文件签名（magic bytes）
FILE_SIGNATURES = {
    "ELF": [b"\x7fELF"],
    "PE": [b"MZ"],
    "MACH-O": [b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"],
    "DEX": [b"dex\n035", b"dex\n037", b"dex\n038", b"dex\n039"],
    "ZIP": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
    "ELF-ARM": [b"\x7fELF\x01\x01\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\x02\x00\x28\x00"],
}

# 框架特征（基于字符串特征）
FRAMEWORK_SIGNATURES = {
    "Flutter": ["libflutter.so", "FlutterView", "dart:io"],
    "ReactNative": ["libreactnativejni.so", "ReactNative", "facebook.react"],
    "Cordova": ["cordova.js", "org.apache.cordova"],
    "Xamarin": ["libmonodroid.so", "Xamarin", "Mono"],
    "Native-Kotlin": ["kotlin", "Kotlin"],
    "Native-Java": ["java.", "javax.", "android."],
}


class TriageWorker(AnalysisWorker):
    """
    分诊工作者 — 快速指纹识别

    工作流（从 android-reverse-engineering-skill 考古提取）：
    1. 读取文件头 → 判断文件类型
    2. 扫描关键字符串 → 判断框架和技术栈
    3. 估算混淆级别 → 预期分析难度
    4. 推荐分析策略 → 选择合适的工具链
    5. 输出分诊报告 → 决定是否进入下一阶段

    为什么这一步很重要？
    - 避免用错工具（比如用 jadx 分析 Flutter app，得到的几乎都是垃圾）
    - 节省时间（不同框架有不同的最佳分析路径）
    - 管理预期（混淆级别决定了分析深度和时间成本）
    """

    @property
    def worker_type(self) -> str:
        return "binary_triage"

    @property
    def phase_number(self) -> int:
        return 0

    def _run_analysis(
        self, session_id: str, task: Dict[str, Any]
    ) -> Dict[str, Any]:
        target = task.get("target_path", "")
        target_path = Path(target)

        if not target_path.exists():
            return {"error": f"File not found: {target}"}

        findings = []

        file_type = self._detect_file_type(target_path)
        findings.append({
            "type": "file_type",
            "description": f"File type: {file_type}",
            "confidence": 0.9,
        })

        file_size = target_path.stat().st_size
        file_md5 = self._calculate_md5(target_path)
        findings.append({
            "type": "file_metadata",
            "description": f"Size: {file_size} bytes, MD5: {file_md5}",
            "confidence": 1.0,
        })

        framework = self._detect_framework(target_path, file_type)
        if framework:
            findings.append({
                "type": "framework",
                "description": f"Detected framework: {framework}",
                "confidence": 0.7,
            })

        obfuscation_level = self._estimate_obfuscation(target_path, file_type)
        findings.append({
            "type": "obfuscation",
            "description": f"Estimated obfuscation level: {obfuscation_level}",
            "confidence": 0.5,
        })

        strategy = self._recommend_strategy(file_type, framework, obfuscation_level)
        findings.append({
            "type": "recommendation",
            "description": f"Recommended strategy: {strategy}",
            "confidence": 0.6,
        })

        for f in findings:
            self._add_finding(
                session_id,
                f["type"],
                f["description"],
                confidence=f["confidence"],
            )

        return {
            "file_type": file_type,
            "file_size": file_size,
            "file_md5": file_md5,
            "framework": framework or "unknown",
            "obfuscation_level": obfuscation_level,
            "recommended_strategy": strategy,
        }

    def _detect_file_type(self, path: Path) -> str:
        """检测文件类型（基于 magic bytes）"""
        try:
            with open(path, "rb") as f:
                header = f.read(64)

            for ftype, signatures in FILE_SIGNATURES.items():
                for sig in signatures:
                    if header.startswith(sig):
                        return ftype
            return "unknown"
        except Exception:
            return "unreadable"

    def _calculate_md5(self, path: Path) -> str:
        """计算文件 MD5"""
        md5 = hashlib.md5()
        try:
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    md5.update(chunk)
            return md5.hexdigest()
        except Exception:
            return "unknown"

    def _detect_framework(self, path: Path, file_type: str) -> Optional[str]:
        """检测框架类型（基于字符串扫描）"""
        if file_type not in ("ZIP", "APK", "DEX"):
            return None

        try:
            import zipfile
            if zipfile.is_zipfile(path):
                with zipfile.ZipFile(path) as zf:
                    names = zf.namelist()
                    for framework, signatures in FRAMEWORK_SIGNATURES.items():
                        for sig in signatures:
                            if any(sig in name for name in names):
                                return framework
        except Exception:
            pass
        return None

    def _estimate_obfuscation(self, path: Path, file_type: str) -> str:
        """估算混淆级别"""
        if file_type in ("unknown", "unreadable"):
            return "unknown"

        try:
            size = path.stat().st_size
            if size < 10000:
                return "low"
            elif size < 1000000:
                return "medium"
            else:
                return "high"
        except Exception:
            return "unknown"

    def _recommend_strategy(
        self, file_type: str, framework: Optional[str], obfuscation: str
    ) -> str:
        """推荐分析策略"""
        if framework == "Flutter":
            return "flutter_native_analysis"
        elif framework == "ReactNative":
            return "react_native_javascript_analysis"
        elif file_type == "ELF":
            return "ghidra_native_analysis"
        elif file_type == "PE":
            return "ida_pe_analysis"
        elif file_type in ("DEX", "ZIP") and framework in ("Native-Kotlin", "Native-Java", None):
            return "jadx_java_analysis"
        else:
            return "general_static_analysis"
