"""Read-only R1/R2 archaeology inventory for the free-research sandbox.

This module does *not* revive an earlier runtime.  It inspects a small,
allow-listed set of historical artifacts and produces a reproducible map of
what is supported by execution evidence versus what is merely a surviving
design or script.  Its output is intentionally suitable only for the
``07_SANDBOX/free_research`` proposal boundary.

The distinction matters: an old loop, heartbeat, or advisor script is not a
current capability merely because its source code still exists.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable


CONTRACT_VERSION = "ace.museum_archaeology_inventory.v1"

RUNNING = "RUNNING"
HISTORICAL_EXECUTED = "HISTORICAL_EXECUTED"
CODE_ONLY = "CODE_ONLY"
DESIGN_ONLY = "DESIGN_ONLY"
DUPLICATE = "DUPLICATE"
SUPERSEDED = "SUPERSEDED"

ABSORB = "ABSORB"
ADAPT = "ADAPT"
CONFLICT = "CONFLICT"
REDUNDANT = "REDUNDANT"
REJECT = "REJECT"

ECOLOGY_CONSTITUTION = "ECOLOGY_CONSTITUTION"
RUN_TRACE = "RUN_TRACE"
ROLE_DOSSIER = "ROLE_DOSSIER"
FAILURE_CASE = "FAILURE_CASE"
TOOL_RELIC = "TOOL_RELIC"
CONTINUITY_EVIDENCE = "CONTINUITY_EVIDENCE"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _as_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_json_keys(path: Path) -> tuple[list[str], dict[str, Any]]:
    """Read only schema/time fields from a historical JSON report.

    Historical report bodies can contain user narratives.  The inventory never
    copies them; it records only top-level schema and the two date anchors used
    to establish that a report series actually existed.
    """

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return [], {}
    if not isinstance(payload, dict):
        return [], {}
    anchors = {
        key: _as_iso(payload.get(key))
        for key in ("report_date", "generated_at", "date", "timestamp")
        if _as_iso(payload.get(key))
    }
    return sorted(payload.keys()), anchors


@dataclass(frozen=True)
class ArtifactSpec:
    artifact_id: str
    title: str
    relative_dir: str
    pattern: str
    status: str
    disposition: str
    safe_semantic: str
    current_ace_consumption: str
    rationale: str
    report_series: bool = False
    fragment_types: tuple[str, ...] = ()


class MuseumArchaeologyInventory:
    """Build a narrow, evidence-first R1/R2 inventory.

    ``history_root`` normally points to ``C:\\tmp``.  The allow-list avoids
    broad home-directory scans and deliberately excludes private credentials,
    runtime configuration, model keys, chat logs, and browser state.
    """

    _SPECS = (
        ArtifactSpec(
            artifact_id="R2_DAILY_KNOWLEDGE_REPORTS",
            title="R2 structured daily knowledge reports",
            relative_dir="private_claw-soul/07_OPERATIONS/knowledge_reports",
            pattern="daily_report_*.json",
            status=HISTORICAL_EXECUTED,
            disposition=ADAPT,
            safe_semantic="daily structured evidence ledger: observation, experience, signals, decisions, summary",
            current_ace_consumption="No direct ACE consumer of this historical report series.",
            rationale="A consecutive report series is execution evidence for a reporting cadence, not proof that every embedded conclusion was true.",
            report_series=True,
            fragment_types=(CONTINUITY_EVIDENCE, RUN_TRACE),
        ),
        ArtifactSpec(
            artifact_id="R2_KNOWLEDGE_SHIFT_ECHO",
            title="R2 early/noon knowledge shift with prior-day echo",
            relative_dir="private_claw-soul/lab_02/06_SCRIPTS/01_knowledge",
            pattern="knowledge_shift.py",
            status=CODE_ONLY,
            disposition=ADAPT,
            safe_semantic="carry unresolved observations forward for a later review window",
            current_ace_consumption="The sandbox preserves experiments, but has no historical-echo selector.",
            rationale="The script is available, but the local reports do not prove this exact script produced the daily reports.",
            fragment_types=(TOOL_RELIC,),
        ),
        ArtifactSpec(
            artifact_id="MINE_SEED_DAILY_SELF_LOOP",
            title="mine-seed daily self-loop",
            relative_dir="mine-seed/04_PROTOCOLS",
            pattern="daily_self_loop.py",
            status=CODE_ONLY,
            disposition=CONFLICT,
            safe_semantic="bounded daily recovery, asset audit, evidence report",
            current_ace_consumption="ACE has its own daemon and sandbox automations; this script is not a current daemon consumer.",
            rationale="It mixes useful observation semantics with automatic advisor execution, task scheduling, and a second loop.",
            fragment_types=(TOOL_RELIC,),
        ),
        ArtifactSpec(
            artifact_id="MINE_SEED_HEARTBEAT",
            title="mine-seed heartbeat",
            relative_dir="mine-seed/04_PROTOCOLS",
            pattern="heartbeat.py",
            status=CODE_ONLY,
            disposition=CONFLICT,
            safe_semantic="periodic health observation and explicit no-news state",
            current_ace_consumption="Current ACE has a sole daemon; old heartbeat code has no direct production consumer.",
            rationale="The code includes Telegram and advisor triggers. A dated heartbeat note proves historical activity, not that this source executed it.",
            fragment_types=(TOOL_RELIC,),
        ),
        ArtifactSpec(
            artifact_id="MINE_SEED_AUTONOMOUS_LOOP",
            title="mine-seed gateway autonomous loop",
            relative_dir="mine-seed/05_TOOLS/gateway",
            pattern="autonomous_loop.py",
            status=CODE_ONLY,
            disposition=REJECT,
            safe_semantic="observe before acting",
            current_ace_consumption="None; deliberately not a production candidate.",
            rationale="This historical loop starts processes, installs dependencies, and can invoke stock-advisor work. It conflicts with the one-daemon boundary.",
            fragment_types=(TOOL_RELIC,),
        ),
        ArtifactSpec(
            artifact_id="R1_R2_DAILY_ARCHAEOLOGY",
            title="R1-to-R2 daily archaeology reports",
            relative_dir="r1-archaeology/analysis",
            pattern="archaeology_report_*.md",
            status=HISTORICAL_EXECUTED,
            disposition=ABSORB,
            safe_semantic="record discoveries, contradictions, missing evidence, and the next bounded question",
            current_ace_consumption="Repository memory is known to ACE, but the sandbox does not yet use a dated archaeology series as input.",
            rationale="Multiple dated reports demonstrate recurring archaeology work; their conclusions remain historical claims and require independent review before adoption.",
            fragment_types=(CONTINUITY_EVIDENCE, RUN_TRACE),
        ),
        ArtifactSpec(
            artifact_id="R1_FIVE_FACTORY_FREEZONE",
            title="R1 five-factory/freezone model",
            relative_dir="mine-seed/03_DATA/superseded_archive/research/r1_archaeology/daily",
            pattern="2026-06-28_R1_五大加工厂_废墟熔炼厂_孟婆人格考古__SUPERSEDED_*.md",
            status=SUPERSEDED,
            disposition=REDUNDANT,
            safe_semantic="preserve failures and transform them into reviewable research material",
            current_ace_consumption="Already represented by free-research experiments, quarantine, curator, court, and teacher queue.",
            rationale="Useful vocabulary, but the current sandbox already implements the safe core without reviving persona machinery.",
            fragment_types=(ECOLOGY_CONSTITUTION, ROLE_DOSSIER),
        ),
        ArtifactSpec(
            artifact_id="R1_ENVIRONMENT_AWARENESS",
            title="R1 environmental-awareness principle",
            relative_dir="mine-seed/02_MEMORY/assets/cognition",
            pattern="CG-002-environmental-awareness.md",
            status=DESIGN_ONLY,
            disposition=ADAPT,
            safe_semantic="perception precedes action; observed context becomes a reviewable hypothesis rather than an automatic command",
            current_ace_consumption="Production observes runtime and data health only; desktop or human-environment sensing is not a daemon consumer.",
            rationale="The asset establishes a recoverable principle, not execution evidence for any legacy sensor or automatic task dispatcher.",
            fragment_types=(ECOLOGY_CONSTITUTION,),
        ),
        ArtifactSpec(
            artifact_id="R1_COGNITIVE_ROUTING_ARCHAEOLOGY",
            title="R1 cognitive routing archaeology",
            relative_dir="mine-seed/03_DATA/superseded_archive/research/r1_archaeology/daily",
            pattern="2026-06-28_R1认知路由协议考古报告__SUPERSEDED_*.md",
            status=SUPERSEDED,
            disposition=DUPLICATE,
            safe_semantic="separate discovered evidence, role interpretation, and human approval",
            current_ace_consumption="Current task roles and sandbox society cover the role-separation idea.",
            rationale="The historical report itself says this concept was already absorbed; it is a provenance source, not an implementation candidate.",
            fragment_types=(ECOLOGY_CONSTITUTION, ROLE_DOSSIER),
        ),
        ArtifactSpec(
            artifact_id="R2_RUNTIME_DEADLOCK_FORENSICS",
            title="R2 CentralController deadlock forensics",
            relative_dir="private_claw-soul/05_PROJECTS/r1_archaeology",
            pattern="R2_RUNTIME_FORENSICS.md",
            status=HISTORICAL_EXECUTED,
            disposition=REJECT,
            safe_semantic="treat repeated failure as evidence and retain the counterexample",
            current_ace_consumption="The current sandbox can preserve failure evidence; no old runtime should be restored.",
            rationale="The forensic record describes an old self-locking start loop. It is a counterexample to preserve, not a capability to revive.",
            fragment_types=(FAILURE_CASE,),
        ),
        ArtifactSpec(
            artifact_id="MINE_SEED_SHADOW_AUDIT",
            title="mine-seed shadow-audit records",
            relative_dir="mine-seed/03_DATA/shadow_audit",
            pattern="shadow_audit_log.jsonl",
            status=HISTORICAL_EXECUTED,
            disposition=REDUNDANT,
            safe_semantic="read-only shadow observation with a time-bounded review condition",
            current_ace_consumption="ACE already uses a shadow/research boundary and must not revive historical automatic stock-advisor paths.",
            rationale="The isolation pattern is worth remembering, but this particular lineage includes historic recommendation material and is not reusable as a current source.",
            fragment_types=(CONTINUITY_EVIDENCE, RUN_TRACE),
        ),
    )

    def __init__(self, history_root: str | Path) -> None:
        self.history_root = Path(history_root).resolve()

    def scan(self) -> dict[str, Any]:
        artifacts = [self._inspect(spec) for spec in self._SPECS]
        visible = [artifact for artifact in artifacts if artifact["present"]]
        inventory = {
            "contract_version": CONTRACT_VERSION,
            "mode": "FREE_RESEARCH_ONLY",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "history_root": str(self.history_root),
            "explicit_non_actions": [
                "No historical daemon, scheduler, heartbeat, advisor, Telegram sender, broker, model call, or production config is started or changed.",
                "No historical narrative is treated as current market, runtime, or recommendation evidence.",
            ],
            "summary": {
                "artifact_count": len(artifacts),
                "present_artifact_count": len(visible),
                "by_status": self._count(visible, "status"),
                "by_disposition": self._count(visible, "disposition"),
                "by_fragment_type": self._count_many(visible, "fragment_types"),
                "historical_daily_report_count": self._daily_report_count(artifacts),
            },
            "artifacts": artifacts,
        }
        immutable = {key: value for key, value in inventory.items() if key != "generated_at"}
        inventory["inventory_sha256"] = hashlib.sha256(_canonical(immutable).encode("utf-8")).hexdigest()
        return inventory

    def _inspect(self, spec: ArtifactSpec) -> dict[str, Any]:
        directory = self.history_root / Path(spec.relative_dir)
        paths = sorted(directory.glob(spec.pattern)) if directory.exists() else []
        files = [self._file_evidence(path, spec.report_series) for path in paths if path.is_file()]
        return {
            "artifact_id": spec.artifact_id,
            "title": spec.title,
            "present": bool(files),
            "status": spec.status,
            "disposition": spec.disposition,
            "fragment_types": list(spec.fragment_types),
            "safe_semantic": spec.safe_semantic,
            "current_ace_consumption": spec.current_ace_consumption,
            "rationale": spec.rationale,
            "source_path": str(directory),
            "pattern": spec.pattern,
            "files": files,
            "evidence_strength": self._evidence_strength(spec, files),
        }

    @staticmethod
    def _file_evidence(path: Path, report_series: bool) -> dict[str, Any]:
        evidence = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        if report_series and path.suffix.lower() == ".json":
            schema, anchors = _read_json_keys(path)
            evidence["schema_keys"] = schema
            evidence["time_anchors"] = anchors
        return evidence

    @staticmethod
    def _evidence_strength(spec: ArtifactSpec, files: Iterable[dict[str, Any]]) -> str:
        count = len(list(files))
        if not count:
            return "MISSING"
        if spec.status == HISTORICAL_EXECUTED and spec.report_series and count >= 7:
            return "SERIES_EXECUTION_EVIDENCE"
        if spec.status == HISTORICAL_EXECUTED:
            return "HISTORICAL_ARTIFACT_EVIDENCE"
        if spec.status == CODE_ONLY:
            return "SOURCE_ONLY"
        if spec.status in {SUPERSEDED, DUPLICATE}:
            return "ARCHIVAL_CONTEXT_ONLY"
        return "DESIGN_CONTEXT_ONLY"

    @staticmethod
    def _count(artifacts: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for artifact in artifacts:
            value = str(artifact[field])
            result[value] = result.get(value, 0) + 1
        return dict(sorted(result.items()))

    @staticmethod
    def _count_many(artifacts: Iterable[dict[str, Any]], field: str) -> dict[str, int]:
        result: dict[str, int] = {}
        for artifact in artifacts:
            for value in artifact.get(field, []):
                text = str(value)
                result[text] = result.get(text, 0) + 1
        return dict(sorted(result.items()))

    @staticmethod
    def _daily_report_count(artifacts: Iterable[dict[str, Any]]) -> int:
        for artifact in artifacts:
            if artifact["artifact_id"] == "R2_DAILY_KNOWLEDGE_REPORTS":
                return len(artifact["files"])
        return 0

    @staticmethod
    def render_markdown(inventory: dict[str, Any]) -> str:
        summary = inventory["summary"]
        lines = [
            "# R1 / R2 Museum Archaeology Inventory",
            "",
            f"- Generated: `{inventory['generated_at']}`",
            f"- Mode: `{inventory['mode']}`",
            f"- Inventory hash: `{inventory['inventory_sha256']}`",
            f"- Present artifacts: {summary['present_artifact_count']} / {summary['artifact_count']}",
            f"- Historical daily reports verified: {summary['historical_daily_report_count']}",
            "",
            "## Boundary",
            "",
        ]
        lines.extend(f"- {item}" for item in inventory["explicit_non_actions"])
        lines.extend([
            "",
            "## Evidence map",
            "",
            "| Artifact | Fragment types | Evidence status | Disposition | Files | Safe semantic |",
            "| --- | --- | --- | --- | ---: | --- |",
        ])
        for artifact in inventory["artifacts"]:
            files = artifact["files"]
            lines.append(
                "| {title} | {types} | `{status}` / {strength} | `{disposition}` | {count} | {semantic} |".format(
                    title=artifact["title"],
                    types=", ".join(f"`{value}`" for value in artifact["fragment_types"]) or "-",
                    status=artifact["status"],
                    strength=artifact["evidence_strength"],
                    disposition=artifact["disposition"],
                    count=len(files),
                    semantic=artifact["safe_semantic"],
                )
            )
        lines.extend([
            "",
            "## Reading rule",
            "",
            "`HISTORICAL_EXECUTED` proves that an artifact/reporting cadence existed at the recorded time. It does not prove that an old code path, a historical conclusion, or an external action is currently valid.",
            "",
            "Only `ABSORB` or `ADAPT` items may become sandbox experiments. Every downstream output remains `PROPOSAL_ONLY` until separate human and governed review.",
            "",
        ])
        return "\n".join(lines)
