from copy import deepcopy

from core.evidence_relevance_shadow import evaluate_task, shadow_audit


def admitted_task():
    stock_a = "runtime/stock_benchmark.json#pytdx"
    stock_b = "runtime/stock_benchmark.json#sina"
    return {
        "task_id": "RQ-shadow-stock",
        "title": "核查A股数据源退化与字段冲突",
        "hypothesis": "复核行情源的血缘、字段缺口和连续稳定性。",
        "status": "archived",
        "evidence": [
            {
                "source": "downloads/电销规则.txt",
                "content": "客户回访与电话号码异常比例超过阈值时判定为无效数据。",
            },
            {
                "source": stock_a,
                "content": "stock data availability field completeness and lineage metrics",
            },
            {
                "source": stock_b,
                "content": "stock data availability field completeness and lineage metrics",
            },
        ],
        "outputs": {
            "source_obs_description": "A股数据源基准发现可用性和字段完整性退化。",
            "admission": {
                "evidence": [
                    {
                        "source": "pytdx",
                        "source_ref": stock_a,
                        "content": "stock data availability field completeness and lineage metrics",
                        "metadata": {
                            "upstream_identity": "TDX quotation protocol",
                            "independence_group": "tdx_tcp_protocol",
                            "lineage_observable": True,
                        },
                    },
                    {
                        "source": "sina",
                        "source_ref": stock_b,
                        "content": "stock data availability field completeness and lineage metrics",
                        "metadata": {
                            "upstream_identity": "Sina public quotation endpoints",
                            "independence_group": "sina_public_http",
                            "lineage_observable": True,
                        },
                    },
                ],
                "expected_result": "A bounded stock data production-role recommendation.",
                "verification_method": "Compare stock benchmark lineage and field metrics.",
            },
        },
        "audit_log": [
            {
                "event": "transition",
                "from": "approved",
                "to": "archived",
                "actor": "archivist",
                "at": "2026-08-25T11:29:07",
            }
        ],
    }


def test_shadow_flags_unadmitted_cross_domain_evidence_without_a_verdict():
    report = evaluate_task(admitted_task())

    assert report["mode"] == "shadow_only"
    assert report["enforcement"] is False
    assert "would_decision" not in report
    assert "possible_semantic_contamination" in report["warnings"]
    contaminated = report["evidence_records"][0]
    assert contaminated["admission_trace"] == "untraced"
    assert contaminated["lexical_relevance"] == "low_alignment"
    assert contaminated["warnings"] == ["possible_semantic_contamination"]
    assert report["evidence_records"][1]["admission_trace"] == "traced"
    assert report["evidence_records"][2]["admission_trace"] == "traced"


def test_admission_trace_preserves_two_explicit_independence_groups():
    report = evaluate_task(admitted_task())

    assert report["lineage"]["observable_count"] == 2
    assert report["lineage"]["independent_group_count"] == 2
    assert report["lineage"]["independence_groups"] == [
        "sina_public_http",
        "tdx_tcp_protocol",
    ]
    assert "source_independence_unverified" not in report["warnings"]


def test_exact_and_cross_source_content_duplicates_are_separate_warnings():
    task = admitted_task()
    task["evidence"] = [
        {"source": "source:a", "content": "same substantive evidence"},
        {"source": "source:a", "content": "same substantive evidence"},
        {"source": "source:b", "content": "same substantive evidence"},
    ]
    task["outputs"]["admission"]["evidence"] = []

    report = evaluate_task(task)

    assert report["duplicates"]["exact_duplicate_count"] == 1
    assert report["duplicates"]["cross_source_duplicate_count"] == 1
    assert "exact_duplicate_evidence" in report["warnings"]
    assert "cross_source_content_duplicate" in report["warnings"]


def test_missing_explicit_lineage_is_not_inferred_from_wrapper_names():
    task = admitted_task()
    task["outputs"]["admission"]["evidence"] = [
        {
            "source_ref": "finshare:auto",
            "content": "aggregated quote",
            "metadata": {"upstream_identity": "UNVERIFIED_AGGREGATE"},
        },
        {
            "source_ref": "finshare:fallback",
            "content": "aggregated minute bars",
            "metadata": {"upstream_identity": "UNVERIFIED_AGGREGATE"},
        },
    ]
    task["evidence"] = [
        {"source": "finshare:auto", "content": "aggregated quote"},
        {"source": "finshare:fallback", "content": "aggregated minute bars"},
    ]

    report = evaluate_task(task)

    assert report["lineage"]["independent_group_count"] == 0
    assert "lineage_unobservable" in report["warnings"]
    assert "source_independence_unverified" in report["warnings"]


def test_generic_archaeology_question_is_unassessed_not_contaminated():
    task = {
        "task_id": "RQ-generic",
        "title": "启动碎片考古 — OBS-1",
        "hypothesis": "处理尚未考古的文件。",
        "status": "archived",
        "evidence": [
            {"source": "archive/file.md", "content": "historical architecture fragment"}
        ],
        "outputs": {},
    }

    report = evaluate_task(task)

    assert report["query_specificity"] == "generic"
    assert report["evidence_records"][0]["lexical_relevance"] == "unassessed"
    assert "possible_semantic_contamination" not in report["warnings"]
    assert "generic_research_question" in report["warnings"]


def test_shadow_audit_filters_archives_by_transition_window_and_never_mutates():
    included = admitted_task()
    excluded = deepcopy(included)
    excluded["task_id"] = "RQ-yesterday"
    excluded["audit_log"][0]["at"] = "2026-08-24T23:59:59"
    before = deepcopy([included, excluded])

    report = shadow_audit(
        [included, excluded],
        start_at="2026-08-25T00:00:00",
        end_at="2026-08-25T23:59:59",
    )

    assert report["mode"] == "shadow_only"
    assert report["enforcement"] is False
    assert report["task_count"] == 1
    assert report["records"][0]["task_id"] == "RQ-shadow-stock"
    assert [included, excluded] == before
