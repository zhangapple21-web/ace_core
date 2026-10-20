from core.hindsight_memory_adapter import (
    HindsightStyleRetriever,
    consolidate_observations,
    project_knowledge_page,
    run_synthetic_ab_benchmark,
)


def _entries():
    return [
        {
            "id": "shot-1",
            "title": "\u955c\u5934\u8868\u6f14\u8fde\u7eed\u6027",
            "summary": "\u6f14\u5458\u5148\u4f4e\u5934\u770b\u684c\u9762\uff0c\u518d\u62ac\u5934\u5b8c\u6210\u624b\u90e8\u52a8\u4f5c\u3002",
            "related_concepts": ["\u8868\u6f14", "\u8fde\u7eed\u6027", "\u624b\u90e8"],
            "created_at": "2026-09-20T10:00:00+00:00",
            "data_class": "STRUCTURE",
            "source_path": "receipt://shot-1",
        },
        {
            "id": "routing-1",
            "title": "\u8def\u7531\u5065\u5eb7\u68c0\u67e5",
            "summary": "\u6a21\u578b\u5931\u8d25\u540e\u5207\u6362\u5230\u5065\u5eb7\u7684\u5907\u7528\u7ebf\u8def\u3002",
            "related_concepts": ["\u8def\u7531", "\u5065\u5eb7"],
            "created_at": "2026-09-21T10:00:00+00:00",
            "data_class": "PRIVATE",
            "source_path": "receipt://routing-1",
        },
        {
            "id": "unclassified",
            "title": "\u672a\u5206\u7c7b\u8bb0\u5f55",
            "summary": "\u4e0d\u5141\u8bb8\u8fdb\u5165\u53ec\u56de\u3002",
        },
    ]


def test_retriever_fuses_concept_and_keyword_and_rejects_unknown_boundary():
    result = HindsightStyleRetriever(_entries()).retrieve("\u62ac\u5934 \u624b\u90e8", limit=2)
    assert result["results"][0]["memory_id"] == "shot-1"
    assert "graph" in result["results"][0]["signals"]
    assert len(result["boundary_rejections"]) == 1
    assert result["execution_authorized"] is False
    assert result["production_integration"] is False


def test_temporal_window_excludes_old_records():
    result = HindsightStyleRetriever(_entries()).retrieve(
        "\u8fde\u7eed\u6027",
        after="2026-09-21T00:00:00+00:00",
        limit=10,
    )
    assert [item["memory_id"] for item in result["results"]] == []


def test_observation_consolidation_deduplicates_evidence_and_preserves_candidate_status():
    result = consolidate_observations(
        [
            {
                "id": "r1",
                "observation_key": "shot.action",
                "claim": "\u52a8\u4f5c\u9700\u8981\u7ee7\u627f\u5c3e\u5e27",
                "evidence": [{"ref": "receipt-1", "quote": "\u5c3e\u5e27\u65ad\u88c2"}],
                "data_class": "STRUCTURE",
            },
            {
                "id": "r2",
                "observation_key": "shot.action",
                "claim": "\u52a8\u4f5c\u9700\u8981\u7ee7\u627f\u5c3e\u5e27",
                "evidence": [{"ref": "receipt-1", "quote": "\u5c3e\u5e27\u65ad\u88c2"}],
                "data_class": "STRUCTURE",
            },
        ]
    )
    observation = result["observations"][0]
    assert observation["support_count"] == 1
    assert observation["status"] == "CANDIDATE_OBSERVATION"
    assert result["promotion_status"] == "CANDIDATE_ONLY"


def test_conflicting_observation_stays_unknown():
    result = consolidate_observations(
        [
            {
                "id": "r1",
                "observation_key": "route.health",
                "claim": "\u8def\u7ebf\u53ef\u7528",
                "polarity": "SUPPORTED",
                "evidence": [{"ref": "receipt-1"}],
                "data_class": "CAPABILITY",
            },
            {
                "id": "r2",
                "observation_key": "route.health",
                "claim": "\u8def\u7ebf\u53ef\u7528",
                "polarity": "CONTRADICTED",
                "evidence": [{"ref": "receipt-2"}],
                "data_class": "CAPABILITY",
            },
        ]
    )
    assert result["observations"][0]["status"] == "UNKNOWN_CONFLICT"


def test_knowledge_page_is_read_only_projection():
    projection = project_knowledge_page(
        "\u5f53\u524d\u955c\u5934\u7ecf\u9a8c",
        [{"observation_id": "OBS-1", "observation_key": "shot.action", "support_count": 2}],
    )
    assert projection["projection_type"] == "READ_ONLY_PROJECTION"
    assert projection["authority"] == "NONE"
    assert projection["source_of_truth"] == "ACE_GOVERNED_RECORDS"


def test_synthetic_ab_benchmark_passes_without_production_promotion():
    report = run_synthetic_ab_benchmark()
    assert report["status"] == "PASS"
    assert report["adapter_hit_rate"] > report["baseline_hit_rate"]
    assert report["adapter_mrr"] > report["baseline_mrr"]
    assert report["temporal_expected_top1"] is True
    assert report["boundary_rejections"] == 1
    assert report["boundary_leaks"] == 0
    assert report["network_calls"] == 0
    assert report["external_model_calls"] == 0
    assert report["promotion_decision"] == "NOT_AUTOMATICALLY_PROMOTED"


def test_secret_like_content_is_rejected_before_retrieval():
    records = [
        {
            "id": "secret",
            "title": "token",
            "summary": "ghp_123456789012345678901234567890123456",
            "data_class": "PRIVATE",
        }
    ]
    retriever = HindsightStyleRetriever(records)
    assert retriever.entries == []
    assert retriever.rejected_entries[0]["reason"] == ["credential_like_content_detected"]
