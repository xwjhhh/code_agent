import json
from pathlib import Path
from types import SimpleNamespace

from code_agent.memory import MemoryManager, MemoryManagerConfig, MemoryNode, MemoryStore


class FakeEmbedder:
    config = SimpleNamespace(model="BAAI/bge-m3")

    def embed(self, texts):
        values = [texts] if isinstance(texts, str) else texts
        return [[1.0, 0.0] if "window" in value.lower() else [0.0, 1.0] for value in values]


class MemoryModel:
    def query_text(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        if "Analyze this programming problem" in prompt:
            return json.dumps(
                {
                    "task_query": "minimum window problem",
                    "subtask_queries": ["maintain a sliding window"],
                    "problem_family": ["array"],
                    "algorithm_tags": ["sliding-window"],
                }
            )
        if "Extract up to six" in prompt:
            return json.dumps(
                {
                    "memories": [
                        {
                            "category": "strategy",
                            "granularity": "task",
                            "trigger": "positive array and contiguous window condition",
                            "content": "Use a sliding window when the maintained sum is monotonic.",
                            "purpose": "avoid quadratic interval enumeration",
                            "steps": ["expand right", "shrink left while valid"],
                            "negative_example": "recompute every interval sum",
                            "problem_family": ["array", "interval"],
                            "algorithm_tags": ["sliding-window"],
                            "constraints": ["large input"],
                            "priority": 1,
                        }
                    ]
                }
            )
        if "Candidate memories" in prompt:
            candidates = prompt.split("Candidate memories:\n", 1)[1]
            first_id = candidates.split("'id': '", 1)[1].split("'", 1)[0]
            return json.dumps({"selected_ids": [first_id]})
        raise AssertionError(prompt)


def node() -> MemoryNode:
    memory = MemoryNode(
        category="strategy",
        granularity="task",
        trigger="contiguous interval with monotonic statistic",
        content="Maintain the statistic while moving the window boundaries.",
        problem_family=["array"],
        algorithm_tags=["sliding-window"],
        source_run_id="run-1",
    )
    memory.embedding_text = memory.build_embedding_text()
    memory.embedding = [1.0, 0.0]
    memory.embedding_model = "BAAI/bge-m3"
    return memory


def test_memory_store_persists_and_filters_by_metadata(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    task_memory = node()
    store.add(task_memory)
    recovery = MemoryNode(
        category="recovery",
        granularity="subtask",
        trigger="test output differs",
        content="Inspect output normalization.",
        source_run_id="run-1",
        embedding=[1.0, 0.0],
        embedding_text="output normalization",
    )
    store.add(recovery)

    matches = store.search([1.0, 0.0], category="strategy", granularity="task", limit=5)

    assert store.count() == 2
    assert [match.node.id for match in matches] == [task_memory.id]
    assert MemoryStore(tmp_path / "memory.sqlite3").list()[0].id in {task_memory.id, recovery.id}


def test_manager_learns_deduplicates_and_retrieves_context(tmp_path: Path):
    solution = tmp_path / "solution.py"
    solution.write_text("def solve(text): return text\n", encoding="utf-8")
    manager = MemoryManager(
        MemoryModel(),
        FakeEmbedder(),
        MemoryStore(tmp_path / "memory.sqlite3"),
        MemoryManagerConfig(rerank_with_llm=False, min_similarity=0.0),
    )
    result = {"verified": True, "solution_path": str(solution), "last_test_output": "2 passed", "steps": []}

    added = manager.learn_from_run(task="find a minimum window", result=result, review={"content": "O(n)"}, source_run_id="run-1")
    duplicate = manager.learn_from_run(task="find a minimum window", result=result, review={"content": "O(n)"}, source_run_id="run-2")
    retrieval = manager.retrieve_for_task("find a minimum window in a positive array")

    assert len(added) == 1
    assert duplicate == []
    assert manager.store.count() == 1
    assert len(retrieval.selected) == 1
    assert "Relevant Past Experience" in retrieval.context
    assert "sliding window" in retrieval.context


def test_recovery_retrieval_only_uses_recovery_memories(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    strategy = node()
    store.add(strategy)
    recovery = MemoryNode(
        category="recovery",
        granularity="subtask",
        trigger="pytest output mismatches expected lines",
        content="Preserve line boundaries with splitlines when they carry meaning.",
        source_run_id="run-1",
        embedding=[0.0, 1.0],
        embedding_text="pytest output line mismatch",
    )
    store.add(recovery)
    manager = MemoryManager(
        MemoryModel(),
        FakeEmbedder(),
        store,
        MemoryManagerConfig(rerank_with_llm=False, min_similarity=0.0),
    )

    retrieval = manager.retrieve_for_failure("format a string", "expected two lines, got one", [])

    assert retrieval.phase == "recovery"
    assert retrieval.selected
    assert all(item.node.category == "recovery" for item in retrieval.selected)


def test_empty_store_skips_model_and_embedding_calls(tmp_path: Path):
    class FailingModel:
        def query_text(self, messages, **kwargs):
            raise AssertionError("No query is needed for an empty memory store")

    class FailingEmbedder:
        def embed(self, texts):
            raise AssertionError("No embedding is needed for an empty memory store")

    manager = MemoryManager(FailingModel(), FailingEmbedder(), MemoryStore(tmp_path / "memory.sqlite3"))

    retrieval = manager.retrieve_for_task("a new task")

    assert retrieval.context == ""
    assert retrieval.selected == []
