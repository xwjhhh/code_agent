"""Keep the first memory store compact by suppressing near duplicates."""

from __future__ import annotations

from code_agent.memory.schemas import MemoryNode
from code_agent.memory.store import MemoryStore


class MemoryConsolidator:
    def __init__(self, store: MemoryStore, duplicate_threshold: float = 0.96):
        self.store = store
        self.duplicate_threshold = duplicate_threshold

    def is_duplicate(self, node: MemoryNode) -> bool:
        matches = self.store.search(
            node.embedding,
            category=node.category,
            granularity=node.granularity,
            limit=1,
            min_similarity=self.duplicate_threshold,
            query_text=node.embedding_text,
        )
        return bool(matches)
