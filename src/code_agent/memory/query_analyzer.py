"""Turn a new coding task into task-level and subtask-level memory queries."""

from __future__ import annotations

import json
from typing import Any, Protocol

from code_agent.memory.schemas import MemoryQuery


class TextModel(Protocol):
    def query_text(self, messages: list[dict[str, Any]], **kwargs: Any) -> str: ...


class QueryAnalyzer:
    def __init__(self, model: TextModel):
        self.model = model

    def analyze(self, task: str) -> list[MemoryQuery]:
        fallback = [MemoryQuery(granularity="task", text=task)]
        try:
            response = self.model.query_text(
                [
                    {
                        "role": "system",
                        "content": "You analyze algorithm problems for a reusable experience-memory retriever. Return JSON only.",
                    },
                    {
                        "role": "user",
                        "content": f"""Analyze this programming problem and produce search queries for past reusable experience.

Problem:
{task[:12000]}

Return exactly one JSON object:
{{
  "task_query": "a concise description of the overall problem structure",
  "subtask_queries": ["up to three concrete algorithm, implementation, validation, or input-output concerns"],
  "problem_family": ["array", "graph", "string", ...],
  "algorithm_tags": ["sliding-window", "dijkstra", ...]
}}

Do not solve the problem. Do not include sample-specific values.""",
                    },
                ]
            )
        except Exception:
            return fallback
        try:
            data = parse_json_object(response)
            family = tuple(_strings(data.get("problem_family")))
            tags = tuple(_strings(data.get("algorithm_tags")))
            task_query = str(data.get("task_query", "")).strip()
            queries = [
                MemoryQuery("task", task_query, problem_family=family, algorithm_tags=tags)
            ] if task_query else fallback
            for query in _strings(data.get("subtask_queries"))[:3]:
                queries.append(MemoryQuery("subtask", query, problem_family=family, algorithm_tags=tags))
            return queries
        except (TypeError, ValueError, json.JSONDecodeError):
            return fallback


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Expected a JSON object.")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed


def _strings(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
