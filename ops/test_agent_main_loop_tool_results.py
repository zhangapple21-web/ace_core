import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = ROOT / "core" / "agent" / "main_loop.py"
SPEC = importlib.util.spec_from_file_location("ace_agent_main_loop_under_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

AgentMainLoop = MODULE.AgentMainLoop
TurnContext = MODULE.TurnContext


class DummyTool:
    def execute(self, tool_input):
        return f"ok:{tool_input['value']}"


class DummyToolRegistry:
    def get(self, name):
        if name == "demo":
            return DummyTool()
        return None


class DummyModelClient:
    pass


def test_process_attachments_emits_function_call_output_with_call_id_for_openai_style_tools():
    loop = AgentMainLoop(model_client=DummyModelClient(), tool_registry=DummyToolRegistry())
    state = TurnContext(
        tool_use_blocks=[
            {"name": "demo", "input": {"value": "42"}, "id": "toolu_1", "call_id": "call_123"}
        ]
    )

    state = loop._tool_execution(state)
    state = loop._process_attachments(state)

    assert state.messages == [
        {
            "role": "user",
            "content": [
                {
                    "type": "function_call_output",
                    "call_id": "call_123",
                    "output": "ok:42",
                }
            ],
        }
    ]


def test_process_attachments_keeps_missing_call_id_in_legacy_shape():
    loop = AgentMainLoop(model_client=DummyModelClient(), tool_registry=DummyToolRegistry())
    state = TurnContext(
        tool_use_blocks=[
            {"type": "function_call", "name": "demo", "input": {"value": "42"}, "id": "call_from_id"}
        ]
    )

    state = loop._tool_execution(state)
    state = loop._process_attachments(state)

    assert state.messages[0]["content"][0] == {
        "type": "tool_result",
        "tool_use_id": "call_from_id",
        "content": "ok:42",
    }
