import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from recovery import state_snapshot as state


class StateTests(unittest.TestCase):
    def fixture(self, root):
        source, snapshot, workspace = root / 'source', root / 'snapshot', root / 'workspace'
        for relative in ('task_pool/pending/T1.json', '09_KNOWLEDGE/index.json',
                         '06_RUNTIME/ace/data/memory/evidence/result.json',
                         '06_RUNTIME/ace/data/heartbeat.json',
                         '06_RUNTIME/ace/backups/test/data.json'):
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({'status': 'pending', 'token': '<placeholder>'}), encoding='utf-8')
        subprocess.run(['git', 'init', '-q', str(workspace)], check=True, capture_output=True)
        return source, snapshot, workspace

    def test_round_trip_counts_hashes_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, snapshot, workspace = self.fixture(Path(tmp))
            result = state.export(source, snapshot, {'private': True})
            self.assertEqual(result['counts']['files'], 3)
            self.assertEqual(result['counts']['evidence_files'], 1)
            self.assertEqual(result['excluded_files'], 2)
            restored = state.restore(snapshot, workspace)
            self.assertEqual(restored['counts'], result['counts'])
            for entry in json.loads((snapshot / state.MANIFEST).read_text())['files']:
                self.assertEqual((source / entry['path']).read_bytes(), (workspace / entry['path']).read_bytes())
            self.assertEqual(json.loads((workspace / 'task_pool/pending/T1.json').read_text())['status'], 'pending')

    def test_secret_blocks_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, snapshot, workspace = self.fixture(Path(tmp))
            (source / 'task_pool/pending/T1.json').write_text(json.dumps({'api_key': 'actual_secret_value_12345'}))
            with self.assertRaisesRegex(RuntimeError, 'credential blocked'):
                state.export(source, snapshot, {'private': True})
            self.assertFalse(snapshot.exists())

    def test_raw_html_excluded_json_evidence_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, snapshot, workspace = self.fixture(Path(tmp))
            relative = '06_RUNTIME/ace/data/public_sentiment_evidence/day/close_review/raw.html'
            html = source / relative
            html.parent.mkdir(parents=True)
            html.write_text('cookie="actual_secret_value_12345"', encoding='utf-8')
            evidence = html.with_suffix('.json')
            evidence.write_text(json.dumps({'source_hash': state.digest(html.read_bytes())}), encoding='utf-8')
            state.export(source, snapshot, {'private': True})
            manifest = json.loads((snapshot / state.MANIFEST).read_text())
            entry = next(item for item in manifest['excluded'] if item['path'] == relative)
            self.assertIn('not restorable', entry['reason'])
            self.assertFalse(entry['restorable'])
            self.assertEqual(entry['sha256'], state.digest(html.read_bytes()))
            self.assertFalse((snapshot / relative).exists())
            state.restore(snapshot, workspace)
            self.assertEqual(evidence.read_bytes(), (workspace / evidence.relative_to(source)).read_bytes())
            self.assertFalse((workspace / relative).exists())

    def test_html_elsewhere_and_sensitive_json_still_block(self):
        for relative in ('task_pool/page.html',
                         '06_RUNTIME/ace/data/public_sentiment_evidence/day/result.json'):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                source, snapshot, workspace = self.fixture(Path(tmp))
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(json.dumps({'cookie': 'actual_secret_value_12345'}), encoding='utf-8')
                original = target.read_bytes()
                with self.assertRaisesRegex(RuntimeError, 'credential blocked'):
                    state.export(source, snapshot, {'private': True})
                self.assertFalse(snapshot.exists())
                self.assertEqual(target.read_bytes(), original)

    def test_oversized_selected_or_excluded_blob_blocks(self):
        for relative in ('task_pool/large.json',
                         '06_RUNTIME/ace/data/public_sentiment_evidence/day/raw.html'):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as tmp:
                source, snapshot, workspace = self.fixture(Path(tmp))
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'x' * 129)
                with patch.object(state, 'MAX_BYTES', 128):
                    with self.assertRaisesRegex(RuntimeError, '100 MiB blocked'):
                        state.export(source, snapshot, {'private': True})
                self.assertFalse(snapshot.exists())

    def test_oversized_restore_blocks_before_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, snapshot, workspace = self.fixture(Path(tmp))
            state.export(source, snapshot, {'private': True})
            with patch.object(state, 'MAX_BYTES', 1):
                with self.assertRaisesRegex(RuntimeError, '100 MiB blocked'):
                    state.restore(snapshot, workspace)
            self.assertFalse((workspace / 'task_pool').exists())

    def test_excluded_changes_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, snapshot, workspace = self.fixture(Path(tmp))
            selected, excluded = state.inventory(source)
            changed = [dict(item) for item in excluded]
            changed[0]['sha256'] = 'changed'
            with patch.object(state, 'inventory', side_effect=[(selected, excluded), (selected, changed)]):
                with self.assertRaisesRegex(RuntimeError, 'changed between'):
                    state.export(source, snapshot, {'private': True})
            self.assertFalse(snapshot.exists())

    def test_manifest_tamper_and_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, snapshot, workspace = self.fixture(Path(tmp))
            state.export(source, snapshot, {'private': True})
            (snapshot / state.MANIFEST).write_text('{}')
            with self.assertRaisesRegex(RuntimeError, 'Manifest hash mismatch'):
                state.restore(snapshot, workspace)
            for relative in ('../escape', '/absolute', 'C:/escape', 'task_pool/../escape', 'task_pool\\escape'):
                with self.assertRaises(RuntimeError):
                    state.safe_path(workspace, relative)

    def test_source_changes_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, snapshot, workspace = self.fixture(Path(tmp))
            original = state.inventory(source)
            altered = ({}, [])
            with patch.object(state, 'inventory', side_effect=[original, altered]):
                with self.assertRaisesRegex(RuntimeError, 'changed between'):
                    state.export(source, snapshot, {'private': True})
            self.assertFalse(snapshot.exists())

    def test_untracked_conflict_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, snapshot, workspace = self.fixture(Path(tmp))
            state.export(source, snapshot, {'private': True})
            asset = workspace / 'user_asset.txt'
            asset.write_text('preserve')
            with self.assertRaisesRegex(RuntimeError, 'fresh clean'):
                state.restore(snapshot, workspace)
            self.assertEqual(asset.read_text(), 'preserve')

    def test_private_required_before_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            source, snapshot, workspace = self.fixture(Path(tmp))
            with self.assertRaisesRegex(RuntimeError, 'Private repository verification required'):
                state.export(source, snapshot, {'private': False})
            self.assertFalse(snapshot.exists())

    def test_private_failure_never_exposes_output(self):
        proc = subprocess.CompletedProcess([], 1, 'password=do-not-print', 'private error')
        with patch.object(state.subprocess, 'run', return_value=proc):
            with self.assertRaisesRegex(RuntimeError, '^Private repository verification blocked: credential or GitHub API unavailable$'):
                state.verify_private(state.STATE_URL)


if __name__ == '__main__':
    unittest.main()
