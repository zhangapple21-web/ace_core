"""一阶尺子检查器回归测试。

跑法：
    cd C:/tmp/ace_core
    PYTHONIOENCODING=utf-8 py -3.11 -m pytest ops/test_check_external_mechanism_safety.py -q
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ops.check_external_mechanism_safety import check_text  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

YAML_ALL_GOOD = """
mechanisms:
  - id: SELF-1
    name: live carrier
    enforced_by: self
    status: VERIFIED
    absorption: true
    carrier: "ops/check_external_mechanism_safety.py"
  - id: CPTY-1
    name: counterparty with sweeper
    enforced_by: counterparty
    status: VERIFIED
    carrier: "ops/check_beneficiary_test.py"
    sweeper: "ops/cleanup_expired_tasks.py --daily"
  - id: SRV-1
    name: proven server enforcement
    enforced_by: third_party_server
    status: VERIFIED
    evidence:
      - {type: file, path: "%s"}
""" % (ROOT / "ops" / "external_mechanism_safety.sample.yaml").as_posix()


def _by_id(report):
    return {row["id"]: row for row in report["mechanisms"]}


def test_declared_and_carrier_backed_mechanisms_pass():
    report = check_text(YAML_ALL_GOOD)
    rows = _by_id(report)
    assert rows["SELF-1"]["verdict"] == "PASS"
    assert rows["CPTY-1"]["verdict"] == "PASS"
    assert rows["SRV-1"]["verdict"] == "PASS"
    assert report["totals"]["reject"] == 0


def test_unclassified_enforcement_is_rejected():
    report = check_text('mechanisms:\n  - id: X\n    name: no ruler question asked\n')
    assert report["mechanisms"][0]["reasons"] == ["unclassified_enforcement"]
    assert report["mechanisms"][0]["verdict"] == "REJECT"


def test_self_mechanism_without_carrier_is_rejected():
    report = check_text("mechanisms:\n  - id: Y\n    enforced_by: self\n")
    assert "no_carrier_criterion_S27" in report["mechanisms"][0]["reasons"]


def test_dead_carrier_is_rejected():
    report = check_text(
        'mechanisms:\n  - id: Z\n    enforced_by: self\n    carrier: "ops/does_not_exist_yet.py"\n'
    )
    assert report["mechanisms"][0]["reasons"] == ["carrier_dead:ops/does_not_exist_yet.py"]


def test_counterparty_without_sweeper_is_rejected():
    report = check_text(
        'mechanisms:\n  - id: C\n    enforced_by: counterparty\n    carrier: "ops/check_beneficiary_test.py"\n'
    )
    assert "counterparty_without_sweeper" in report["mechanisms"][0]["reasons"]


def test_none_string_sweeper_does_not_count():
    report = check_text(
        'mechanisms:\n  - id: C2\n    enforced_by: counterparty\n'
        '    carrier: "ops/check_beneficiary_test.py"\n    sweeper: "none"\n'
    )
    assert "counterparty_without_sweeper" in report["mechanisms"][0]["reasons"]


def test_remedy_in_counterparty_hand_is_rejected():
    report = check_text(
        'mechanisms:\n  - id: R\n    enforced_by: counterparty\n'
        '    carrier: "ops/check_beneficiary_test.py"\n    sweeper: "cron daily"\n'
        "    remedy_in_counterparty_hand: true\n"
    )
    assert "remedy_in_counterparty_hand" in report["mechanisms"][0]["reasons"]
    assert report["mechanisms"][0]["verdict"] == "REJECT"


def test_server_enforcement_needs_resolvable_evidence():
    report = check_text(
        "mechanisms:\n  - id: S\n    enforced_by: third_party_server\n"
        '    evidence:\n      - {type: file, path: "C:/tmp/definitely-absent-9c1e.json"}\n'
    )
    assert "server_enforcement_unproven" in report["mechanisms"][0]["reasons"]


def test_premature_absorption_of_discovered_counterparty_warns():
    report = check_text(
        'mechanisms:\n  - id: P\n    enforced_by: counterparty\n    status: DISCOVERED\n'
        '    carrier: "ops/check_beneficiary_test.py"\n    sweeper: "cron"\n    absorption: true\n'
    )
    row = report["mechanisms"][0]
    assert "premature_absorption" in row["reasons"]
    assert row["verdict"] == "WARN"


def test_markdown_table_with_enforced_by_column_parses():
    text = (
        "| id | enforced_by | carrier | sweeper |\n"
        "|---|---|---|---|\n"
        "| M1 | self | ops/check_beneficiary_test.py |  |\n"
        "| M2 | counterparty | ops/check_beneficiary_test.py | cron daily |\n"
    )
    rows = _by_id(check_text(text))
    assert rows["M1"]["verdict"] == "PASS"
    assert rows["M2"]["verdict"] == "PASS"


def test_json_input_parses():
    text = json.dumps({"mechanisms": [
        {"id": "J1", "enforced_by": "self", "carrier": "ops/task_ledger_reconcile.py"},
    ]})
    rows = _by_id(check_text(text))
    assert rows["J1"]["verdict"] == "PASS"


def test_backslash_paths_in_yaml_fail_loudly_not_silently():
    bad = (
        "mechanisms:\n  - id: B\n    enforced_by: third_party_server\n"
        '    evidence:\n      - {type: file, path: "C:\\tmp\\ace_core\\ops"}\n'
    )
    try:
        check_text(bad)
    except ValueError as error:
        assert "mechanism_declaration_unparsable" in str(error)
    else:
        raise AssertionError("unparsable declaration was silently treated as empty")


def test_sample_manifest_rejects_broken_shapes_and_exit_code_is_one():
    result = subprocess.run(
        [sys.executable, str(ROOT / "ops" / "check_external_mechanism_safety.py"),
         str(ROOT / "ops" / "external_mechanism_safety.sample.yaml"), "--quiet"],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    totals = payload["files"][0]
    assert totals["reject"] == 5 and totals["pass"] == 3


def test_clean_manifest_exit_zero_and_missing_input_exit_two():
    with tempfile.TemporaryDirectory() as temp_dir:
        good = Path(temp_dir) / "good.yaml"
        good.write_text(YAML_ALL_GOOD.replace(
            (ROOT / "ops" / "external_mechanism_safety.sample.yaml").as_posix(),
            (Path(temp_dir) / "good.yaml").as_posix(),
        ), encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "ops" / "check_external_mechanism_safety.py"), str(good), "--quiet"],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert result.returncode == 0, result.stdout + result.stderr
        missing = subprocess.run(
            [sys.executable, str(ROOT / "ops" / "check_external_mechanism_safety.py"),
             str(Path(temp_dir) / "absent.yaml")],
            capture_output=True, text=True, encoding="utf-8",
        )
        assert missing.returncode == 2
