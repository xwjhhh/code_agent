"""One entry point for the memory system lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable

from code_agent.memory.consolidator import MemoryConsolidator
from code_agent.memory.embedding import SiliconFlowEmbeddingClient
from code_agent.memory.extractor import ExperienceExtractor
from code_agent.memory.formatter import format_memory_context
from code_agent.memory.query_analyzer import QueryAnalyzer, TextModel
from code_agent.memory.reranker import MemoryReranker
from code_agent.memory.router import MemoryRelevance, MemoryRelevanceGrader, MemoryRoute, MemoryRouter
from code_agent.memory.schemas import MemoryNode, MemoryQuery, RetrievedMemory
from code_agent.memory.store import MemoryStore


@dataclass(frozen=True)
class MemoryManagerConfig:
    recall_limit_per_query: int = 8
    selected_limit: int = 4
    min_similarity: float = 0.35
    rerank_with_llm: bool = True
    route_with_llm: bool = True
    grade_with_llm: bool = True
    max_query_rewrites: int = 2


@dataclass(frozen=True)
class MemoryRetrieval:
    phase: str
    queries: list[MemoryQuery]
    candidates: list[RetrievedMemory]
    selected: list[RetrievedMemory]
    route_action: str | None = None
    route_reason: str = ""
    grade_relevant: bool | None = None
    grade_reason: str = ""
    grade_score: float | None = None
    rewrite_count: int = 0

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
            "route_action": self.route_action,
            "route_reason": self.route_reason,
            "grade_relevant": self.grade_relevant,
            "grade_reason": self.grade_reason,
            "grade_score": self.grade_score,
            "rewrite_count": self.rewrite_count,
        }

    def with_agentic_metadata(
        self,
        *,
        route: MemoryRoute | None = None,
        relevant: bool | None = None,
        grade_reason: str = "",
        grade_score: float | None = None,
        rewrite_count: int = 0,
        selected: list[RetrievedMemory] | None = None,
    ) -> "MemoryRetrieval":
        return replace(
            self,
            selected=self.selected if selected is None else selected,
            route_action=route.action if route else self.route_action,
            route_reason=route.reason if route else self.route_reason,
            grade_relevant=relevant,
            grade_reason=grade_reason,
            grade_score=grade_score,
            rewrite_count=rewrite_count,
        )


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
        self.router = MemoryRouter(model)
        self.relevance_grader = MemoryRelevanceGrader(model)
        self.consolidator = MemoryConsolidator(store)
        self.event_callback = event_callback

    def retrieve_agentic(self, task: str) -> MemoryRetrieval:
        """Route, retrieve, grade, and rewrite a task query a bounded number of times."""
        if self.store.count() == 0:
            route = MemoryRoute("skip", task, "记忆库为空，跳过检索")
            retrieval = MemoryRetrieval("task", [], [], [], route_action="skip", route_reason=route.reason)
            self._emit("memory_route_decided", phase="task", action=route.action, reason=route.reason)
            return retrieval

        route = self.router.decide(task) if self.config.route_with_llm else MemoryRoute("retrieve", task, "配置要求检索")
        self._emit(
            "memory_route_decided",
            phase="task",
            action=route.action,
            query=route.query,
            reason=route.reason,
            fallback=route.fallback,
        )
        if route.action == "skip":
            return MemoryRetrieval("task", [], [], [], route_action="skip", route_reason=route.reason)

        query = route.query or task
        rewrite_count = 0
        while True:
            retrieval = self.retrieve_for_task(query)
            grade = self.relevance_grader.grade(task, retrieval.selected) if self.config.grade_with_llm else self._fallback_grade(retrieval.selected)
            self._emit(
                "memory_relevance_graded",
                phase="task",
                relevant=grade.relevant,
                score=grade.score,
                reason=grade.reason,
                fallback=grade.fallback,
                rewrite_count=rewrite_count,
            )
            annotated = retrieval.with_agentic_metadata(
                route=route,
                relevant=grade.relevant,
                grade_reason=grade.reason,
                grade_score=grade.score,
                rewrite_count=rewrite_count,
                selected=retrieval.selected if grade.relevant else [],
            )
            if grade.relevant or rewrite_count >= max(0, self.config.max_query_rewrites):
                if not grade.relevant:
                    self.store.record_retrievals([])
                return annotated

            rewritten = self.router.rewrite(task, query, grade.reason)
            if not rewritten or rewritten.casefold() == query.casefold():
                return annotated
            rewrite_count += 1
            self._emit(
                "memory_query_rewritten",
                phase="task",
                previous_query=query,
                query=rewritten,
                attempt=rewrite_count,
                reason=grade.reason,
            )
            query = rewritten

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
        grade = self.relevance_grader.grade(task, retrieval.selected) if self.config.grade_with_llm else self._fallback_grade(retrieval.selected)
        self._emit(
            "memory_relevance_graded",
            phase="recovery",
            relevant=grade.relevant,
            score=grade.score,
            reason=grade.reason,
            fallback=grade.fallback,
            rewrite_count=0,
        )
        retrieval = retrieval.with_agentic_metadata(
            relevant=grade.relevant,
            grade_reason=grade.reason,
            grade_score=grade.score,
            selected=retrieval.selected if grade.relevant else [],
        )
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
    def _fallback_grade(selected: list[RetrievedMemory]) -> MemoryRelevance:
        return MemoryRelevance(
            relevant=bool(selected),
            reason="使用已召回经验",
            score=max((item.similarity for item in selected), default=0.0),
            fallback=True,
        )

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
