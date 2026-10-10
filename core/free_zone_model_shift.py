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
                foundry = self._foundry_seed(state)
                if foundry is not None:
                    _, foundry_seed = foundry
                    if foundry_seed["seed_hash"] not in done:
                        selected = (None, foundry_seed)
        if not selected:
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
        foundry_from = seed.get("foundry_model") if isinstance(seed, dict) else None
        receipt=FreeZoneModelResearch(self.pool).run(seed,max_tokens=max_tokens)
        outcome='INCONCLUSIVE' if receipt['outcome']=='MODEL_TURN_RECORDED' else 'FAIL'
        exp_id='EXP-MODEL-'+seed['seed_hash'][:16].upper()
        if path is not None:
            source_ref, is_derived, is_foundry = str(path), False, False
        elif foundry_from:
            source_ref, is_derived, is_foundry = f"foundry:{foundry_from}", False, True
        else:
            source_ref, is_derived, is_foundry = f"derived:{derived_from}", True, False
        record=self.sandbox.record_experiment(experiment_id=exp_id,hypothesis=seed['transfer_hypothesis'],method=seed['next_verification'],outcome=outcome,evidence={'seed_hash':seed['seed_hash'],'model_receipt':receipt},metadata={'source_kind':'semantic_seed_model_turn','source_ref':source_ref,'free_zone_only':True,'automatic_model_call':True,'derived_seed': is_derived,'foundry_seed': is_foundry})
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

    FOUNDRY_DAILY_CAP = 1
    FOUNDRY_MAX_TOKENS = 512

    def _foundry_context(self, limit: int = 2) -> list:
        """Recent sandbox distillations as inspiration, newest first.

        Any status qualifies as context (even FAIL failures teach), unlike
        derivation which needs substantive open questions. Sandbox-grade
        records only - never internal tasks.
        """
        dist_dir = self.root / "distillations"
        if not dist_dir.is_dir():
            return []
        found = []
        for path in sorted(dist_dir.glob("*.json"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(record, dict):
                continue
            text = str(record.get("pattern") or record.get("reason") or "").strip()
            if not text:
                continue
            found.append({
                "experiment_id": str(record.get("experiment_id") or path.stem),
                "outcome": str(record.get("outcome") or "?"),
                "status": str(record.get("status") or "?"),
                "text": text[:400],
                "file": f"distillations/{path.name}",
            })
            if len(found) >= limit:
                break
        return found

    def _foundry_seed(self, state) -> tuple | None:
        """Paid thinks, free labors: one strategic seed per day, last resort.

        Only when the inbox is empty and derivation declined. The strategic
        model reads recent sandbox distillations and proposes one fresh
        research seed; the free twins execute it. Bounded by a daily cap
        recorded in shift state; every failure mode returns None so the
        shift degrades to NO_SEED instead of manufacturing work.
        """
        from datetime import date as _date

        spend = state.get("foundry_spend")
        if not isinstance(spend, dict):
            spend = {}
        today = str(_date.today())
        if spend.get("date") == today and int(spend.get("count", 0) or 0) >= self.FOUNDRY_DAILY_CAP:
            return None
        context = self._foundry_context()
        if not context:
            return None
        brief = "\n".join(
            f"- [{item['experiment_id']}/{item['outcome']}] {item['text']}"
            for item in context
        )
        prompt = (
            "You are seeding a sandbox research loop. Nothing you write reaches "
            "production, creates tasks, or changes systems. Propose ONE research "
            "seed as strict JSON with exactly these keys: transfer_hypothesis, "
            "counterexample_question, next_verification. Each a single concrete "
            "sentence about autonomous-system self-observation. No markdown, no "
            "extra keys.\nRecent sandbox findings:\n" + brief
        )
        try:
            response = self.pool.chat(
                task_type="strategic",
                messages=[{"role": "user", "content": prompt}],
                system_prompt="Sandbox seed foundry only. Output strict JSON.",
                max_retries=2,
                max_tokens=self.FOUNDRY_MAX_TOKENS,
                data_boundary={"data_class": "PUBLIC"},
            )
        except Exception:
            return None
        try:
            same_day = spend.get("date") == today
            spend["date"] = today
            spend["count"] = (int(spend.get("count", 0) or 0) + 1) if same_day else 1
            state["foundry_spend"] = spend
        except Exception:
            pass
        if not isinstance(response, dict) or not response.get("success"):
            return None
        content = str(response.get("content") or "").strip()
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(lines[1:-1] if len(lines) > 2 else [])
        try:
            proposed = json.loads(content.strip())
        except (ValueError, json.JSONDecodeError, AttributeError):
            return None
        if not isinstance(proposed, dict):
            return None
        try:
            snapshot_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
            seed = normalize_semantic_seed({
                "contract_version": "ace.semantic_seed.v1",
                "source_ref": f"foundry:{response.get('provider', '?')}:{response.get('model', '?')}:{today}",
                "source_snapshot_hash": snapshot_hash,
                "source_kind": "paid_foundry_seed",
                "extracted_mechanism": str(proposed.get("transfer_hypothesis", "")).strip()[:600],
                "ace_symptom": "evening loop out of seeds; foundry asked for one",
                "transfer_hypothesis": str(proposed.get("transfer_hypothesis", "")).strip(),
                "counterexample_question": str(proposed.get("counterexample_question", "")).strip(),
                "next_verification": str(proposed.get("next_verification", "")).strip(),
                "local_evidence_refs": [item["file"] for item in context],
                "external_evidence_refs": [],
                "lineage": ["shift-foundry", today],
            })
        except (ValueError, SemanticSeedError):
            return None
        seed["foundry_model"] = f"{response.get('provider', '')}:{response.get('model', '')}"
        return seed["foundry_model"], seed

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
