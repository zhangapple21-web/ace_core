#!/usr/bin/env python3
"""测试 mine_seed_scanner"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.mine_seed_scanner import MineSeedScanner

base_dir = Path(__file__).parent.parent
mine_seed_path = Path.home() / '.trae' / 'work' / 'repos' / 'mine-seed'
state_file = base_dir / '02_FRAGMENT_INDEX' / '.mine_seed_state.json'

print(f'mine_seed_path: {mine_seed_path}')
print(f'state_file: {state_file}')

scanner = MineSeedScanner(str(mine_seed_path), str(state_file))
commits = scanner.fetch_and_get_new_commits()
print(f'发现 {len(commits)} 个新 commit')
for c in commits[:5]:
    hash_val = c.get("hash", "?")[:8]
    msg = c.get("message", "?")[:50]
    print(f'  - {hash_val}: {msg}')
scanner._save_state()
print('状态已保存')