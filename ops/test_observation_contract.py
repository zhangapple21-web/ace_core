"""Observation categories are a closed vocabulary with declared routing.

Every category literal produced anywhere under core/ or by the daemon
must be registered here with either its conversion rules or an explicit
"unrouted" mark. A new literal fails until registered; a wrong mark
fails against the rules themselves. That is the whole point: vocabulary
drift becomes a red test instead of a silent void.
"""
import glob
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


CATEGORY_ROUTING = {
    'anomaly': ['recent_errors', 'tension_question'],
    'api_error': "unrouted",
    'bottleneck': ['review_queue_bottleneck'],
    'file_change': "unrouted",
    'file_deleted': "unrouted",
    'financial_research': "unrouted",
    'gap': ['lexicon_category_gap', 'fragment_backlog', 'cross_agent_idle'],
    'git_log': "unrouted",
    'health': ['checkup_error', 'disk_space_low'],
    'improvement': ['scheduled_task_inactive', 'discovery_candidate'],
    'manual': "unrouted",
    'models_available': "unrouted",
    'module_missing': "unrouted",
    'need': "unrouted",
    'new_files': "unrouted",
    'provider_anomaly': "unrouted",
    'provider_down': "unrouted",
    'provider_error': "unrouted",
    'provider_missing': "unrouted",
    'provider_ok': "unrouted",
    'sensor_error': "unrouted",
    # This one entry was fiction for as long as it existed. It named two rules,
    # `window_lane_refusal` and `unclaimed_region_write`, that were never in
    # BUILTIN_RULES: four processes produce this category and the converter matched
    # nothing - not even perception-only, which is reserved for host_session - so
    # the escalations of three structural watches accumulated unread while the
    # vocabulary test stayed green. The rule that actually exists is
    # `structural_gap_review`, and the test below now checks this direction too,
    # which is the part that let the fiction survive.
    'structural_gap': ['structural_gap_review'],
    'trending_repo': "unrouted",
    '任务归档': "unrouted",
    '切片考古': "unrouted",
    '外部知识': "unrouted",
    '系统运行记录': "unrouted",
    '考古发现': "unrouted",
}


def _produced_categories():
    root = Path(__file__).resolve().parent.parent
    found = set()
    for path in list((root / "core").glob("*.py")) + [root / "ace_daemon.py"]:
        try:
            src = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for match in re.finditer(r'category\s*=\s*["\']([^"\']+)["\']', src):
            found.add(match.group(1))
    return found


def test_every_produced_category_is_registered():
    assert set(CATEGORY_ROUTING) == _produced_categories()


def test_routing_marks_match_the_builtin_rules():
    from core.observation_to_task import BUILTIN_RULES

    by_category = {}
    for rule in BUILTIN_RULES:
        by_category.setdefault(rule.category, []).append(rule.name)
    for category, rules in by_category.items():
        assert category in CATEGORY_ROUTING, f"rule category unregistered: {category}"
        marked = CATEGORY_ROUTING[category]
        assert marked != "unrouted", f"{category} routed by {rules} but marked unrouted"
        for name in rules:
            assert name in marked, f"{name} routes {category} but registry omits it"
    for category, marked in CATEGORY_ROUTING.items():
        if marked == "unrouted":
            assert category not in by_category, f"{category} marked unrouted but routed"
    # And the other direction, which is what was missing: a registry may not name a
    # rule that does not exist. Checking only rule -> registry allowed a category to
    # be declared routed by two invented rule names for as long as the produced
    # vocabulary stayed green - which is exactly what happened to `structural_gap`.
    known = {rule.name for rule in BUILTIN_RULES}
    for category, marked in CATEGORY_ROUTING.items():
        if marked == "unrouted":
            continue
        for name in marked:
            assert name in known, (
                f"{category} is declared routed by {name!r}, which is not a rule"
            )

