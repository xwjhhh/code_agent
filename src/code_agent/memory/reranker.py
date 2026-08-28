"""Select a compact, non-conflicting subset after vector candidate recall."""

from __future__ import annotations

from typing import Any

from code_agent.memory.query_analyzer import TextModel, parse_json_object
from code_agent.memory.schemas import RetrievedMemory


class MemoryReranker:
    def __init__(self, model: TextModel):
        self.model = model

    def select(self, task: str, candidates: list[RetrievedMemory], limit: int) -> list[RetrievedMemory]:
        fallback = candidates[:limit]
        if len(candidates) <= limit:
            return fallback
        compact = [
            {
                "id": item.node.id,
                "category": item.node.category,
                "granularity": item.node.granularity,
                "trigger": item.node.trigger,
                "content": item.node.content,
                "steps": item.node.steps,
                "similarity": round(item.similarity, 3),
                "quality_score": item.node.quality_score,
            }
            for item in candidates[:20]
        ]
        try:
            response = self.model.query_text(
                [
                    {
                        "role": "system",
                        "content": "You select advisory experience memories for an algorithm coding agent. Return JSON only.",
                    },
                    {
                        "role": "user",
                        "content": f"""Current problem:
{task[:12000]}

Candidate memories:
{compact}

Select at most {limit} memory ids. Prefer applicable, actionable, high-quality, non-redundant advice. Reject candidates that merely have similar wording but imply a different algorithm. Return exactly {{"selected_ids": ["id", ...]}}.""",
                    },
                ]
            )
            ids = parse_json_object(response).get("selected_ids", [])
            if not isinstance(ids, list):
                return fallback
            selected_ids = [item for item in ids if isinstance(item, str)]
            by_id = {item.node.id: item for item in candidates}
            selected = [by_id[memory_id] for memory_id in selected_ids if memory_id in by_id]
            return selected[:limit] or fallback
        except Exception:
            return fallback
