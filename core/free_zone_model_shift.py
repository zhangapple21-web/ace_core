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
        path,seed=selected; receipt=FreeZoneModelResearch(self.pool).run(seed,max_tokens=max_tokens)
        outcome='INCONCLUSIVE' if receipt['outcome']=='MODEL_TURN_RECORDED' else 'FAIL'
        exp_id='EXP-MODEL-'+seed['seed_hash'][:16].upper()
        record=self.sandbox.record_experiment(experiment_id=exp_id,hypothesis=seed['transfer_hypothesis'],method=seed['next_verification'],outcome=outcome,evidence={'seed_hash':seed['seed_hash'],'model_receipt':receipt},metadata={'source_kind':'semantic_seed_model_turn','source_ref':str(path),'free_zone_only':True,'automatic_model_call':True})
        distilled=self.sandbox.distill(exp_id)
        state['completed_seed_hashes']=sorted(done|{seed['seed_hash']}); state['last_receipt_hash']=record['record_hash']
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
