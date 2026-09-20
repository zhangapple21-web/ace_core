"""受治理的外部矿工入口。

这不是旧版 WebScout 的旁路。它只做四件可审计的事：

1. 从官方 GitHub API/raw 页面只读抓取仓库元数据、README、许可证；
2. 把带哈希的证据交给 ACE MinerPool 做结构化提炼；
3. 以 learning admission 创建一个普通 TaskPool 任务；
4. 写入可复盘收据，随后由既有 Researcher → Validator → Guardian 继续处理。

它不 clone、不执行外部代码、不安装依赖、不切换生产模型或视频入口。
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


class GovernedExternalMiner:
    """把外部仓库矿源接入唯一 TaskPool 生命周期。"""

    def __init__(
        self,
        *,
        base_dir: Path,
        task_pool: Any,
        miner_pool: Any,
        targets: Iterable[Dict[str, Any]],
        enabled: bool = True,
        max_readme_chars: int = 12000,
        timeout: int = 20,
        fetcher: Optional[Callable[[str], Tuple[bytes, str, Dict[str, str]]]] = None,
    ):
        self.base_dir = Path(base_dir)
        self.task_pool = task_pool
        self.miner_pool = miner_pool
        self.targets = [dict(item) for item in targets if isinstance(item, dict)]
        self.enabled = bool(enabled)
        self.max_readme_chars = int(max_readme_chars)
        self.timeout = int(timeout)
        self.fetcher = fetcher or self._http_get
        self.data_dir = self.base_dir / "06_RUNTIME" / "ace" / "data" / "governed_external_miner"
        self.report_dir = self.base_dir / "07_SANDBOX" / "free_research" / "reports"
        self.state_path = self.data_dir / "state.json"
        self.report_path = self.report_dir / "governed_external_mining_latest.json"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _repo_parts(repository: str) -> Tuple[str, str]:
        match = re.match(r"https?://github\.com/([^/]+)/([^/#]+)", repository.rstrip("/"))
        if not match:
            raise ValueError("unsupported_repository")
        return match.group(1), match.group(2).removesuffix(".git")

    def _http_get(self, url: str) -> Tuple[bytes, str, Dict[str, str]]:
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "ACE-governed-external-miner/1.0",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read(), response.headers.get("Content-Type", ""), dict(response.headers.items())

    def _fetch(self, url: str) -> Tuple[Any, str]:
        raw, content_type, _headers = self.fetcher(url)
        if len(raw) > 2_000_000:
            raise ValueError("external_payload_too_large")
        text = raw.decode("utf-8", errors="replace")
        if "json" in content_type.lower() or url.endswith("/license") or "/repos/" in url and url.count("/") >= 5:
            try:
                return json.loads(text), content_type
            except json.JSONDecodeError:
                pass
        return text, content_type

    def _fetch_repo(self, target: Dict[str, Any]) -> Dict[str, Any]:
        repository = str(target.get("repository", "")).strip()
        owner, name = self._repo_parts(repository)
        api_root = f"https://api.github.com/repos/{owner}/{name}"
        metadata, _ = self._fetch(api_root)
        if not isinstance(metadata, dict):
            raise ValueError("github_metadata_not_json")

        readme = None
        readme_url = ""
        readme_errors: List[str] = []
        for branch in ("main", "master"):
            candidate = f"https://raw.githubusercontent.com/{owner}/{name}/{branch}/README.md"
            try:
                readme, _ = self._fetch(candidate)
                readme_url = candidate
                break
            except Exception as error:
                readme_errors.append(f"{branch}:{type(error).__name__}")
        if not isinstance(readme, str) or not readme.strip():
            readme = ""

        license_payload: Any = {}
        license_url = f"{api_root}/license"
        try:
            license_payload, _ = self._fetch(license_url)
        except Exception as error:
            license_payload = {"fetch_error": type(error).__name__}

        license_text = ""
        if isinstance(license_payload, dict):
            encoded = license_payload.get("content")
            if isinstance(encoded, str):
                try:
                    license_text = base64.b64decode(encoded).decode("utf-8", errors="replace")
                except Exception:
                    license_text = ""

        metadata_view = {
            "full_name": metadata.get("full_name"),
            "html_url": metadata.get("html_url") or repository,
            "default_branch": metadata.get("default_branch"),
            "description": metadata.get("description"),
            "stargazers_count": metadata.get("stargazers_count"),
            "updated_at": metadata.get("updated_at"),
            "license": (metadata.get("license") or {}).get("spdx_id") if isinstance(metadata.get("license"), dict) else None,
            "archived": metadata.get("archived"),
        }
        evidence = [
            {
                "source": "github_api_metadata",
                "source_ref": api_root,
                "content": json.dumps(metadata_view, ensure_ascii=False, sort_keys=True),
                "metadata": {"independence_group": "github_api_metadata", "source_tier": "primary"},
            },
            {
                "source": "github_raw_readme",
                "source_ref": readme_url or f"{repository}/README.md",
                "content": readme[: self.max_readme_chars],
                "metadata": {"independence_group": "github_raw_readme", "source_tier": "primary", "fetch_warnings": readme_errors},
            },
            {
                "source": "github_license_api",
                "source_ref": license_url,
                "content": json.dumps(
                    {
                        "spdx_id": (metadata.get("license") or {}).get("spdx_id") if isinstance(metadata.get("license"), dict) else None,
                        "name": (metadata.get("license") or {}).get("name") if isinstance(metadata.get("license"), dict) else None,
                        "license_text_excerpt": license_text[:4000],
                        "fetch_status": "fetched" if license_text else "metadata_only",
                    }, ensure_ascii=False, sort_keys=True,
                ),
                "metadata": {"independence_group": "github_license_api", "source_tier": "primary"},
            },
        ]
        fetched = {
            "repository": repository,
            "retrieved_at": _now(),
            "metadata": metadata_view,
            "readme_url": readme_url,
            "license_url": license_url,
            "evidence": evidence,
        }
        fetched["fingerprint"] = _sha(fetched)
        return fetched

    @staticmethod
    def _parse_model_result(response: Any) -> Dict[str, Any]:
        if not isinstance(response, dict):
            return {"status": "UNAVAILABLE", "raw": ""}
        content = response.get("content", "")
        result: Dict[str, Any] = {
            "status": "COMPLETED" if response.get("success") else "UNAVAILABLE",
            "provider": response.get("provider", ""),
            "model": response.get("model", ""),
            "tried_models": response.get("tried_models", []),
            "raw_sha256": _sha(content),
        }
        if isinstance(content, str) and content.strip():
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    result["analysis"] = parsed
                else:
                    result["analysis"] = {"raw_text": content[:4000]}
            except json.JSONDecodeError:
                result["analysis"] = {"raw_text": content[:4000]}
        else:
            result["analysis"] = {"unknowns": [response.get("error", "miner_pool_no_result")]}
        return result
    def _write_report(self, report: Dict[str, Any]) -> None:
        self.report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def _read_state(self) -> Dict[str, Any]:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"cursor": 0, "processed": {}}

    def _write_state(self, state: Dict[str, Any]) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)

    def run_once(self, max_tasks: int = 1) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": "DISABLED" if not self.enabled else "NO_TARGET",
            "chain": {"web_scout": "NOT_RUN", "miner_pool": "NOT_RUN", "task_pool": "NOT_RUN", "researcher": "PENDING", "validator": "PENDING", "guardian": "PENDING"},
            "tasks_created": 0,
            "reports": [],
        }
        if not self.enabled or not self.targets:
            self._write_report({"at": _now(), **result})
            return result
        state = self._read_state()
        processed = state.setdefault("processed", {})
        cursor = int(state.get("cursor", 0)) % len(self.targets)
        attempts = 0
        while attempts < len(self.targets):
            target = self.targets[(cursor + attempts) % len(self.targets)]
            repo = str(target.get("repository", "")).strip()
            if repo and repo not in processed:
                break
            attempts += 1
        if attempts >= len(self.targets):
            result["status"] = "IDEMPOTENT_NO_NEW_TARGET"
            result["chain"]["web_scout"] = "NO_NEW_TARGET"
            self._write_report({"at": _now(), **result})
            return result

        target = self.targets[(cursor + attempts) % len(self.targets)]
        result["target"] = {k: target.get(k) for k in ("id", "title", "repository", "disposition")}
        try:
            fetched = self._fetch_repo(target)
            result["chain"]["web_scout"] = "FETCHED"
            result["fetch"] = {"repository": fetched["repository"], "fingerprint": fetched["fingerprint"], "evidence_count": len(fetched["evidence"]), "readme_url": fetched["readme_url"], "license_url": fetched["license_url"]}
        except Exception as error:
            result.update({"status": "FETCH_FAILED", "error": f"{type(error).__name__}: {error}"})
            result["chain"]["web_scout"] = "FAILED"
            self._write_report({"at": _now(), **result})
            return result

        evidence = fetched["evidence"]
        evidence_text = "\n\n".join(f"[{item['source']}] {item['content'][:6000]}" for item in evidence)
        prompt = (
            "你是 ACE 外部矿源研究员。只根据给定的官方抓取证据输出 JSON，不得把推测写成事实。"
            "判断可吸收能力、许可证/运行风险、与 ACE 视频王国的兼容性、反例、未知项和下一步验证。"
            "字段必须包含 facts, compatibility, risks, objections, unknowns, next_verification, disposition。"
        )
        model_response = self.miner_pool.chat(
            task_type="reasoning",
            system_prompt=prompt,
            messages=[{"role": "user", "content": f"仓库：{fetched['repository']}\n证据：\n{evidence_text}"}],
            max_retries=2,
            task_context={"source": "governed_external_miner", "repository": fetched["repository"]},
        )
        model_result = self._parse_model_result(model_response)
        result["chain"]["miner_pool"] = "COMPLETED" if model_result["status"] == "COMPLETED" else "UNAVAILABLE"

        admission_evidence = [
            {
                "source": item["source"],
                "source_ref": item["source_ref"],
                "content": item["content"][:10000],
                "confidence": 0.9,
                "author": "ACE governed WebScout",
                "source_location": item["source_ref"],
                "metadata": {**item.get("metadata", {}), "upstream_identity": fetched["repository"], "lineage_observable": True, "directness": "primary", "cross_validation_source": "external"},
            }
            for item in evidence
        ]
        source_ref = f"{fetched['repository']}@{fetched['fingerprint'][:16]}"
        learning_contract = {
            "why_learn": f"官方抓取证据已到达，需独立核验 {fetched['repository']} 的可复用边界。",
            "learning_objective": str(target.get("objective") or target.get("title") or "核验外部视频能力"),
            "required_evidence": ["GitHub API 元数据", "官方 README 原文", "许可证 API 内容"],
            "mastery_criteria": ["记录事实、未知、反例和下一步验证，并明确 ABSORB/ADAPT/CONFLICT/REJECT 边界。"],
            "requires_miner": True,
        }
        admission = {
            "source_type": "learning",
            "source_ref": source_ref,
            "why_now": "外部矿源已在官方入口完成一次只读抓取，进入受治理研究队列。",
            "evidence": admission_evidence,
            "expected_result": "得到可复核的能力、许可证、运行条件和 ACE 兼容性结论。",
            "verification_method": "Researcher 重读抓取证据；Validator 找反例；Guardian 决定是否只沉积为经验。",
            "risk": "外部内容不可信；禁止安装、执行、上传素材或修改生产路由。",
            "estimated_scope": "bounded_read_only_repo_review",
            "learning_contract": learning_contract,
        }
        outputs = {
            "external_mining": {
                "schema_version": "ace.governed-external-mining.v1",
                "chain": ["WebScout", "MinerPool", "TaskPool", "Researcher", "Validator", "Guardian"],
                "fetched": fetched,
                "miner_result": model_result,
                "production_integration": False,
            },
            "discovery": {"fingerprint": f"governed_external_miner:{source_ref}", "candidate_source": "governed_web_scout"},
        }
        task = self.task_pool.create_task(
            title=f"外部矿工：{target.get('title') or fetched['repository']}",
            hypothesis=learning_contract["learning_objective"],
            creator="governed_web_scout",
            priority="medium",
            tags=["external", "requires_miner", "governed_web_scout", "video_kingdom"],
            admission=admission,
            outputs=outputs,
            complexity="standard",
        )
        result["chain"]["task_pool"] = "CREATED"
        result["status"] = "QUEUED"
        result["task_id"] = task.task_id
        result["tasks_created"] = 1
        processed[repo] = {"fingerprint": fetched["fingerprint"], "task_id": task.task_id, "at": _now()}
        state["cursor"] = (cursor + attempts + 1) % len(self.targets)
        state["last_task_id"] = task.task_id
        state["last_fingerprint"] = fetched["fingerprint"]
        self._write_state(state)
        self._write_report({"at": _now(), **result, "task": {"task_id": task.task_id, "source_ref": source_ref}, "miner_result": model_result})
        return result
