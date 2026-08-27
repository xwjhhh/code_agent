"""Independent, read-only review of a locally verified solution."""

from pathlib import Path
from typing import Any, Protocol


class TextModel(Protocol):
    def query_text(self, messages: list[dict[str, Any]], **kwargs: Any) -> str: ...


class Reviewer:
    def __init__(self, model: TextModel):
        self.model = model

    def review(self, task: str, agent_result: dict[str, Any]) -> dict[str, Any]:
        if agent_result.get("status") != "success" or not agent_result.get("verified"):
            raise ValueError("Reviewer can run only after local verification succeeds.")

        solution_path = Path(agent_result["solution_path"])
        test_path = Path(agent_result["test_path"])
        solution = solution_path.read_text(encoding="utf-8")
        tests = test_path.read_text(encoding="utf-8")
        prompt = f"""Review this algorithm solution independently.

Problem:
{task}

Solution:
```python
{solution}
```

Locally generated tests:
```python
{tests}
```

Local test output:
{agent_result.get('last_test_output', '')}

Respond in Chinese with these sections:
1. Algorithm approach
2. Time and space complexity
3. Boundary cases
4. Test coverage
5. Potential risks and code quality

State only that local verification passed. Do not claim that hidden online judge tests are guaranteed to pass.
"""
        content = self.model.query_text(
            [
                {
                    "role": "system",
                    "content": "You are a read-only algorithm code reviewer. Do not propose tool calls or modify files.",
                },
                {"role": "user", "content": prompt},
            ]
        )
        return {
            "status": "completed",
            "local_verification": "passed",
            "content": content,
        }
