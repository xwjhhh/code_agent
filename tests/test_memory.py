import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from code_agent.memory import (
    MemoryManager,
    MemoryManagerConfig,
    MemoryNode,
    MemoryStore,
    RecoveryEpisodeBuilder,
)
from code_agent.memory.consolidator import MemoryConsolidator


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
                    "queries": ["minimum window problem", "maintain a sliding window"],
                    "problem_family": ["array"],
                    "algorithm_tags": ["sliding-window"],
                }
            )
        if "Extract up to 3" in prompt:
            return json.dumps(
                {
                    "memories": [
                        {
                            "category": "strategy",
                            "trigger": "positive array and contiguous window condition",
                            "content": "Use a sliding window when the maintained sum is monotonic.",
                            "purpose": "avoid quadratic interval enumeration",
                            "steps": ["expand right", "shrink left while valid"],
                            "negative_example": "recompute every interval sum",
                            "problem_family": ["array", "interval"],
                            "algorithm_tags": ["sliding-window"],
                            "constraints": ["large input"],
                            "evidence": ["本地测试全部通过"],
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
        trigger="test output differs",
        content="Inspect output normalization.",
        source_run_id="run-1",
        embedding=[1.0, 0.0],
        embedding_text="output normalization",
    )
    store.add(recovery)

    matches = store.search([1.0, 0.0], category="strategy", limit=5)

    assert store.count() == 2
    assert [match.node.id for match in matches] == [task_memory.id]
    assert MemoryStore(tmp_path / "memory.sqlite3").list()[0].id in {task_memory.id, recovery.id}


def test_legacy_granularity_column_is_migrated_without_losing_memories(tmp_path: Path):
    database = tmp_path / "memory.sqlite3"
    store = MemoryStore(database)
    memory = node()
    store.add(memory)
    with sqlite3.connect(database) as connection:
        connection.execute("ALTER TABLE memories ADD COLUMN granularity TEXT NOT NULL DEFAULT 'task'")

    migrated = MemoryStore(database)
    with sqlite3.connect(database) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(memories)")}
    assert "granularity" not in columns
    assert migrated.count() == 1
    assert migrated.list()[0].id == memory.id


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


class AgenticMemoryModel:
    def __init__(self, grades: list[bool]):
        self.grades = iter(grades)
        self.calls: list[str] = []

    def query_text(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        self.calls.append(prompt)
        if "判断是否需要检索" in prompt:
            return json.dumps({"action": "retrieve", "query": "sliding window rewritten", "reason": "可能复用窗口维护经验"})
        if "Analyze this programming problem" in prompt:
            return json.dumps({
                "queries": ["minimum window problem", "maintain a sliding window"],
                "problem_family": ["array"],
                "algorithm_tags": ["sliding-window"],
            })
        if "返回一个更具体" in prompt:
            return json.dumps({"query": "sliding window invariant and boundary handling"})
        if "召回经验" in prompt:
            return json.dumps({"relevant": next(self.grades), "score": 0.9, "reason": "与当前问题的窗口约束一致"})
        raise AssertionError(prompt)


def test_agentic_retrieval_rewrites_when_grade_rejects(tmp_path: Path):
    model = AgenticMemoryModel([False, True])
    events: list[tuple[str, dict]] = []
    manager = MemoryManager(
        model,
        FakeEmbedder(),
        MemoryStore(tmp_path / "memory.sqlite3"),
        MemoryManagerConfig(rerank_with_llm=False, min_similarity=0.0, max_query_rewrites=2),
        event_callback=lambda event_type, data: events.append((event_type, data)),
    )
    memory = node()
    manager.store.add(memory)

    retrieval = manager.retrieve_agentic("find a minimum window in a positive array")

    assert retrieval.grade_relevant is True
    assert retrieval.rewrite_count == 1
    assert retrieval.selected
    assert any("返回一个更具体" in prompt for prompt in model.calls)
    assert [event_type for event_type, _ in events].count("memory_route_decided") == 1
    assert [event_type for event_type, _ in events].count("memory_relevance_graded") == 2
    assert [event_type for event_type, _ in events].count("memory_query_rewritten") == 1


def test_agentic_route_can_skip_non_retrieval(tmp_path: Path):
    class SkipModel:
        def query_text(self, messages, **kwargs):
            return json.dumps({"action": "skip", "query": "", "reason": "无需历史经验"})

    class FailingEmbedder:
        config = SimpleNamespace(model="test")

        def embed(self, texts):
            raise AssertionError("skip route must not embed")

    store = MemoryStore(tmp_path / "memory.sqlite3")
    memory = node()
    store.add(memory)
    manager = MemoryManager(
        SkipModel(),
        FailingEmbedder(),
        store,
        MemoryManagerConfig(),
    )

    retrieval = manager.retrieve_agentic("write a hello world program")

    assert retrieval.route_action == "skip"
    assert retrieval.grade_relevant is None
    assert retrieval.context == ""


def _recovery_result(include_pass: bool = True, changed: bool = True) -> dict:
    steps = [
        {
            "step": 1,
            "action": {"command": "python -m pytest -q"},
            "observation": {"returncode": 1, "output": "1 failed"},
            "solution_before": "def solve(text): return 0\n",
            "solution_after": "def solve(text): return 0\n",
        },
    ]
    if changed:
        steps.append(
            {
                "step": 2,
                "action": {"command": "python -c 'write solution.py'"},
                "observation": {"returncode": 0, "output": ""},
                "solution_before": "def solve(text): return 0\n",
                "solution_after": "def solve(text): return 1\n",
                "solution_changed": True,
            }
        )
    if include_pass:
        steps.append(
            {
                "step": 3,
                "action": {"command": "python -m pytest -q"},
                "observation": {"returncode": 0, "output": "1 passed"},
                "solution_before": "def solve(text): return 0\n",
                "solution_after": "def solve(text): return 1\n",
            }
        )
    return {"verified": include_pass, "steps": steps, "last_test_output": "1 passed" if include_pass else "1 failed"}


def test_recovery_episode_requires_edit_and_following_pass():
    episodes = RecoveryEpisodeBuilder().build(_recovery_result())
    assert len(episodes) == 1
    assert episodes[0].failure_output == "1 failed"
    assert episodes[0].actions_between == ["python -c 'write solution.py'"]
    assert episodes[0].code_before.endswith("return 0\n")
    assert episodes[0].code_after.endswith("return 1\n")

    assert RecoveryEpisodeBuilder().build(_recovery_result(include_pass=False)) == []
    assert RecoveryEpisodeBuilder().build(_recovery_result(changed=False)) == []


class FailureMemoryModel:
    def query_text(self, messages, **kwargs):
        prompt = messages[-1]["content"]
        if "FAILURE experiences" in prompt:
            return json.dumps(
                {
                    "memories": [
                        {
                            "experience_type": "failure",
                            "category": "recovery",
                            "trigger": "测试出现失败输出后修改了解题代码",
                            "content": "根据失败输出定位状态转移错误，修复后重新运行同一测试",
                            "purpose": "避免重复出现相同测试失败",
                            "steps": ["读取失败输出", "修改状态转移", "重新运行测试"],
                            "failure": "测试输出失败",
                            "fix": "修正状态转移",
                            "verification": "修改后测试通过",
                            "evidence": ["1 failed", "1 passed"],
                            "priority": 1,
                        }
                    ]
                }
            )
        raise AssertionError("success extraction should not be created for this test")


def test_manager_learns_only_evidence_backed_failure(tmp_path: Path):
    manager = MemoryManager(
        FailureMemoryModel(),
        FakeEmbedder(),
        MemoryStore(tmp_path / "memory.sqlite3"),
        MemoryManagerConfig(rerank_with_llm=False, min_similarity=0.0),
    )
    learned = manager.learn_from_run(
        task="debug a dynamic programming solution",
        result=_recovery_result(),
        review=None,
        source_run_id="run-failure",
    )
    assert len(learned) == 1
    assert learned[0].experience_type == "failure"
    assert learned[0].category == "recovery"
    assert learned[0].source_task == "debug a dynamic programming solution"
    assert learned[0].evidence == ["1 failed", "1 passed"]


def test_llm_duplicate_judgment_runs_before_vector_threshold(tmp_path: Path):
    class Judge:
        def __init__(self):
            self.calls = 0

        def query_text(self, messages, **kwargs):
            self.calls += 1
            return json.dumps({"duplicate": False, "matched_id": None, "reason": "虽然向量相似，但行动建议不同"})

    store = MemoryStore(tmp_path / "memory.sqlite3")
    existing = node()
    store.add(existing)
    judge = Judge()
    incoming = node()
    incoming.id = "incoming"
    incoming.content = "A different actionable rule"
    incoming.embedding_text = incoming.build_embedding_text()
    incoming.embedding = [1.0, 0.0]
    consolidator = MemoryConsolidator(store, model=judge)
    assert consolidator.is_duplicate(incoming) is False
    assert judge.calls == 1
    assert consolidator.last_judgment is not None
    assert consolidator.last_judgment.fallback is False


def test_weighted_search_exposes_task_and_memory_scores(tmp_path: Path):
    store = MemoryStore(tmp_path / "memory.sqlite3")
    first = node()
    first.source_task = "window task"
    first.source_task_embedding = [1.0, 0.0]
    first.embedding = [0.0, 1.0]
    first.embedding_text = first.build_embedding_text()
    second = node()
    second.source_task = "other task"
    second.source_task_embedding = [0.0, 1.0]
    second.embedding = [1.0, 0.0]
    second.embedding_text = second.build_embedding_text()
    store.add(first)
    store.add(second)
    matches = store.search([1.0, 0.0], task_embedding=[1.0, 0.0], limit=2)
    assert matches[0].node.id == first.id
    assert matches[0].similarity == 0.6
    assert all(match.task_similarity >= 0 for match in matches)
    assert all(match.memory_similarity >= 0 for match in matches)
