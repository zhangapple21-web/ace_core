"""Runtime Observation records and state-level idempotence."""

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class Observation:
    obs_id: str
    description: str
    system_state: Dict[str, Any]
    severity: str
    source: str
    category: str
    related_tasks: List[str]
    task_generated: Optional[str]
    auto_generated: bool
    created_at: str
    signature: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuntimeObserver:
    def __init__(self, data_dir: str = None):
        if data_dir is None:
            base = Path(__file__).resolve().parent.parent
            data_dir = base / "06_RUNTIME" / "ace" / "data" / "observations"
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.observations_file = self.data_dir / "observations.jsonl"
        self.index_file = self.data_dir / "observation_index.json"
        self._seq_file = self.data_dir / "seq_counter.txt"
        self._observations: List[Observation] = []
        self._seq = 0
        self._signature_index: Dict[str, Dict[str, Any]] = {}
        # Rows this store could not build, most recent load last. A row that cannot
        # be parsed is one lost row, not a reason to believe the store is empty.
        self.skipped_rows: List[str] = []
        self._load()

    def _load(self):
        if self._seq_file.exists():
            try:
                self._seq = int(self._seq_file.read_text(encoding="utf-8").strip())
            except ValueError:
                self._seq = 0
        if self.observations_file.exists():
            try:
                text = self.observations_file.read_text(encoding="utf-8")
            except OSError:
                text = ""
            # One row is one row. A row that cannot be built is skipped and named,
            # because the alternative - losing the whole store to a single truncated
            # line - is how a partial problem becomes a total one: the process then
            # believes it has never seen an observation and rewrites the file from an
            # empty list.
            for number, line in enumerate(text.splitlines(), start=1):
                if not line.strip():
                    continue
                try:
                    payload = json.loads(line)
                except ValueError as error:
                    self.skipped_rows.append(
                        f"line {number}: unparseable json ({type(error).__name__})")
                    continue
                if not isinstance(payload, dict):
                    self.skipped_rows.append(f"line {number}: row is not an object")
                    continue
                # A row written before a field existed must still load. The field is
                # absent, not the row: skipping it would lose history every time the
                # schema grows, which is how a compatibility question turns into a
                # silent deletion.
                if payload.get("related_tasks") is None:
                    payload["related_tasks"] = []
                try:
                    self._observations.append(Observation(**payload))
                except TypeError as error:
                    label = str(payload.get("obs_id") or f"line {number}")
                    self.skipped_rows.append(f"{label}: {error}")
            self._observations = self._observations[-200:]
        if self.index_file.exists():
            try:
                self._signature_index = json.loads(
                    self.index_file.read_text(encoding="utf-8")
                ).get("signatures", {})
            except (OSError, json.JSONDecodeError, AttributeError):
                self._signature_index = {}

    def _save_seq(self):
        self._seq_file.write_text(str(self._seq), encoding="utf-8")

    def _save_signature_index(self):
        # Each process only knows the keys it has seen, and this file is rewritten
        # whole. Writing memory alone deleted keys another writer had added - a
        # watch's dedup key among them - which makes the same incident look like a
        # new identity on the next tick and produces a duplicate task with it.
        # Adopt the disk's keys; where both know one, keep this process's view,
        # because a status change made here is newer than the loaded snapshot.
        merged = dict(self._signature_index)
        if self.index_file.exists():
            try:
                on_disk = json.loads(
                    self.index_file.read_text(encoding="utf-8")
                ).get("signatures", {})
            except (OSError, json.JSONDecodeError, AttributeError):
                on_disk = {}
            if isinstance(on_disk, dict):
                for signature, entry in on_disk.items():
                    merged.setdefault(signature, entry)
        self._signature_index = merged
        self.index_file.write_text(
            json.dumps({"signatures": merged}, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    @staticmethod
    def _signature(
        description: str,
        system_state: Dict[str, Any],
        source: str,
        category: str,
    ) -> str:
        payload = json.dumps(
            {
                "category": category,
                "description": description,
                "source": source,
                "system_state": system_state,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _dedup_signature(
        dedup_key: Any,
        source: str,
        category: str,
    ) -> str:
        """Build an idempotence identity for observations with volatile telemetry.

        Some observations carry rolling counters or samples for diagnosis.  Those
        fields remain useful telemetry, but must not turn the same incident into
        a new Work item on every loop.  Callers opt in with an incident identity
        that changes only when the underlying incident changes.
        """
        payload = json.dumps(
            {
                "category": category,
                "dedup_key": dedup_key,
                "source": source,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _find_observation(self, obs_id: str) -> Optional[Observation]:
        for observation in reversed(self._observations):
            if observation.obs_id == obs_id:
                return observation
        return None

    def _append(self, observation: Observation):
        self._observations.append(observation)
        with self.observations_file.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(observation.to_dict(), ensure_ascii=False) + "\n")
        self._observations = self._observations[-200:]

    def _next_id(self) -> str:
        # The counter is a shared file and this value is a snapshot taken at load,
        # so a second process that minted an id since then gets handed the same
        # number twice. Two writers of this store exist, and
        # _adopt_external_appends() resolves rows by id, so a collision would mark
        # the wrong record consumed. Take the higher of memory and disk.
        if self._seq_file.exists():
            try:
                self._seq = max(
                    self._seq, int(self._seq_file.read_text(encoding="utf-8").strip())
                )
            except (OSError, ValueError):
                pass
        self._seq += 1
        self._save_seq()
        return f"OBS-{datetime.now().strftime('%Y%m%d')}-{self._seq:04d}"

    def record(
        self,
        description: str,
        system_state: Dict[str, Any],
        severity: str = "medium",
        source: str = "daemon_loop",
        category: str = "anomaly",
        auto_generated: bool = True,
        dedup_key: Optional[Any] = None,
    ) -> Observation:
        signature = (
            self._dedup_signature(dedup_key, source, category)
            if dedup_key is not None
            else self._signature(description, system_state, source, category)
        )
        existing = self._signature_index.get(signature, {})
        if existing.get("status") == "active":
            active = self._find_observation(existing.get("obs_id", ""))
            # Returning a consumed observation made this an observation of a single
            # moment that then stopped representing anything. mark_consumed() says
            # the converter read this record once; it says nothing about the world.
            # Because the converter will never look at that record again, a
            # condition that stays true froze onto its first observation forever
            # and could not re-enter the unprocessed queue - so it could neither be
            # re-reported nor recognised as recovered. Both semantic incidents ended
            # up that way: real conditions, both still true (pending_scan 7847
            # against a threshold of 500, last_mine_seed_scan still "never"),
            # carrying remediation tasks that were archived over them.
            #
            # Re-report instead. This does not create a task per cycle: the
            # converter reuses by semantic signature, and those signatures exclude
            # rolling counters (fragment_backlog encodes only whether the
            # condition holds), so a value that ticks from 7847 to 7800 refreshes
            # the evidence and reuses the same task. Recovery also becomes visible
            # again, which is what lets _reconcile_persistent_incidents close the
            # incident on real evidence rather than never.
            if active is not None and active.task_generated is None:
                return active
        observation = Observation(
            obs_id=self._next_id(),
            description=description,
            system_state=system_state,
            severity=severity,
            source=source,
            category=category,
            related_tasks=[],
            task_generated=None,
            auto_generated=auto_generated,
            created_at=datetime.now().isoformat(),
            signature=signature,
        )
        self._append(observation)
        self._signature_index[signature] = {
            "status": "active",
            "obs_id": observation.obs_id,
            "updated_at": observation.created_at,
        }
        self._save_signature_index()
        return observation

    def resolve_signature(self, signature: str) -> bool:
        entry = self._signature_index.get(signature)
        if entry is None:
            return False
        entry["status"] = "recovered"
        entry["updated_at"] = datetime.now().isoformat()
        self._save_signature_index()
        return True

    def get_recent(self, limit: int = 20) -> List[Observation]:
        return list(reversed(self._observations[-limit:]))

    def get_by_category(self, category: str, limit: int = 20) -> List[Observation]:
        return [
            observation
            for observation in reversed(self._observations)
            if observation.category == category
        ][:limit]

    def get_unprocessed(self, limit: int = 50) -> List[Observation]:
        # This queue answers "what is unconsumed", so a record another process
        # appended belongs in the answer. Without this, an escalated finding would
        # only surface whenever some unrelated consumption happened to trigger the
        # rewrite - its latency decided by activity it has nothing to do with.
        self._adopt_external_appends()
        return [
            observation
            for observation in reversed(self._observations)
            if observation.task_generated is None
        ][:limit]

    def _adopt_external_appends(self) -> None:
        """Take in rows another process appended since this one loaded the file.

        The daemon holds one RuntimeObserver for hours while the structural watches
        are separate processes appending to the same store. `_append()` opens the
        file in append mode, so their records do reach disk - and then
        `mark_consumed()` rewrote the whole file from this process's memory, which
        is a startup snapshot, deleting them without an error anywhere. The loss was
        observed directly on 2026-10-17: a SYSTEM-run watch recorded DAEMON_STOPPED
        at 14:16:33 and the file held it; at 14:17:49 the daemon's rewrite left it
        gone and no task was ever created from it.

        Merging cannot reconstruct the true interleaving of two writers, so this
        does not claim to. The disk file is the shared append log and supplies the
        order. Rows only this process knows about are deliberately not re-appended:
        a record the file no longer holds is older than the window it keeps, and
        re-appending it would promote an ancient row to the newest position.
        """
        if not self.observations_file.exists():
            return
        try:
            rows = [
                Observation(**json.loads(line))
                for line in self.observations_file.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, json.JSONDecodeError, TypeError):
            return
        if rows:
            self._observations = rows[-200:]

    def mark_consumed(self, obs_id: str, task_id: str):
        # Before the lookup, so a record this process has never seen is still
        # resolvable - and before the rewrite, so it survives to be converted.
        self._adopt_external_appends()
        observation = self._find_observation(obs_id)
        if observation is None:
            return
        observation.task_generated = task_id
        # The reverse edge was declared on the dataclass and initialised empty by
        # record(); nothing anywhere appended to it, so the store carried a field
        # that claimed a relation to work and could not represent any. Fill it
        # idempotently, and only for real tasks - PERCEPTION_ONLY is a disposition,
        # not work. The edge still lives only as long as the observation does; the
        # durable copy of the evidence is on the task side.
        if task_id and task_id != "PERCEPTION_ONLY":
            related = list(observation.related_tasks or [])
            if task_id not in related:
                related.append(task_id)
            observation.related_tasks = related
        self._rewrite_store()

    def _rewrite_store(self) -> None:
        """Write the store by moving a completed file into place.

        This used to write straight into the store with `open("w")`. A process killed
        part-way through left a truncated line behind, and the next load treated that
        line as unparseable - emptying the store, after which the rewrite that
        followed replaced two hundred good rows with nothing, silently. Writing beside
        the store and renaming means a half-finished write never becomes the store.
        The pattern is the one `core/continuity_audit.py::_atomic_write` already uses.
        """
        temporary = self.observations_file.with_name(
            f"{self.observations_file.name}.{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8") as stream:
                for stored in self._observations:
                    stream.write(json.dumps(stored.to_dict(), ensure_ascii=False) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(self.observations_file)
        finally:
            if temporary.exists():
                temporary.unlink()

    def get_stats(self) -> Dict[str, Any]:
        by_category: Dict[str, int] = {}
        by_severity: Dict[str, int] = {}
        unprocessed = 0
        for observation in self._observations:
            by_category[observation.category] = by_category.get(observation.category, 0) + 1
            by_severity[observation.severity] = by_severity.get(observation.severity, 0) + 1
            if observation.task_generated is None:
                unprocessed += 1
        return {
            "total": len(self._observations),
            "unprocessed": unprocessed,
            "by_category": by_category,
            "by_severity": by_severity,
            "last_obs_id": self._observations[-1].obs_id if self._observations else None,
        }
