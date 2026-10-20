import sys
from pathlib import Path
from types import SimpleNamespace
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.worker_router import WorkerRouter, WorkerCapability
from core.opencode_worker import OPENCODE_MODELS

MODELS = [OPENCODE_MODELS['heavy_agent'], OPENCODE_MODELS['creative_candidate']]
def router():
    return WorkerRouter([WorkerCapability(str(i), 'opencode-cli', frozenset({'structured_readonly'}), metadata={'model': m}) for i,m in enumerate(MODELS)])
GOOD = {'success': True, 'changed': False, 'parsed_result': {'result': 'ok', 'evidence': ['verified probe']}}
class Fake:
    def __init__(self, responses): self.responses = iter(responses); self.calls = []
    def run(self, **kwargs): self.calls.append(kwargs); return next(self.responses).copy()
def verify(r): return isinstance(r.get('parsed_result'), dict) and r.get('changed') is False
@pytest.mark.parametrize('bad', [{'success':False,'raw_output':'provider.quota status 429'}, {'success':False,'error':'timeout'}, {'success':True,'parsed_result':None,'changed':False}])
def test_fallback(bad):
    w=Fake([bad, GOOD]); r=router().run('structured_readonly', w, verify=verify)
    assert r['success'] and r['fallback_used'] and r['model']==MODELS[1]
    assert [c['model_order'] for c in w.calls]==[[MODELS[0]],[MODELS[1]]]
    assert len(r['router_attempts'])==2

def test_all_failed():
    r=router().run('structured_readonly', Fake([{'success':False}, {'success':False}]), verify=verify)
    assert not r['success'] and len(r['router_attempts'])==2

def test_workspace_change_stops():
    w=Fake([{'success':False,'changed':True}, GOOD]); r=router().run('structured_readonly',w,verify=verify)
    assert not r['success'] and len(w.calls)==1

def test_empty_evidence_is_rejected():
    w=Fake([{'success':True,'changed':False,'parsed_result':{'result':'ok','evidence':[]}}, GOOD])
    r=router().run('structured_readonly', w, verify=lambda x: bool(x.get('parsed_result',{}).get('evidence')) and x.get('changed') is False)
    assert r['success'] and r['fallback_used'] and len(w.calls)==2

def test_task_execution_delegates_to_the_task_lifecycle(tmp_path):
    """Superseded: worker execution inside _execute_task_with_worker.

    Commit a2d7fac retired this path -- task execution now goes through the
    task lifecycle, and the worker's remaining production caller is the
    delivery stage (_delivery_worker_runner, covered by
    ops/test_delivery_worker_router_wiring.py). These two cases used to
    assert a governance envelope and a worker receipt here; both described a
    contract the daemon no longer has. Reinstating them would resurrect a
    retired path, so they now pin the delegation that replaced it.
    """
    from ace_daemon import AceDaemon
    d=AceDaemon.__new__(AceDaemon)
    d.worker_router=router(); d.opencode_worker=Fake([]); d.opencode_workspace=tmp_path
    t=SimpleNamespace(task_id='probe', outputs={}, hypothesis='probe',
                      add_evidence=lambda *a,**k:None)
    result=d._execute_task_with_worker(t)
    assert result['reason']=='superseded_by_task_lifecycle'
    assert result['delegated_to']=='task_lifecycle'
    assert not d.opencode_worker.calls, 'a retired path must never call a model'
