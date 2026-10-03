import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from core.local_archaeologist import LocalArchaeologist
from core.learning_return_bridge import LearningReturnBridge


def scanner_at(root):
    return LocalArchaeologist(root, SimpleNamespace(), SimpleNamespace())


def test_bounded_rotation_cooldown_and_append_only_lineage(tmp_path):
    root = tmp_path / '08_ARCHAEOLOGY'
    root.mkdir()
    for n in range(4):
        (root / f'{n}.md').write_text(f'# Candidate {n}', encoding='utf-8')
    scanner = scanner_at(tmp_path)
    scanner._budget['max_files_per_scan'] = 1
    assert scanner.scan(force=True)['files_scanned'] == 1
    first = dict(scanner._state['fingerprints'])
    assert scanner.scan()['files_scanned'] == 1
    assert len(scanner._state['fingerprints']) == 2
    assert scanner._state['source_last_seen']['archaeology']
    ledger = scanner.state_file.with_suffix('.lineage.jsonl')
    old = ledger.read_text(encoding='utf-8')
    scanner.scan()
    assert ledger.read_text(encoding='utf-8').startswith(old)
    assert len(scanner._state['known_structures']) == 0
    for record in scanner._state['fingerprints'].values():
        record['seen_at'] = (datetime.now() - timedelta(days=31)).isoformat()
    assert any(c['fingerprint'] in first for c in scanner._collect_candidate_files())


def test_source_priority_and_fairness(tmp_path):
    scanner = scanner_at(tmp_path)
    items = [{'source_class': s, 'priority': p, 'path': str(n)} for s, p, n in [('archaeology', 5, 0), ('archaeology', 5, 1), ('protocol_material', 4, 2)]]
    assert scanner._fair_select(items)[0]['priority'] == 5
    scanner._state['source_last_seen']['archaeology'] = datetime.now().isoformat()
    assert scanner._fair_select(items)[0]['source_class'] == 'protocol_material'


def test_governance_candidate_never_mutates_or_protects(tmp_path):
    source = tmp_path / 'old.md'
    source.write_text('source', encoding='utf-8')
    scanner = scanner_at(tmp_path)
    candidate = scanner.governance_candidate({'path': str(source), 'fingerprint': 'sha256:x', 'intake_policy': {'cooldown_days': 30}}, pollution_score=0.9)
    assert candidate['graveyard_candidate']
    assert candidate['guardian_required']
    assert not candidate['source_mutated']
    assert not candidate['core_protection_applied']
    assert source.read_text() == 'source'


def test_candidate_propagates_policy_and_lineage(tmp_path):
    source = tmp_path / '08_ARCHAEOLOGY' / 'note.md'
    source.parent.mkdir()
    source.write_text('# Research', encoding='utf-8')
    task = SimpleNamespace(task_id='lineage', guardian_decision='experience', evidence=[], outputs={'source_file': str(source), 'fingerprint': 'sha256:x', 'intake_policy': {'retention': 'LINEAGE'}, 'lineage': {'source_ref': str(source), 'read_only': True}})
    result = LearningReturnBridge(tmp_path).materialize(task)
    card = json.loads(Path(result['card_path']).read_text(encoding='utf-8'))
    assert card['retention_policy'] == 'LINEAGE'
    assert card['source_fingerprint'] == 'sha256:x'
    assert card['lineage']['source_ref'] == str(source)
    assert not card['production_integration']


def test_old_design_is_research_not_authorization():
    note = Path(__file__).resolve().parents[1] / '08_ARCHAEOLOGY' / 'RESEARCH_RETURN_2026-ARCHAEOLOGY.md'
    text = note.read_text(encoding='utf-8')
    assert 'append-only' in text
    assert 'not verified' in text
    assert 'No production permission' in text
