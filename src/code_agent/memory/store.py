"""SQLite persistence and weighted cosine search for structured memories."""

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
                    id, category, experience_type, trigger_text, content, purpose,
                    steps_json, negative_example, problem_family_json, algorithm_tags_json,
                    constraints_json, priority, quality_score, source_run_id, source_verified,
                    source_task, evidence_json, failure_text, fix_text, verification_text,
                    embedding_text, embedding_model, embedding_json, source_task_embedding_json,
                    created_at, retrieval_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._values(node),
            )

    def count(self, *, verified_only: bool = False) -> int:
        with self._connect() as connection:
            query = "SELECT COUNT(*) FROM memories"
            if verified_only:
                query += " WHERE source_verified = 1"
            row = connection.execute(query).fetchone()
        return int(row[0])

    def list(self, limit: int = 100, *, verified_only: bool = False) -> list[MemoryNode]:
        with self._connect() as connection:
            where = "WHERE source_verified = 1" if verified_only else ""
            rows = connection.execute(
                f"SELECT * FROM memories {where} ORDER BY created_at DESC LIMIT ?", (max(1, limit),)
            ).fetchall()
        return [self._from_row(row) for row in rows]

    def search(
        self,
        query_embedding: list[float],
        *,
        task_embedding: list[float] | None = None,
        experience_type: str | None = None,
        category: str | None = None,
        verified_only: bool = False,
        limit: int = 10,
        min_similarity: float = 0.0,
        query_text: str = "",
    ) -> list[RetrievedMemory]:
        clauses: list[str] = []
        parameters: list[str | int] = []
        if experience_type:
            clauses.append("experience_type = ?")
            parameters.append(experience_type)
        if category:
            clauses.append("category = ?")
            parameters.append(category)
        if verified_only:
            clauses.append("source_verified = 1")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(f"SELECT * FROM memories {where}", parameters).fetchall()

        matches: list[RetrievedMemory] = []
        for row in rows:
            node = self._from_row(row)
            memory_similarity = cosine_similarity(query_embedding, node.embedding)
            if task_embedding and node.source_task_embedding:
                task_similarity = cosine_similarity(task_embedding, node.source_task_embedding)
                score = 0.6 * task_similarity + 0.4 * memory_similarity
            else:
                # Legacy rows do not have source-task vectors; retain useful
                # retrieval by falling back to their memory vector.
                task_similarity = memory_similarity
                score = memory_similarity
            if score >= min_similarity:
                matches.append(
                    RetrievedMemory(
                        node=node,
                        similarity=score,
                        query_text=query_text,
                        task_similarity=task_similarity,
                        memory_similarity=memory_similarity,
                    )
                )
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
                    experience_type TEXT NOT NULL DEFAULT 'success',
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
                    source_task TEXT NOT NULL DEFAULT '',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    failure_text TEXT NOT NULL DEFAULT '',
                    fix_text TEXT NOT NULL DEFAULT '',
                    verification_text TEXT NOT NULL DEFAULT '',
                    embedding_text TEXT NOT NULL,
                    embedding_model TEXT NOT NULL,
                    embedding_json TEXT NOT NULL,
                    source_task_embedding_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    retrieval_count INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)").fetchall()}
            additions = {
                "experience_type": "TEXT NOT NULL DEFAULT 'success'",
                "source_task": "TEXT NOT NULL DEFAULT ''",
                "evidence_json": "TEXT NOT NULL DEFAULT '[]'",
                "failure_text": "TEXT NOT NULL DEFAULT ''",
                "fix_text": "TEXT NOT NULL DEFAULT ''",
                "verification_text": "TEXT NOT NULL DEFAULT ''",
                "source_task_embedding_json": "TEXT NOT NULL DEFAULT '[]'",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE memories ADD COLUMN {name} {declaration}")
            # Existing recovery nodes were generated before evidence-backed
            # episodes existed. Quarantine them rather than treating them as
            # verified failure experience.
            connection.execute(
                """
                UPDATE memories
                SET experience_type = 'failure', source_verified = 0
                WHERE category = 'recovery' AND source_task = '' AND evidence_json = '[]'
                """
            )
            connection.execute("DROP INDEX IF EXISTS idx_memory_type")
            if "granularity" in columns:
                # Drop the obsolete task/subtask field while preserving all
                # memory content and vectors in existing databases.
                try:
                    connection.execute("ALTER TABLE memories DROP COLUMN granularity")
                except sqlite3.OperationalError:
                    self._rebuild_without_granularity(connection)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_memory_type ON memories(experience_type, category)")

    @staticmethod
    def _rebuild_without_granularity(connection: sqlite3.Connection) -> None:
        columns = (
            "id, category, experience_type, trigger_text, content, purpose, "
            "steps_json, negative_example, problem_family_json, algorithm_tags_json, "
            "constraints_json, priority, quality_score, source_run_id, source_verified, "
            "source_task, evidence_json, failure_text, fix_text, verification_text, "
            "embedding_text, embedding_model, embedding_json, source_task_embedding_json, "
            "created_at, retrieval_count"
        )
        connection.execute("ALTER TABLE memories RENAME TO memories_with_legacy_granularity")
        connection.execute(
            """
            CREATE TABLE memories (
                id TEXT PRIMARY KEY,
                category TEXT NOT NULL,
                experience_type TEXT NOT NULL DEFAULT 'success',
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
                source_task TEXT NOT NULL DEFAULT '',
                evidence_json TEXT NOT NULL DEFAULT '[]',
                failure_text TEXT NOT NULL DEFAULT '',
                fix_text TEXT NOT NULL DEFAULT '',
                verification_text TEXT NOT NULL DEFAULT '',
                embedding_text TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                source_task_embedding_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                retrieval_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            f"INSERT INTO memories ({columns}) SELECT {columns} FROM memories_with_legacy_granularity"
        )
        connection.execute("DROP TABLE memories_with_legacy_granularity")

    @staticmethod
    def _values(node: MemoryNode) -> tuple:
        return (
            node.id,
            node.category,
            node.experience_type,
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
            node.source_task,
            json.dumps(node.evidence, ensure_ascii=False),
            node.failure,
            node.fix,
            node.verification,
            node.embedding_text,
            node.embedding_model,
            json.dumps(node.embedding),
            json.dumps(node.source_task_embedding),
            node.created_at,
            node.retrieval_count,
        )

    @staticmethod
    def _from_row(row: sqlite3.Row) -> MemoryNode:
        return MemoryNode(
            id=row["id"],
            category=row["category"],
            experience_type=row["experience_type"] if "experience_type" in row.keys() else None,
            trigger=row["trigger_text"],
            content=row["content"],
            purpose=row["purpose"],
            steps=_json_list(row["steps_json"]),
            negative_example=row["negative_example"],
            problem_family=_json_list(row["problem_family_json"]),
            algorithm_tags=_json_list(row["algorithm_tags_json"]),
            constraints=_json_list(row["constraints_json"]),
            priority=row["priority"],
            quality_score=row["quality_score"],
            source_run_id=row["source_run_id"],
            source_verified=bool(row["source_verified"]),
            source_task=row["source_task"] if "source_task" in row.keys() else "",
            evidence=_json_list(row["evidence_json"]) if "evidence_json" in row.keys() else [],
            failure=row["failure_text"] if "failure_text" in row.keys() else "",
            fix=row["fix_text"] if "fix_text" in row.keys() else "",
            verification=row["verification_text"] if "verification_text" in row.keys() else "",
            embedding_text=row["embedding_text"],
            embedding_model=row["embedding_model"],
            embedding=_json_floats(row["embedding_json"]),
            source_task_embedding=_json_floats(row["source_task_embedding_json"]) if "source_task_embedding_json" in row.keys() else [],
            created_at=row["created_at"],
            retrieval_count=row["retrieval_count"],
        )


def _json_list(value: object) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _json_floats(value: object) -> list[float]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, json.JSONDecodeError):
        return []
    return [float(item) for item in parsed] if isinstance(parsed, list) else []


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return -1.0
    return dot / (left_norm * right_norm)
