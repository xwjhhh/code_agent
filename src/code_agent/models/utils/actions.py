"""Bash tool definition and tool-call message formatting."""

import json
from typing import Any

from code_agent.exceptions import FormatError

BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Execute one Bash command in the task workspace.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The Bash command to execute.",
                }
            },
            "required": ["command"],
        },
    },
}


def parse_tool_calls(tool_calls: list[Any]) -> list[dict[str, Any]]:
    if not tool_calls:
        raise FormatError(_format_error("No Bash tool call was found."))
    if len(tool_calls) != 1:
        raise FormatError(_format_error("Exactly one Bash tool call is allowed per model response."))

    actions = []
    for tool_call in tool_calls:
        function = _get(tool_call, "function")
        name = _get(function, "name")
        raw_arguments = _get(function, "arguments", "")
        tool_call_id = _get(tool_call, "id")

        if isinstance(raw_arguments, dict):
            arguments = raw_arguments
        else:
            try:
                arguments = json.loads(raw_arguments)
            except (TypeError, json.JSONDecodeError) as error:
                raise FormatError(_format_error(f"Bash arguments are not valid JSON: {error}")) from error

        if name != "bash":
            raise FormatError(_format_error(f"Unknown tool: {name!r}. Only 'bash' is available."))
        if not isinstance(arguments, dict) or not isinstance(arguments.get("command"), str):
            raise FormatError(_format_error("The Bash tool requires a string 'command' argument."))
        if not arguments["command"].strip():
            raise FormatError(_format_error("The Bash command cannot be empty."))
        if not tool_call_id:
            raise FormatError(_format_error("The Bash tool call is missing its id."))

        actions.append({"command": arguments["command"], "tool_call_id": tool_call_id})
    return actions


def format_observation_messages(
    actions: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    messages = []
    for action, output in zip(actions, outputs, strict=True):
        content = json.dumps(
            {
                "returncode": output["returncode"],
                "output": output["output"],
                "exception_info": output.get("exception_info", ""),
            },
            ensure_ascii=False,
        )
        messages.append(
            {
                "role": "tool",
                "tool_call_id": action["tool_call_id"],
                "content": content,
                "extra": {"action": action, "observation": output},
            }
        )
    return messages


def _format_error(error: str) -> dict[str, Any]:
    return {
        "role": "user",
        "content": (
            f"Tool call error: {error}\n"
            "Respond again with at least one valid bash tool call. "
            "Use the bash tool with a non-empty command string."
        ),
        "extra": {"error_type": "FormatError"},
    }


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
