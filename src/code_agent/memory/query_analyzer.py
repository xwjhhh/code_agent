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
                        "content": "You analyze algorithm problems for a reusable experience-memory retriever. Return JSON only. Write task_query and subtask_queries in concise Simplified Chinese; keep problem_family and algorithm_tags as short stable tags.",
                    },
                    {
                        "role": "user",
                        "content": f"""Analyze this programming problem and produce search queries for past reusable experience.

Problem:
{task[:12000]}

Return exactly one JSON object. The query fields must be written in Simplified Chinese so they match the Chinese memories saved by the system:
{{
  "task_query": "用简体中文描述整体问题结构",
  "subtask_queries": ["最多三个具体的算法、实现、校验或输入输出关注点（使用简体中文）"],
  "problem_family": ["array", "graph", "string", ...],
  "algorithm_tags": ["sliding-window", "dijkstra", ...]
}}

Do not solve the problem. Do not include sample-specific values. Keep the two query fields in Simplified Chinese; stable metadata tags may remain short English identifiers for matching.""",
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
