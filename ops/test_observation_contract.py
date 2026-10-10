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

