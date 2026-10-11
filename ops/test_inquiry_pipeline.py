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
    # One distinct objection is one question. Re-asking it in rule mode costs a
    # model call and cannot move the verdict: the researcher answer is canned and
    # adds no evidence, so round N+1 is a verbatim copy of round N.
    assert result["inquiry_rounds"] == 1
    assert len(result["questions"]) == 1
    assert len(task.validation_notes) >= 1
    assert len(task.research_notes) >= 1
    # And the stop is declared, not silent.
    assert any("无新异议" in note for _, note in task.validation_notes)


def test_rule_mode_can_resolve_after_new_evidence_threshold():
    task = DummyTask([
        {"content": "证据一", "source": "a"},
        {"content": "证据二", "source": "b"},
        {"content": "证据三", "source": "c"},
    ])
    result = InquiryPipeline(max_rounds=3).run(task, {"passed": False, "objections": ["需要交叉核对"]})
    assert result["final_verdict"] == "passed"
    # Resolves on the first round, not the second. The old rule required
    # round_num >= 2, but by the time _re_judge runs the researcher has already
    # answered, so round 2 carried no information the task did not already have.
    assert result["inquiry_rounds"] == 1


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


def test_each_round_asks_a_different_objection():
    """The validator re-deposits its standard objections every pass; the pipeline
    must not spend its budget re-asking the first one."""
    task = DummyTask()
    objections = ["仅2条证据", "未主动寻找反例", "关键词无对应概念"]
    result = InquiryPipeline(max_rounds=3).run(task, {"passed": False, "objections": objections})
    assert result["inquiry_rounds"] == 3
    assert len(set(result["questions"])) == 3, "each round must interrogate a different objection"


def test_duplicate_objections_are_counted_not_asked_twice():
    """Observed on all 67 non-convergent blocked tasks: a 12-16 item objection
    list holding only 2-4 distinct texts."""
    task = DummyTask()
    objections = ["仅证据不足"] * 6 + ["样本量不足"] * 6
    result = InquiryPipeline(max_rounds=3).run(task, {"passed": False, "objections": objections})
    assert result["distinct_objections"] == 2
    assert result["duplicate_objections_dropped"] == 10
    assert result["inquiry_rounds"] == 2
    assert len(set(result["questions"])) == 2


def test_sacrificial_round_cannot_come_back():
    """Regression guard: with evidence present the task resolves immediately.

    If a mandatory round 2 is ever reintroduced, this turns RED.
    """
    task = DummyTask([
        {"content": "证据一", "source": "a"},
        {"content": "证据二", "source": "b"},
        {"content": "证据三", "source": "c"},
    ])
    result = InquiryPipeline(max_rounds=3).run(task, {"passed": False, "objections": ["需要交叉核对"]})
    assert result["final_verdict"] == "passed"
    assert result["inquiry_rounds"] == 1
    assert len(task.research_notes) == 1
