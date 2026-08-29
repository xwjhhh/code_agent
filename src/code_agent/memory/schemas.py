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
        # Keep the embedded document bilingual at the structural level while
        # preserving the original Chinese memory text verbatim.
        avoid = self.negative_example or "无"
        return "\n".join(
            [
                f"记忆类型: {self.category}",
                f"记忆层级: {self.granularity}",
                f"问题类型: {', '.join(self.problem_family) or '通用'}",
                f"算法标签: {', '.join(self.algorithm_tags) or '无'}",
                f"适用条件: {self.trigger}",
                f"约束条件: {', '.join(self.constraints) or '无'}",
                f"可复用知识: {self.content}",
                f"行动步骤: {'；'.join(self.steps) or '无'}",
                f"需要避免: {avoid}",
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
