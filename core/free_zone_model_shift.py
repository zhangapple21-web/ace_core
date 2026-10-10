"""One daily, bounded Free Zone model-research shift; never a second scheduler."""
from __future__ import annotations
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .free_research_sandbox import FreeResearchSandbox
from .free_zone_model_research import FreeZoneModelResearch
from .semantic_seed import normalize_semantic_seed, SemanticSeedError

def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class FreeZoneModelShift:
    def __init__(self, root: str | Path, miner_pool: Any):
        self.root=Path(root); self.pool=miner_pool; self.inbox=self.root/'inbox'; self.state_path=self.root/'model_shift_state.json'; self.sandbox=FreeResearchSandbox(self.root)
    def run_once(self, *, max_tokens: int=1024) -> dict:
        state=self._read(self.state_path); done=set(state.get('completed_seed_hashes',[]))
        selected=None; valid_count=0; invalid_count=0
        for path in sorted(self.inbox.glob('*.json')):
            try: seed=normalize_semantic_seed(json.loads(path.read_text(encoding='utf-8'))); valid_count += 1
            except (OSError, ValueError, json.JSONDecodeError, SemanticSeedError): invalid_count += 1; continue
            if seed['seed_hash'] not in done: selected=(path,seed); break
        if not selected:
            reason = 'NO_INBOX_SEED' if valid_count == 0 and invalid_count == 0 else ('ALL_SEEDS_INVALID' if valid_count == 0 else 'ALL_ELIGIBLE_SEEDS_ALREADY_CONSUMED')
            used_sources = state.get('derived_distillation_ids', [])
            derived = self._derive_seed_from_distillation(done, used_sources)
            if derived is not None:
                _, derived_seed = derived
                selected = (None, derived_seed)
            else:
                return {
                    'status':'NO_UNCONSUMED_SEMANTIC_SEED',
                    'reason': reason,
                    'inbox_fingerprint': self.inbox_fingerprint(),
                    'invitation': {
                        'research_object_status': 'NO_ELIGIBLE_SEED',
                        'miner_pool_invitation_status': 'NOT_DISPATCHED',
                        'valid_seed_count': valid_count,
                        'invalid_seed_count': invalid_count,
                        'cloud_invitation_status': 'NOT_ISSUED_NO_RESEARCH_OBJECT',
                        'fallback': 'WAIT_FOR_EVIDENCE_BACKED_SEED',
                    },
                    'production_integration':False,
                }
        path,seed=selected
        derived_from = seed.get("derived_from_distillation") if isinstance(seed, dict) else None
        receipt=FreeZoneModelResearch(self.pool).run(seed,max_tokens=max_tokens)
        outcome='INCONCLUSIVE' if receipt['outcome']=='MODEL_TURN_RECORDED' else 'FAIL'
        exp_id='EXP-MODEL-'+seed['seed_hash'][:16].upper()
        record=self.sandbox.record_experiment(experiment_id=exp_id,hypothesis=seed['transfer_hypothesis'],method=seed['next_verification'],outcome=outcome,evidence={'seed_hash':seed['seed_hash'],'model_receipt':receipt},metadata={'source_kind':'semantic_seed_model_turn','source_ref':str(path) if path is not None else f"derived:{derived_from}",'free_zone_only':True,'automatic_model_call':True,'derived_seed': path is None})
        distilled=self.sandbox.distill(exp_id)
        state['completed_seed_hashes']=sorted(done|{seed['seed_hash']}); state['last_receipt_hash']=record['record_hash']
        if derived_from:
            used_sources = list(state.get('derived_distillation_ids', []))
            if derived_from not in used_sources:
                used_sources.append(derived_from)
            state['derived_distillation_ids'] = used_sources
        state['last_shift'] = {
            'outcome': receipt['outcome'],
            'dual_source_status': receipt['dual_source_status'],
            'model_execution_realm': receipt['model_execution_realm'],
            'provider': receipt['provider'],
            'seed_hash': seed['seed_hash'],
            'record_hash': record['record_hash'],
            'recorded_at': receipt['recorded_at'],
            'invitation': receipt['invitation'],
            'raw_content_retained': False,
            'production_integration': False,
        }
        self._write(self.state_path,state)
        return {'status':'MODEL_SHIFT_RECORDED','seed_hash':seed['seed_hash'],'experiment_id':exp_id,'receipt':receipt,'distillation_status':distilled.get('status'),'invitation':receipt['invitation'],'inbox_fingerprint':self.inbox_fingerprint(),'production_integration':False}
    def _distillation_from_derived_turn(self, exp_dir: Path, dist_id: str) -> bool:
        """True when this distillation came out of a derived-seed turn.

        Derived turns may not seed further turns, or the loop feeds on its
        own exhaust forever. Resolved via the experiment record, which the
        shift marks at record time.
        """
        try:
            candidates = [exp_dir / f"{dist_id}.json"]
            for name in exp_dir.glob("*.json"):
                if name.stem.startswith(dist_id[:16]):
                    candidates.append(name)
            for candidate in candidates:
                try:
                    experiment = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if not isinstance(experiment, dict):
                    continue
                metadata = experiment.get("metadata")
                if isinstance(metadata, dict) and metadata.get("derived_seed") is True:
                    return True
        except OSError:
            pass
        return False

    def _derive_seed_from_distillation(self, done, used_distillations=()) -> Optional[tuple]:
        """Last-resort ammo: one seed from a substantive distillation.

        Only sandbox distillations (OPEN_QUESTION/INCONCLUSIVE with a real
        pattern) qualify - never internal tasks, whose contents carry a
        different data grade. Three guards against self-feeding: already-used
        sources are skipped, distillations from derived-seed turns are
        skipped, and the seed itself is consumed-hash deduped. The seed is
        provenance-marked and validated by the same normalize contract.
        Returns (dist_id, seed) or None. Ephemeral: nothing is written to
        the inbox.
        """
        from datetime import date as _date

        used = set(used_distillations or [])
        dist_dir = self.root / "distillations"
        exp_dir = self.root / "experiments"
        if not dist_dir.is_dir():
            return None
        candidates = []
        for path in dist_dir.glob("*.json"):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            if record.get("status") not in {"OPEN_QUESTION", "INCONCLUSIVE"}:
                continue
            pattern = record.get("pattern")
            if not isinstance(pattern, str) or not pattern.strip():
                continue
            dist_id = str(record.get("experiment_id") or path.stem)
            if dist_id in used:
                continue
            if self._distillation_from_derived_turn(exp_dir, dist_id):
                continue
            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue
            candidates.append((mtime, path, record))
        for _, path, record in sorted(candidates, key=lambda item: item[0], reverse=True):
            pattern = str(record.get("pattern")).strip()
            reason = str(record.get("reason") or "open_question_requires_new_observation")
            dist_id = str(record.get("experiment_id") or path.stem)
            try:
                snapshot_hash = _file_digest(path)
            except OSError:
                continue
            try:
                seed = normalize_semantic_seed({
                    "contract_version": "ace.semantic_seed.v1",
                    "source_ref": f"distillation:{dist_id}",
                    "source_snapshot_hash": snapshot_hash,
                    "source_kind": "auto_derived_distillation",
                    "extracted_mechanism": pattern[:600],
                    "ace_symptom": f"OPEN_QUESTION {dist_id} awaits new observation ({reason[:120]})",
                    "transfer_hypothesis": pattern[:600],
                    "counterexample_question": "What new observation would disprove or bound this pattern?",
                    "next_verification": f"Gather the missing observation named by {dist_id}, then re-run the turn.",
                    "local_evidence_refs": [f"distillations/{path.name}"],
                    "external_evidence_refs": [],
                    "lineage": ["shift-fallback-derivation", str(_date.today())],
                })
            except (ValueError, SemanticSeedError):
                continue
            if seed["seed_hash"] in done:
                continue
            seed["derived_from_distillation"] = dist_id
            return dist_id, seed
        return None

    def inbox_fingerprint(self) -> str:
        """Identify whether the sandbox invitation set changed without reading content."""
        entries=[]
        for path in sorted(self.inbox.glob('*.json')):
            try:
                stat=path.stat()
            except OSError:
                continue
            entries.append({'name':path.name,'size':stat.st_size,'mtime_ns':stat.st_mtime_ns})
        return hashlib.sha256(json.dumps(entries,sort_keys=True,separators=(',',':')).encode('utf-8')).hexdigest()
    @staticmethod
    def _read(path):
        try: value=json.loads(path.read_text(encoding='utf-8')); return value if isinstance(value,dict) else {}
        except (OSError,ValueError,json.JSONDecodeError): return {}
    @staticmethod
    def _write(path,value):
        # Reuse the sandbox's atomic, fsync-backed ledger writer.  A consumed
        # seed must not be lost or partially recorded on an interrupted shift.
        FreeResearchSandbox._write(path, value)
