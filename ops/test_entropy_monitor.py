import json

from core.governance.entropy_monitor import EntropyMonitor


def test_entropy_report_handles_bom_and_records_duplicates(tmp_path):
    lexicon = tmp_path / "lexicon.json"
    experiences = tmp_path / "experiences.json"
    evolution = tmp_path / "evolution.json"
    lexicon.write_text(json.dumps({"concepts": {}}, ensure_ascii=False), encoding="utf-8-sig")
    experiences.write_text(json.dumps([
        {"experience_id": "a", "title": "governed entropy duplicate material", "conclusion": "same governed material verifies entropy execution", "source": "probe"},
        {"experience_id": "b", "title": "governed entropy duplicate material", "conclusion": "same governed material verifies entropy execution", "source": "probe"},
    ], ensure_ascii=False), encoding="utf-8-sig")
    evolution.write_text("[]", encoding="utf-8")

    report = EntropyMonitor(str(tmp_path / "reports")).generate_report(
        str(lexicon), str(experiences), str(evolution)
    )

    assert report.read_errors == {}
    assert report.input_status == {"lexicon": "loaded", "experiences": "loaded", "evolution": "loaded"}
    assert report.entropy_score > 0
    assert report.semantic_duplicates


def test_entropy_report_exposes_missing_input(tmp_path):
    report = EntropyMonitor(str(tmp_path / "reports")).generate_report(
        str(tmp_path / "missing-lexicon.json"),
        str(tmp_path / "missing-experiences.json"),
        str(tmp_path / "missing-evolution.json"),
    )

    assert report.entropy_score == 0
    assert report.input_status == {"lexicon": "missing", "experiences": "missing", "evolution": "missing"}
    assert set(report.read_errors) == {"lexicon", "experiences", "evolution"}
