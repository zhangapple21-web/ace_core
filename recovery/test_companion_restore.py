"""Offline recovery contract tests; never clone, install or start ACE."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from recovery import restore_from_remote as restore
from recovery.test_recovery import checks, command_result


class CompanionRestoreTests(unittest.TestCase):
    def test_bridge_restore_and_failures(self):
        for failure in ('', 'pin', 'deps'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / 'relocated workspace'
                events = []

                def clone(url, ref, destination, *, result):
                    destination.mkdir(parents=True)
                    events.append(destination.name)
                    result.update(status='PASS')
                    if destination.name == 'ace_core':
                        (destination / 'recovery').mkdir()
                        (destination / 'recovery/bootstrap_report.json').write_text(json.dumps({'checks': checks()}))

                def run(cmd, cwd=None):
                    events.append(cmd)
                    if 'rev-parse' in cmd:
                        return command_result(stdout='0' * 40 if failure == 'pin' else restore.BRIDGE_COMMIT)
                    if 'pip' in cmd and failure == 'deps':
                        return command_result(1)
                    return command_result()

                argv = ['restore', '--workspace-root', str(root), '--state-url', '', '--with-bridge']
                with patch.object(restore.sys, 'argv', argv), patch.object(restore.shutil, 'which', return_value='git'), patch.object(restore, 'clone', side_effect=clone), patch.object(restore, 'run', side_effect=run), contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(restore.main(), 1 if failure else 0)
                bootstrap = next(i for i, e in enumerate(events) if isinstance(e, list) and 'recovery/bootstrap.py' in e)
                self.assertLess(bootstrap, events.index('ace-host-adapter-lab'))
                if not failure:
                    config = json.loads((root / 'ACE_MCP_CONFIG.json').read_text())['mcpServers']['ace-readonly']
                    self.assertEqual(config['args'][-1], str(root / 'ace_core'))
                    self.assertIn(str(root), config['command'])
                    receipt = json.loads((root / 'ACE_REMOTE_RESTORE_RECEIPT.json').read_text(encoding='utf-8'))
                    self.assertEqual(receipt['bridge']['host_registration'], 'NOT_PERFORMED')
                else:
                    self.assertEqual(len(list(Path(tmp).rglob('ACE_REMOTE_RESTORE_RECEIPT.json'))), 1)
                    self.assertFalse(list(Path(tmp).rglob('ACE_MCP_CONFIG.json')))


if __name__ == '__main__':
    unittest.main()
