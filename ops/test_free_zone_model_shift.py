import json
from core.free_zone_model_shift import FreeZoneModelShift

class Pool:
    def chat(self, **_):
        return {"success": True, "content": json.dumps({"hypotheses":["a"],"counterexamples":["b"],"evidence_gaps":["c"],"next_verification":["d"]}), "provider":"fixture", "model":"fixture", "usage":{}, "latency_ms":1, "attempts":[]}

def test_shift_consumes_one_seed_and_distills_model_material(tmp_path):
    inbox=tmp_path/'inbox'; inbox.mkdir()
    inbox.joinpath('seed.json').write_text(json.dumps({"contract_version":"ace.semantic_seed.v1","food_kind":"semantic_seed","source_ref":"x","source_snapshot_hash":"a"*64,"source_kind":"fixture","extracted_mechanism":"m","ace_symptom":"s","transfer_hypothesis":"h","counterexample_question":"q","next_verification":"v","local_evidence_refs":[],"external_evidence_refs":[],"lineage":["x"]}),encoding='utf-8')
    result=FreeZoneModelShift(tmp_path,Pool()).run_once()
    assert result['status']=='MODEL_SHIFT_RECORDED'
    assert result['receipt']['research_material']['status']=='STRUCTURED_DISTILLATION'
    assert result['production_integration'] is False
    state=json.loads((tmp_path/'model_shift_state.json').read_text(encoding='utf-8'))
    assert state['last_shift']['dual_source_status'] == 'LOCAL_BASELINE_PLUS_UNCLASSIFIED_MODEL'
    assert state['last_shift']['raw_content_retained'] is False
    assert state['last_shift']['invitation']['research_object_status'] == 'ELIGIBLE_SEED_SELECTED'

def test_shift_explains_that_no_invitation_was_sent_without_a_research_object(tmp_path):
    result=FreeZoneModelShift(tmp_path, Pool()).run_once()
    assert result['status'] == 'NO_UNCONSUMED_SEMANTIC_SEED'
    assert result['reason'] == 'NO_INBOX_SEED'
    assert result['invitation']['cloud_invitation_status'] == 'NOT_ISSUED_NO_RESEARCH_OBJECT'
    assert len(result['inbox_fingerprint']) == 64


def test_shift_fingerprint_changes_when_a_late_research_invitation_arrives(tmp_path):
    shift = FreeZoneModelShift(tmp_path, Pool())
    empty = shift.inbox_fingerprint()
    shift.inbox.mkdir(parents=True)
    shift.inbox.joinpath('late.json').write_text('{}', encoding='utf-8')
    assert shift.inbox_fingerprint() != empty

def test_daemon_waits_for_the_dedicated_free_zone_shift():
    from ace_daemon import AceDaemon
    daemon=AceDaemon.__new__(AceDaemon); daemon.config={"runtime":{"free_zone_model_shift":{"enabled":True}}}; daemon.state={}; daemon.miner_pool=None
    assert daemon._run_free_zone_model_shift_if_due()['status'] in {'WAITING_FOR_DEDICATED_SHIFT','NO_EXISTING_MINER_POOL'}
