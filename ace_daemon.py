#!/usr/bin/env python3
"""
ACE 自动考古主循环（Daemon v2 — 深度挖矿版）

TRAE 负责叫醒，ACE 自己决定今天挖什么、怎么挖、挖多少。

决策优先级：
1. 发现已知大矿（eco_layer、Ω-FINAL）→ 按每日定量深挖
2. 发现新文件/新路径 → 扫描 + 概念提取
3. 词库有明显缺口 → 从已有材料中补全
4. 都没有 → 今日无新增，不强行产出

每日挖矿预算：不会一次挖完，可持续生长。
"""

import json
import os
import signal
import sys
import time
import traceback
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from collections import defaultdict
from threading import Event, Thread

base_dir = Path(__file__).parent
sys.path.insert(0, str(base_dir))

from core.identity import Identity
from core.lexicon import Lexicon
from core.memory_index import MemoryIndex
from core.disk_scanner import DiskScanner
from core.eco_parser import EcoLayerParser
from core.slice_clusterer import SliceClusterer
from core.archaeology_exporter import ArchaeologyExporter
from core.repo_syncer import RepoSyncer
from core.core_syncer import CoreSyncer
from core.task import Task, TaskPool
from core.task_roles import Observer, Researcher, Validator, Archivist, Guardian
from core.task_creator import TaskCreator
from core.fragment_index import FragmentIndex
from core.file_scanner import FileScanner
from core.mine_seed_scanner import MineSeedScanner
from core.heartbeat import Heartbeat
from core.self_healing import SelfHealing
from core.web_scout import WebScout
from core.local_archaeologist import LocalArchaeologist
from core.skill_generator import SkillGenerator
from core.observation import RuntimeObserver
from core.observation_to_task import ObservationToTaskConverter
from core.discovery import DiscoveryCandidate, DiscoveryMode
from core.model_work_discovery import ModelWorkDiscovery
from core.daily_growth import DailyGrowthLedger
from core.daily_learning import DailyLearningLoop
from core.autonomous_work_allocation import AutonomousWorkAllocation
from core.stock_discovery_sources import StockDiscoverySources
from core.governance.evidence_registry import EvidenceRegistry
from core.governance.knowledge_governor import Governor
from core.governance.knowledge_lifecycle import LifecycleManager
from core.miner_pool.miner_pool import MinerPool
from core.miner_pool.model_router import ModelRouter
from core.repository_curator import RepositoryCurator
from core.similarity_engine import SimilarityEngine
from core.value_scorer import ValueScorer
from core.sync_manager import SyncManager

from core.experience_deposition import ExperienceDeposition


def load_config(base_dir: Path) -> dict:
    config_path = base_dir / "ace_config.json"
    config_path = config_path.resolve()
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


DAILY_BUDGET = {
    "eco_narrative": 100,
    "eco_behavioral": 150,
    "eco_structural": 100,
    "eco_transactional": 150,
    "eco_free_zone": 200,
    "slice_overview": 1,
    "slice_by_file": 1,
    "slice_by_category": 1,
    "disk_scan_paths": 2,
    "concept_extraction_budget": 10,
}


class AceDaemon:
    """ACE 自动考古主循环 v2 — 深度挖矿版"""

    def __init__(self, base_dir: Path, config: dict):
        self.base_dir = base_dir
        self.config = config
        self.repository_sync_enabled = bool(
            config.get("runtime", {}).get("allow_repository_sync", False)
        )
        data_cfg = config.get("data", {})
        self.data_dir = (base_dir / data_cfg.get("memory_cache_dir", "06_RUNTIME/ace/data/memory")).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.identity = Identity(base_dir, config)
        self.lexicon = Lexicon(self.data_dir, self.identity)
        self.memory_index = MemoryIndex(self.data_dir, self.identity, self.lexicon)
        self.disk_scanner = DiskScanner(self.identity, self.lexicon, self.memory_index)

        self.state_file = self.data_dir / "daemon_state.json"
        self.state = self._load_state()

        self.concept_miner = None
        try:
            from core.concept_miner import ConceptMiner
            self.concept_miner = ConceptMiner(self.lexicon)
        except ImportError as error:
            self._log_error("concept_miner_init", str(error))

        self.eco_parser = None
        self.slice_clusterer = None
        self.exporter = None
        self.syncer = None
        self.core_syncer = None
        self.task_pool = None
        self.observer = None
        self.researcher = None
        self.validator = None
        self.archivist = None
        self.guardian = None
        self.event_listener = None
        self.experience_deposition = None
        self.task_creator = None
        self.fragment_index = None
        self.file_scanner = None
        self.mine_seed_scanner = None
        self.web_scout = None
        self.local_archaeologist = None
        self.skill_generator = None
        self.runtime_observer = None  # RO：持续观察者
        self.obs_to_task_converter = None  # Observation → Task 转换器
        self.discovery_mode = None
        self.daily_learning = None
        self.miner_pool = None
        self.model_router = None
        self.repository_curator = None  # 仓库馆长（唯一有权决定同步的 Agent）
        self.lifecycle_lock_token = None
        self.daemon_lock_token = None
        self.daemon_lock_file = self.data_dir / ".daemon.lock"
        self.shutdown_event = Event()
        self.shutdown_reason = ""
        self.run_id = ""
        self._init_miners()
        self._init_export_sync()
        self._init_task_lifecycle()

    def _init_miners(self):
        """尝试初始化各挖矿模块（找不到文件也不报错，跳过即可）"""
        eco_candidates = self._find_eco_layer()
        if eco_candidates:
            try:
                self.eco_parser = EcoLayerParser(
                    eco_candidates[0],
                    lexicon=self.lexicon,
                    memory_index=self.memory_index,
                )
                if self.eco_parser.load():
                    pass
                else:
                    self.eco_parser = None
            except Exception:
                self.eco_parser = None

        omega_candidates = self._find_omega_final()
        if omega_candidates:
            try:
                self.slice_clusterer = SliceClusterer(
                    omega_candidates[0],
                    lexicon=self.lexicon,
                    memory_index=self.memory_index,
                )
                if self.slice_clusterer.load():
                    pass
                else:
                    self.slice_clusterer = None
            except Exception:
                self.slice_clusterer = None

        self.mine_seed_path = None

    def _init_export_sync(self):
        """初始化导出器和同步器（找不到mine-seed也不报错）"""
        mine_seed_path = self._find_mine_seed()
        if mine_seed_path:
            self.mine_seed_path = mine_seed_path
            if self.repository_sync_enabled:
                try:
                    self.exporter = ArchaeologyExporter(
                        ace_base_dir=self.base_dir,
                        mine_seed_path=mine_seed_path,
                    )
                    self.syncer = RepoSyncer(repo_path=mine_seed_path)
                except Exception:
                    self.exporter = None
                    self.syncer = None

        if (self.base_dir / ".git").exists() and self.repository_sync_enabled:
            try:
                self.core_syncer = CoreSyncer(
                    repo_path=str(self.base_dir),
                    remote="ace-core",
                    branch="main",
                    debounce_minutes=60,
                )
            except Exception as e:
                self._log_error("core_syncer_init", str(e))
                self.core_syncer = None

        if (self.base_dir / ".git").exists():
            try:
                curator_data_dir = self.base_dir / "06_RUNTIME" / "ace" / "data" / "curator"
                mine_seed_str = str(self.mine_seed_path) if self.mine_seed_path else ""
                ace_core_str = str(self.base_dir)
                sim_engine = SimilarityEngine(str(curator_data_dir))
                val_scorer = ValueScorer(data_dir=str(curator_data_dir))
                sync_mgr = (
                    SyncManager(data_dir=str(curator_data_dir))
                    if self.repository_sync_enabled
                    else None
                )

                self.repository_curator = RepositoryCurator(
                    ace_runtime_dir=ace_core_str,
                    mine_seed_dir=mine_seed_str,
                    ace_core_dir=ace_core_str,
                    similarity_engine=sim_engine,
                    value_scorer=val_scorer,
                    sync_manager=sync_mgr,
                    data_dir=str(curator_data_dir),
                )
                print(f"[Curator] 仓库馆长已初始化 (数据目录: {curator_data_dir})")
            except Exception as e:
                self._log_error("curator_init", str(e))
                self.repository_curator = None
                print(f"[Curator] 初始化失败: {e}")
    def _init_task_lifecycle(self):
        """初始化任务生命周期系统"""
        try:
            task_pool_dir = self.base_dir / "task_pool"
            self.task_pool = TaskPool(str(task_pool_dir))
            self.observer = Observer(
                task_pool=self.task_pool,
                lexicon=self.lexicon,
                memory_index=self.memory_index,
                daemon_state=self.state,
            )
            model_state_dir = self.base_dir / "06_RUNTIME" / "ace" / "data" / "miner_pool"
            miner_assets_path = self.config.get("runtime", {}).get("miner_pool_assets_path")
            self.miner_pool = MinerPool(
                coze_assets_path=miner_assets_path,
                state_dir=str(model_state_dir),
            )
            self.researcher = Researcher(
                task_pool=self.task_pool,
                lexicon=self.lexicon,
                memory_index=self.memory_index,
                eco_parser=self.eco_parser,
                slice_clusterer=self.slice_clusterer,
                llm_router=self.miner_pool,
            )
            self.validator = Validator(
                task_pool=self.task_pool,
                lexicon=self.lexicon,
                memory_index=self.memory_index,
                llm_router=self.miner_pool,
            )
            self.archivist = Archivist(
                task_pool=self.task_pool,
                memory_index=self.memory_index,
                lexicon=self.lexicon,
            )
            self.guardian = Guardian(
                task_pool=self.task_pool,
                lexicon=self.lexicon,
                memory_index=self.memory_index,
            )
            self.event_listener = None
            knowledge_dir = self.base_dir / "09_KNOWLEDGE"
            self.experience_deposition = ExperienceDeposition(str(knowledge_dir))
            fragment_dir = self.base_dir / "02_FRAGMENT_INDEX"
            self.fragment_index = FragmentIndex(str(fragment_dir))
            scan_roots = [
                self.base_dir.parent,
                Path.home() / "Downloads",
            ]
            self.file_scanner = FileScanner(
                task_pool=self.task_pool,
                fragment_index=self.fragment_index,
                scan_roots=scan_roots,
                max_depth=4,
            )
            if self.mine_seed_path:
                state_file = self.base_dir / "02_FRAGMENT_INDEX" / ".mine_seed_state.json"
                self.mine_seed_scanner = MineSeedScanner(
                    mine_seed_path=str(self.mine_seed_path),
                    state_file=str(state_file),
                    max_new_commits=5,
                )

            # 初始化本地考古扫描器
            local_arch_state = self.base_dir / "06_RUNTIME" / "ace" / "data" / "local_archaeologist_state.json"
            self.local_archaeologist = LocalArchaeologist(
                base_dir=self.base_dir,
                lexicon=self.lexicon,
                memory_index=self.memory_index,
                task_pool=self.task_pool,
                state_file=local_arch_state,
            )

            # 初始化外网学习模块
            web_scout_state = self.base_dir / "06_RUNTIME" / "ace" / "data" / "web_scout_state.json"
            self.web_scout = WebScout(
                base_dir=self.base_dir,
                lexicon=self.lexicon,
                memory_index=self.memory_index,
                task_pool=self.task_pool,
                state_file=web_scout_state,
            )

            # 初始化技能生成器
            skills_dir = self.base_dir / "09_KNOWLEDGE" / "skills"
            self.skill_generator = SkillGenerator(
                skills_dir=skills_dir,
                task_pool=self.task_pool,
            )

            # 初始化 task_creator，传入 skill_generator
            self.task_creator = TaskCreator(
                task_pool=self.task_pool,
                base_dir=self.base_dir,
                lexicon=self.lexicon,
                memory_index=self.memory_index,
                skill_generator=self.skill_generator,
            )

            # 初始化 RO（Runtime Observer）和 Observation → Task 转换器
            obs_data_dir = self.base_dir / "06_RUNTIME" / "ace" / "data" / "observations"
            self.runtime_observer = RuntimeObserver(str(obs_data_dir))
            self.obs_to_task_converter = ObservationToTaskConverter(
                observer=self.runtime_observer,
                task_pool=self.task_pool,
            )
            self.model_router = ModelRouter()
            stock_discovery = StockDiscoverySources(
                observer=self.runtime_observer,
                base_dir=str(self.base_dir),
            )
            self.discovery_mode = DiscoveryMode(
                task_pool=self.task_pool,
                observer=self.runtime_observer,
                base_dir=str(self.base_dir),
                model_router=self.model_router,
                candidate_sources=stock_discovery.candidate_sources(),
            )
            self.model_work_discovery = ModelWorkDiscovery(
                discovery=self.discovery_mode,
                report_path=str(
                    self.base_dir
                    / "06_RUNTIME"
                    / "ace"
                    / "data"
                    / "model_work_discovery_latest.json"
                ),
            )
            self.daily_growth = DailyGrowthLedger(
                self.task_pool,
                str(self.base_dir / "06_RUNTIME" / "ace" / "data" / "daily_growth_latest.json"),
            )
            governance_dir = self.base_dir / "08_GOVERNANCE"
            self.daily_learning = DailyLearningLoop(
                data_dir=str(self.data_dir / "daily_learning"),
                discovery=self.discovery_mode,
                converter=self.obs_to_task_converter,
                task_pool=self.task_pool,
                evidence_registry=EvidenceRegistry(str(governance_dir)),
                knowledge_governor=Governor(str(self.base_dir / "06_RUNTIME" / "ace")),
                lifecycle_manager=LifecycleManager(str(governance_dir / "daily_learning_lifecycle.jsonl")),
                internal_candidate_sources=[self._daily_learning_candidates],
            )
            self.lifecycle_lock_file = task_pool_dir / ".lifecycle.lock"
        except Exception as e:
            self._log_error("task_lifecycle_init", str(e))
            self.task_pool = None

        self.heartbeat = Heartbeat(self.data_dir)
        self.self_healing = SelfHealing(self.data_dir)

    def _find_mine_seed(self) -> Optional[str]:
        """自动寻找 mine-seed 仓库 — 不硬编码路径"""
        candidates = []

        trae_work = Path.home() / ".trae" / "work"
        if trae_work.exists():
            try:
                for repo_dir in trae_work.glob("*/repos/mine-seed"):
                    repo_dir = repo_dir.resolve()
                    git_dir = repo_dir / ".git"
                    if git_dir.exists():
                        candidates.append(str(repo_dir))
            except Exception:
                pass

        search_roots = [
            self.base_dir.parent,
            Path.home() / "Documents",
            Path.home() / "projects",
            Path.home() / "workspace",
        ]
        for root in search_roots:
            if not root.exists():
                continue
            try:
                for p in root.rglob("mine-seed/.git"):
                    if p.is_dir():
                        candidates.append(str(p.parent))
                        if len(candidates) >= 3:
                            return candidates[0]
            except Exception:
                pass

        return candidates[0] if candidates else None

    def _find_eco_layer(self) -> List[str]:
        """自动寻找 eco_layer.json — 不硬编码路径"""
        candidates = []
        search_roots = [
            self.base_dir,
            self.base_dir.parent,
            Path.home() / "Downloads",
            Path.home() / "Desktop",
        ]

        for root in search_roots:
            if not root.exists():
                continue
            try:
                for p in root.rglob("eco_layer*.json"):
                    if p.is_file():
                        candidates.append(str(p))
                        if len(candidates) >= 3:
                            return candidates
            except Exception:
                pass

        return candidates

    def _find_omega_final(self) -> List[str]:
        """自动寻找 Ω-FINAL — 不硬编码路径"""
        candidates = []
        search_roots = [
            self.base_dir,
            self.base_dir.parent,
            Path.home() / "Downloads",
            Path.home() / "Desktop",
        ]

        keywords = ["omega_final", "Ω_FINAL", "R1_Ω", "r1_final", "final_state"]

        for root in search_roots:
            if not root.exists():
                continue
            try:
                for p in root.rglob("*.json"):
                    name = p.name.lower()
                    if any(kw.lower() in name for kw in keywords):
                        candidates.append(str(p))
                        if len(candidates) >= 3:
                            return candidates
            except Exception:
                pass

        return candidates

    def _load_state(self) -> dict:
        if not self.state_file.exists():
            for temporary in self.data_dir.glob(f"{self.state_file.name}.*.tmp"):
                try:
                    with open(temporary, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    os.replace(temporary, self.state_file)
                    return state
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
            return {
                "last_run": None,
                "last_backup": None,
                "last_scan_paths": {},
                "last_lexicon_count": 0,
                "last_memory_count": 0,
                "daily_summaries": [],
                "discovered_paths": [],
                "mining_progress": {
                    "eco_layer": {},
                    "slices": {},
                },
                "errors": [],
            }
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            for temporary in self.data_dir.glob(f"{self.state_file.name}.*.tmp"):
                try:
                    with open(temporary, "r", encoding="utf-8") as f:
                        state = json.load(f)
                    os.replace(temporary, self.state_file)
                    return state
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
            raise RuntimeError(f"无法恢复 daemon_state.json: {error}") from error

    def _save_state(self):
        temporary = self.state_file.with_suffix(f".json.{uuid.uuid4().hex}.tmp")
        with open(temporary, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, self.state_file)

    def _begin_cycle_progress(self) -> None:
        self.state["cycle_progress"] = {
            "current_stage": None,
            "started_at": datetime.now().isoformat(),
            "completed_stages": [],
        }
        self._save_state()

    def _start_cycle_stage(self, stage: str) -> float:
        progress = self.state.setdefault("cycle_progress", {})
        progress["current_stage"] = stage
        self._save_state()
        return time.monotonic()

    def _complete_cycle_stage(self, stage: str, started_at: float) -> None:
        progress = self.state.setdefault("cycle_progress", {})
        completed = progress.setdefault("completed_stages", [])
        completed.append({
            "stage": stage,
            "duration_seconds": round(time.monotonic() - started_at, 6),
            "completed_at": datetime.now().isoformat(),
        })
        progress["current_stage"] = None
        self._save_state()

    def _finalize_cycle(self, outcome: str, reason: str = "") -> None:
        """Persist an explicit cycle terminal state for every exit path."""
        progress = self.state.setdefault("cycle_progress", {})
        current = progress.get("current_stage")
        if current:
            progress.setdefault("completed_stages", []).append({
                "stage": current,
                "outcome": outcome,
                "reason": reason,
                "completed_at": datetime.now().isoformat(),
            })
        progress["current_stage"] = None
        progress["cycle_status"] = outcome
        progress["stop_reason"] = reason
        progress["finished_at"] = datetime.now().isoformat()
        self._save_state()

    def _recover_stale_cycle(self) -> None:
        """Close a cycle left open by an interrupted or killed prior run."""
        progress = self.state.get("cycle_progress", {})
        if not isinstance(progress, dict) or not progress.get("current_stage"):
            return
        stale_run_id = self.state.get("run_id")
        reason = f"stale_cycle_recovered:{progress.get('current_stage')}"
        progress.setdefault("completed_stages", []).append({
            "stage": progress.get("current_stage"),
            "outcome": "interrupted",
            "reason": reason,
            "previous_run_id": stale_run_id,
            "completed_at": datetime.now().isoformat(),
        })
        progress["current_stage"] = None
        progress["cycle_status"] = "interrupted"
        progress["stop_reason"] = reason
        progress["finished_at"] = datetime.now().isoformat()
        self.state["last_exit_reason"] = reason
        self.state["last_exit_time"] = datetime.now().isoformat()
        self._save_state()

    def _start_stage_heartbeat(self, stage: str, interval_seconds: float = 15.0):
        """Keep the liveness proof fresh while a synchronous stage is running.

        Curator work can legitimately take minutes.  The daemon loop must not
        block the only heartbeat writer during that interval, otherwise an
        external observer cannot distinguish slow work from a dead process.
        This is a liveness-only pulse; it does not schedule work or alter the
        cycle state machine.
        """
        stop_event = Event()

        def pulse():
            while not stop_event.wait(interval_seconds):
                self.heartbeat.beat(reason=f"stage:{stage}")
                self.heartbeat.status["current_stage"] = stage
                self.heartbeat.status["stage_heartbeat_at"] = datetime.now().isoformat()
                self.heartbeat._save()

        self.heartbeat.beat(reason=f"stage:{stage}")
        self.heartbeat.status["current_stage"] = stage
        self.heartbeat.status["stage_heartbeat_at"] = datetime.now().isoformat()
        self.heartbeat._save()
        thread = Thread(target=pulse, name=f"ace-{stage}-heartbeat", daemon=True)
        thread.start()
        return stop_event, thread

    @staticmethod
    def _stop_stage_heartbeat(handle) -> None:
        if not handle:
            return
        stop_event, thread = handle
        stop_event.set()
        thread.join(timeout=2.0)

    def request_shutdown(self, reason: str) -> None:
        if not self.shutdown_event.is_set():
            self.shutdown_reason = reason
            self.shutdown_event.set()

    def _handle_shutdown_signal(self, signum, frame) -> None:
        self.shutdown_event.set()

    def _install_shutdown_handlers(self) -> Dict[int, Any]:
        handlers = {}
        for signal_name in ("SIGINT", "SIGTERM", "SIGBREAK"):
            value = getattr(signal, signal_name, None)
            if value is None:
                continue
            try:
                handlers[value] = signal.getsignal(value)
                signal.signal(value, self._handle_shutdown_signal)
            except (ValueError, OSError):
                pass
        return handlers

    def _restore_shutdown_handlers(self, handlers: Dict[int, Any]) -> None:
        for signum, handler in handlers.items():
            try:
                signal.signal(signum, handler)
            except (ValueError, OSError):
                pass

    def _checkpoint_shutdown(self, reason: str) -> None:
        exit_time = datetime.now().isoformat()
        self.heartbeat.mark_stopping(
            reason=reason,
            pid=os.getpid(),
            run_id=self.run_id,
            exit_time=exit_time,
        )
        self.state["last_exit_reason"] = reason
        self.state["last_exit_time"] = exit_time
        self.state["pid"] = os.getpid()
        self.state["run_id"] = self.run_id
        outcome = "failed" if reason.startswith("fatal_error:") else (
            "interrupted" if reason in {"keyboard_interrupt", "shutdown_requested"} else "completed"
        )
        self.state["run_status"] = outcome
        self._finalize_cycle(outcome, reason)
        self._save_state()
        if reason.startswith("fatal_error:"):
            self.heartbeat.mark_dead(
                reason=reason,
                pid=os.getpid(),
                run_id=self.run_id,
                exit_time=exit_time,
            )

    def _checkpoint_startup(self) -> None:
        """Persist the identity of the live run before its first cycle starts."""
        self.state["pid"] = os.getpid()
        self.state["run_id"] = self.run_id
        self.state["run_started_at"] = datetime.now().isoformat()
        self.state["run_status"] = "alive"
        self._save_state()

    def run_periodic_backup(self) -> Dict[str, Any]:
        from ops.backup_data import backup_runtime

        backup_dir, manifest = backup_runtime(self.base_dir)
        result = {
            "path": str(backup_dir),
            "manifest": manifest,
            "completed_at": datetime.now().isoformat(),
        }
        self.state["last_backup"] = {
            "path": result["path"],
            "completed_at": result["completed_at"],
            "asset_count": len(manifest["assets"]),
            "manifest_version": manifest["version"],
        }
        self._save_state()
        return result

    def _backup_due(self) -> bool:
        interval = self.config.get("runtime", {}).get("backup_interval_seconds", 86400)
        if interval <= 0:
            return True
        last_backup = self.state.get("last_backup") or {}
        completed_at = last_backup.get("completed_at")
        if not completed_at:
            return True
        try:
            elapsed = (datetime.now() - datetime.fromisoformat(completed_at)).total_seconds()
        except (TypeError, ValueError):
            return True
        return elapsed >= interval

    def _log_error(self, module: str, error: str, context: str = ""):
        """记录错误，但不中断主循环"""
        err_entry = {
            "time": datetime.now().isoformat(),
            "module": module,
            "error": error,
            "context": context[:200],
        }
        if "errors" not in self.state:
            self.state["errors"] = []
        self.state["errors"].insert(0, err_entry)
        self.state["errors"] = self.state["errors"][:50]

    def _model_pipeline_metrics(self) -> Dict[str, Any]:
        metrics = {
            "reasoning_tasks_created": 0,
            "model_tasks_created": 0,
            "task_types": {},
            "production_task_calls": 0,
            "providers": {},
            "selected_models": {},
            "api_called": 0,
            "api_result": {},
            "fallback": {},
            "trace_complete": 0,
        }
        for task in self.task_pool.list_tasks(limit=10000):
            outputs = task.outputs if isinstance(task.outputs, dict) else {}
            admission = outputs.get("model_task_admission")
            if not isinstance(admission, dict) or admission.get("eligible") is not True:
                continue
            classification = str(admission.get("classification", ""))
            if classification not in {"reasoning", "strategic", "execution"}:
                continue
            if f"task_type:{classification}" not in task.tags:
                continue
            metrics["model_tasks_created"] += 1
            metrics["task_types"][classification] = metrics["task_types"].get(classification, 0) + 1
            if classification == "reasoning":
                metrics["reasoning_tasks_created"] += 1
            traces = outputs.get("model_execution", [])
            if not isinstance(traces, list):
                continue
            for trace in traces:
                if not isinstance(trace, dict):
                    continue
                metrics["production_task_calls"] += 1
                provider = trace.get("provider")
                if isinstance(provider, str) and provider:
                    providers = metrics["providers"]
                    providers[provider] = providers.get(provider, 0) + 1
                selected_model = trace.get("selected_model")
                if isinstance(selected_model, str) and selected_model:
                    selected_models = metrics["selected_models"]
                    selected_models[selected_model] = selected_models.get(selected_model, 0) + 1
                if trace.get("api_called") is True:
                    metrics["api_called"] += 1
                api_result = trace.get("api_result")
                if isinstance(api_result, str) and api_result:
                    api_results = metrics["api_result"]
                    api_results[api_result] = api_results.get(api_result, 0) + 1
                if "fallback" in trace:
                    fallback = str(bool(trace["fallback"])).lower()
                    fallbacks = metrics["fallback"]
                    fallbacks[fallback] = fallbacks.get(fallback, 0) + 1
                if trace.get("trace_complete") is True:
                    metrics["trace_complete"] += 1
        return metrics

    def get_status(self) -> dict:
        lex_stats = self.lexicon.get_stats()
        mem_stats = self.memory_index.get_stats()

        eco_info = None
        if self.eco_parser:
            eco_info = {
                "loaded": True,
                "layers": self.eco_parser.get_layer_stats(),
            }

        slice_info = None
        if self.slice_clusterer:
            slice_info = {
                "loaded": True,
                "total_slices": self.slice_clusterer.total_slices,
            }

        export_info = None
        if self.repository_sync_enabled and self.exporter and self.syncer:
            export_info = {
                "mine_seed_found": True,
                "target_dir": "03_DATA/research/r1_archaeology",
            }

        task_info = None
        if self.task_pool:
            task_stats = self.task_pool.get_stats()
            task_info = task_stats

        knowledge_info = None
        if self.experience_deposition:
            try:
                knowledge_info = self.experience_deposition.get_stats()
            except Exception:
                pass

        fragment_info = None
        if self.fragment_index:
            try:
                fragment_info = self.fragment_index.get_stats()
            except Exception:
                pass

        web_scout_info = None
        if self.web_scout:
            try:
                web_scout_info = self.web_scout.get_stats()
            except Exception:
                pass

        local_arch_info = None
        if self.local_archaeologist:
            try:
                local_arch_info = self.local_archaeologist.get_stats()
            except Exception:
                pass

        skill_info = None
        if self.skill_generator:
            try:
                skill_info = self.skill_generator.get_stats()
            except Exception:
                pass

        return {
            "lexicon": {
                "concepts": lex_stats.get("total_concepts", 0),
                "categories": lex_stats.get("total_categories", 0),
            },
            "memory_index": {
                "total": mem_stats.get("total", 0),
                "by_type": mem_stats.get("by_type", {}),
            },
            "eco_parser": eco_info,
            "slice_clusterer": slice_info,
            "export_sync": export_info,
            "task_pool": task_info,
            "knowledge": knowledge_info,
            "fragment_index": fragment_info,
            "local_archaeologist": local_arch_info,
            "web_scout": web_scout_info,
            "skills": skill_info,
            "last_run": self.state.get("last_run"),
            "mining_progress": self.state.get("mining_progress", {}),
        }

    def discover_scan_targets(self) -> List[Dict[str, Any]]:
        targets = []
        already_scanned = set(self.state.get("last_scan_paths", {}).keys())

        for entry in self.memory_index.search(limit=500):
            src = entry.get("source_path", "")
            if src and src not in already_scanned:
                parent = str(Path(src).parent)
                if parent and parent not in already_scanned:
                    targets.append({
                        "path": parent,
                        "source": "memory_index_derived",
                        "reason": "从记忆索引中的文件路径向外扩展",
                        "priority": 2,
                    })
                    already_scanned.add(parent)

        home = Path.home()
        candidates = [
            home / "Downloads",
            home / "Documents",
            home / "Desktop",
        ]

        relevant_keywords = [
            "r1", "R1", "考古", "research", "工程",
            "engineering", "知识", "knowledge",
            "系统", "system", "ace", "ACE",
            "mine", "seed", "lexicon", "记忆",
            "eco", "omega", "Ω", "persona",
        ]

        for candidate in candidates:
            if not candidate.exists():
                continue
            candidate_str = str(candidate)
            if candidate_str in already_scanned:
                continue

            keyword_hits = 0
            try:
                for item in candidate.iterdir():
                    name = item.name.lower()
                    if any(kw.lower() in name for kw in relevant_keywords):
                        keyword_hits += 1
            except Exception:
                pass

            if keyword_hits > 0:
                targets.append({
                    "path": candidate_str,
                    "source": "auto_discovered",
                    "reason": f"目录下有 {keyword_hits} 个相关命名的子项",
                    "priority": keyword_hits,
                })

        return targets

    def decide_today_task(self) -> Dict[str, Any]:
        """
        决定今天做什么。

        决策优先级（v2）：
        1. eco_layer 有未挖完的层 → 按每日预算挖一层
        2. Ω-FINAL 切片未分析完 → 按每日预算做一种分析
        3. 有新路径可扫描 → 磁盘扫描
        4. 词库有明显缺口 → 从已有材料中补全
        5. 都没有 → 今日无新增
        """
        lex_stats = self.lexicon.get_stats()
        mem_stats = self.memory_index.get_stats()
        current_concepts = lex_stats.get("total_concepts", 0)
        current_memories = mem_stats.get("total", 0)

        last_concepts = self.state.get("last_lexicon_count", 0)
        last_memories = self.state.get("last_memory_count", 0)

        new_since_last = {
            "new_concepts": current_concepts - last_concepts,
            "new_memories": current_memories - last_memories,
        }

        scan_targets = self.discover_scan_targets()
        mining_progress = self.state.get("mining_progress", {})

        decision = {
            "date": datetime.now().strftime("%Y-%m-%d"),
            "decided_at": datetime.now().isoformat(),
            "current_state": {
                "concepts": current_concepts,
                "memories": current_memories,
                "since_last": new_since_last,
            },
            "scan_targets_count": len(scan_targets),
            "actions": [],
        }

        if self.eco_parser:
            eco_task = self._decide_eco_task(mining_progress)
            if eco_task:
                decision["actions"].append(eco_task)

        if self.slice_clusterer:
            slice_task = self._decide_slice_task(mining_progress)
            if slice_task:
                decision["actions"].append(slice_task)

        if scan_targets and len(decision["actions"]) < 3:
            priority_targets = sorted(
                scan_targets,
                key=lambda x: x.get("priority", 0),
                reverse=True,
            )
            decision["actions"].append({
                "type": "disk_scan",
                "targets": priority_targets[:DAILY_BUDGET["disk_scan_paths"]],
                "reason": f"发现 {len(scan_targets)} 个可扫描路径",
            })

        weak_categories = []
        for cat, count in lex_stats.get("categories", {}).items():
            if count <= 2:
                weak_categories.append(cat)
        if weak_categories and len(decision["actions"]) < 4:
            decision["actions"].append({
                "type": "lexicon_gap",
                "categories": weak_categories,
                "reason": f"有 {len(weak_categories)} 个分类概念数<=2，需要补充",
            })

        if not decision["actions"]:
            decision["actions"].append({
                "type": "no_new_discovery",
                "reason": "已知矿已挖完今日份、无新路径、无明显缺口，今日以稳",
            })

        return decision

    def _decide_eco_task(self, progress: dict) -> Optional[Dict[str, Any]]:
        """决定今天挖 eco_layer 的哪一层、从哪里开始"""
        eco_progress = progress.get("eco_layer", {})
        layer_stats = self.eco_parser.get_layer_stats()

        for layer in self.eco_parser.LAYER_PRIORITY:
            if layer not in layer_stats:
                continue

            layer_progress = eco_progress.get(layer, {"offset": 0, "last_mined": None})
            total = layer_stats[layer]["count"]
            offset = layer_progress.get("offset", 0)

            if offset >= total:
                continue

            today_budget = DAILY_BUDGET.get(f"eco_{layer}", 100)
            remaining = total - offset

            if remaining > 0:
                mine_count = min(today_budget, remaining)
                return {
                    "type": "eco_mining",
                    "layer": layer,
                    "layer_name": layer_stats[layer]["name"],
                    "offset": offset,
                    "count": mine_count,
                    "total": total,
                    "remaining": remaining,
                    "reason": (
                        f"{layer_stats[layer]['name']}共{total}条，"
                        f"已挖{offset}条，今日挖{mine_count}条"
                    ),
                }

        return None

    def _decide_slice_task(self, progress: dict) -> Optional[Dict[str, Any]]:
        """决定今天做切片的哪种分析"""
        slice_progress = progress.get("slices", {})

        analysis_order = [
            ("overview", "切片总览统计", 1),
            ("by_file", "按文件聚类", 1),
            ("by_category", "按功能类别聚类", 1),
            ("core_modules", "识别核心模块", 1),
            ("config_files", "提取配置文件", 1),
        ]

        for mode, name, per_day in analysis_order:
            done_today = slice_progress.get(f"{mode}_done_today", 0)
            last_done_date = slice_progress.get(f"{mode}_last_date", "")
            today = datetime.now().strftime("%Y-%m-%d")

            if last_done_date != today or done_today < per_day:
                return {
                    "type": "slice_mining",
                    "mode": mode,
                    "mode_name": name,
                    "reason": f"切片考古：{name}",
                }

        return None

    def execute_eco_mining(self, action: Dict) -> Dict[str, Any]:
        """执行 eco_layer 挖矿"""
        if not self.eco_parser:
            return {"error": "eco_parser not available"}

        layer = action["layer"]
        offset = action["offset"]
        count = action["count"]

        try:
            result = self.eco_parser.mine_layer(
                layer=layer,
                max_entries=count,
                offset=offset,
                auto_index=True,
            )

            mining_progress = self.state.setdefault("mining_progress", {})
            eco_progress = mining_progress.setdefault("eco_layer", {})
            layer_progress = eco_progress.setdefault(layer, {"offset": 0})
            layer_progress["offset"] = offset + result.get("mined", 0)
            layer_progress["last_mined"] = datetime.now().isoformat()
            layer_progress["total_mined"] = layer_progress["offset"]

            try:
                report = self.eco_parser.generate_deep_report(mining_progress)
                if "error" not in report:
                    report_json = json.dumps(report, ensure_ascii=False)[:3000]
                    self.memory_index.add(
                        title=f"eco_layer深度考古报告",
                        content=report_json,
                        memory_type="eco_analysis_report",
                        category="考古发现",
                        source="eco_parser:deep_report",
                        tags=["eco_layer", "deep_analysis", layer],
                    )
                    result["report"] = True
            except Exception:
                pass

            return result
        except Exception as e:
            self._log_error("eco_mining", str(e), f"layer={layer}")
            return {"error": str(e), "layer": layer}

    def _mine_concepts_from_eco(self, eco_result: Dict, action: Dict) -> int:
        """从eco挖矿结果中提炼新概念并加入词库"""
        if not self.eco_parser or not self.concept_miner:
            return 0

        layer = action.get("layer", "")
        offset = action.get("offset", 0)
        count = min(action.get("count", 100), 200)

        try:
            samples = self.eco_parser.sample_layer(layer, count=count, offset=offset)
            if not samples:
                return 0

            text_chunks = [{"content": s["content"]} for s in samples if len(s.get("content", "")) > 100]
            if not text_chunks:
                return 0

            result = self.concept_miner.batch_mine(
                text_chunks,
                source=f"eco:{layer}",
                max_total_concepts=DAILY_BUDGET["concept_extraction_budget"],
            )

            return result.get("added", 0)
        except Exception as e:
            self._log_error("eco_concept_mining", str(e), f"layer={layer}")
            return 0

    def execute_slice_mining(self, action: Dict) -> Dict[str, Any]:
        """执行切片聚类分析"""
        if not self.slice_clusterer:
            return {"error": "slice_clusterer not available"}

        mode = action["mode"]

        try:
            result = self.slice_clusterer.mine(mode=mode, auto_index=True)

            mining_progress = self.state.setdefault("mining_progress", {})
            slice_progress = mining_progress.setdefault("slices", {})
            today = datetime.now().strftime("%Y-%m-%d")

            last_date = slice_progress.get(f"{mode}_last_date", "")
            if last_date == today:
                slice_progress[f"{mode}_done_today"] = slice_progress.get(f"{mode}_done_today", 0) + 1
            else:
                slice_progress[f"{mode}_last_date"] = today
                slice_progress[f"{mode}_done_today"] = 1

            slice_progress[f"{mode}_total_done"] = slice_progress.get(f"{mode}_total_done", 0) + 1

            return result
        except Exception as e:
            self._log_error("slice_mining", str(e), f"mode={mode}")
            return {"error": str(e), "mode": mode}

    def execute_disk_scan(self, targets: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = {
            "scanned": 0,
            "new_files": 0,
            "new_indexed": 0,
            "new_concepts_added": 0,
            "details": [],
        }

        last_scan = self.state.get("last_scan_paths", {})

        for target in targets:
            path = target["path"]
            try:
                scan_result = self.disk_scanner.scan_path(
                    path,
                    max_depth=3,
                    max_files=150,
                    auto_index=True,
                )
                files_count = scan_result.get("files", 0)
                indexed = scan_result.get("indexed_count", 0)

                last_scan[path] = {
                    "last_scanned_at": datetime.now().isoformat(),
                    "files": files_count,
                    "interesting": scan_result.get("interesting_count", 0),
                }

                results["scanned"] += 1
                results["new_files"] += scan_result.get("interesting_count", 0)
                results["new_indexed"] += indexed
                results["details"].append({
                    "path": path,
                    "files": files_count,
                    "interesting": scan_result.get("interesting_count", 0),
                    "indexed": indexed,
                })
            except Exception as e:
                self._log_error("disk_scan", str(e), f"path={path}")
                results["details"].append({"path": path, "error": str(e)})

        self.state["last_scan_paths"] = last_scan
        return results

    def extract_new_concepts(self) -> int:
        """
        从最近索引的记忆中提取新概念。
        使用 concept_miner 真正提炼，不是占位。
        """
        if not self.concept_miner:
            return 0

        if not self.concept_miner:
            return 0

        try:
            recent_entries = self.memory_index.search(limit=200)
            if not recent_entries:
                return 0

            text_chunks = []
            for entry in recent_entries:
                content = entry.get("content", "")
                if len(content) > 50:
                    text_chunks.append({"content": content})

            if not text_chunks:
                return 0

            result = self.concept_miner.batch_mine(
                text_chunks,
                source="daemon_daily_extract",
                max_total_concepts=DAILY_BUDGET["concept_extraction_budget"],
            )

            return result.get("added", 0)
        except Exception as e:
            self._log_error("concept_extraction", str(e))
            return 0

    def auto_archive_files(self) -> List[Dict[str, Any]]:
        archived = []
        recent = self.memory_index.search(limit=50)

        for entry in recent:
            concepts = [c.get("name", "") for c in entry.get("related_concepts", [])]
            category = entry.get("category", "未分类")
            src_path = entry.get("source_path", "")
            if not src_path:
                continue

            archive_dir = self._determine_archive_path(concepts, category)
            archived.append({
                "source": src_path,
                "archive_category": archive_dir,
                "concepts": concepts[:3],
            })

        return archived

    def _determine_archive_path(self, concepts: List[str], category: str) -> str:
        category_map = {
            "灵魂资产": "02_CONSTRAINT",
            "架构分层": "03_ARCHITECTURE",
            "架构模式": "03_ARCHITECTURE",
            "核心机制": "04_PROTOCOL",
            "治理原则": "02_CONSTRAINT",
            "身份系统": "01_LEXICON",
            "ACE概念": "06_RUNTIME",
            "核心组件": "03_ARCHITECTURE",
            "恢复机制": "05_MEMORY",
            "演化机制": "07_SEEDS",
            "考古发现": "08_ARCHAEOLOGY",
            "身体层": "09_BODY",
        }

        for concept in concepts:
            concept_data = self.lexicon.get_concept(concept) or {}
            cat = concept_data.get("category", "")
            if cat in category_map:
                return category_map[cat]

        if category in category_map:
            return category_map[category]

        return "00_INBOX"

    def _lifecycle_lock_owner_alive(self, pid: int) -> bool:
        if pid <= 0:
            return False
        if pid == os.getpid():
            return True
        if os.name == "nt":
            import ctypes

            handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return False
            try:
                exit_code = ctypes.c_ulong()
                if not ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return False
                return exit_code.value == 259
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    def _publish_lock(self, lock_file: Path, token: str) -> bool:
        temporary = lock_file.with_name(f"{lock_file.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "token": token, "created_at": time.time()}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, lock_file)
            except FileExistsError:
                return False
            return True
        finally:
            try:
                temporary.unlink()
            except FileNotFoundError:
                pass

    def _read_lock_owner(self, lock_file: Path) -> dict:
        try:
            return json.loads(lock_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return json.loads(lock_file.read_text(encoding="utf-8"))

    def _acquire_daemon_lock(self) -> bool:
        lock_file = self.daemon_lock_file
        token = f"{os.getpid()}:{time.time_ns()}"
        for _ in range(2):
            try:
                owner = self._read_lock_owner(lock_file)
            except FileNotFoundError:
                if self._publish_lock(lock_file, token):
                    self.daemon_lock_token = token
                    return True
                continue
            except (json.JSONDecodeError, OSError, ValueError):
                try:
                    lock_file.unlink()
                except FileNotFoundError:
                    pass
                continue
            if self._lifecycle_lock_owner_alive(int(owner.get("pid", 0))):
                return False
            try:
                lock_file.unlink()
            except FileNotFoundError:
                pass
        return False

    def _release_daemon_lock(self) -> None:
        if not self.daemon_lock_token:
            return
        try:
            owner = json.loads(self.daemon_lock_file.read_text(encoding="utf-8"))
            if owner.get("token") == self.daemon_lock_token:
                self.daemon_lock_file.unlink()
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        finally:
            self.daemon_lock_token = None

    def _acquire_lifecycle_lock(self) -> bool:
        lock_file = getattr(self, "lifecycle_lock_file", None)
        if not lock_file:
            return True
        token = f"{os.getpid()}:{time.time_ns()}"
        for _ in range(2):
            try:
                descriptor = os.open(str(lock_file), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                try:
                    owner = json.loads(lock_file.read_text(encoding="utf-8"))
                    if self._lifecycle_lock_owner_alive(int(owner.get("pid", 0))):
                        return False
                    lock_file.unlink()
                except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
                    try:
                        lock_file.unlink()
                    except FileNotFoundError:
                        pass
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump({"pid": os.getpid(), "token": token, "created_at": time.time()}, handle)
            self.lifecycle_lock_token = token
            return True
        return False

    def _release_lifecycle_lock(self) -> None:
        lock_file = getattr(self, "lifecycle_lock_file", None)
        if not lock_file or not self.lifecycle_lock_token:
            return
        try:
            owner = json.loads(lock_file.read_text(encoding="utf-8"))
            if owner.get("token") == self.lifecycle_lock_token:
                lock_file.unlink()
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        finally:
            self.lifecycle_lock_token = None

    def recover_task_pool(self, now: Optional[str] = None) -> List[str]:
        if not self.task_pool:
            return []
        self.task_pool.recover_incomplete_transitions()
        reclaimed = self.task_pool.reclaim_stale_leases(now=now)
        return [task.task_id for task in reclaimed]

    def _daily_learning_candidates(self) -> List[Any]:
        if not self.runtime_observer:
            return []
        candidates = []
        for observation in self.runtime_observer.get_recent(limit=50):
            candidate = self._data_health_learning_candidate(observation)
            if candidate is not None:
                candidates.append(candidate)
        return candidates

    def _data_health_learning_candidate(self, observation) -> Optional[Any]:
        if not observation.auto_generated or observation.source != "stock_discovery":
            return None
        state = observation.system_state if isinstance(observation.system_state, dict) else {}
        health = state.get("stock_data_health")
        degraded = state.get("degraded_sources")
        if not isinstance(health, dict) or not isinstance(degraded, dict):
            return None
        source_metrics = health.get("summary", {}).get("sources", {})
        if not isinstance(source_metrics, dict):
            return None
        evidence = []
        for source, metrics in degraded.items():
            if not isinstance(source, str) or not isinstance(metrics, dict):
                continue
            measured = source_metrics.get(source, metrics)
            if not isinstance(measured, dict):
                continue
            evidence.append({
                "source": source,
                "source_ref": f"{health.get('path', 'runtime_observation')}#{source}",
                "content": json.dumps({
                    "availability": measured.get("availability"),
                    "field_completeness": measured.get("field_completeness"),
                    "coverage": measured.get("coverage"),
                    "consistency": measured.get("consistency"),
                }, ensure_ascii=False, sort_keys=True),
                "confidence": 0.95,
                "author": "stock_data_benchmark",
                "source_location": health.get("path", "runtime_observation"),
                "metadata": {
                    "source_tier": "technical_primary",
                    "publisher": source,
                    "upstream_identity": source,
                    "independence_group": source,
                    "directness": "primary",
                    "retrieval_method": "runtime_benchmark",
                    "cross_validation_source": "internal",
                    "observation_id": observation.obs_id,
                },
            })
        if len(evidence) < 2:
            return None
        fingerprint = f"stock_data_health_learning:{observation.signature or observation.obs_id}"
        learning = {
            "why_learn": "Independent runtime measurements show multiple data sources below production thresholds.",
            "learning_objective": "Establish the measured failure boundaries and permitted offline fallback roles for degraded data sources.",
            "required_evidence": ["two independent degraded source measurements"],
            "mastery_criteria": ["Record each source metric, failure boundary, and verification result in the governed learning outcome."],
        }
        candidate = DiscoveryCandidate(
            fingerprint=fingerprint,
            title="学习多源数据退化的运行边界",
            description=observation.description,
            reason=learning["why_learn"],
            objective=learning["learning_objective"],
            completion_criteria=learning["mastery_criteria"][0],
            verification_method="Reinspect the recorded benchmark path and compare each source metric with its production threshold.",
            priority="medium",
            task_type="reasoning",
            severity="high",
            candidate_source="stock_data_health",
            metadata={"learning": learning},
        )
        return candidate, evidence

    def run_daily_learning(self, run_date: Optional[str] = None) -> Dict[str, Any]:
        date = run_date or datetime.now().date().isoformat()
        if not self.daily_learning:
            return {
                "date": date,
                "mode": "none",
                "outcome": "NO_VALID_LEARNING_TARGET",
                "reason": "daily_learning_unavailable",
                "no_side_effects": True,
            }
        return self.daily_learning.run(date)

    def _refresh_shenwen_daily_cost(self, run_date: Optional[str] = None) -> Dict[str, Any]:
        date = run_date or datetime.now().date().isoformat()
        health_calls = self.state.get("shenwen_daily_health", {}).get(date, {}).get("calls", [])
        health_total = 0.0
        health_successful = 0
        for call in health_calls:
            if not isinstance(call, dict) or not call.get("success"):
                continue
            cost = call.get("cost", {})
            amount = cost.get("total_usd", 0) if isinstance(cost, dict) else 0
            if isinstance(amount, (int, float)):
                health_total += amount
                health_successful += 1

        task_total = 0.0
        task_successful = 0
        task_call_count = 0
        for task in self.task_pool.list_tasks(limit=10000):
            traces = task.outputs.get("model_execution", []) if isinstance(task.outputs, dict) else []
            for trace in traces:
                if not isinstance(trace, dict):
                    continue
                if trace.get("provider") != "shenwen":
                    continue
                if not str(trace.get("at", "")).startswith(date):
                    continue
                task_call_count += 1
                if trace.get("api_result") != "success":
                    continue
                cost = trace.get("cost", {})
                amount = cost.get("total_usd", 0) if isinstance(cost, dict) else 0
                if isinstance(amount, (int, float)):
                    task_total += amount
                    task_successful += 1

        summary = {
            "currency": "USD",
            "total_usd": round(health_total + task_total, 12),
            "successful_calls": health_successful + task_successful,
            "total_calls": len(health_calls) + task_call_count,
            "health_call_count": health_successful,
            "task_call_count": task_call_count,
            "updated_at": datetime.now().isoformat(),
        }
        self.state.setdefault("shenwen_daily_cost", {})[date] = summary
        return summary

    def _run_shenwen_daily_health(self, run_date: Optional[str] = None) -> Dict[str, Any]:
        date = run_date or datetime.now().date().isoformat()
        records = self.state.setdefault("shenwen_daily_health", {})
        if date in records:
            return {"date": date, "executed": False, "record": records[date]}

        calls = []
        for task_type, model in (
            ("strategic", "gpt-5.6-terra"),
            ("execution", "gpt-5.4-mini"),
        ):
            try:
                response = self.miner_pool.chat(
                    task_type=task_type,
                    messages=[{"role": "user", "content": "Return OK."}],
                    system_prompt="Daily provider health check. Return only OK.",
                    max_retries=1,
                    max_tokens=8,
                )
            except Exception as error:
                response = {"success": False, "error": str(error)}
            calls.append({
                "task_type": task_type,
                "expected_model": model,
                "success": bool(response.get("success")),
                "provider": str(response.get("provider", "")),
                "model": str(response.get("model", "")),
                "usage": dict(response.get("usage", {})),
                "cost": dict(response.get("cost", {})),
                "latency_ms": response.get("latency_ms", 0),
                "attempts": list(response.get("attempts", [])),
                "error": str(response.get("error", "")),
                "at": datetime.now().isoformat(),
            })

        record = {"date": date, "calls": calls, "completed_at": datetime.now().isoformat()}
        records[date] = record
        self._refresh_shenwen_daily_cost(date)
        self._save_state()
        return {"date": date, "executed": True, "record": record}

    def _task_production_policy(self) -> Dict[str, bool]:
        pending_tasks = len(self.task_pool.list_tasks(status="pending", limit=10000)) if self.task_pool else 0
        high_priority_tasks = sum(
            len(self.task_pool.list_tasks(status="pending", priority=priority, limit=10000))
            for priority in ("critical", "high")
        ) if self.task_pool else 0
        backlog_protected = pending_tasks >= 20
        return {
            "backlog_protected": backlog_protected,
            "file_scanner": not backlog_protected,
            "observer": not backlog_protected,
            # Discovery is an observation responsibility, not execution
            # throughput.  A LOCAL backlog must not suppress the bounded,
            # date-idempotent ModelWorkDiscovery window.
            "discovery": True,
            "task_creator": not backlog_protected,
            "priority_producers": True,
            "low_value_production": not backlog_protected,
            "daily_learning": True,
            "dependency_recovery": True,
            "pending_tasks": pending_tasks,
            "high_priority_tasks": high_priority_tasks,
        }

    def _run_task_lifecycle(self) -> Dict[str, Any]:
        if not self._acquire_lifecycle_lock():
            return {"skipped": True, "reason": "lifecycle_locked"}
        try:
            return self._run_task_lifecycle_unlocked()
        finally:
            self._release_lifecycle_lock()

    def _run_task_lifecycle_unlocked(self) -> Dict[str, Any]:
        """
        运行一轮完整任务生命周期：
        事件监听 → Observer发现 → 依赖检查 → Researcher研究 → Validator验证 → Archivist归档 → Guardian判决 → 经验沉积 → 墓地清理
        """
        result = {
            "events_processed": 0,
            "new_tasks": 0,
            "fragment_scanned": 0,
            "fragment_new": 0,
            "fragment_tasks": 0,
            "mine_seed_commits": 0,
            "mine_seed_tasks": 0,
            "blocked_unblocked": 0,
            "stale_leases_reclaimed": 0,
            "researched": 0,
            "validated": 0,
            "archived": 0,
            "judged": 0,
            "experiences_deposited": 0,
            "experience_deposition_failures": 0,
            "graveyarded": 0,
            "discovery": None,
            "discovery_tasks": 0,
            "model_pipeline": {},
            "daily_learning": None,
            "production_policy": {},
        }
        production_policy = self._task_production_policy()
        result["production_policy"] = production_policy

        try:
            recovered = self.recover_task_pool()
            result["stale_leases_reclaimed"] = len(recovered)
        except Exception as e:
            self._log_error("task_pool_recovery", str(e))

        try:
            result["daily_learning"] = self.run_daily_learning()
        except Exception as e:
            self._log_error("daily_learning", str(e))

        try:
            if self.mine_seed_scanner:
                ms_result = self.mine_seed_scanner.scan_and_create_tasks(
                    self.task_pool,
                    max_tasks=1,
                    allowed_priorities=(
                        None if production_policy["low_value_production"] else {"critical", "high"}
                    ),
                )
                result["mine_seed_commits"] = ms_result.get("new_commits", 0)
                result["mine_seed_tasks"] = ms_result.get("tasks_created", 0)
        except Exception as e:
            self._log_error("mine_seed_scanner", str(e))

        try:
            if self.file_scanner:
                scan_result = self.file_scanner.scan_and_create(
                    max_new=2,
                    allowed_priorities=None if production_policy["file_scanner"] else {"critical", "high"},
                )
                result["fragment_scanned"] = scan_result.get("scanned", 0)
                result["fragment_new"] = scan_result.get("new_files", 0)
                result["fragment_tasks"] = scan_result.get("tasks_created", 0)
        except Exception as e:
            self._log_error("file_scanner", str(e))

        if self.event_listener:
            try:
                evt_result = self.event_listener.scan_and_process()
                result["events_processed"] = len(evt_result.get("processed", []))
            except Exception as e:
                self._log_error("event_listener", str(e))

        try:
            new_tasks = self.observer.observe_and_create(
                max_new=2,
                allowed_priorities=None if production_policy["observer"] else {"critical", "high"},
            )
            result["new_tasks"] = len(new_tasks)
        except Exception as e:
            self._log_error("observer", str(e))

        try:
            if self.discovery_mode and self.obs_to_task_converter:
                allowed_priorities = (
                    None if production_policy["discovery"] else {"critical", "high"}
                )
                result["model_work_discovery"] = self.model_work_discovery.discover_daily(
                    allowed_priorities=allowed_priorities,
                )
                result["discovery"] = result["model_work_discovery"].get(
                    "discovery",
                    {"status": "not_run", "reason": "already_discovered_today"},
                )
                conversion = self.obs_to_task_converter.convert(
                    allowed_priorities=allowed_priorities,
                )
                result["model_work_admission"] = (
                    self.model_work_discovery.record_admission(conversion)
                )
                result["discovery_tasks"] = conversion.get("tasks_created", 0)
        except Exception as e:
            self._log_error("discovery_mode", str(e))

        try:
            unblocked = self.task_pool.unblock_ready_dependencies()
            result["blocked_unblocked"] = len(unblocked)
        except Exception as e:
            self._log_error("blocked_check", str(e))

        try:
            for _ in range(2):
                task = self.researcher.pick_up_task(priority="any")
                if not task:
                    break
                try:
                    if task.depends_on and not self.task_pool.check_depends_satisfied(task):
                        self.task_pool.block_task(
                            task.task_id,
                            reason=f"依赖未满足: {task.depends_on}",
                            actor="lifecycle",
                        )
                        continue
                    self.researcher.research_task(task)
                    result["researched"] += 1
                except Exception as e:
                    self.task_pool.fail_task(
                        task.task_id,
                        str(e),
                        actor="researcher",
                        failure_type="retryable",
                    )
                    self._log_error("researcher_task", str(e), task.task_id)
        except Exception as e:
            self._log_error("researcher", str(e))
        try:
            review_tasks = self.task_pool.list_tasks(status="review", limit=3)
            for task in review_tasks:
                self.validator.validate_task(task)
                result["validated"] += 1
        except Exception as e:
            self._log_error("validator", str(e))

        try:
            approved_tasks = self.task_pool.list_tasks(status="approved", limit=5)
            for task in approved_tasks:
                if not task.guardian_decision:
                    self.guardian.judge(task)
                    result["judged"] += 1
        except Exception as e:
            self._log_error("guardian", str(e))

        try:
            approved_tasks = self.task_pool.list_tasks(status="approved", limit=5)
            for task in approved_tasks:
                if not self.archivist.archive_task(task):
                    continue
                result["archived"] += 1
                self._deposit_archived_experience(task, result)
                if self.skill_generator:
                    try:
                        skill = self.skill_generator.generate_skill_from_task(task)
                        if skill:
                            if "skills_generated" not in result:
                                result["skills_generated"] = 0
                            result["skills_generated"] += 1
                    except Exception as e:
                        self._log_error("skill_generation", str(e))
        except Exception as e:
            self._log_error("archivist", str(e))

        try:
            result["daily_growth"] = self.daily_growth.build()
        except Exception as e:
            self._log_error("daily_growth", str(e))

        try:
            buried = self.task_pool.check_graveyard()
            result["graveyarded"] = len(buried)
        except Exception as e:
            self._log_error("graveyard", str(e))

        try:
            all_tasks = self.task_pool.list_tasks(limit=100, sort_by="reference_count")
            for task in all_tasks[:20]:
                self.task_pool.check_heat_upgrade(task)
        except Exception:
            pass

        try:
            if self.task_creator:
                creator_result = self.task_creator.scan_and_create(
                    max_new=2,
                    allowed_priorities=None if production_policy["task_creator"] else {"critical", "high"},
                )
                result["task_creator_tasks"] = len(creator_result.get("tasks_created", []))
                result["task_creator_summary"] = creator_result.get("scan_summary", "")
        except Exception as e:
            self._log_error("task_creator", str(e))

        result["model_pipeline"] = self._model_pipeline_metrics()
        return result

    def _deposit_archived_experience(self, task, result: Dict[str, Any]) -> None:
        """Deposit one archived task and make any retention failure observable."""
        if not self.experience_deposition:
            return
        try:
            exp = self.experience_deposition.deposit_from_task(
                task, lexicon=self.lexicon
            )
            if exp:
                result["experiences_deposited"] += 1
        except Exception as exc:
            result["experience_deposition_failures"] += 1
            self._log_error("experience_deposition", str(exc), task.task_id)

    def _run_autonomous_loop(self, max_depth: int = 20) -> Dict[str, Any]:
        lifecycle = self._run_task_lifecycle()
        if lifecycle.get("skipped"):
            return {
                "iterations": 0,
                "max_depth_reached": max_depth,
                "tasks_executed": 0,
                "tasks_blocked": 0,
                "tasks_failed": 0,
                "events_emitted": 0,
                "depth_distribution": {},
                "stop_reason": lifecycle["reason"],
                "delegated_to": "task_lifecycle",
            }
        return {
            "iterations": 1,
            "max_depth_reached": max_depth,
            "tasks_executed": lifecycle.get("researched", 0),
            "tasks_blocked": 0,
            "tasks_failed": 0,
            "events_emitted": 0,
            "depth_distribution": {"lifecycle_round": 1},
            "stop_reason": "delegated_to_task_lifecycle",
            "delegated_to": "task_lifecycle",
            "lifecycle": lifecycle,
        }

    def _execute_task_with_worker(self, task) -> Dict[str, Any]:
        return {
            "status": "blocked",
            "reason": "superseded_by_task_lifecycle",
            "task_id": task.task_id,
            "delegated_to": "task_lifecycle",
        }

    def _record_system_observations(self) -> int:
        """
        在主循环末尾收集当前系统状态，生成 Observation 记录。

        这是 RO（Runtime Observer）的核心职责：
        不是判断，而是客观记录当前系统状态。
        由后续的 Observation → Task 规则引擎决定是否生成 Task。
        """
        if not self.runtime_observer:
            return 0

        obs_count = 0
        task_pool_stats = self.task_pool.get_stats() if self.task_pool else {}
        by_status = task_pool_stats.get("by_status", {})

        review_count = by_status.get("review", 0)
        pending_count = by_status.get("pending", 0)
        active_count = by_status.get("active", 0)
        blocked_count = by_status.get("blocked", 0)
        total = task_pool_stats.get("total", 0)

        # === 瓶颈类 Observation ===
        if review_count >= 5 or (review_count > 0 and active_count == 0 and pending_count == 0):
            self.runtime_observer.record(
                description=f"Review 队列积压 {review_count} 个任务，Runtime 流水线在 Validator 阶段阻塞。"
                           f"当前 pending={pending_count}, active={active_count}。",
                system_state={
                    "review": review_count,
                    "pending": pending_count,
                    "active": active_count,
                    "blocked": blocked_count,
                    "total": total,
                },
                severity="critical" if review_count >= 10 else "high",
                source="daemon_loop",
                category="bottleneck",
            )
            obs_count += 1

        # === 词库缺口 Observation ===
        lex_stats = self.lexicon.get_stats()
        gap_categories = [
            cat for cat, cnt in lex_stats.get("categories", {}).items()
            if cnt < 5
        ]
        if len(gap_categories) >= 3:
            concepts = lex_stats.get("total_concepts", 0)
            # 统计待分类概念数
            uncategorized = 0
            try:
                lexicon_path = self.base_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
                if lexicon_path.exists():
                    lex_data = json.load(open(lexicon_path, "r", encoding="utf-8"))
                    concepts_map = lex_data.get("concepts", {})
                    uncategorized = sum(
                        1 for c in concepts_map.values()
                        if isinstance(c, dict) and c.get("category") == "待分类"
                    )
            except Exception:
                pass

            self.runtime_observer.record(
                description=f"词库存在 {len(gap_categories)} 个稀缺分类（< 5 个概念），"
                           f"另有 {uncategorized} 个概念待分类。",
                system_state={
                    "gap_categories": gap_categories,
                    "total_concepts": concepts,
                    "uncategorized": uncategorized,
                    "all_categories": lex_stats.get("categories", {}),
                },
                severity="medium",
                source="daemon_loop",
                category="gap",
            )
            obs_count += 1

        # === 碎片积压 Observation ===
        if self.fragment_index:
            fi_stats = self.fragment_index.get_stats()
            fragment_statuses = fi_stats.get("by_status", {})
            pending_scan = fragment_statuses.get("pending_scan", 0)
            archaeologized = fragment_statuses.get("archaeologized", 0)
            if pending_scan > 500:
                self.runtime_observer.record(
                    description=f"碎片索引积压 {pending_scan} 个未考古文件，已考古 {archaeologized} 个。",
                    system_state={
                        "total": fi_stats.get("total", 0),
                        "pending_scan": pending_scan,
                        "archaeologized": archaeologized,
                    },
                    severity="medium",
                    source="daemon_loop",
                    category="gap",
                )
                obs_count += 1

        # === 跨智能体学习未激活 ===
        last_mine_seed = self.state.get("last_mine_seed_scan", "never")
        if last_mine_seed == "never":
            self.runtime_observer.record(
                description="mine-seed 扫描器从未执行，跨智能体学习通道关闭。",
                system_state={
                    "last_mine_seed_scan": last_mine_seed,
                    "mine_seed_path": str(self.mine_seed_path) if self.mine_seed_path else None,
                },
                severity="medium",
                source="daemon_loop",
                category="gap",
            )
            obs_count += 1

        # === 近期错误 Observation ===
        errors = self.state.get("errors", [])
        recent_errors = []
        now = datetime.now()
        for e in errors:
            try:
                t = datetime.fromisoformat(e.get("time", "").replace("Z", ""))
                if (now - t).total_seconds() < 86400:
                    recent_errors.append({
                        "module": e.get("module", "?"),
                        "error": e.get("error", "?")[:60],
                    })
            except Exception:
                pass

        if len(recent_errors) > 3:
            self.runtime_observer.record(
                description=f"近24小时出现 {len(recent_errors)} 个系统错误。",
                system_state={
                    "recent_error_count": len(recent_errors),
                    "error_samples": [
                        f"{e['module']}: {e['error']}" for e in recent_errors[:5]
                    ],
                },
                severity="high",
                source="daemon_loop",
                category="anomaly",
            )
            obs_count += 1

        # === 磁盘空间 Observation ===
        import shutil
        try:
            usage = shutil.disk_usage(str(self.base_dir))
            free_pct = usage.free / usage.total * 100
            free_gb = usage.free / (1024 ** 3)
            if free_pct < 15:
                self.runtime_observer.record(
                    description=f"磁盘剩余空间不足：{free_pct:.1f}% ({free_gb:.1f}GB）。",
                    system_state={
                        "disk_free_pct": round(free_pct, 1),
                        "disk_free_gb": round(free_gb, 1),
                    },
                    severity="high",
                    source="daemon_loop",
                    category="health",
                )
                obs_count += 1
        except Exception:
            pass

        # === 计划任务未执行 Observation ===
        # 通过检查 checkup_history 来判断
        checkup_file = self.base_dir / "ops" / "logs" / "checkup_history.jsonl"
        if checkup_file.exists():
            try:
                lines = checkup_file.read_text(encoding="utf-8").strip().split("\n")
                if lines:
                    last_checkup = json.loads(lines[-1])
                    last_time = last_checkup.get("timestamp", "")
                    if last_time:
                        last_dt = datetime.fromisoformat(last_time)
                        hours_since = (now - last_dt).total_seconds() / 3600
                        if hours_since > 25:
                            self.runtime_observer.record(
                                description=f"计划任务超过 {hours_since:.0f} 小时未执行，自动巡检可能中断。",
                                system_state={
                                    "task_never_run": False,
                                    "last_checkup": last_time,
                                    "hours_since": round(hours_since, 1),
                                },
                                severity="medium",
                                source="daemon_loop",
                                category="improvement",
                            )
                            obs_count += 1
            except Exception:
                pass

        return obs_count

    def export_artifacts_and_sync(
        self,
        decision: Dict,
        action_results: List[Dict],
        total_concepts_added: int,
        total_indexed: int,
    ) -> Dict[str, Any]:
        """导出考古产物并同步到 mine-seed 仓库"""
        result = {"exported": False, "synced": False, "details": {}}

        if not self.exporter or not self.syncer:
            result["error"] = "exporter_or_syncer_not_initialized"
            return result

        try:
            lex_data = self.lexicon.to_dict() if hasattr(self.lexicon, 'to_dict') else {
                "concepts": {c["name"]: c for c in self.lexicon.list_concepts(limit=10000)},
                "categories": {cat: self.lexicon._categories.get(cat, []) for cat in self.lexicon.list_categories()},
                "version": "auto_export",
                "exported_at": datetime.now().isoformat(),
            }
        except Exception as e:
            self._log_error("export_lexicon", str(e))
            lex_data = {"error": str(e)}

        try:
            mem_entries = self.memory_index.search(limit=5000)
            mem_data = {
                "total": len(mem_entries),
                "entries": mem_entries,
                "exported_at": datetime.now().isoformat(),
            }
        except Exception as e:
            self._log_error("export_memory", str(e))
            mem_data = {"error": str(e)}

        eco_stats = None
        if self.eco_parser:
            try:
                eco_stats = self.eco_parser.get_layer_stats()
            except Exception:
                eco_stats = None

        slice_results = {}
        if self.slice_clusterer:
            try:
                slice_results["overview"] = self.slice_clusterer.get_overview()
            except Exception:
                pass

        today = datetime.now().strftime("%Y-%m-%d")
        actions_list = [a.get("type") for a in decision.get("actions", [])]
        summary_text = (
            f"- 行动: {', '.join(actions_list)}\n"
            f"- 新增概念: {total_concepts_added}\n"
            f"- 新增索引: {total_indexed}\n"
            f"- 词库总量: {len(self.lexicon.list_concepts(limit=10000))}\n"
            f"- 记忆索引总量: {self.memory_index.get_stats().get('total', 0)}\n"
        )

        try:
            export_result = self.exporter.export_all(
                lexicon_data=lex_data,
                memory_index_data=mem_data,
                daemon_state=self.state,
                daily_summary=summary_text,
                eco_stats=eco_stats,
                slice_results=slice_results,
            )
            result["exported"] = True
            result["details"]["export"] = export_result
        except Exception as e:
            self._log_error("export_all", str(e))
            result["details"]["export_error"] = str(e)
            return result

        # 注意：不再直接调用 syncer.sync() — 所有同步决策统一由 Repository Curator 做出
        # Curator 在主循环末尾被唤醒，对所有产物进行评分、去重、分类后再同步
        result["synced"] = False  # Curator 将在后续独立处理
        result["details"]["sync"] = {"note": "deferred_to_curator"}

        return result

    def write_daily_summary(
        self,
        decision: Dict,
        action_results: List[Dict],
        total_concepts_added: int,
        total_indexed: int,
    ) -> str:
        today = datetime.now().strftime("%Y-%m-%d")

        actions_summary = []
        for i, action in enumerate(decision.get("actions", [])):
            atype = action.get("type", "unknown")
            reason = action.get("reason", "")
            result = action_results[i] if i < len(action_results) else {}

            if atype == "eco_mining":
                layer_name = action.get("layer_name", "")
                mined = result.get("mined", 0)
                patterns = result.get("patterns_found", 0)
                concepts = result.get("concept_candidates", [])
                indexed = result.get("indexed", 0)
                actions_summary.append(
                    f"eco挖矿[{layer_name}]: 挖了 {mined} 条，发现 {patterns} 种模式，索引 {indexed} 条，新概念候选 {len(concepts)} 个"
                )
            elif atype == "slice_mining":
                mode_name = action.get("mode_name", "")
                actions_summary.append(f"切片考古[{mode_name}]: 完成分析")
            elif atype == "disk_scan":
                targets = action.get("targets", [])
                actions_summary.append(
                    f"磁盘扫描: 扫了 {len(targets)} 个路径，新索引 {result.get('new_indexed', 0)} 个文件"
                )
            elif atype == "lexicon_gap":
                cats = action.get("categories", [])
                actions_summary.append(
                    f"词库缺口: {len(cats)} 个分类待补充，本轮新增 {total_concepts_added} 个概念"
                )
            elif atype == "no_new_discovery":
                actions_summary.append("今日无新增发现，但现有证据未改变结论")
            else:
                actions_summary.append(f"{atype}: {reason}")

        lex_stats = self.lexicon.get_stats()
        mem_stats = self.memory_index.get_stats()

        mining_progress = self.state.get("mining_progress", {})
        eco_prog = mining_progress.get("eco_layer", {})
        eco_summary_lines = []
        for layer, prog in eco_prog.items():
            offset = prog.get("offset", 0)
            eco_summary_lines.append(f"  - {layer}: 已挖 {offset} 条")

        summary_content = (
            f"日期: {today}\n"
            f"运行时间: {datetime.now().strftime('%H:%M:%S')}\n\n"
            f"【今日行动】\n"
            + "\n".join("- " + a for a in actions_summary)
            + f"\n\n【词库状态】\n"
            f"- 概念总数: {lex_stats.get('total_concepts', 0)}\n"
            f"- 分类总数: {lex_stats.get('total_categories', 0)}\n"
            f"- 本轮新增概念: {total_concepts_added}\n\n"
            f"【记忆索引状态】\n"
            f"- 总条目数: {mem_stats.get('total', 0)}\n"
            f"- 类型分布: {json.dumps(mem_stats.get('by_type', {}), ensure_ascii=False)}\n"
            f"- 本轮新增索引: {total_indexed}\n\n"
        )

        if eco_summary_lines:
            summary_content += "【eco_layer 挖矿进度】\n" + "\n".join(eco_summary_lines) + "\n\n"

        errors = self.state.get("errors", [])
        if errors:
            today_errors = [e for e in errors if e.get("time", "").startswith(today)]
            if today_errors:
                summary_content += f"【今日错误记录】\n- 错误数: {len(today_errors)}\n"
                for e in today_errors[:5]:
                    summary_content += f"  - {e['module']}: {e['error'][:50]}\n"
                summary_content += "\n"

        if hasattr(self, 'heartbeat'):
            hb_status = self.heartbeat.get_status()
            summary_content += "【系统存活状态】\n"
            summary_content += f"- 心跳状态: {hb_status.get('status', 'unknown')}\n"
            summary_content += f"- 累计心跳: {hb_status.get('beat_count', 0)} 次\n"
            summary_content += f"- 死亡次数: {hb_status.get('death_count', 0)} 次\n"
            summary_content += f"- 当前存活: {hb_status.get('current_uptime_seconds', 0)}s\n"
            summary_content += "\n"

        if hasattr(self, 'self_healing'):
            healing_stats = self.self_healing.get_healing_stats()
            if healing_stats.get('total_healing_events', 0) > 0:
                summary_content += "【自我修复记录】\n"
                summary_content += f"- 修复事件: {healing_stats.get('total_healing_events', 0)} 次\n"
                summary_content += f"- 成功率: {healing_stats.get('success_rate', 0)*100:.1f}%\n"
                by_type = healing_stats.get('by_issue_type', {})
                if by_type:
                    top_types = sorted(by_type.items(), key=lambda x: -x[1])[:3]
                    summary_content += f"- 主要类型: {', '.join(f'{k}({v})' for k, v in top_types)}\n"
                summary_content += "\n"

        summary_id = self.memory_index.add(
            title=f"运行周期摘要 - {today}",
            content=summary_content,
            memory_type="cycle_summary",
            category="系统运行记录",
            source="ace_daemon",
            tags=["daemon", "cycle", today],
        )

        daily_record = {
            "date": today,
            "summary_id": summary_id,
            "summary_kind": "cycle_summary",
            "actions": [a.get("type") for a in decision.get("actions", [])],
            "concepts_added": total_concepts_added,
            "files_indexed": total_indexed,
            "ran_at": datetime.now().isoformat(),
        }

        if "daily_summaries" not in self.state:
            self.state["daily_summaries"] = []
        self.state["daily_summaries"].insert(0, daily_record)
        self.state["daily_summaries"] = self.state["daily_summaries"][:90]

        self.state["last_run"] = datetime.now().isoformat()
        self.state["last_lexicon_count"] = lex_stats.get("total_concepts", 0)
        self.state["last_memory_count"] = mem_stats.get("total", 0)

        return summary_id

    def run_daemon(self, interval_seconds: int = 300, max_iterations: int = 0,
                   force: bool = False, dry_run: bool = False) -> Dict[str, Any]:
        """
        守护模式：持续运行，不只是跑一次。

        为什么叫守护模式？
        - 系统自己醒着，不用别人叫
        - 周期性跳心跳，证明自己活着
        - 发现问题自己修
        - 没事干的时候也不死，只是休息

        参数：
        - interval_seconds: 每轮之间的间隔（默认5分钟）
        - max_iterations: 最大轮数（0=无限）
        - force: 每轮都强制运行
        - dry_run: 只看决策不执行
        """
        if not self._acquire_daemon_lock():
            return {
                "iterations": 0,
                "total_tasks_executed": 0,
                "uptime": 0,
                "stop_reason": "daemon_locked",
                "healing_stats": self.self_healing.get_healing_stats(),
                "final_health": self.self_healing.diagnose(self.base_dir)["health_score"],
            }

        print("=" * 60)
        print(f"ACE 守护模式启动 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"间隔: {interval_seconds}秒 | 最大轮数: {'无限' if max_iterations == 0 else max_iterations}")
        print("=" * 60)
        print()

        iteration = 0
        total_tasks_executed = 0
        stop_reason = ""
        self._recover_stale_cycle()
        self.run_id = uuid.uuid4().hex
        handlers = self._install_shutdown_handlers()

        try:
            self.heartbeat.mark_starting(pid=os.getpid(), run_id=self.run_id)
            self._checkpoint_startup()
            self.heartbeat.beat(reason="startup")
            print(f"心跳已启动。当前存活: {self.heartbeat.get_uptime_string()}")
            print()

            while True:
                if self.shutdown_event.is_set():
                    stop_reason = self.shutdown_reason or "shutdown_requested"
                    break

                iteration += 1
                if max_iterations > 0 and iteration > max_iterations:
                    stop_reason = "reached_max_iterations"
                    break

                print("-" * 60)
                print(f"第 {iteration} 轮 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                print("-" * 60)

                self._begin_cycle_progress()
                stage_started = self._start_cycle_stage("heartbeat")
                self.heartbeat.beat(reason="regular")
                self._complete_cycle_stage("heartbeat", stage_started)

                diagnosis = self.self_healing.diagnose(self.base_dir)
                health = diagnosis["health_score"]
                print(f"健康度: {health}/100 | 问题: {diagnosis['issue_count']}个")

                if diagnosis["issue_count"] > 0 and health < 80:
                    print(f"检测到问题，尝试自我修复...")
                    heal_result = self.self_healing.heal(self.base_dir)
                    print(f"  修复: {heal_result['fixed']}个成功, {heal_result['failed']}个失败")
                    if heal_result["fixed"] > 0:
                        self.heartbeat.beat(reason="recovery")

                if self.shutdown_event.is_set():
                    stop_reason = self.shutdown_reason or "shutdown_requested"
                    break

                print()
                stage_started = self._start_cycle_stage("model_health")
                try:
                    health_result = self._run_shenwen_daily_health()
                    if health_result.get("executed"):
                        successful = sum(
                            1 for call in health_result["record"]["calls"] if call["success"]
                        )
                        print(f"神隐每日健康调用: {successful}/2 成功")
                except Exception as e:
                    self._log_error("shenwen_daily_health", str(e))
                self._complete_cycle_stage("model_health", stage_started)

                try:
                    result = self.run_once(
                        force=force,
                        dry_run=dry_run,
                        _preserve_cycle_progress=True,
                    )
                    self._refresh_shenwen_daily_cost()
                    self._save_state()
                    tasks_done = result.get("auto_result", {}).get("tasks_executed", 0)
                    total_tasks_executed += tasks_done
                    print(f"本轮执行任务: {tasks_done} | 累计: {total_tasks_executed}")
                    if self._backup_due():
                        stage_started = self._start_cycle_stage("backup")
                        backup_result = self.run_periodic_backup()
                        print(f"运行时备份完成: {backup_result['path']}")
                        self._complete_cycle_stage("backup", stage_started)
                except Exception as e:
                    print(f"本轮执行出错: {e}")
                    traceback.print_exc()
                    self._log_error(f"daemon_iteration_{iteration}", str(e))
                    stop_reason = f"fatal_error: {e}"
                    break

                print()
                print(f"存活时长: {self.heartbeat.get_uptime_string()}")
                print(f"下一轮: {interval_seconds}秒后")
                print()

                if self.shutdown_event.wait(interval_seconds):
                    stop_reason = self.shutdown_reason or "shutdown_requested"
                    break

        except KeyboardInterrupt:
            self.request_shutdown("keyboard_interrupt")
            stop_reason = self.shutdown_reason

        except Exception as e:
            print(f"守护模式异常退出: {e}")
            traceback.print_exc()
            stop_reason = f"fatal_error: {e}"

        finally:
            stop_reason = stop_reason or self.shutdown_reason or "shutdown_requested"
            try:
                self._checkpoint_shutdown(stop_reason)
            finally:
                self._release_lifecycle_lock()
                self._release_daemon_lock()
                self._restore_shutdown_handlers(handlers)

        final_status = self.heartbeat.get_status()
        healing_stats = self.self_healing.get_healing_stats()
        try:
            final_health = self.self_healing.diagnose(self.base_dir)["health_score"]
        except Exception:
            final_health = None

        print()
        print("=" * 60)
        print("守护模式结束")
        print("=" * 60)
        print(f"  运行轮数: {iteration - 1}")
        print(f"  执行任务: {total_tasks_executed}")
        print(f"  存活时长: {self.heartbeat.get_uptime_string()}")
        print(f"  修复事件: {healing_stats['total_healing_events']}次")
        print(f"  修复成功率: {healing_stats['success_rate']*100:.1f}%")
        print(f"  结束原因: {stop_reason}")
        print()

        return {
            "iterations": iteration - 1,
            "total_tasks_executed": total_tasks_executed,
            "uptime": final_status.get("current_uptime_seconds", 0),
            "stop_reason": stop_reason,
            "healing_stats": healing_stats,
            "final_health": final_health,
        }

    def run_once(
        self,
        force: bool = False,
        dry_run: bool = False,
        _preserve_cycle_progress: bool = False,
    ) -> Dict[str, Any]:
        if not _preserve_cycle_progress:
            self._begin_cycle_progress()
        production_policy = self._task_production_policy()
        allowed_priorities = (
            None if production_policy["low_value_production"] else {"critical", "high"}
        )
        print("=" * 60)
        print(f"ACE 自动考古主循环 v2 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 60)
        print()

        status = self.get_status()
        print("【当前状态】")
        print(f"  词库概念: {status['lexicon']['concepts']} 个")
        print(f"  词库分类: {status['lexicon']['categories']} 个")
        print(f"  记忆索引: {status['memory_index']['total']} 条")
        print(f"  上次运行: {status['last_run'] or '首次运行'}")
        if status.get("eco_parser"):
            eco = status["eco_parser"]
            print(f"  eco_layer: 已加载")
            for layer, stats in eco.get("layers", {}).items():
                print(f"    - {stats['name']}: {stats['count']} 条")
        if status.get("slice_clusterer"):
            sc = status["slice_clusterer"]
            print(f"  Ω切片: {sc['total_slices']} 个")
        if status.get("export_sync"):
            es = status["export_sync"]
            print(f"  mine-seed: 已连接 → {es['target_dir']}")
        if status.get("task_pool"):
            tp = status["task_pool"]
            print(f"  任务池: {tp.get('total', 0)} 个任务")
            bs = tp.get("by_status", {})
            if bs:
                print(f"    pending={bs.get('pending',0)} active={bs.get('active',0)} blocked={bs.get('blocked',0)} review={bs.get('review',0)} approved={bs.get('approved',0)} archived={bs.get('archived',0)}")
        if status.get("knowledge"):
            kp = status["knowledge"]
            print(f"  经验库: {kp.get('total', 0)} 条")
            kb = kp.get("by_type", {})
            if kb:
                ax = kb.get("axiom", 0)
                cn = kb.get("constraint", 0)
                pt = kb.get("pattern", 0)
                ls = kb.get("lesson", 0)
                print(f"    axiom={ax} constraint={cn} pattern={pt} lesson={ls}")
        if status.get("fragment_index"):
            fi = status["fragment_index"]
            print(f"  碎片索引: {fi.get('total', 0)} 个文件")
            bs = fi.get("by_status", {})
            if bs:
                parts = [f"{k}={v}" for k, v in sorted(bs.items())]
                print(f"    {' '.join(parts)}")
        if status.get("local_archaeologist"):
            la = status["local_archaeologist"]
            print(f"  本地考古: 已吸收{la.get('absorbed_files_count', 0)}文件, 已知结构{la.get('known_structures_count', 0)}个")
        if status.get("web_scout"):
            ws = status["web_scout"]
            print(f"  外网学习: 今日{ws.get('today_sources_count', 0)}源, 累计发现{ws.get('total_findings', 0)}个")
        if status.get("skills"):
            sk = status["skills"]
            print(f"  技能库: {sk.get('total_skills', 0)}个技能, 类型分布: {json.dumps(sk.get('by_type', {}), ensure_ascii=False)}")
        print()

        # === 第零步：技能注册（每日扫描技能目录，更新清单） ===
        stage_started = self._start_cycle_stage("skill_registration")
        if self.skill_generator and not dry_run:
            print("【技能注册中...】")
            try:
                archived_tasks = self.task_pool.list_tasks(status="archived", limit=100)
                skill_result = self.skill_generator.analyze_archived_tasks(archived_tasks)
                print(f"  分析归档任务: {skill_result['tasks_analyzed']}个")
                print(f"  发现模式: {skill_result['patterns_found']}种")
                print(f"  新生成技能: {len(skill_result['new_skills'])}个")
                if skill_result['new_skills']:
                    print(f"  新技能: {', '.join(skill_result['new_skills'])}")
            except Exception as e:
                self._log_error("skill_registration", str(e))
                print(f"  [错误] {e}")
            print()
        self._complete_cycle_stage("skill_registration", stage_started)

        # === 第一步：本地考古（优先，检查家里抽屉） ===
        stage_started = self._start_cycle_stage("local_archaeology")
        local_arch_result = None
        if self.local_archaeologist and not dry_run:
            print("【本地考古中...】")
            try:
                local_arch_result = self.local_archaeologist.scan(
                    allowed_priorities=allowed_priorities,
                )
                status_l = local_arch_result["status"]
                if status_l == "found_new_structures":
                    print(f"  扫描文件: {local_arch_result['files_scanned']} 个")
                    print(f"  发现新结构: {local_arch_result['new_structures_count']} 个")
                    if local_arch_result.get("new_structures"):
                        print(f"  前5个: {', '.join(local_arch_result['new_structures'][:5])}")
                    print(f"  创建任务: {local_arch_result['tasks_created']} 个")
                elif status_l == "all_absorbed":
                    print(f"  全部已吸收，无新增")
                elif status_l == "no_new_structures":
                    print(f"  扫描了 {local_arch_result['files_scanned']} 个文件，未发现未吸收结构")
                else:
                    print(f"  状态: {status_l}")
            except Exception as e:
                self._log_error("local_archaeologist", str(e))
                print(f"  [错误] {e}")
            print()
        elif dry_run:
            print("【本地考古: DRY-RUN 模式，不执行】")
            print()

        # === 第二步：外网学习（补充，不是默认行为） ===
        web_scout_result = None
        if self.web_scout and not dry_run:
            # 只有本地考古没有重要发现时才做外网学习
            has_local_findings = (
                local_arch_result and
                local_arch_result.get("status") == "found_new_structures" and
                local_arch_result.get("new_structures_count", 0) > 5
            )

            if not has_local_findings:
                print("【外网学习中...】")
                try:
                    web_scout_result = self.web_scout.scout(
                        allowed_priorities=allowed_priorities,
                    )
                    ws_status = web_scout_result["status"]
                    if ws_status == "success":
                        print(f"  来源: {web_scout_result['source']}")
                        print(f"  新发现: {web_scout_result['new_count']} 个")
                        print(f"  入库概念: {len(web_scout_result['concepts_added'])} 个")
                        print(f"  创建任务: {web_scout_result['tasks_created']} 个")
                    elif ws_status == "no_new_findings":
                        print(f"  今日外网无新增")
                    elif ws_status == "budget_exhausted":
                        print(f"  今日外网预算已用完")
                    elif ws_status == "error":
                        print(f"  错误: {web_scout_result.get('error', '')}")
                    else:
                        print(f"  状态: {ws_status}")
                except Exception as e:
                    self._log_error("web_scout", str(e))
                    print(f"  [错误] {e}")
                print()
            else:
                print("【外网学习: 跳过（本地已有足够新发现）】")
                print()
        elif dry_run:
            print("【外网学习: DRY-RUN 模式，不执行】")
            print()

        self._complete_cycle_stage("local_archaeology", stage_started)

        stage_started = self._start_cycle_stage("decision")
        print("【决策中...】")
        decision = self.decide_today_task()
        print(f"  决策日期: {decision['date']}")
        print(f"  可扫描路径: {decision['scan_targets_count']} 个")
        print(f"  计划行动: {len(decision['actions'])} 项")
        for action in decision["actions"]:
            print(f"    - {action['type']}: {action.get('reason', '')}")
        print()
        self._complete_cycle_stage("decision", stage_started)

        if dry_run:
            print("【DRY-RUN 模式，不执行】")
            return {"decision": decision, "executed": False}

        stage_started = self._start_cycle_stage("actions")
        action_results = []
        total_concepts_added = 0
        total_indexed = 0

        for action in decision["actions"]:
            atype = action["type"]
            result = {}

            try:
                if atype == "eco_mining":
                    layer_name = action.get("layer_name", "")
                    print(f"【执行: eco挖矿 - {layer_name}】")
                    result = self.execute_eco_mining(action)
                    print(f"  挖掘条目: {result.get('mined', 0)}")
                    print(f"  发现模式: {result.get('patterns_found', 0)}")
                    print(f"  索引条目: {result.get('indexed', 0)}")
                    candidates = result.get("concept_candidates", [])
                    if candidates:
                        print(f"  概念候选: {len(candidates)} 个")
                        for c in candidates[:5]:
                            print(f"    - {c['name'] if isinstance(c, dict) else c}")
                    total_indexed += result.get("indexed", 0)

                    if result.get("mined", 0) > 0:
                        print("  (从eco内容中提炼新概念...)")
                        eco_added = self._mine_concepts_from_eco(result, action)
                        total_concepts_added += eco_added
                        print(f"  eco新概念入词库: {eco_added} 个")

                elif atype == "slice_mining":
                    mode_name = action.get("mode_name", "")
                    print(f"【执行: 切片考古 - {mode_name}】")
                    result = self.execute_slice_mining(action)
                    if "error" in result:
                        print(f"  错误: {result['error']}")
                    else:
                        print("  分析完成")

                elif atype == "disk_scan":
                    print("【执行: 磁盘扫描】")
                    targets = action.get("targets", [])
                    result = self.execute_disk_scan(targets)
                    print(f"  扫描了 {result['scanned']} 个路径")
                    print(f"  新发现: {result.get('new_files', 0)} 个有趣文件")
                    print(f"  新索引: {result.get('new_indexed', 0)} 个文件")
                    total_indexed += result.get("new_indexed", 0)

                elif atype == "lexicon_gap":
                    print("【执行: 词库缺口补全】")
                    cats = action.get("categories", [])
                    print(f"  待补充分类: {', '.join(cats)}")
                    print("  (提取新概念中...)")
                    added = self.extract_new_concepts()
                    total_concepts_added += added
                    result = {"added": added}
                    print(f"  新增概念: {added} 个")

                elif atype == "no_new_discovery":
                    if force:
                        print("【执行: 无新发现，但强制运行】")
                        added = self.extract_new_concepts()
                        total_concepts_added += added
                        result = {"forced": True, "added": added}
                    else:
                        print("【执行: 今日无新增发现】")
                        result = {"forced": False}
                    print("  今日无新增发现，但现有证据未改变结论。")

                else:
                    print(f"【执行: {atype}】")
                    result = {"type": atype, "status": "unknown_action"}

            except Exception as e:
                self._log_error(f"action:{atype}", str(e), traceback.format_exc()[-500:])
                print(f"  [错误] {e}")
                result = {"error": str(e)}

            action_results.append(result)
            print()

        if total_indexed > 0 and total_concepts_added == 0:
            print("【自动概念提取】")
            added = self.extract_new_concepts()
            total_concepts_added += added
            print(f"  从新索引内容中提取新概念: {added} 个")
            print()

        self._complete_cycle_stage("actions", stage_started)

        stage_started = self._start_cycle_stage("task_lifecycle")
        print("【任务生命周期运转】")
        lifecycle_result = {}
        if self.task_pool and self.observer:
            lifecycle_result = self._run_task_lifecycle()
            print(f"  事件处理: {lifecycle_result.get('events_processed', 0)} 个")
            ms_commits = lifecycle_result.get('mine_seed_commits', 0)
            ms_tasks = lifecycle_result.get('mine_seed_tasks', 0)
            if ms_commits > 0:
                print(f"  矿场扫描: 发现{ms_commits}个新commit，建任务{ms_tasks}个")
            frag_scanned = lifecycle_result.get('fragment_scanned', 0)
            frag_new = lifecycle_result.get('fragment_new', 0)
            frag_tasks = lifecycle_result.get('fragment_tasks', 0)
            if frag_scanned > 0:
                print(f"  碎片扫描: 扫描{frag_scanned}个文件，新发现{frag_new}个，建任务{frag_tasks}个")
            print(f"  TaskCreator发现: {lifecycle_result.get('task_creator_tasks', 0)} 个新任务")
            if lifecycle_result.get('task_creator_summary'):
                print(f"  {lifecycle_result['task_creator_summary']}")
            print(f"  Observer发现: {lifecycle_result.get('new_tasks', 0)} 个新任务")
            print(f"  阻塞解除: {lifecycle_result.get('blocked_unblocked', 0)} 个")
            print(f"  Researcher完成: {lifecycle_result.get('researched', 0)} 个任务")
            print(f"  Validator验证: {lifecycle_result.get('validated', 0)} 个任务")
            print(f"  Archivist归档: {lifecycle_result.get('archived', 0)} 个任务")
            print(f"  经验沉积: {lifecycle_result.get('experiences_deposited', 0)} 条")
            print(f"  Guardian判决: {lifecycle_result.get('judged', 0)} 个任务")
            print(f"  墓地清理: {lifecycle_result.get('graveyarded', 0)} 个任务")
            pool_stats = self.task_pool.get_stats()
            print(f"  任务池总数: {pool_stats['total']} 个")
        else:
            print("  (任务生命周期系统未初始化)")
        self.state.setdefault("cycle_progress", {})["model_pipeline"] = lifecycle_result.get(
            "model_pipeline", {}
        )
        work_allocation = AutonomousWorkAllocation(self.task_pool).report(lifecycle_result)
        lifecycle_result["work_allocation"] = work_allocation
        self.state.setdefault("cycle_progress", {})["work_allocation"] = work_allocation
        self._save_state()
        print()
        self._complete_cycle_stage("task_lifecycle", stage_started)

        auto_result = {
            "delegated_to": "task_lifecycle",
            "tasks_executed": lifecycle_result.get("researched", 0),
            "stop_reason": "run_once_uses_task_lifecycle",
        }

        stage_started = self._start_cycle_stage("archive_analysis")
        print("【自动归档分析】")
        archived = self.auto_archive_files()
        print(f"  分析了 {len(archived)} 条记忆的归档位置")
        if archived:
            cat_counts = defaultdict(int)
            for a in archived:
                cat_counts[a["archive_category"]] += 1
            for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
                print(f"    {cat}: {count} 条")
        print()
        self._complete_cycle_stage("archive_analysis", stage_started)

        stage_started = self._start_cycle_stage("daily_summary")
        print("【写入今日考古摘要】")
        summary_id = self.write_daily_summary(decision, action_results, total_concepts_added, total_indexed)
        print(f"  摘要ID: {summary_id}")
        print()
        self._complete_cycle_stage("daily_summary", stage_started)

        # === RO：记录系统 Observation → 自动生成 Task ===
        stage_started = self._start_cycle_stage("runtime_observations")
        print("【RO 观察记录与自动转换】")
        obs_recorded = 0
        obs_converted = 0
        try:
            obs_recorded = self._record_system_observations()
            print(f"  记录 Observations: {obs_recorded} 条")
        except Exception as e:
            self._log_error("runtime_observer", str(e))
            print(f"  [错误] {e}")

        observation_policy = self._task_production_policy()
        observation_priorities = (
            None if observation_policy["observer"] else {"critical", "high"}
        )
        if obs_recorded > 0 and self.obs_to_task_converter:
            try:
                convert_result = self.obs_to_task_converter.convert(
                    allowed_priorities=observation_priorities,
                )
                obs_converted = convert_result.get("tasks_created", 0)
                obs_checked = convert_result.get("observations_checked", 0)
                obs_matched = convert_result.get("rules_matched", 0)
                obs_skipped = convert_result.get("skipped", 0)
                print(f"  检查 Observations: {obs_checked} 条")
                print(f"  规则匹配: {obs_matched} 条")
                print(f"  生成 Tasks: {obs_converted} 条")
                print(f"  跳过（已处理）: {obs_skipped} 条")
                if convert_result.get("details"):
                    for d in convert_result["details"]:
                        if "task_id" in d:
                            print(f"    → {d['task_id']} ({d['task_priority']}) {d['task_title'][:50]}")
            except Exception as e:
                self._log_error("obs_to_task_converter", str(e))
                print(f"  [错误] {e}")
        elif self.obs_to_task_converter:
            try:
                convert_result = self.obs_to_task_converter.convert(
                    allowed_priorities=observation_priorities,
                )
                obs_converted = convert_result.get("tasks_created", 0)
                print(f"  无新增 Observation，转换跳过")
                print(f"  历史 Observations 检查: {convert_result.get('observations_checked', 0)} 条，生成 Tasks: {obs_converted} 条")
            except Exception as e:
                self._log_error("obs_to_task_converter", str(e))
        print()
        self._complete_cycle_stage("runtime_observations", stage_started)

        self._save_state()

        # === Curator：Today's Work Finished — 馆长唤醒 ===
        stage_started = self._start_cycle_stage("curator")
        print("【Repository Curator：今日产物整理】")
        curator_heartbeat = self._start_stage_heartbeat("curator")
        try:
            if self.repository_curator:
                curator_result = self.repository_curator.wakeup(triggered_by="daemon_loop")
                scanned = curator_result.get("artifacts_scanned", 0)
                summary = curator_result.get("summary", "无")
                print(f"  扫描产物: {scanned} 个")
                print(f"  决策摘要: {summary}")
                if curator_result.get("duplicates_found"):
                    print(f"  发现重复: {len(curator_result['duplicates_found'])} 个")
                if curator_result.get("split_candidates"):
                    print(f"  需拆分: {len(curator_result['split_candidates'])} 个")
            else:
                print("  [跳过] Curator 未初始化")
        except Exception as e:
            self._log_error("repository_curator", str(e))
            print(f"  [错误] {e}")
        finally:
            self._stop_stage_heartbeat(curator_heartbeat)
            self.heartbeat.status.pop("current_stage", None)
            self.heartbeat.status.pop("stage_heartbeat_at", None)
            self.heartbeat.beat(reason="stage:curator_complete")
        print()
        self._complete_cycle_stage("curator", stage_started)

        if self.repository_sync_enabled and self.core_syncer:
            try:
                cs_result = self.core_syncer.sync()
                if cs_result.get("skipped"):
                    pass
                elif cs_result.get("pushed"):
                    print(f"  ace-core推送: 成功 ({cs_result.get('commit_hash', '')}) — {cs_result.get('changed_files', [])[:3]}")
                elif cs_result.get("error") == "no_changes":
                    pass
                elif cs_result.get("error"):
                    print(f"  ace-core: {cs_result['error']}")
            except Exception as e:
                self._log_error("core_syncer", str(e))

        stage_started = self._start_cycle_stage("repository_sync")
        print("【导出考古产物到 mine-seed】")
        sync_result = {}
        if self.repository_sync_enabled and self.exporter and self.syncer:
            try:
                sync_result = self.export_artifacts_and_sync(
                    decision, action_results, total_concepts_added, total_indexed
                )
                if sync_result.get("exported"):
                    export_detail = sync_result.get("details", {}).get("export", {})
                    print(f"  导出文件: {export_detail.get('total_files', 0)} 个")
                sync_detail = sync_result.get("details", {}).get("sync", {})
                if sync_detail.get("pushed"):
                    print(f"  Git推送: 成功 ({sync_detail.get('commit_hash', '')})")
                elif sync_detail.get("committed"):
                    print(f"  Git提交: 成功 (推送失败)")
                elif sync_detail.get("error") == "no_changes":
                    print("  Git状态: 无变更，跳过提交")
                else:
                    err = sync_detail.get("error", "unknown")
                    print(f"  Git状态: {err}")
            except Exception as e:
                self._log_error("export_sync_main", str(e))
                print(f"  [错误] {e}")
        else:
            print("  (未找到 mine-seed 仓库，跳过导出同步)")
        print()
        self._complete_cycle_stage("repository_sync", stage_started)

        self._finalize_cycle("completed", "cycle_complete")

        print("=" * 60)
        print("主循环结束")
        print("=" * 60)

        return {
            "decision": decision,
            "action_results": action_results,
            "auto_result": auto_result,
            "lifecycle": lifecycle_result,
            "concepts_added": total_concepts_added,
            "summary_id": summary_id,
            "archived": len(archived),
            "total_indexed": total_indexed,
            "sync": sync_result,
        }


def main():
    base_dir = Path(__file__).parent
    config = load_config(base_dir)

    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv

    daemon = AceDaemon(base_dir, config)
    result = daemon.run_once(force=force, dry_run=dry_run)

    if not dry_run:
        has_action = any(
            a.get("type") != "no_new_discovery"
            for a in result.get("decision", {}).get("actions", [])
        )
        if not has_action and not force:
            print()
            print("今日无新增发现，但现有证据未改变结论。")
            print()


if __name__ == "__main__":
    main()
