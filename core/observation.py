"""Runtime Observation records and state-level idempotence."""

import hashlib
import json
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
        self._load()

    def _load(self):
        if self._seq_file.exists():
            try:
                self._seq = int(self._seq_file.read_text(encoding="utf-8").strip())
            except ValueError:
                self._seq = 0
        if self.observations_file.exists():
            try:
                for line in self.observations_file.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        self._observations.append(Observation(**json.loads(line)))
                self._observations = self._observations[-200:]
            except (OSError, json.JSONDecodeError, TypeError):
                self._observations = []
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
        self.index_file.write_text(
            json.dumps({"signatures": self._signature_index}, ensure_ascii=False, sort_keys=True),
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
    ) -> Observation:
        signature = self._signature(description, system_state, source, category)
        existing = self._signature_index.get(signature, {})
        if existing.get("status") == "active":
            active = self._find_observation(existing.get("obs_id", ""))
            if active is not None:
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
        return [
            observation
            for observation in reversed(self._observations)
            if observation.task_generated is None
        ][:limit]

    def mark_consumed(self, obs_id: str, task_id: str):
        observation = self._find_observation(obs_id)
        if observation is None:
            return
        observation.task_generated = task_id
        with self.observations_file.open("w", encoding="utf-8") as stream:
            for stored in self._observations:
                stream.write(json.dumps(stored.to_dict(), ensure_ascii=False) + "\n")

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
