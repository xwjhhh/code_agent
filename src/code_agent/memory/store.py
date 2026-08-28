"""SQLite persistence and local cosine search for structured memories."""

from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Iterable

from code_agent.memory.schemas import MemoryNode, RetrievedMemory


class MemoryStore:
    def __init__(self, database_path: str | Path):
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add(self, node: MemoryNode) -> None:
        if not node.embedding:
            raise ValueError("A memory must have an embedding before it can be stored.")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO memories (
                    id, category, granularity, trigger_text, content, purpose,
                    steps_json, negative_example, problem_family_json,
                    algorithm_tags_json, constraints_json, priority, quality_score,
                    source_run_id, source_verified, embedding_text, embedding_model,
                    embedding_json, created_at, retrieval_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._values(node),
            )

    def count(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM memories").fetchone()
        return int(row[0])

    def list(self, limit: int = 100) -> list[MemoryNode]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (max(1, limit),)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def search(
        self,
        query_embedding: list[float],
        *,
        category: str | None = None,
        granularity: str | None = None,
        limit: int = 10,
        min_similarity: float = 0.0,
        query_text: str = "",
    ) -> list[RetrievedMemory]:
        clauses: list[str] = []
        parameters: list[str] = []
        if category:
            clauses.append("category = ?")
            parameters.append(category)
        if granularity:
            clauses.append("granularity = ?")
            parameters.append(granularity)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM memories {where}", parameters).fetchall()

        matches = []
        for row in rows:
            node = self._from_row(row)
            similarity = cosine_similarity(query_embedding, node.embedding)
            if similarity >= min_similarity:
                matches.append(RetrievedMemory(node=node, similarity=similarity, query_text=query_text))
        matches.sort(
            key=lambda item: (item.similarity, item.node.quality_score, item.node.priority),
            reverse=True,
        )
        return matches[: max(1, limit)]

    def record_retrievals(self, memory_ids: Iterable[str]) -> None:
        ids = list(dict.fromkeys(memory_ids))
        if not ids:
            return
        with self._connect() as connection:
            connection.executemany(
                "UPDATE memories SET retrieval_count = retrieval_count + 1 WHERE id = ?",
                [(memory_id,) for memory_id in ids],
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    granularity TEXT NOT NULL,
                    trigger_text TEXT NOT NULL,
                    content TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    steps_json TEXT NOT NULL,
                    negative_example TEXT,
                    problem_family_json TEXT NOT NULL,
                    algorithm_tags_json TEXT NOT NULL,
                    constraints_json TEXT NOT NULL,
                    priority INTEGER NOT NULL,
                    quality_score REAL NOT NULL,
                    source_run_id TEXT NOT NULL,
                    source_verified INTEGER NOT NULL,
                    embedding_text TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    retrieval_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memories(category, granularity)")

    @staticmethod
    def _values(node: MemoryNode) -> tuple:
        return (
            node.id,
            node.category,
            node.granularity,
            node.trigger,
            node.content,
            node.purpose,
            json.dumps(node.steps, ensure_ascii=False),
            node.negative_example,
            json.dumps(node.problem_family, ensure_ascii=False),
            json.dumps(node.algorithm_tags, ensure_ascii=False),
            json.dumps(node.constraints, ensure_ascii=False),
            node.priority,
            node.quality_score,
            node.source_run_id,
            int(node.source_verified),
            node.embedding_text,
            node.embedding_model,
            json.dumps(node.embedding),
            node.created_at,
            node.retrieval_count,
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> MemoryNode:
        return MemoryNode(
            id=row["id"],
            category=row["category"],
            granularity=row["granularity"],
            trigger=row["trigger_text"],
            content=row["content"],
            purpose=row["purpose"],
            steps=json.loads(row["steps_json"]),
            negative_example=row["negative_example"],
            problem_family=json.loads(row["problem_family_json"]),
            algorithm_tags=json.loads(row["algorithm_tags_json"]),
            constraints=json.loads(row["constraints_json"]),
            priority=row["priority"],
            quality_score=row["quality_score"],
            source_run_id=row["source_run_id"],
            source_verified=bool(row["source_verified"]),
            embedding_text=row["embedding_text"],
            embedding_model=row["embedding_model"],
            embedding=json.loads(row["embedding_json"]),
            created_at=row["created_at"],
            retrieval_count=row["retrieval_count"],
        )


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return dot / (left_norm * right_norm)
