# Worker base classes — 统一任务执行接口

# Importing any ACE module installs the process-wide continuation guard.  This
# is deliberately implicit so newly added scripts that import ``core`` cannot
# accidentally skip the boundary.
import sys
from pathlib import Path

_shared_root = Path(__file__).resolve().parents[2]
if str(_shared_root) not in sys.path:
    sys.path.insert(0, str(_shared_root))
import continue_gate_runtime

continue_gate_runtime.install()
