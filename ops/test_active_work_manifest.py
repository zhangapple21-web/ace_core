from datetime import datetime, timedelta, timezone

from agent_team.active_work_manifest import conflict_hints, is_stale, new_manifest, save_manifest, validate_entry, validate_manifest


def _entry(work_id, scope, **overrides):
    item = {
        "work_id": work_id,
        "agent": "codex-main",
        "owner": "window-a",
        "mission": "bounded review",
        "workspace": "C:\\tmp\\ace_core",
        "scope": scope,
        "status": "active",
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
        "ttl_seconds": 3600,
        "production_integration": False,
        "taskpool_authority": False,
        "takeover_requires_new_declaration": True,
    }
    item.update(overrides)
    return item


def test_manifest_is_explicitly_non_production_metadata():
    manifest = new_manifest()
    assert manifest["invariants"]["taskpool_authority"] is False
    assert manifest["invariants"]["automatic_takeover"] is False
    assert validate_entry(_entry("one", ["core/a.py"])) == []
    assert validate_manifest({**manifest, "entries": [_entry("one", ["core/a.py"])]}) == []
    assert "must_be_false:taskpool_authority" in validate_entry(_entry("bad", ["core/a.py"], taskpool_authority=True))


def test_owner_is_required_and_other_windows_are_read_only():
    from agent_team.active_work_manifest import READ_ONLY_MODE, WRITE_MODE, access_mode, can_write, ownership_decision, require_write_access

    assert "missing:owner" in validate_entry(_entry("missing", ["core/a.py"], owner=""))
    assert access_mode(_entry("one", ["core/a.py"]), "window-a") == WRITE_MODE
    assert require_write_access(_entry("one", ["core/a.py"]), "window-a")["reason"] == "declared_owner"
    assert not can_write(_entry("one", ["core/a.py"]), "window-b")
    assert ownership_decision(_entry("one", ["core/a.py"]), "window-b") == {
        "work_id": "one",
        "window_id": "window-b",
        "owner": "window-a",
        "mode": READ_ONLY_MODE,
        "reason": "owned_by_other_window",
    }
    try:
        require_write_access(_entry("one", ["core/a.py"]), "window-b")
    except PermissionError as exc:
        assert "read-only" in str(exc)
    else:
        raise AssertionError("non-owner write must be rejected")


def test_malformed_or_completed_entries_fail_closed_to_read_only():
    from agent_team.active_work_manifest import READ_ONLY_MODE, access_mode

    assert access_mode(_entry("bad", ["core/a.py"], owner=None), "window-a") == READ_ONLY_MODE
    assert access_mode(_entry("done", ["core/a.py"], status="completed"), "window-a") == READ_ONLY_MODE
    assert access_mode(None, "window-a") == READ_ONLY_MODE
    assert validate_manifest({"schema_version": 2, "entries": [{}], "invariants": {}})[0] == "entry[0]:missing:work_id"


def test_save_manifest_rejects_missing_owner_before_writing(tmp_path):
    path = tmp_path / "manifest.json"
    invalid = {**new_manifest(), "entries": [_entry("bad", ["core/a.py"], owner="")]}
    try:
        save_manifest(path, invalid)
    except ValueError as exc:
        assert "missing:owner" in str(exc)
    else:
        raise AssertionError("invalid manifest must not be written")
    assert not path.exists()


def test_whitespace_owner_is_missing_and_read_only():
    from agent_team.active_work_manifest import READ_ONLY_MODE, access_mode

    entry = _entry("bad-owner", ["core/a.py"], owner="   ")
    assert "missing:owner" in validate_entry(entry)
    assert access_mode(entry, "   ") == READ_ONLY_MODE


def test_overlap_is_a_hint_not_a_takeover():
    now = datetime(2026, 8, 27, 10, 10, tzinfo=timezone.utc)
    hints = conflict_hints([_entry("one", ["core"]), _entry("two", ["core/daily_shift.py"])], now=now)
    assert hints == [{"left_work_id": "one", "right_work_id": "two", "action": "COMPARE_THEN_SPLIT_OR_WAIT"}]
    assert conflict_hints([{"status": "active"}, None], now=now) == []


def test_expiry_only_marks_a_declaration_stale():
    now = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    expired = _entry("one", ["core/a.py"], heartbeat_at="2026-08-27T10:00:00+00:00")
    assert is_stale(expired, now=now) is True


def test_expired_owner_is_read_only_and_never_taken_over():
    from agent_team.active_work_manifest import READ_ONLY_MODE, access_mode, ownership_decision

    expired = _entry("one", ["core/a.py"], heartbeat_at="2026-08-27T10:00:00+00:00")
    observed_at = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
    assert access_mode(expired, "window-a", now=observed_at) == READ_ONLY_MODE
    # ownership_decision uses wall-clock freshness and therefore remains a
    # stale hint in the current run too.
    assert ownership_decision(expired, "window-a")["reason"] == "stale_hint"


def test_mixed_timezone_inputs_fail_closed_instead_of_raising():
    naive_now = datetime(2026, 8, 27, 12, 0)
    assert is_stale(_entry("one", ["core/a.py"]), now=naive_now) is True


