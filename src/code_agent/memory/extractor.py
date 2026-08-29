"""Extract generalized, reusable experiences from a verified coding run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from code_agent.memory.query_analyzer import TextModel, _strings, parse_json_object
from code_agent.memory.schemas import MemoryNode, VALID_CATEGORIES, VALID_GRANULARITIES


class ExperienceExtractor:
    def __init__(self, model: TextModel):
        self.model = model

    def extract(
        self,
        *,
        task: str,
        result: dict[str, Any],
        review: dict[str, Any] | None,
        source_run_id: str,
    ) -> list[MemoryNode]:
        if not result.get("verified"):
            return []
        solution = _read_optional(result.get("solution_path"))
        response = self.model.query_text(
            [
                {
                    "role": "system",
                    "content": "You distill verified coding-agent execution into concise reusable procedural memories. Return JSON only. All natural-language values must be written in Simplified Chinese. Keep category and granularity as the exact lowercase English enum values.",
                },
                {
                    "role": "user",
                    "content": f"""Extract up to six high-value reusable experiences from this verified coding run.

Problem:
{task[:12000]}

Execution summary:
{_trajectory_summary(result)}

Local test output:
{str(result.get("last_test_output", ""))[:3000]}

Reviewer result:
{str((review or {}).get("content", ""))[:5000]}

Final solution:
```python
{solution[:10000]}
```

Return exactly this JSON object. The values of trigger, content, purpose, steps, negative_example, problem_family, algorithm_tags, and constraints must be concise Simplified Chinese (do not write these fields in English):
{{"memories": [
  {{
    "category": "strategy|recovery|optimization",
    "granularity": "task|subtask",
    "trigger": "适用条件（不要包含样例专属值）",
    "content": "可复用、可执行的知识",
    "purpose": "希望达成的目标",
    "steps": ["具体行动 1", "具体行动 2"],
    "negative_example": "需要避免的做法，或 null",
    "problem_family": ["问题类型"],
    "algorithm_tags": ["算法标签"],
    "constraints": ["约束条件"],
    "priority": 1
  }}
]}}

Rules: do not copy source code, task names, sample values, variable names, file paths, or raw trajectory narration. Keep only experiences that state when they apply and what action to take. A recovery memory must describe a failure signal and successful repair. Do not produce generic advice such as 'consider edge cases'. Use Simplified Chinese even when the problem statement or reviewer result is in English.""",
                },
            ]
        )
        nodes = self._parse_nodes(response, source_run_id)
        if nodes:
            return nodes

        # Provider responses occasionally contain explanatory text or omit an
        # enum field. A single strict retry keeps a verified run from losing
        # its experience solely because of a transient formatting error.
        try:
            retry_response = self.model.query_text(
                [
                    {
                        "role": "system",
                        "content": "Return valid JSON only. Do not use Markdown fences or commentary. Use category strategy, recovery, or optimization and granularity task or subtask.",
                    },
                    {
                        "role": "user",
                        "content": f"Repair this experience extraction into a JSON object with a memories array. Keep the useful Chinese experiences and include trigger, content, purpose, steps, negative_example, problem_family, algorithm_tags, constraints, priority, category, and granularity for every item.\n\n{response[:12000]}",
                    },
                ]
            )
        except Exception:
            return []
        return self._parse_nodes(retry_response, source_run_id)

    @classmethod
    def _parse_nodes(cls, response: str, source_run_id: str) -> list[MemoryNode]:
        try:
            items = parse_json_object(response).get("memories", [])
        except (TypeError, ValueError):
            return []
        if not isinstance(items, list):
            return []
        nodes: list[MemoryNode] = []
        for item in items[:6]:
            node = cls._node_from_item(item, source_run_id)
            if node is not None:
                nodes.append(node)
        return nodes

    @staticmethod
    def _node_from_item(item: object, source_run_id: str) -> MemoryNode | None:
        if not isinstance(item, dict):
            return None
        category = str(item.get("category", "")).strip().lower()
        granularity = str(item.get("granularity", "")).strip().lower()
        trigger = str(item.get("trigger", "")).strip()
        content = str(item.get("content", "")).strip()
        if category not in VALID_CATEGORIES or granularity not in VALID_GRANULARITIES or not trigger or not content:
            return None
        try:
            priority = int(item.get("priority", 3))
        except (TypeError, ValueError):
            priority = 3
        negative = item.get("negative_example")
        return MemoryNode(
            category=category,
            granularity=granularity,
            trigger=trigger,
            content=content,
            purpose=str(item.get("purpose", "")).strip(),
            steps=_strings(item.get("steps")),
            negative_example=negative.strip() if isinstance(negative, str) and negative.strip() else None,
            problem_family=_strings(item.get("problem_family")),
            algorithm_tags=_strings(item.get("algorithm_tags")),
            constraints=_strings(item.get("constraints")),
            priority=priority,
            quality_score=0.85,
            source_run_id=source_run_id,
            source_verified=True,
        )


def _read_optional(path: object) -> str:
    if not isinstance(path, str):
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _trajectory_summary(result: dict[str, Any]) -> str:
    entries = []
    for step in result.get("steps", [])[-20:]:
        if not isinstance(step, dict):
            continue
        action = step.get("action")
        observation = step.get("observation")
        if isinstance(action, dict):
            command = str(action.get("command", "")).replace("\n", " ")[:400]
            output = str((observation or {}).get("output", "")).replace("\n", " ")[:600] if isinstance(observation, dict) else ""
            entries.append(f"command: {command}\nresult: {output}")
    return "\n---\n".join(entries) or "No action trace available."
