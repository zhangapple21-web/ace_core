from core.inquiry_pipeline import InquiryPipeline


class DummyTask:
    def __init__(self, evidence=None):
        self.title = "测试任务"
        self.hypothesis = "验证一个待解决问题"
        self.evidence = list(evidence or [])
        self.validation_notes = []
        self.research_notes = []

    def add_validation_note(self, note, validator=""):
        self.validation_notes.append((validator, note))

    def add_research_note(self, note, researcher=""):
        self.research_notes.append((researcher, note))

    def add_evidence(self, content, source=""):
        self.evidence.append({"content": content, "source": source})


def test_passed_validation_is_not_queried():
    result = InquiryPipeline().run(DummyTask(), {"passed": True, "objections": []})
    assert result["final_verdict"] == "skipped"
    assert result["inquiry_rounds"] == 0


def test_rule_mode_is_bounded_when_evidence_is_missing():
    task = DummyTask()
    result = InquiryPipeline(max_rounds=3).run(task, {"passed": False, "objections": ["证据不足"]})
    assert result["final_verdict"] == "inconclusive"
    assert result["inquiry_rounds"] == 3
    assert len(result["questions"]) == 3
    assert len(task.validation_notes) >= 3
    assert len(task.research_notes) >= 3


def test_rule_mode_can_resolve_after_new_evidence_threshold():
    task = DummyTask([
        {"content": "证据一", "source": "a"},
        {"content": "证据二", "source": "b"},
        {"content": "证据三", "source": "c"},
    ])
    result = InquiryPipeline(max_rounds=3).run(task, {"passed": False, "objections": ["需要交叉核对"]})
    assert result["final_verdict"] == "passed"
    assert result["inquiry_rounds"] == 2


def test_model_claimed_evidence_is_not_promoted_into_task_evidence():
    task = DummyTask()
    pipeline = InquiryPipeline(max_rounds=1)
    pipeline._research_answer = lambda *_args: ("模型回答", ["模型声称的来源，但尚未核验"])
    pipeline._re_judge = lambda *_args: {
        "resolved": False,
        "reason": "仍需独立来源",
        "remaining_objections": ["需要独立来源"],
    }
    result = pipeline.run(task, {"passed": False, "objections": ["需要独立来源"]})
    assert task.evidence == []
    assert result["unverified_candidates"] == ["模型声称的来源，但尚未核验"]
    assert any("待核验模型候选" in note for _, note in task.research_notes)
