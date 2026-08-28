"""Structured objects shared by the memory write and read paths."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

MemoryCategory = Literal["strategy", "recovery", "optimization"]
MemoryGranularity = Literal["task", "subtask"]

VALID_CATEGORIES = {"strategy", "recovery", "optimization"}
VALID_GRANULARITIES = {"task", "subtask"}


@dataclass
class MemoryNode:
    category: MemoryCategory
    granularity: MemoryGranularity
    trigger: str
    content: str
    purpose: str = ""
    steps: list[str] = field(default_factory=list)
    negative_example: str | None = None
    problem_family: list[str] = field(default_factory=list)
    algorithm_tags: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    priority: int = 3
    quality_score: float = 1.0
    source_run_id: str = ""
    source_verified: bool = True
    embedding_text: str = ""
    embedding_model: str = ""
    embedding: list[float] = field(default_factory=list, repr=False)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    retrieval_count: int = 0

    def __post_init__(self) -> None:
        if self.category not in VALID_CATEGORIES:
            raise ValueError(f"Unsupported memory category: {self.category}")
        if self.granularity not in VALID_GRANULARITIES:
            raise ValueError(f"Unsupported memory granularity: {self.granularity}")
        self.priority = max(1, min(5, int(self.priority)))
        self.quality_score = max(0.0, min(1.0, float(self.quality_score)))

    def to_dict(self, include_embedding: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_embedding:
            data.pop("embedding", None)
        return data

    def build_embedding_text(self) -> str:
        avoid = self.negative_example or "None"
        return "\n".join(
            [
                f"Memory Type: {self.category}",
                f"Granularity: {self.granularity}",
                f"Problem Family: {', '.join(self.problem_family) or 'general'}",
                f"Algorithm Tags: {', '.join(self.algorithm_tags) or 'none'}",
                f"Trigger: {self.trigger}",
                f"Constraints: {', '.join(self.constraints) or 'none'}",
                f"Reusable Knowledge: {self.content}",
                f"Action Steps: {'; '.join(self.steps) or 'none'}",
                f"Avoid: {avoid}",
            ]
        )


@dataclass(frozen=True)
class MemoryQuery:
    granularity: MemoryGranularity
    text: str
    category: MemoryCategory | None = None
    problem_family: tuple[str, ...] = ()
    algorithm_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievedMemory:
    node: MemoryNode
    similarity: float
    query_text: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.node.to_dict(),
            "similarity": round(self.similarity, 6),
            "matched_query": self.query_text,
        }
