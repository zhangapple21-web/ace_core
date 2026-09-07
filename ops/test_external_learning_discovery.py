from core.external_learning_discovery import ExternalLearningDiscovery


def github_item(name="example/agent-runtime"):
    return {"full_name": name, "name": name.split("/")[-1], "description": "An agent runtime with evidence governance.", "html_url": f"https://github.com/{name}", "updated_at": "2026-08-26T00:00:00Z", "default_branch": "main"}


def test_single_upstream_external_discovery_is_recorded_but_never_becomes_work():
    discovery = ExternalLearningDiscovery(fetch_json=lambda _: {"items": [github_item()]})
    assert discovery.discover("Find ACE learning", ["technical_primary"]) == []
    assert discovery.last_result["status"] == "CANDIDATE_FOUND_BUT_INSUFFICIENT_EVIDENCE"
    assert discovery.last_result["insufficient_findings"] == 1


def test_external_source_failure_is_explicit_and_nonfatal():
    discovery = ExternalLearningDiscovery(fetch_json=lambda _: (_ for _ in ()).throw(OSError("offline")))
    assert discovery.discover("Find ACE learning", ["technical_primary"]) == []
    assert discovery.last_result["status"] == "SOURCE_UNAVAILABLE"


def test_external_evidence_keeps_observable_lineage_and_content_hash():
    discovery = ExternalLearningDiscovery(fetch_json=lambda _: {"items": []})
    evidence = discovery._evidence_for(github_item(), {"id": "fixture"})[0]
    assert evidence["source_ref"].startswith("https://github.com/example/agent-runtime#sha256=")
    assert evidence["metadata"]["lineage_observable"] is True
    assert evidence["metadata"]["independence_group"] == "github_repo:example/agent-runtime"


