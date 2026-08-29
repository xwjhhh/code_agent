"""One entry point for the memory system lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from code_agent.memory.consolidator import MemoryConsolidator
from code_agent.memory.embedding import SiliconFlowEmbeddingClient
from code_agent.memory.extractor import ExperienceExtractor
from code_agent.memory.formatter import format_memory_context
from code_agent.memory.query_analyzer import QueryAnalyzer, TextModel
from code_agent.memory.reranker import MemoryReranker
from code_agent.memory.schemas import MemoryNode, MemoryQuery, RetrievedMemory
from code_agent.memory.store import MemoryStore


@dataclass(frozen=True)
class MemoryManagerConfig:
    recall_limit_per_query: int = 8
    selected_limit: int = 4
    min_similarity: float = 0.35
    rerank_with_llm: bool = True


@dataclass(frozen=True)
class MemoryRetrieval:
    phase: str
    queries: list[MemoryQuery]
    candidates: list[RetrievedMemory]
    selected: list[RetrievedMemory]

    @property
    def context(self) -> str:
        return format_memory_context(self.selected)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "queries": [
                {"granularity": query.granularity, "category": query.category, "text": query.text}
                for query in self.queries
            ],
            "candidate_count": len(self.candidates),
            "selected": [memory.to_dict() for memory in self.selected],
        }


class MemoryManager:
    def __init__(
        self,
        model: TextModel,
        embedder: SiliconFlowEmbeddingClient,
        store: MemoryStore,
        config: MemoryManagerConfig | None = None,
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ):
        self.model = model
        self.embedder = embedder
        self.store = store
        self.config = config or MemoryManagerConfig()
        self.query_analyzer = QueryAnalyzer(model)
        self.extractor = ExperienceExtractor(model)
        self.reranker = MemoryReranker(model)
        self.consolidator = MemoryConsolidator(store)
        self.event_callback = event_callback

    def retrieve_for_task(self, task: str) -> MemoryRetrieval:
        if self.store.count() == 0:
            return MemoryRetrieval("task", [], [], [])
        self._emit("memory_retrieval_started", phase="task")
        queries = self.query_analyzer.analyze(task)
        retrieval = self._retrieve("task", task, queries)
        self._emit("memory_retrieval_finished", **retrieval.to_dict())
        return retrieval

    def retrieve_for_failure(self, task: str, error: str, steps: list[dict[str, Any]]) -> MemoryRetrieval:
        if self.store.count() == 0:
            return MemoryRetrieval("recovery", [], [], [])
        self._emit("memory_retrieval_started", phase="recovery")
        recent = self._recent_actions(steps)
        text = f"Problem:\n{task[:8000]}\n\nPytest failure:\n{error[:5000]}\n\nRecent actions:\n{recent}"
        queries = [
            MemoryQuery("subtask", text, category="recovery"),
            MemoryQuery("task", text, category="recovery"),
        ]
        retrieval = self._retrieve("recovery", task, queries)
        self._emit("memory_retrieval_finished", **retrieval.to_dict())
        return retrieval

    def learn_from_run(
        self,
        *,
        task: str,
        result: dict[str, Any],
        review: dict[str, Any] | None,
        source_run_id: str,
    ) -> list[MemoryNode]:
        if not result.get("verified"):
            return []
        self._emit("memory_learning_started", source_run_id=source_run_id)
        candidates = self.extractor.extract(
            task=task,
            result=result,
            review=review,
            source_run_id=source_run_id,
        )
        for node in candidates:
            node.embedding_text = node.build_embedding_text()
        vectors = self.embedder.embed([node.embedding_text for node in candidates]) if candidates else []
        added: list[MemoryNode] = []
        for node, vector in zip(candidates, vectors, strict=True):
            node.embedding = vector
            node.embedding_model = self.embedder.config.model
            if not self.consolidator.is_duplicate(node):
                self.store.add(node)
                added.append(node)
        self._emit(
            "memory_learning_finished",
            extracted_count=len(candidates),
            stored_count=len(added),
            memories=[node.to_dict() for node in added],
        )
        return added

    def list_memories(self, limit: int = 100) -> list[MemoryNode]:
        return self.store.list(limit)

    def _retrieve(self, phase: str, task: str, queries: list[MemoryQuery]) -> MemoryRetrieval:
        vectors = self.embedder.embed([query.text for query in queries])
        by_id: dict[str, RetrievedMemory] = {}
        for query, vector in zip(queries, vectors, strict=True):
            for match in self.store.search(
                vector,
                category=query.category,
                granularity=query.granularity,
                limit=self.config.recall_limit_per_query,
                min_similarity=self.config.min_similarity,
                query_text=query.text,
            ):
                previous = by_id.get(match.node.id)
                if previous is None or match.similarity > previous.similarity:
                    by_id[match.node.id] = match
        candidates = sorted(
            by_id.values(),
            key=lambda item: (item.similarity, item.node.quality_score, item.node.priority),
            reverse=True,
        )
        if self.config.rerank_with_llm:
            selected = self.reranker.select(task, candidates, self.config.selected_limit)
        else:
            selected = candidates[: self.config.selected_limit]
        self.store.record_retrievals(item.node.id for item in selected)
        return MemoryRetrieval(phase, queries, candidates, selected)

    @staticmethod
    def _recent_actions(steps: list[dict[str, Any]]) -> str:
        actions = []
        for step in steps[-5:]:
            action = step.get("action") if isinstance(step, dict) else None
            if isinstance(action, dict):
                actions.append(str(action.get("command", ""))[:500])
        return "\n".join(actions) or "No prior actions recorded."

    def _emit(self, event_type: str, **data: Any) -> None:
        if self.event_callback is None:
            return
        try:
            self.event_callback(event_type, data)
        except Exception:
            pass
