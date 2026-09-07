#!/usr/bin/env python3
"""
ENV-001: Environment Sensor - 环境传感器
=========================================

RFC: V6_RFC/RFC-ENV-001-Environment-Layer.md

职责：持续感知环境变化，生成 Observation 列表。
不做决策，不做分析——只感知和记录。

传感器列表：
  - local:     git status + 文件修改检测 + 模块健康
  - github:    trending 仓库 + watch list 变更
  - models:    GitHub Models 可用性
  - providers: 数据源健康检测

用法：
  python environment_sensor.py
  python environment_sensor.py --json
  python environment_sensor.py --source local
  python environment_sensor.py --source providers
"""
import os, sys, json, time, argparse, subprocess, urllib.request, urllib.error
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Any, Optional

WORKSPACE = Path(__file__).parent.parent


@dataclass
class Observation:
    """环境观察"""
    source: str          # "local" | "github" | "model" | "provider"
    category: str        # "file_change" | "new_repo" | "provider_down" | ...
    severity: str        # "info" | "warning" | "critical"
    title: str           # 简短描述
    detail: Dict[str, Any] = field(default_factory=dict)
    capability_ref: str = ""  # 关联的 ACE capability
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class EnvironmentSensor:
    """环境传感器"""

    def __init__(self, workspace: Path = None):
        self.workspace = workspace or WORKSPACE

    # ==================== Local Sensor ====================

    def scan_local(self) -> List[Observation]:
        """扫描本地资产变更"""
        observations = []

        # 1. git status
        try:
            r = subprocess.run(
                ["git", "status", "--short"],
                cwd=str(self.workspace),
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0 and r.stdout.strip():
                lines = [l.strip() for l in r.stdout.strip().split("\n") if l.strip()]
                modified = [l for l in lines if l.startswith(" M") or l.startswith("M ")]
                untracked = [l for l in lines if l.startswith("??")]
                deleted = [l for l in lines if l.startswith(" D") or l.startswith("D ")]

                if modified:
                    observations.append(Observation(
                        source="local", category="file_change",
                        severity="info",
                        title=f"{len(modified)} files modified",
                        detail={"files": modified[:10]},
                        capability_ref="workspace"
                    ))
                if untracked:
                    observations.append(Observation(
                        source="local", category="new_files",
                        severity="info",
                        title=f"{len(untracked)} untracked files",
                        detail={"files": untracked[:10]},
                        capability_ref="workspace"
                    ))
                if deleted:
                    observations.append(Observation(
                        source="local", category="file_deleted",
                        severity="warning",
                        title=f"{len(deleted)} files deleted",
                        detail={"files": deleted[:10]},
                        capability_ref="workspace"
                    ))
        except Exception:
            pass

        # 2. 模块健康检查 — 检查关键 .py 文件是否能 import
        critical_modules = [
            "05_TOOLS/advisor/stock_advisor.py",
            "05_TOOLS/advisor/stock_query.py",
            "05_TOOLS/signals/dragon_leader_v2.py",
            "05_TOOLS/miner/task_router_v2.py",
        ]
        for mod_path in critical_modules:
            full = self.workspace / mod_path
            if not full.exists():
                observations.append(Observation(
                    source="local", category="module_missing",
                    severity="critical",
                    title=f"Critical module missing: {mod_path}",
                    detail={"path": mod_path},
                    capability_ref="runtime"
                ))

        # 3. 检查死代码标记
        try:
            r = subprocess.run(
                ["git", "log", "--oneline", "-5", "--format=%h %s %cr"],
                cwd=str(self.workspace),
                capture_output=True, text=True, timeout=10
            )
            if r.returncode == 0:
                observations.append(Observation(
                    source="local", category="git_log",
                    severity="info",
                    title="Recent commits",
                    detail={"commits": r.stdout.strip().split("\n")[:5]},
                    capability_ref="workspace"
                ))
        except Exception:
            pass

        return observations

    # ==================== Provider Sensor ====================

    def scan_providers(self) -> List[Observation]:
        """扫描数据源健康度"""
        observations = []

        # 腾讯行情 API
        try:
            url = "https://qt.gtimg.cn/q=sh000001"
            req = urllib.request.Request(url)
            req.add_header("User-Agent", "Mozilla/5.0")
            resp = urllib.request.urlopen(req, timeout=5)
            data = resp.read().decode("gbk")
            if "=" in data and "~" in data:
                observations.append(Observation(
                    source="provider", category="provider_ok",
                    severity="info",
                    title="Tencent quote API OK",
                    detail={"api": "qt.gtimg.cn", "latency_ms": 0},
                    capability_ref="stock_data"
                ))
            else:
                observations.append(Observation(
                    source="provider", category="provider_anomaly",
                    severity="warning",
                    title="Tencent API returned unexpected format",
                    detail={"response": data[:200]},
                    capability_ref="stock_data"
                ))
        except Exception as e:
            observations.append(Observation(
                source="provider", category="provider_down",
                severity="critical",
                title=f"Tencent quote API down: {type(e).__name__}",
                detail={"error": str(e)[:200]},
                capability_ref="stock_data"
            ))

        # akshare 可用性（快速检测，不实际拉数据）
        try:
            import akshare as ak
            observations.append(Observation(
                source="provider", category="provider_ok",
                severity="info",
                title=f"akshare v{ak.__version__} available",
                detail={"version": ak.__version__},
                capability_ref="stock_data"
            ))
        except ImportError:
            observations.append(Observation(
                source="provider", category="provider_missing",
                severity="critical",
                title="akshare not installed",
                detail={},
                capability_ref="stock_data"
            ))
        except Exception as e:
            observations.append(Observation(
                source="provider", category="provider_error",
                severity="warning",
                title=f"akshare error: {type(e).__name__}",
                detail={"error": str(e)[:200]},
                capability_ref="stock_data"
            ))

        return observations

    # ==================== GitHub Sensor ====================

    def scan_github(self) -> List[Observation]:
        """扫描 GitHub 环境变化"""
        observations = []

        # GitHub Trending (via API)
        try:
            # 使用 GitHub search API 查找最近创建/更新的 Python 量化项目
            since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            url = f"https://api.github.com/search/repositories?q=quantitative+trading+language:python+pushed:>{since}&sort=stars&order=desc&per_page=5"
            req = urllib.request.Request(url)
            req.add_header("Accept", "application/vnd.github.v3+json")
            req.add_header("User-Agent", "ACE-EnvironmentSensor")
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))

            for repo in data.get("items", [])[:5]:
                observations.append(Observation(
                    source="github", category="trending_repo",
                    severity="info",
                    title=f"GitHub: {repo['full_name']} (★{repo['stargazers_count']})",
                    detail={
                        "url": repo["html_url"],
                        "stars": repo["stargazers_count"],
                        "description": repo.get("description", "")[:200],
                        "updated": repo.get("updated_at", ""),
                    },
                    capability_ref="external_asset"
                ))
        except urllib.error.HTTPError as e:
            observations.append(Observation(
                source="github", category="api_error",
                severity="warning",
                title=f"GitHub API rate limited ({e.code})",
                detail={"error": str(e)},
                capability_ref="external_asset"
            ))
        except Exception as e:
            observations.append(Observation(
                source="github", category="api_error",
                severity="warning",
                title=f"GitHub scan failed: {type(e).__name__}",
                detail={"error": str(e)[:200]},
                capability_ref="external_asset"
            ))

        return observations

    # ==================== Model Sensor ====================

    def scan_models(self) -> List[Observation]:
        """扫描模型可用性"""
        observations = []

        # GitHub Models 可用性检测
        try:
            token = os.environ.get("GITHUB_TOKEN", "")
            url = "https://models.inference.ai.azure.com/models"
            req = urllib.request.Request(url)
            if token:
                req.add_header("Authorization", f"Bearer {token}")
            req.add_header("User-Agent", "ACE-EnvironmentSensor")
            resp = urllib.request.urlopen(req, timeout=10)
            data = json.loads(resp.read().decode("utf-8"))

            model_count = len(data) if isinstance(data, list) else 0
            observations.append(Observation(
                source="model", category="models_available",
                severity="info",
                title=f"GitHub Models: {model_count} models available",
                detail={"count": model_count},
                capability_ref="llm_inference"
            ))
        except Exception as e:
            # 不报 critical，因为模型 API 可能需要 token
            observations.append(Observation(
                source="model", category="api_error",
                severity="info",
                title=f"GitHub Models API: {type(e).__name__}",
                detail={"error": str(e)[:200]},
                capability_ref="llm_inference"
            ))

        return observations

    # ==================== All-in-one ====================

    def scan_all(self, sources: list = None) -> List[Observation]:
        """全量扫描"""
        sources = sources or ["local", "providers", "github", "models"]
        results = []
        for src in sources:
            try:
                if src == "local":
                    results.extend(self.scan_local())
                elif src == "providers":
                    results.extend(self.scan_providers())
                elif src == "github":
                    results.extend(self.scan_github())
                elif src == "models":
                    results.extend(self.scan_models())
            except Exception as e:
                results.append(Observation(
                    source=src, category="sensor_error",
                    severity="warning",
                    title=f"Sensor '{src}' failed: {type(e).__name__}",
                    detail={"error": str(e)[:200]},
                    capability_ref="environment"
                ))
        return results


class SituationBuilder:
    """态势构建器 — 将原始观察聚合成态势报告"""

    # 能力图谱 — 关键词到 capability 的映射
    CAPABILITY_KEYWORDS = {
        "stock_data": ["stock", "quant", "trading", "akshare", "tushare", "kline", "quote"],
        "llm_inference": ["model", "gpt", "llm", "inference", "openrouter"],
        "environment": ["sensor", "scan", "environment", "heartbeat"],
        "runtime": ["runtime", "scheduler", "router", "worker"],
        "external_asset": ["github", "repo", "trending"],
    }

    def __init__(self, workspace: Path = None):
        self.workspace = workspace or WORKSPACE
        self.history_dir = self.workspace / "02_MEMORY" / "environment"

    def _score_relevance(self, obs: Observation) -> int:
        """根据关键词匹配度评分"""
        text = (obs.title + " " + " ".join(str(v) for v in obs.detail.values())).lower()
        score = 0
        for cap, keywords in self.CAPABILITY_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    score += 1
        return score

    def _deduplicate(self, observations: List[Observation]) -> List[Observation]:
        """与上次扫描对比，去除重复"""
        last_file = self.history_dir / "latest_observations.json"
        if not last_file.exists():
            return observations

        try:
            with open(last_file, encoding="utf-8") as f:
                last_obs = json.load(f)
            seen = set()
            for o in last_obs:
                seen.add(f"{o['source']}:{o['category']}:{o['title']}")
            return [o for o in observations if f"{o.source}:{o.category}:{o.title}" not in seen]
        except Exception:
            return observations

    def build(self, observations: List[Observation]) -> dict:
        """生成态势报告"""
        # 去重
        new_obs = self._deduplicate(observations)

        # 分类
        by_source = {}
        for o in new_obs:
            by_source.setdefault(o.source, []).append(asdict(o))

        # 评分并排序
        scored = [(o, self._score_relevance(o)) for o in new_obs]
        scored.sort(key=lambda x: x[1], reverse=True)

        # 高优先级（critical 或 相关度>=3）
        high_priority = [
            asdict(o) for o, s in scored
            if o.severity == "critical" or s >= 3
        ]

        situation = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "timestamp": datetime.now().isoformat(),
            "summary": f"扫描到 {len(observations)} 个观察，其中 {len(new_obs)} 个新变化，{len(high_priority)} 个高优先级",
            "total_observations": len(observations),
            "new_observations": len(new_obs),
            "by_source": {k: len(v) for k, v in by_source.items()},
            "high_priority": high_priority,
            "all_observations": [asdict(o) for o in new_obs],
        }

        # 保存
        self.history_dir.mkdir(parents=True, exist_ok=True)
        out_file = self.history_dir / f"situation_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(situation, f, ensure_ascii=False, indent=2, default=str)

        # 更新 latest
        with open(self.history_dir / "latest_observations.json", "w", encoding="utf-8") as f:
            json.dump([asdict(o) for o in observations], f, ensure_ascii=False, indent=2, default=str)

        with open(self.history_dir / "latest_situation.json", "w", encoding="utf-8") as f:
            json.dump(situation, f, ensure_ascii=False, indent=2, default=str)

        return situation


def main():
    parser = argparse.ArgumentParser(description="ENV-001 Environment Sensor")
    parser.add_argument("--source", choices=["local", "providers", "github", "models", "all"],
                       default="all", help="Sensor source to scan")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--no-situation", action="store_true", help="Skip situation building")
    args = parser.parse_args()

    sensor = EnvironmentSensor()

    if args.source == "all":
        observations = sensor.scan_all()
    else:
        observations = sensor.scan_all(sources=[args.source])

    if args.no_situation:
        result = {"observations": [asdict(o) for o in observations]}
    else:
        builder = SituationBuilder()
        result = builder.build(observations)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        print(f"  Environment Scan — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print(f"{'='*60}\n")

        if "summary" in result:
            print(f"  Summary: {result['summary']}\n")

        for obs in result.get("all_observations", result.get("observations", [])):
            icon = {"critical": "[!]", "warning": "[~]", "info": "[+]"}.get(obs.get("severity", "info"), "[+]")
            print(f"  {icon} [{obs.get('source','?'):8s}] {obs.get('title','')}")

        if result.get("high_priority"):
            print(f"\n  High Priority ({len(result['high_priority'])}):")
            for hp in result["high_priority"]:
                print(f"    [!] {hp.get('source','?'):8s} {hp.get('title','')}")

        print()


if __name__ == "__main__":
    main()
