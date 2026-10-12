# Worker base classes — 统一任务执行接口

# Importing any ACE module installs the process-wide continuation guard.  This
# is deliberately implicit so newly added scripts that import ``core`` cannot
# accidentally skip the boundary.
import sys
from pathlib import Path

# ``core`` lives one level below the repository root, which is where
# ``continue_gate_runtime`` is installed.  ``parents[1]`` is that root;
# ``parents[2]`` would be a directory *outside* the repository.
_repo_root = Path(__file__).resolve().parents[1]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
try:
    import continue_gate_runtime
except ImportError:
    # The gate module is injected on operator machines via a user-level
    # ``sitecustomize.py``.  A checkout without it must stay importable — the
    # daemon still performs its explicit boundary check and writes a durable
    # handoff receipt.  Fail-closed on the gate, never on the import itself.
    continue_gate_runtime = None

if continue_gate_runtime is not None:
    continue_gate_runtime.install()
