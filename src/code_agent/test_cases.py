"""Canonical test-case files and model-assisted test generation."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Protocol


class TextModel(Protocol):
    def query_text(self, messages: list[dict[str, Any]], **kwargs: Any) -> str: ...


TEST_CASES_FILENAME = "test_cases.json"
TEST_RUNNER_FILENAME = "test_solution.py"


def task_with_test_file(task: str, case_count: int) -> str:
    return (
        f"{task}\n\n"
        f"测试输入输出已经保存在工作目录中的 {TEST_CASES_FILENAME}，共有 {case_count} 个用例。"
        "该文件是输入格式和输出格式的权威说明。开始编码前必须先读取它；"
        "solution.py 必须提供 solve(input_text: str) -> str。"
        f"禁止修改 {TEST_CASES_FILENAME} 和 {TEST_RUNNER_FILENAME}。"
    )


def normalize_cases(cases: list[dict[str, Any]], source: str) -> list[dict[str, str]]:
    normalized = []
    for index, case in enumerate(cases, start=1):
        input_value = str(case.get("input", ""))
        expected = str(case.get("expected_output", ""))
        name = str(case.get("name") or f"case_{index}")
        normalized.append({"name": name, "input": input_value, "expected_output": expected, "source": source})
    if not normalized:
        raise ValueError("至少需要一个测试用例。")
    return normalized


def save_test_files(workspace: Path, task: str, cases: list[dict[str, str]], source: str) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "source": source, "problem": task, "cases": cases}
    (workspace / TEST_CASES_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (workspace / TEST_RUNNER_FILENAME).write_text(_pytest_runner(), encoding="utf-8")


def load_test_cases(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("test_cases.json 中的 cases 必须是数组。")
    return normalize_cases(cases, str(payload.get("source", "unknown")))


def generate_test_cases(model: TextModel, task: str, count: int = 6) -> list[dict[str, str]]:
    generator = getattr(model, "generate_test_cases", None)
    if callable(generator):
        return normalize_cases(generator(task, count), "generated")

    prompt = f"""根据下面的算法题生成 {count} 个具有确定答案的测试用例。

题目：
{task}

只返回 JSON 数组，不要 Markdown，不要解释。每个元素必须是：
{{"name": "简短名称", "input": "完整标准输入文本", "expected_output": "完整标准输出文本"}}

input 和 expected_output 都必须是字符串。输入要严格符合题目输入格式，输出要严格符合题目输出格式。覆盖题目样例、边界情况和典型情况，不要生成无法从题目确定答案的用例。
"""
    content = model.query_text(
        [
            {"role": "system", "content": "你是算法题测试设计器，只输出合法 JSON。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
    )
    return normalize_cases(_parse_json_array(content), "generated")


def _parse_json_array(content: str) -> list[dict[str, Any]]:
    text = content.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"测试生成模型没有返回合法 JSON：{error}") from error
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("测试生成模型必须返回 JSON 对象数组。")
    return value


def _pytest_runner() -> str:
    return '''import json
from pathlib import Path

import pytest

from solution import solve


def normalize_output(value):
    return str(value).replace("\\r\\n", "\\n").rstrip("\\n")


payload = json.loads(Path("test_cases.json").read_text(encoding="utf-8"))
CASES = payload["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_solution(case):
    actual = solve(case["input"])
    assert normalize_output(actual) == normalize_output(case["expected_output"])
'''
