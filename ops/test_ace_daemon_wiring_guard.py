"""Guard against the exact accident that happened during the merge.

Two windows edit ``ace_daemon.py`` on a shared tree.  A whole-file restore from
an older snapshot silently deletes the other window's wiring, and because that
wiring only matters at runtime, the loss can reach a commit unnoticed: the
reuse window's own commit e0d4ce3 shipped a ``ace_daemon.py`` that does not
even parse.

These tests fail loudly on both failure modes:

  * the file must compile;
  * every reuse landmark must still be present;
  * the governance landmarks must still be present;
  * the reuse landmarks must appear inside a function body, not only in the
    module-level import.
"""
import ast
import py_compile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent
DAEMON = ROOT / "ace_daemon.py"

# Landmarks owned by the reuse window. Losing any of them breaks the closed loop.
REUSE_LANDMARKS = (
    "KnowledgeReuseGate",
    "_run_knowledge_reuse_stage",
    "_write_knowledge_reuse_report",
    "_reuse_hint_for",
    "_record_reuse_contributions",
    "_knowledge_reuse_contributions",
    "artifact_contributions",
)

# Landmarks owned by the governance window.
GOVERNANCE_LANDMARKS = (
    "self.knowledge_governor",
    "experience_deposition=self.experience_deposition",
    "self.experience_deposition = ExperienceDeposition(",
)


def _source() -> str:
    return DAEMON.read_text(encoding="utf-8")


def test_ace_daemon_parses():
    """e0d4ce3 shipped a syntactically broken ace_daemon.py. Never again."""
    try:
        py_compile.compile(str(DAEMON), cfile=str(DAEMON) + ".pytest.pyc", doraise=True)
    except py_compile.PyCompileError as exc:  # pragma: no cover - the failure path
        pytest_fail = f"ace_daemon.py does not compile: {exc}"
        raise AssertionError(pytest_fail)


def test_reuse_lifeline_is_present():
    source = _source()
    missing = [m for m in REUSE_LANDMARKS if m not in source]
    assert not missing, f"reuse wiring lost from ace_daemon.py: {missing}"


def test_governance_lifeline_is_present():
    source = _source()
    missing = [m for m in GOVERNANCE_LANDMARKS if m not in source]
    assert not missing, f"governance wiring lost from ace_daemon.py: {missing}"


def test_reuse_landmarks_are_wired_not_merely_imported():
    """An import alone is not a lifeline; the stage must be called and reported."""
    tree = ast.parse(_source())
    methods = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AceDaemon":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods[item.name] = item

    for name in ("_run_knowledge_reuse_stage", "_write_knowledge_reuse_report",
                 "_reuse_hint_for", "_record_reuse_contributions"):
        assert name in methods, f"AceDaemon.{name} is missing"

    # The stage must be invoked from the lifecycle, not just defined.
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    assert "_run_knowledge_reuse_stage" in calls, \
        "_run_knowledge_reuse_stage is defined but never called"
    assert "_write_knowledge_reuse_report" in calls, \
        "_write_knowledge_reuse_report is defined but never called"


def test_governor_is_a_single_shared_instance():
    """A second Governor instance would reintroduce a split governance record."""
    tree = ast.parse(_source())
    constructions = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            value = node.value
            if isinstance(value, ast.Call) and getattr(value.func, "id", "") == "Governor":
                constructions.append(ast.dump(node))
    assert len(constructions) == 1, \
        f"expected exactly one Governor construction, found {len(constructions)}"


def _method_body(name: str) -> str:
    tree = ast.parse(_source())
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "AceDaemon":
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                        and item.name == name:
                    return ast.get_source_segment(_source(), item)
    raise AssertionError(f"AceDaemon.{name} is missing")


def test_the_single_governor_is_built_in_init_and_handed_to_the_archivist():
    """A Governor built at the injection site is a second, unshared instance."""
    init = _method_body("__init__")
    assert "self.knowledge_governor = Governor(" in init, \
        "the Governor must be built once in __init__, not at each consumer"

    lifecycle = _method_body("_init_task_lifecycle")
    assert "knowledge_governor=self.knowledge_governor" in lifecycle, \
        "the Archivist must reuse the shared instance"
    assert "knowledge_governor=Governor(" not in lifecycle, \
        "the Archivist is still constructing its own Governor"


def test_experience_deposition_is_built_before_the_guardian_judges():
    """Guardian is the last gate before long-term knowledge.

    If the writer is constructed after the Guardian, the promotion gate reads an
    empty store and a single unverified execution can be promoted.
    """
    lifecycle = _method_body("_init_task_lifecycle")
    built = lifecycle.find("self.experience_deposition = ExperienceDeposition(")
    guarded = lifecycle.find("self.guardian = Guardian(")
    assert built != -1 and guarded != -1
    assert built < guarded, \
        "ExperienceDeposition must exist before Guardian is constructed"
    assert "experience_deposition=self.experience_deposition" in lifecycle, \
        "Guardian must receive the writer"


def test_local_work_accounting_survives_update_task():
    """Regression guard.

    Rebuilding this file from an older snapshot silently dropped the
    ``reviewed``/``blocked`` accounting after ``update_task``, which would have
    shipped a commit that quietly stopped counting completed local work.
    """
    body = _method_body("_run_local_only_work")
    assert "summary[\"reviewed\"] += 1" in body, \
        "reviewed accounting lost in _run_local_only_work"
    assert "summary[\"blocked\"] += 1" in body, \
        "blocked accounting lost in _run_local_only_work"


def test_continuous_guard_script_agrees():
    """ops/verify_fixes.py asserts the same landmarks; both must hold."""
    guard = (ROOT / "ops" / "verify_fixes.py").read_text(encoding="utf-8")
    for marker in REUSE_LANDMARKS:
        if marker == "KnowledgeReuseGate":
            continue
        assert marker in guard, \
            f"ops/verify_fixes.py no longer guards {marker}; the continuity check has rotted"