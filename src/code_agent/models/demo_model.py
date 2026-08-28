"""Deterministic model used to demo the complete local pipeline without an API key."""

import json
from typing import Any

from code_agent.models.utils.actions import format_observation_messages


class DemoModel:
    """A tiny scripted model for smoke tests and UI demos.

    It deliberately uses the same assistant tool-call shape as the LiteLLM adapter,
    so the Agent loop and local executor are exercised rather than mocked out.
    """

    def __init__(self, task: str, test_cases: list[dict[str, str]] | None = None):
        self.task = task
        self.test_cases = test_cases or []
        self.calls = 0

    def query(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        self.calls += 1
        if self.calls == 1:
            command = self._write_files_command()
        elif self.calls == 2:
            command = "python -m pytest -q"
        else:
            command = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
        call_id = f"demo-call-{self.calls}"
        return {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": call_id, "type": "function", "function": {"name": "bash", "arguments": json.dumps({"command": command})}}],
            "extra": {"actions": [{"command": command, "tool_call_id": call_id}]},
        }

    def format_message(self, **kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    def format_observation_messages(self, message: dict[str, Any], outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return format_observation_messages(message.get("extra", {}).get("actions", []), outputs)

    def serialize(self) -> dict[str, Any]:
        return {"model_type": type(self).__name__, "model": "demo"}

    def query_text(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        return "算法思路：使用一次线性扫描完成处理。\n时间复杂度：O(n)。\n空间复杂度：O(n)。\n测试覆盖了样例和边界输入。"

    def generate_test_cases(self, task: str, count: int = 6) -> list[dict[str, str]]:
        if "加密" in task:
            cases = [
                {"name": "题目样例", "input": "I love 007", "expected_output": "L oryh 007"},
                {"name": "字母回绕", "input": "xyz XYZ", "expected_output": "abc ABC"},
                {"name": "非字母", "input": "123-+", "expected_output": "123-+"},
            ]
        else:
            cases = [
                {"name": "题目样例", "input": "ab4f35gr#a6", "expected_output": "abfgr#a4356"},
                {"name": "数字交错", "input": "a1b2", "expected_output": "ab12"},
                {"name": "没有数字", "input": "abc#", "expected_output": "abc#"},
                {"name": "全部数字", "input": "123", "expected_output": "123"},
                {"name": "空输入", "input": "", "expected_output": ""},
            ]
        return cases[:count]

    def _write_files_command(self) -> str:
        if "加密" in self.task:
            solution = '''def solve(s: str) -> str:
    result = []
    for char in s:
        if "a" <= char <= "z":
            result.append(chr((ord(char) - ord("a") + 3) % 26 + ord("a")))
        elif "A" <= char <= "Z":
            result.append(chr((ord(char) - ord("A") + 3) % 26 + ord("A")))
        else:
            result.append(char)
    return "".join(result)
'''
        elif "数字字符" in self.task or "字符移动" in self.task or "非数字" in self.task:
            solution = '''def solve(s: str) -> str:
    letters = [char for char in s if not char.isdigit()]
    digits = [char for char in s if char.isdigit()]
    return "".join(letters + digits)
'''
        else:
            solution = '''def solve(s: str) -> str:
    return s
'''
        return f"cat > solution.py <<'PY'\n{solution.rstrip()}\nPY"
