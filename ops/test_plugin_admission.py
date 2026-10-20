from core.plugin_admission import admit_plugin


def test_old_settings_pin_is_rejected():
    manifest = {
        "name": "dsh-subagent-model-routing",
        "engines": {"dsh": ">=0.1.0"},
        "dependencies": {"@deepseek-ai/dsh-settings": "0.1.1-rc.1"},
    }
    env = admit_plugin(
        manifest,
        host_version="0.2.1-rc.2",
        resolved={"@deepseek-ai/dsh-settings": "0.1.1-rc.1"},
    )
    assert env["decision"] == "reject"
    assert any(item["code"] == "host_module_shadow" for item in env["reasons"])
    assert "token" not in str(env)


def test_missing_engine_is_fail_closed():
    env = admit_plugin({"name": "dsh-pet"}, host_version="0.2.1-rc.2")
    assert env["decision"] == "reject"
    assert env["reasons"][0]["code"] == "missing_host_engine"
