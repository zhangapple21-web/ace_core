import json

import pytest

from core.memory_kernel import MemoryIntegrityError, MemoryKernel
from core.memory_index import MemoryIndex


def _kernel(tmp_path):
    return MemoryKernel(tmp_path / "kernel")


def test_missing_evidence_stays_unknown_and_is_recovered(tmp_path):
    kernel = _kernel(tmp_path)
    record = kernel.capture(
        content="这只是一个待核对的观察",
        title="待核对",
        memory_type="OBSERVATION",
        claim_key="demo.observation",
        data_class="STRUCTURE",
        source_refs=["receipt://observation/1"],
    )
    assert record["epistemic_status"] == "UNKNOWN"
    recovered = MemoryKernel(tmp_path / "kernel")
    assert recovered.integrity_report()["valid"] is True
    assert recovered.project_current_state()["unknowns"][0]["id"] == record["id"]


def test_capture_is_idempotent_and_merges_new_evidence(tmp_path):
    kernel = _kernel(tmp_path)
    first = kernel.capture(
        content="动作必须继承尾帧",
        title="连续性",
        memory_type="EXPERIENCE",
        claim_key="video.continuity",
        data_class="CAPABILITY",
        source_refs=["receipt://video/1"],
        evidence_refs=["receipt://video/1"],
    )
    second = kernel.capture(
        content="动作必须继承尾帧",
        title="连续性",
        memory_type="EXPERIENCE",
        claim_key="video.continuity",
        data_class="CAPABILITY",
        source_refs=["receipt://video/1"],
        evidence_refs=["receipt://video/2"],
    )
    assert first["id"] == second["id"]
    assert second["support_count"] == 2
    assert second["evidence_refs"] == ["receipt://video/1", "receipt://video/2"]


def test_conflict_is_preserved_as_unknown_conflict(tmp_path):
    kernel = _kernel(tmp_path)
    supported = kernel.capture(
        content="grok 线路可用",
        memory_type="OBSERVATION",
        claim_key="route.grok",
        data_class="STRUCTURE",
        source_refs=["probe://1"],
        evidence_refs=["probe://1"],
        polarity="SUPPORTED",
    )
    contradicted = kernel.capture(
        content="grok 线路不可用",
        memory_type="OBSERVATION",
        claim_key="route.grok",
        data_class="STRUCTURE",
        source_refs=["probe://2"],
        evidence_refs=["probe://2"],
        polarity="CONTRADICTED",
    )
    assert kernel._records[supported["id"]]["epistemic_status"] == "CONFLICTED"
    assert kernel._records[contradicted["id"]]["epistemic_status"] == "CONFLICTED"
    assert kernel.project_current_state()["next_review"]


def test_verify_requires_independent_receipt(tmp_path):
    kernel = _kernel(tmp_path)
    record = kernel.capture(
        content="模型路由经过探针验证",
        memory_type="OBSERVATION",
        claim_key="route.verified",
        data_class="STRUCTURE",
        source_refs=["probe://1"],
        evidence_refs=["probe://1"],
    )
    with pytest.raises(ValueError, match="verification_receipt"):
        kernel.verify(record["id"], {"result": "PASS"})
    verified = kernel.verify(
        record["id"],
        {
            "receipt_id": "probe-receipt-1",
            "source_refs": ["probe://1", "logs://1"],
            "result": "PASS",
            "reviewer": "guardian",
        },
    )
    assert verified["epistemic_status"] == "VERIFIED"
    assert verified["authority"]["promotion"] is False


def test_capability_promotion_requires_closed_loop_and_painful_review(tmp_path):
    kernel = _kernel(tmp_path)
    record = kernel.capture(
        content="镜头合同会自动生成表演状态字段",
        memory_type="CAPABILITY_CANDIDATE",
        claim_key="video.auto_state_contract",
        data_class="CAPABILITY",
        source_refs=["test://baseline-change"],
        evidence_refs=["test://green"],
    )
    with pytest.raises(ValueError, match="receipt"):
        kernel.promote_capability(record["id"], {})
    kernel.verify(
        record["id"],
        {
            "receipt_id": "receipt://capability/1",
            "source_refs": ["test://green"],
            "result": "VERIFIED",
            "reviewer": "guardian",
        },
    )
    accepted = kernel.promote_capability(
        record["id"],
        {
            "decision": "PROMOTE",
            "baseline": {"pass_rate": 0.7},
            "change": {"pass_rate": 0.9},
            "test": {"status": "PASS"},
            "evaluation": {"regression": False},
            "compare": {"improved": True},
            "independent_evidence_groups": [["test://green"], ["receipt://capability/1"]],
            "painful_review": {
                "cost": "返工两镜",
                "impact": "一集镜头失败",
                "counterfactual": "未拦截会继续批量生成",
                "recurrence_risk": "中",
                "lesson": "合同必须先过表演门",
                "reuse_conditions": "所有含对白镜头",
            },
        },
    )
    assert accepted["memory_type"] == "CAPABILITY_ACCEPTED"
    assert accepted["promotion_receipt"]["decision"] == "PROMOTE"


def test_archive_and_supersede_never_delete_history(tmp_path):
    kernel = _kernel(tmp_path)
    old = kernel.capture(
        content="旧规则",
        memory_type="PROCEDURAL",
        claim_key="rule.example",
        data_class="STRUCTURE",
        source_refs=["doc://old"],
        evidence_refs=["doc://old"],
    )
    replacement = kernel.capture(
        content="新规则",
        memory_type="PROCEDURAL",
        claim_key="rule.example.v2",
        data_class="STRUCTURE",
        source_refs=["doc://new"],
        evidence_refs=["doc://new"],
    )
    archived = kernel.archive(old["id"], reason="被新规则替代前保留历史")
    assert archived["lifecycle_state"] == "ARCHIVED"
    superseded = kernel.supersede(replacement["id"], old["id"], reason="测试反向替代")
    assert superseded["lifecycle_state"] == "SUPERSEDED"
    assert len(kernel._records) == 2
    assert kernel.integrity_report()["events"] == 4


def test_query_is_scoped_and_read_only(tmp_path):
    kernel = _kernel(tmp_path)
    record = kernel.capture(
        content="文姬说话前先看向桌面，再抬头回应",
        memory_type="EXPERIENCE",
        claim_key="video.performance",
        data_class="CAPABILITY",
        source_refs=["video://shot-1"],
        evidence_refs=["video://shot-1"],
        scope="video",
    )
    before_events = kernel.integrity_report()["events"]
    result = kernel.query("抬头 回应", scope="video")
    assert result["results"][0]["memory_id"] == record["id"]
    assert result["execution_authorized"] is False
    assert result["production_integration"] is False
    assert result["retrieval_receipt"]["read_only"] is True
    assert result["retrieval_receipt"]["result_ids"] == [record["id"]]
    assert kernel.integrity_report()["events"] == before_events
    assert kernel.query("抬头", scope="other")["results"] == []
    with pytest.raises(ValueError, match="data_class_invalid"):
        kernel.query("抬头", data_classes=["UNCLASSIFIED"])


def test_credential_like_content_is_rejected(tmp_path):
    kernel = _kernel(tmp_path)
    with pytest.raises(ValueError, match="credential"):
        kernel.capture(
            content="token=ghp_123456789012345678901234567890123456",
            memory_type="WORKING",
            data_class="PRIVATE",
        )
    with pytest.raises(ValueError, match="credential"):
        kernel.capture(
            content="普通内容",
            memory_type="WORKING",
            data_class="PRIVATE",
            metadata={"api_key": "ghp_123456789012345678901234567890123456"},
        )


def test_tampered_event_chain_fails_closed(tmp_path):
    kernel = _kernel(tmp_path)
    kernel.capture(
        content="可回读收据",
        memory_type="OBSERVATION",
        claim_key="receipt.example",
        data_class="STRUCTURE",
        source_refs=["receipt://1"],
    )
    path = tmp_path / "kernel" / "events.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    event = json.loads(lines[0])
    event["payload"]["record"]["content"] = "被篡改"
    lines[0] = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(MemoryIntegrityError, match="hash_invalid"):
        MemoryKernel(tmp_path / "kernel")


def test_import_is_candidate_only(tmp_path):
    kernel = _kernel(tmp_path)
    result = kernel.import_records(
        [
            {
                "id": "legacy-1",
                "title": "旧记忆",
                "summary": "旧系统内容",
                "type": "project",
                "data_class": "PRIVATE",
                "source_path": "legacy://memory/1",
                "created_at": "2026-08-20T10:00:00+00:00",
            }
        ],
        selected_by="test:import-is-candidate-only",
    )
    assert len(result["imported"]) == 1
    receipt = result["batch_receipt"]
    assert receipt["batch_id"].startswith("MB-")
    assert receipt["selected_by"] == "test:import-is-candidate-only"
    assert receipt["selection_identity_authenticated"] is False
    assert receipt["selected_count"] == 1
    assert receipt["imported_count"] == 1
    assert receipt["result"] == "PASS"
    assert receipt["selected_record_hashes"]
    assert kernel.list_import_batches()[0]["status"] == "COMPLETED"
    state = kernel.project_current_state()
    assert state["candidates"][0]["epistemic_status"] == "CANDIDATE"
    assert state["candidates"][0]["metadata"]["imported_from"]["id"] == "legacy-1"
    assert (
        state["candidates"][0]["metadata"]["imported_from"]["created_at"]
        == "2026-08-20T10:00:00+00:00"
    )
    query = kernel.query("旧系统内容")
    assert query["results"]
    assert query["results"][0]["source_ref"] == "legacy://memory/1"


def test_import_preserves_original_time_and_source_for_candidate_retrieval(tmp_path):
    kernel = _kernel(tmp_path)
    result = kernel.import_records(
        [
            {
                "id": "legacy-old",
                "title": "checkpoint note",
                "summary": "checkpoint note",
                "type": "note",
                "data_class": "PRIVATE",
                "source_path": "legacy://old",
                "created_at": "2026-08-20T10:00:00+00:00",
            },
            {
                "id": "legacy-new",
                "title": "checkpoint note",
                "summary": "checkpoint note",
                "type": "note",
                "data_class": "PRIVATE",
                "source_path": "legacy://new",
                "created_at": "2026-09-20T10:00:00+00:00",
            },
        ],
        selected_by="test:source-time-preservation",
    )

    query = kernel.query("2026-08-20 checkpoint note", data_classes=["PRIVATE"])
    results = {item["memory_id"]: item for item in query["results"]}
    old_id, new_id = result["imported"]

    assert results[old_id]["source_ref"] == "legacy://old"
    assert results[new_id]["source_ref"] == "legacy://new"
    assert results[old_id]["signals"]["temporal"] > results[new_id]["signals"]["temporal"]


def test_search_governed_does_not_implicitly_migrate_legacy_index(tmp_path):
    class FakeIdentity:
        name = "ACE"

        def continuity_mark(self):
            return "continuity"

    class FakeLexicon:
        def classify(self, _text):
            return []

    index = MemoryIndex(tmp_path / "legacy", FakeIdentity(), FakeLexicon())
    index.add(
        title="视频动作",
        content="表演必须继承上一镜尾帧",
        memory_type="note",
        data_class="STRUCTURE",
        source_path="receipt://legacy/1",
    )
    result = index.search_governed(
        "尾帧",
        kernel_dir=tmp_path / "kernel",
        scope="ace",
    )
    assert result["retrieval_mode"] == "GOVERNED_MULTI_STRATEGY_READ_ONLY"
    assert result["source_of_truth"] == "ACE_MEMORY_KERNEL_EVENT_LEDGER"
    assert result["promotion"] is False
    assert result["candidate_count"] == 0


def test_selected_legacy_slice_migrates_only_when_explicitly_requested(tmp_path):
    class FakeIdentity:
        name = "ACE"

        def continuity_mark(self):
            return "continuity"

    class FakeLexicon:
        def classify(self, _text):
            return []

    index = MemoryIndex(tmp_path / "legacy", FakeIdentity(), FakeLexicon())
    index.add(
        title="视频动作",
        content="表演必须继承上一镜尾帧",
        memory_type="note",
        data_class="STRUCTURE",
        source_path="receipt://legacy/1",
    )
    kernel = MemoryKernel(tmp_path / "kernel", bank="ace")
    migration = kernel.import_records(
        index._index,
        source_prefix="memory_index",
        selected_by="test:selected-slice",
    )
    assert len(migration["imported"]) == 1
    result = index.search_governed(
        "尾帧",
        kernel_dir=tmp_path / "kernel",
        scope="ace",
    )
    assert result["candidate_count"] == 1
    assert result["promotion"] is False


def test_legacy_import_rejects_oversized_batch_before_writing(tmp_path):
    kernel = _kernel(tmp_path)
    records = [
        {
            "id": f"legacy-{index}",
            "title": f"旧记忆 {index}",
            "summary": f"旧系统内容 {index}",
            "type": "project",
            "data_class": "PRIVATE",
            "source_path": f"legacy://memory/{index}",
        }
        for index in range(51)
    ]
    with pytest.raises(ValueError, match="memory_import_batch_limit_exceeded:50"):
        kernel.import_records(records, selected_by="test:oversized-batch")
    assert kernel.project_current_state()["candidates"] == []
    batches = kernel.list_import_batches()
    assert len(batches) == 1
    assert batches[0]["status"] == "REJECTED"
    assert batches[0]["records_written"] == 0
    assert batches[0]["selected_by"] == "test:oversized-batch"


def test_interrupted_import_is_visible_as_incomplete_batch(tmp_path):
    kernel = _kernel(tmp_path)
    original_capture = kernel.capture
    calls = 0

    def fail_during_import(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected import interruption")
        return original_capture(**kwargs)

    kernel.capture = fail_during_import
    records = [
        {
            "id": f"legacy-{index}",
            "title": f"旧记忆 {index}",
            "summary": f"旧系统内容 {index}",
            "type": "project",
            "data_class": "PRIVATE",
            "source_path": f"legacy://memory/{index}",
        }
        for index in range(3)
    ]
    with pytest.raises(RuntimeError, match="injected import interruption"):
        kernel.import_records(records, selected_by="test:interrupted-import")
    batches = kernel.list_import_batches()
    assert len(batches) == 1
    assert batches[0]["status"] == "INCOMPLETE"
    assert batches[0]["selected_count"] == 3


def test_validity_window_and_retention_are_explicit(tmp_path):
    kernel = _kernel(tmp_path)
    record = kernel.capture(
        content="仅在九月有效的规则",
        memory_type="PROCEDURAL",
        claim_key="rule.september",
        data_class="STRUCTURE",
        source_refs=["doc://september"],
        evidence_refs=["doc://september"],
        valid_from="2026-09-01T00:00:00Z",
        valid_to="2026-09-30T23:59:59Z",
        retention_until="2026-09-30T23:59:59Z",
    )
    assert kernel.query("九月", as_of="2026-09-15T00:00:00Z")["results"]
    assert kernel.query("九月", as_of="2026-10-01T00:00:00Z")["results"] == []
    result = kernel.apply_retention(now="2026-10-01T00:00:00Z")
    assert result["changed"] == [record["id"]]
    assert kernel._records[record["id"]]["lifecycle_state"] == "COLD"
    assert result["deleted"] == []
