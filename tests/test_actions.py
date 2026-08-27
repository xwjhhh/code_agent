import json

import pytest

from code_agent.exceptions import FormatError
from code_agent.models.utils.actions import format_observation_messages, parse_tool_calls


def test_parse_tool_call_to_action():
    calls = [{"id": "call-1", "function": {"name": "bash", "arguments": json.dumps({"command": "ls"})}}]

    assert parse_tool_calls(calls) == [{"command": "ls", "tool_call_id": "call-1"}]


def test_parse_tool_call_accepts_decoded_arguments():
    calls = [{"id": "call-2", "function": {"name": "bash", "arguments": {"command": "pwd"}}}]

    assert parse_tool_calls(calls) == [{"command": "pwd", "tool_call_id": "call-2"}]


@pytest.mark.parametrize(
    "calls",
    [
        [],
        [{"id": "call-1", "function": {"name": "bash", "arguments": "{}"}}],
        [{"id": "call-1", "function": {"name": "bash", "arguments": "not-json"}}],
        [{"id": "call-1", "function": {"name": "python", "arguments": '{"command":"ls"}'}}],
    ],
)
def test_invalid_tool_call_raises_format_error(calls):
    with pytest.raises(FormatError):
        parse_tool_calls(calls)


def test_observation_keeps_tool_call_id():
    messages = format_observation_messages(
        [{"command": "pytest -q", "tool_call_id": "call-1"}],
        [{"output": "1 passed", "returncode": 0, "exception_info": ""}],
    )

    assert messages[0]["role"] == "tool"
    assert messages[0]["tool_call_id"] == "call-1"
    assert '"returncode": 0' in messages[0]["content"]
