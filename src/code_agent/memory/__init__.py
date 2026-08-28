"""Persistent, trajectory-informed experience memory for the coding agent."""

from code_agent.memory.embedding import SiliconFlowEmbeddingClient, SiliconFlowEmbeddingConfig
from code_agent.memory.factory import build_memory_manager, resolve_embedding_api_key
from code_agent.memory.manager import MemoryManager, MemoryManagerConfig, MemoryRetrieval
from code_agent.memory.schemas import MemoryNode, MemoryQuery, RetrievedMemory
from code_agent.memory.store import MemoryStore, cosine_similarity

__all__ = [
    "MemoryManager",
    "MemoryManagerConfig",
    "MemoryNode",
    "MemoryQuery",
    "MemoryRetrieval",
    "MemoryStore",
    "RetrievedMemory",
    "SiliconFlowEmbeddingClient",
    "SiliconFlowEmbeddingConfig",
    "build_memory_manager",
    "cosine_similarity",
    "resolve_embedding_api_key",
]
