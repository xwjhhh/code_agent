"""Extract evidence-backed reasoning memories from coding runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from code_agent.memory.episodes import RecoveryEpisode, recovery_episode_context
from code_agent.memory.query_analyzer import TextModel, _strings, parse_json_object
from code_agent.memory.schemas import (
    MemoryNode,
    VALID_CATEGORIES,
    VALID_EXPERIENCE_TYPES,
)


class ExperienceExtractor:
    """Turn a verified run or a verified recovery episode into memory nodes."""

    MAX_ITEMS = 3

    def __init__(self, model: TextModel):
        self.model = model

    def extract(
        self,
        *,
        task: str,
        result: dict[str, Any],
        review: dict[str, Any] | None,
        source_run_id: str,
        experience_type: str | None = None,
        episodes: list[RecoveryEpisode] | None = None,
    ) -> list[MemoryNode]:
        """Compatibility entry point selecting the correct induction prompt."""
        selected_type = experience_type or ("failure" if episodes else "success")
        if selected_type == "failure":
            return self.extract_failure(task=task, episodes=episodes or [], source_run_id=source_run_id)
        if selected_type != "success" or not result.get("verified"):
            return []
        return self.extract_success(task=task, result=result, review=review, source_run_id=source_run_id)

    def extract_success(
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
        prompt = f"""Extract up to {self.MAX_ITEMS} high-value SUCCESS experiences from this coding run.

The final test command passed and the solution is locally verified. First reason about
which decisions actually caused success, then keep only transferable guidance.
You may return zero items. Never invent a failure or a repair that is absent from
the evidence. Do not summarize the code line by line.

Problem and constraints:
{task[:12000]}

Execution summary:
{_trajectory_summary(result)}

Final test output:
{str(result.get("last_test_output", ""))[:5000]}

Independent reviewer:
{str((review or {}).get("content", ""))[:7000]}

Final solution:
```python
{solution[:12000]}
```

Return exactly a JSON object with a memories array. Every item must have
experience_type="success". Category is only a secondary tag and should normally
be strategy or optimization; do not use recovery for a success item.
{{"memories": [
  {{
    "experience_type": "success",
    "category": "strategy|optimization",
    "trigger": "适用条件，不包含样例专属值",
    "content": "可迁移、可执行的 reasoning",
    "purpose": "它解决的目标",
    "steps": ["具体行动 1", "具体行动 2"],
    "negative_example": "应避免的做法，或 null",
    "problem_family": ["问题类型"],
    "algorithm_tags": ["算法标签"],
    "constraints": ["关键约束"],
    "evidence": ["来自本次运行的可核验证据"],
    "priority": 1
  }}
]}}

Rules: no source code, task names, sample values, variable names, file paths, or
raw trajectory narration. Do not generate generic advice such as 'consider edge
cases'. If the reviewer identifies a correctness defect, return zero success
items instead of turning that defect into a success memory. Use concise
Simplified Chinese for all natural-language fields."""
        response = self._query(prompt, "Return valid JSON only for success experiences.")
        return self._parse_nodes(response, source_run_id, "success", task)

    def extract_failure(
        self,
        *,
        task: str,
        episodes: list[RecoveryEpisode],
        source_run_id: str,
    ) -> list[MemoryNode]:
        if not episodes:
            return []
        prompt = f"""Extract up to {self.MAX_ITEMS} high-value FAILURE experiences from the verified recovery episode(s) below.

Each episode is evidence of test_failed -> code change -> test_passed. Explain
the observed failure, the repair that removed its cause, and when the lesson
transfers to another task. You may return zero items. Do not infer failures from
the final code or reviewer speculation. Merge repeated failures into one lesson.

Problem and constraints:
{task[:12000]}

Recovery evidence:
{recovery_episode_context(episodes)}

Return exactly a JSON object with a memories array. Every item must have
experience_type="failure" and category="recovery". The failure, fix, and
verification fields must be grounded in the episode evidence.
{{"memories": [
  {{
    "experience_type": "failure",
    "category": "recovery",
    "trigger": "出现什么可观察失败信号时适用",
    "content": "失败原因、修复动作和可迁移规则",
    "purpose": "避免再次失败的目标",
    "steps": ["检查失败信号", "执行修复", "重新验证"],
    "negative_example": "导致失败的做法，或 null",
    "failure": "实际失败表现和根因",
    "fix": "实际采取的修复",
    "verification": "修复后的通过证据",
    "problem_family": ["问题类型"],
    "algorithm_tags": ["算法标签"],
    "constraints": ["关键约束"],
    "evidence": ["failed_test / failure_output / passed_test 的证据"],
    "priority": 1
  }}
]}}

Rules: do not copy source code, names, sample values, paths, or raw narration.
Never create a failure item without a causal failure -> fix -> pass chain. Use
concise Simplified Chinese for all natural-language fields."""
        response = self._query(prompt, "Return valid JSON only for failure experiences.")
        return self._parse_nodes(response, source_run_id, "failure", task)

    def _query(self, prompt: str, retry_instruction: str) -> str:
        try:
            response = self.model.query_text(
                [
                    {
                        "role": "system",
                        "content": "You distill coding-agent runs into evidence-backed reasoning memories. Return JSON only. All natural-language fields must be Simplified Chinese.",
                    },
                    {"role": "user", "content": prompt},
                ]
            )
        except Exception:
            return ""
        if self._parse_json_safely(response) is not None:
            return response
        try:
            return self.model.query_text(
                [
                    {"role": "system", "content": retry_instruction},
                    {"role": "user", "content": f"Repair this into a JSON object with a memories array:\n\n{response[:12000]}"},
                ]
            )
        except Exception:
            return ""

    @classmethod
    def _parse_nodes(
        cls,
        response: str,
        source_run_id: str,
        expected_type: str,
        source_task: str,
    ) -> list[MemoryNode]:
        try:
            items = parse_json_object(response).get("memories", [])
        except (TypeError, ValueError):
            return []
        if not isinstance(items, list):
            return []
        nodes: list[MemoryNode] = []
        for item in items[: cls.MAX_ITEMS]:
            node = cls._node_from_item(item, source_run_id, expected_type, source_task)
            if node is not None:
                nodes.append(node)
        return nodes

    @staticmethod
    def _node_from_item(
        item: object,
        source_run_id: str,
        expected_type: str,
        source_task: str,
    ) -> MemoryNode | None:
        if not isinstance(item, dict) or expected_type not in VALID_EXPERIENCE_TYPES:
            return None
        item_type = str(item.get("experience_type", expected_type)).strip().lower()
        if item_type != expected_type:
            return None
        default_category = "recovery" if expected_type == "failure" else "strategy"
        category = str(item.get("category", default_category)).strip().lower()
        if category not in VALID_CATEGORIES:
            category = default_category
        trigger = str(item.get("trigger", "")).strip()
        content = str(item.get("content", "")).strip()
        if not trigger or not content:
            return None
        evidence = _strings(item.get("evidence"))
        failure = str(item.get("failure", "")).strip()
        fix = str(item.get("fix", "")).strip()
        verification = str(item.get("verification", "")).strip()
        # These fields are the trust boundary for extracted memories. A
        # failure item without a concrete fail -> fix -> pass chain is not a
        # reasoning memory, and a success item without any run evidence is
        # indistinguishable from generic advice.
        if not evidence:
            return None
        if expected_type == "failure" and not (failure and fix and verification):
            return None
        try:
            priority = int(item.get("priority", 3))
        except (TypeError, ValueError):
            priority = 3
        try:
            quality_score = float(item.get("quality_score", 0.85))
        except (TypeError, ValueError):
            quality_score = 0.85
        negative = item.get("negative_example")
        return MemoryNode(
            category=category,
            trigger=trigger,
            content=content,
            experience_type=expected_type,
            purpose=str(item.get("purpose", "")).strip(),
            steps=_strings(item.get("steps")),
            negative_example=negative.strip() if isinstance(negative, str) and negative.strip() else None,
            problem_family=_strings(item.get("problem_family")),
            algorithm_tags=_strings(item.get("algorithm_tags")),
            constraints=_strings(item.get("constraints")),
            priority=priority,
            quality_score=quality_score,
            source_run_id=source_run_id,
            source_verified=True,
            source_task=source_task,
            evidence=evidence,
            failure=failure,
            fix=fix,
            verification=verification,
        )

    @staticmethod
    def _parse_json_safely(response: str) -> dict[str, Any] | None:
        try:
            return parse_json_object(response)
        except (TypeError, ValueError):
            return None


def _read_optional(path: object) -> str:
    if not isinstance(path, str):
        return ""
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return ""


def _trajectory_summary(result: dict[str, Any]) -> str:
    entries: list[str] = []
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
