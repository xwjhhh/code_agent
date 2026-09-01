"""Structured objects shared by the memory write and read paths."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

MemoryExperienceType = Literal["success", "failure"]
MemoryCategory = Literal["strategy", "recovery", "optimization"]

VALID_EXPERIENCE_TYPES = {"success", "failure"}
VALID_CATEGORIES = {"strategy", "recovery", "optimization"}


@dataclass
class MemoryNode:
    category: MemoryCategory
    trigger: str
    content: str
    # Top-level meaning; category remains a secondary compatibility tag.
    experience_type: MemoryExperienceType | None = None
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
    source_task: str = ""
    evidence: list[str] = field(default_factory=list)
    failure: str = ""
    fix: str = ""
    verification: str = ""
    embedding_text: str = ""
    embedding_model: str = ""
    embedding: list[float] = field(default_factory=list, repr=False)
    source_task_embedding: list[float] = field(default_factory=list, repr=False)
    id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    retrieval_count: int = 0

    def __post_init__(self) -> None:
        if self.experience_type is None:
            # Preserve callers using the old recovery category.
            self.experience_type = "failure" if self.category == "recovery" else "success"
        if self.experience_type not in VALID_EXPERIENCE_TYPES:
            raise ValueError(f"Unsupported memory experience type: {self.experience_type}")
        if self.category not in VALID_CATEGORIES:
            raise ValueError(f"Unsupported memory category: {self.category}")
        self.priority = max(1, min(5, int(self.priority)))
        self.quality_score = max(0.0, min(1.0, float(self.quality_score)))

    def to_dict(self, include_embedding: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_embedding:
            data.pop("embedding", None)
            data.pop("source_task_embedding", None)
        return data

    def build_embedding_text(self) -> str:
        """Build the document representation used for memory-level similarity."""
        avoid = self.negative_example or "无"
        return "\n".join(
            [
                f"experience_type: {self.experience_type}",
                f"category: {self.category}",
                f"problem_family: {', '.join(self.problem_family) or '通用'}",
                f"algorithm_tags: {', '.join(self.algorithm_tags) or '无'}",
                f"trigger: {self.trigger}",
                f"constraints: {', '.join(self.constraints) or '无'}",
                f"reusable_knowledge: {self.content}",
                f"actions: {'；'.join(self.steps) or '无'}",
                f"avoid: {avoid}",
                f"failure: {self.failure or '无'}",
                f"fix: {self.fix or '无'}",
                f"verification: {self.verification or '无'}",
            ]
        )


@dataclass(frozen=True)
class MemoryQuery:
    text: str
    category: MemoryCategory | None = None
    problem_family: tuple[str, ...] = ()
    algorithm_tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RetrievedMemory:
    node: MemoryNode
    similarity: float
    query_text: str
    task_similarity: float = 0.0
    memory_similarity: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.node.to_dict(),
            "similarity": round(self.similarity, 6),
            "task_similarity": round(self.task_similarity, 6),
            "memory_similarity": round(self.memory_similarity, 6),
            "matched_query": self.query_text,
        }
