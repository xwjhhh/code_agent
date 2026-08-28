"""Configuration helpers for the optional persistent memory subsystem."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable

from code_agent.memory.embedding import SiliconFlowEmbeddingClient, SiliconFlowEmbeddingConfig
from code_agent.memory.manager import MemoryManager, MemoryManagerConfig
from code_agent.memory.query_analyzer import TextModel
from code_agent.memory.store import MemoryStore


def resolve_embedding_api_key() -> str | None:
    return (
        os.getenv("SILICONFLOW_EMBEDDING_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("SILICONFLOW_DEEPSEEK_API_KEY")
    )


def build_memory_manager(
    model: TextModel,
    config: dict[str, Any],
    project_root: str | Path,
    event_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> MemoryManager | None:
    memory = config.get("memory", {})
    if not memory.get("enabled", True):
        return None
    api_key = resolve_embedding_api_key()
    if not api_key:
        return None
    root = Path(project_root)
    database_path = Path(memory.get("database_path", "memory_store/memory.sqlite3"))
    if not database_path.is_absolute():
        database_path = root / database_path
    api_base = memory.get("embedding_api_base") or os.getenv("OPENAI_API_BASE") or "https://api.siliconflow.cn/v1"
    embedder = SiliconFlowEmbeddingClient(
        SiliconFlowEmbeddingConfig(
            api_key=api_key,
            model=memory.get("embedding_model", "BAAI/bge-m3"),
            api_base=api_base,
            dimensions=memory.get("embedding_dimensions"),
            timeout=memory.get("embedding_timeout", 30),
            max_retries=memory.get("embedding_max_retries", 3),
        )
    )
    manager_config = MemoryManagerConfig(
        recall_limit_per_query=memory.get("recall_limit_per_query", 8),
        selected_limit=memory.get("selected_limit", 4),
        min_similarity=memory.get("min_similarity", 0.35),
        rerank_with_llm=memory.get("rerank_with_llm", True),
    )
    return MemoryManager(model, embedder, MemoryStore(database_path), manager_config, event_callback)
