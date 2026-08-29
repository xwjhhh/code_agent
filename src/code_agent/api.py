"""FastAPI bridge for the local coding agent.

The API deliberately stays thin: the existing DefaultAgent still owns the
model/action/environment loop. This module only starts runs and streams its
observable events to a browser client.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import yaml
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from code_agent.agents import DefaultAgent
from code_agent.environments import LocalEnvironment
from code_agent.memory import MemoryManager, build_memory_manager, cosine_similarity
from code_agent.models import PRIMARY_MODEL_NAME, LitellmModel, resolve_api_key, validate_model_name
from code_agent.reviewer import Reviewer
from code_agent.run.main import create_run_id
from code_agent.storage import RunStorage
from code_agent.test_cases import generate_test_cases, normalize_cases, save_test_files, task_with_test_file

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "src" / "code_agent" / "config" / "default.yaml"
load_dotenv(PROJECT_ROOT / ".env")
class TestCaseInput(BaseModel):
    name: str | None = Field(default=None, description="测试名称")
    input: str = Field(default="", description="测试输入")
    expected_output: str = Field(default="", description="期望输出")


class RunRequest(BaseModel):
    task: str = Field(min_length=1, description="算法题目")
    model: str = Field(default=PRIMARY_MODEL_NAME, min_length=1, description="固定使用的 DeepSeek V4 Flash 模型名")
    max_steps: int = Field(default=20, ge=1, le=100)
    timeout: int = Field(default=120, ge=1, le=600)
    test_cases: list[TestCaseInput] = Field(default_factory=list)
    test_case_source: str = Field(default="manual", pattern="^(manual|generated)$")
    # Batch runs can skip the model-backed retrieval pass while retaining
    # post-verification memory extraction and persistence.
    memory_retrieval: bool = Field(default=True, description="是否在运行前检索历史经验")
    review_enabled: bool = Field(default=True, description="是否执行完成后的模型评审")

    @field_validator("model")
    @classmethod
    def only_deepseek_v4_flash(cls, value: str) -> str:
        return validate_model_name(value)

class GenerateTestsRequest(BaseModel):
    task: str = Field(min_length=1, description="算法题目")
    model: str = Field(default=PRIMARY_MODEL_NAME, min_length=1, description="固定使用的 DeepSeek V4 Flash 模型名")
    count: int = Field(default=6, ge=1, le=20)

    @field_validator("model")
    @classmethod
    def only_deepseek_v4_flash(cls, value: str) -> str:
        return validate_model_name(value)

@dataclass
class RunState:
    run_id: str
    task: str
    model_name: str
    workspace: Path
    storage: RunStorage
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    events: list[dict[str, Any]] = field(default_factory=list)
    condition: threading.Condition = field(default_factory=threading.Condition)
    done: bool = False
    result: dict[str, Any] | None = None
    review: dict[str, Any] | None = None
    error: str | None = None
    test_cases: list[dict[str, str]] = field(default_factory=list)
    test_case_source: str = "manual"
    memory: dict[str, Any] = field(default_factory=dict)

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        with self.condition:
            event = {
                "sequence": len(self.events),
                "type": event_type,
                "data": data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self.events.append(event)
            self.condition.notify_all()


app = FastAPI(title="Code Agent API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
RUNS: dict[str, RunState] = {}
RUNS_LOCK = threading.Lock()


def _load_persisted_runs() -> None:
    """Restore completed runs so a backend restart does not hide history."""
    trajectory_root = PROJECT_ROOT / "trajectories"
    if not trajectory_root.is_dir():
        return
    restored: dict[str, RunState] = {}
    for run_dir in trajectory_root.iterdir():
        if not run_dir.is_dir():
            continue
        trajectory_path = run_dir / "trajectory.json"
        if not trajectory_path.is_file():
            continue
        try:
            payload = json.loads(trajectory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
            continue

        result = payload["result"]
        task = str(payload.get("task", "")).strip()
        if not task:
            continue
        model_payload = payload.get("model", {})
        model_config = model_payload.get("model", {}) if isinstance(model_payload, dict) else {}
        model_name = "unknown"
        if isinstance(model_config, dict) and model_config.get("model_name"):
            model_name = str(model_config["model_name"])
        elif isinstance(model_payload, dict) and model_payload.get("model_name"):
            model_name = str(model_payload["model_name"])

        workspace_value = result.get("workspace")
        if not isinstance(workspace_value, str) or not workspace_value:
            environment_payload = payload.get("environment", {})
            environment = environment_payload.get("environment", {}) if isinstance(environment_payload, dict) else {}
            workspace_value = environment.get("cwd") if isinstance(environment, dict) else None
        workspace = Path(workspace_value) if isinstance(workspace_value, str) and workspace_value else PROJECT_ROOT / "workspace" / run_dir.name

        review: dict[str, Any] | None = None
        raw_review = payload.get("review")
        if isinstance(raw_review, dict):
            review = raw_review
        else:
            review_path = run_dir / "review.json"
            if review_path.is_file():
                try:
                    loaded_review = json.loads(review_path.read_text(encoding="utf-8"))
                    if isinstance(loaded_review, dict):
                        review = loaded_review
                except (OSError, json.JSONDecodeError):
                    pass

        test_cases = payload.get("test_cases", [])
        if not isinstance(test_cases, list):
            test_cases = []
        state = RunState(
            run_id=run_dir.name,
            task=task,
            model_name=model_name,
            workspace=workspace,
            storage=RunStorage(run_dir),
            created_at=str(payload.get("created_at") or datetime.fromtimestamp(trajectory_path.stat().st_mtime, timezone.utc).isoformat()),
            events=[event for event in payload.get("events", []) if isinstance(event, dict)],
            done=True,
            result=result,
            review=review,
            error=str(payload.get("error")) if payload.get("error") else None,
            test_cases=[case for case in test_cases if isinstance(case, dict)],
            test_case_source=str(payload.get("test_case_source", "manual")),
            memory=payload.get("memory", {}) if isinstance(payload.get("memory"), dict) else {},
        )
        restored[state.run_id] = state
    with RUNS_LOCK:
        RUNS.update(restored)


_load_persisted_runs()


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "code-agent"}


@app.post("/api/runs", status_code=202)
def create_run(request: RunRequest) -> dict[str, Any]:
    task = request.task.strip()
    if not task:
        raise HTTPException(status_code=400, detail="题目不能为空")
    run_id = create_run_id(task)
    workspace = PROJECT_ROOT / "workspace" / run_id
    storage = RunStorage(PROJECT_ROOT / "trajectories" / run_id)
    state = RunState(run_id, task, request.model, workspace, storage)
    with RUNS_LOCK:
        RUNS[run_id] = state
    thread = threading.Thread(target=_run_agent, args=(state, request), daemon=True)
    thread.start()
    return {"run_id": run_id, "status": "running", "events_url": f"/api/runs/{run_id}/events"}


@app.get("/api/runs")
def list_runs() -> list[dict[str, Any]]:
    with RUNS_LOCK:
        states = list(RUNS.values())
    return [_state_payload(state) for state in reversed(states)]


@app.get("/api/memories")
def list_memories(limit: int = 100) -> dict[str, Any]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    manager = build_memory_manager(_NoopTextModel(), config, PROJECT_ROOT)
    if manager is None:
        return {"enabled": False, "count": 0, "items": []}
    memories = manager.list_memories(max(1, min(limit, 500)))
    return {"enabled": True, "count": manager.store.count(), "items": [node.to_dict() for node in memories]}


@app.get("/api/memories/graph")
def memory_graph(limit: int = 200) -> dict[str, Any]:
    """Return display-ready memory nodes and sparse, typed relationships.

    Embedding vectors stay server-side. The API computes source-run structure
    edges and a maximum of three cosine neighbors per task-level node.
    """
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    manager = build_memory_manager(_NoopTextModel(), config, PROJECT_ROOT)
    if manager is None:
        return {"enabled": False, "count": 0, "nodes": [], "edges": []}

    memories = manager.list_memories(max(1, min(limit, 500)))
    edges: list[dict[str, Any]] = []
    edge_keys: set[tuple[str, str]] = set()

    def add_edge(source: str, target: str, kind: str, similarity: float | None = None) -> None:
        if source == target:
            return
        key = tuple(sorted((source, target)))
        if key in edge_keys:
            return
        edge_keys.add(key)
        edge: dict[str, Any] = {"source": source, "target": target, "kind": kind}
        if similarity is not None:
            edge["similarity"] = round(similarity, 6)
        edges.append(edge)

    # A source run is the only grouping relation available in the current schema.
    by_source: dict[str, list[MemoryNode]] = {}
    for node in memories:
        if node.source_run_id:
            by_source.setdefault(node.source_run_id, []).append(node)
    for group in by_source.values():
        anchor = group[0]
        for node in group[1:]:
            add_edge(anchor.id, node.id, "solid")

    # Keep the similarity graph sparse: each task memory participates in <= 3 edges.
    task_nodes = [node for node in memories if node.granularity == "task"]
    pair_scores: list[tuple[float, MemoryNode, MemoryNode]] = []
    for index, left in enumerate(task_nodes):
        for right in task_nodes[index + 1:]:
            similarity = cosine_similarity(left.embedding, right.embedding)
            if similarity >= float(config.get("memory", {}).get("min_similarity", 0.35)):
                pair_scores.append((similarity, left, right))
    degrees: dict[str, int] = {node.id: 0 for node in task_nodes}
    for similarity, left, right in sorted(pair_scores, key=lambda item: item[0], reverse=True):
        if degrees[left.id] >= 3 or degrees[right.id] >= 3:
            continue
        add_edge(left.id, right.id, "dotted", similarity)
        degrees[left.id] += 1
        degrees[right.id] += 1

    return {
        "enabled": True,
        "count": manager.store.count(),
        "embedding_model": manager.embedder.config.model,
        "nodes": [node.to_dict() for node in memories],
        "edges": edges,
    }


@app.post("/api/test-cases/generate")
def generate_cases(request: GenerateTestsRequest) -> dict[str, Any]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    model = _build_model(request.model, config)
    try:
        cases = generate_test_cases(model, request.task, request.count)
    except Exception as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"source": "generated", "cases": cases}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    state = _get_state(run_id)
    return _state_payload(state)


@app.get("/api/runs/{run_id}/files")
def get_files(run_id: str) -> dict[str, str]:
    state = _get_state(run_id)
    return {
        "solution.py": _read_file(state.workspace / "solution.py"),
        "test_solution.py": _read_file(state.workspace / "test_solution.py"),
        "test_cases.json": _read_file(state.workspace / "test_cases.json"),
    }


@app.get("/api/runs/{run_id}/events")
def stream_events(
    run_id: str,
    cursor: int = 0,
    last_event_id: str | None = Header(default=None),
) -> StreamingResponse:
    state = _get_state(run_id)

    def generate() -> Iterator[str]:
        reconnect_cursor = _next_event_position(last_event_id)
        position = max(cursor, reconnect_cursor)
        position = max(0, min(position, len(state.events)))
        while True:
            with state.condition:
                while position >= len(state.events) and not state.done:
                    state.condition.wait(timeout=1)
                pending = state.events[position:]
                position = len(state.events)
                finished = state.done and not pending
            for event in pending:
                payload = {
                    **event["data"],
                    "_sequence": event["sequence"],
                    "_timestamp": event["timestamp"],
                }
                yield (
                    f"id: {event['sequence']}\n"
                    f"event: {event['type']}\n"
                    f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                )
            if finished:
                break

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


def _run_agent(state: RunState, request: RunRequest) -> None:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    submitted_cases = [case.model_dump() for case in request.test_cases]
    agent: DefaultAgent | None = None
    try:
        model = _build_model(request.model, config)
        try:
            memory_manager = build_memory_manager(model, config, PROJECT_ROOT, state.emit)
        except Exception as memory_error:
            memory_manager = None
            state.memory["enabled"] = False
            state.memory["initialization_error"] = str(memory_error)
            state.emit("memory_error", {"phase": "initialization", "error": str(memory_error)})
        if submitted_cases:
            cases = normalize_cases(submitted_cases, request.test_case_source)
            source = request.test_case_source
        else:
            cases = generate_test_cases(model, state.task)
            source = "generated"
        state.test_cases = cases
        state.test_case_source = source
        save_test_files(state.workspace, state.task, cases, source)
        state.emit("test_cases_ready", {"source": source, "cases": cases})
        task = task_with_test_file(state.task, len(cases))
        if request.memory_retrieval:
            initial_memory_context = _retrieve_task_memory(memory_manager, state, state.task)
            recovery_context_provider = _recovery_context_provider(memory_manager, state)
        else:
            state.memory["retrieval_skipped"] = True
            initial_memory_context = ""
            recovery_context_provider = None
        environment = LocalEnvironment(
            state.workspace,
            timeout=request.timeout,
            protected_files=["test_cases.json", "test_solution.py"],
        )
        agent = DefaultAgent(
            model=model,
            env=environment,
            system_prompt=config["agent"]["system_prompt"],
            task_template=config["agent"]["task_template"],
            step_limit=request.max_steps,
            output_path=state.storage.trajectory_path,
            event_callback=state.emit,
            memory_context=initial_memory_context,
            recovery_context_provider=recovery_context_provider,
        )
        state.result = agent.run(task)
        if request.review_enabled and state.result["status"] == "success" and state.result["verified"]:
            state.emit("review_started", {"step": state.result["model_calls"]})
            try:
                state.review = Reviewer(model).review(task, state.result)
            except Exception as error:
                state.review = {"status": "error", "local_verification": "passed", "content": f"Reviewer 执行失败：{error}"}
            state.storage.save_review(state.review)
            state.emit("review_finished", {"step": state.result["model_calls"], "review": state.review})
        _save_run_snapshot(state, agent)
        _learn_memory(memory_manager, state, agent)
        _save_run_snapshot(state, agent)
    except Exception as error:  # The event stream must expose failures to the UI.
        state.error = str(error)
        state.emit("run_error", {"error": state.error})
    finally:
        verified = bool(state.result and state.result.get("verified"))
        state.emit(
            "run_finished",
            {
                "status": "error" if state.error else "completed",
                "verified": verified,
                "error": state.error or "",
            },
        )
        with state.condition:
            state.done = True
            state.condition.notify_all()
        if agent is not None:
            _save_run_snapshot(state, agent)


def _save_run_snapshot(state: RunState, agent: DefaultAgent) -> None:
    """Persist the completed run and its observability data for restart recovery."""
    state.storage.save_trajectory(
        state.task,
        agent.serialize(
            run_id=state.run_id,
            created_at=state.created_at,
            events=list(state.events),
            test_cases=list(state.test_cases),
            test_case_source=state.test_case_source,
            error=state.error,
            review=state.review,
            memory=state.memory,
        ),
    )


def _build_model(model_name: str, config: dict[str, Any], timeout: int | None = None) -> LitellmModel:
    model_kwargs = dict(config["model"].get("model_kwargs", {}))
    # Bound provider calls as well as shell commands so a stalled model cannot
    # leave a run in a permanent "running" state.
    model_kwargs.setdefault("timeout", max(1, timeout or 120))
    api_base = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
    if api_base:
        model_kwargs["api_base"] = api_base
    api_key = resolve_api_key(model_name)
    if api_key:
        model_kwargs["api_key"] = api_key
    return LitellmModel(model_name=model_name, model_kwargs=model_kwargs, max_retries=config["model"].get("max_retries", 3))


def _retrieve_task_memory(manager: MemoryManager | None, state: RunState, task: str) -> str:
    if manager is None:
        state.memory["enabled"] = False
        return ""
    state.memory["enabled"] = True
    try:
        retrieval = manager.retrieve_for_task(task)
    except Exception as error:
        state.emit("memory_error", {"phase": "task", "error": str(error)})
        state.memory["task_retrieval_error"] = str(error)
        return ""
    state.memory["task_retrieval"] = retrieval.to_dict()
    return retrieval.context


def _recovery_context_provider(manager: MemoryManager | None, state: RunState):
    def provide(task: str, error: str, steps: list[dict[str, Any]]) -> str:
        if manager is None:
            return ""
        try:
            retrieval = manager.retrieve_for_failure(task, error, steps)
        except Exception as retrieval_error:
            state.emit("memory_error", {"phase": "recovery", "error": str(retrieval_error)})
            state.memory["recovery_retrieval_error"] = str(retrieval_error)
            return ""
        state.memory.setdefault("recovery_retrievals", []).append(retrieval.to_dict())
        return retrieval.context

    return provide


def _learn_memory(manager: MemoryManager | None, state: RunState, agent: DefaultAgent) -> None:
    if (
        manager is None
        or state.result is None
        or not state.result.get("verified")
        or not state.review
        or state.review.get("status") != "completed"
    ):
        return
    try:
        learned = manager.learn_from_run(
            task=state.task,
            result=state.result,
            review=state.review,
            source_run_id=state.run_id,
        )
    except Exception as error:
        state.emit("memory_error", {"phase": "learning", "error": str(error)})
        state.memory["learning_error"] = str(error)
        return
    state.memory["learned"] = [node.to_dict() for node in learned]


class _NoopTextModel:
    def query_text(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        raise RuntimeError("Listing persisted memories does not require a model call.")


def _get_state(run_id: str) -> RunState:
    with RUNS_LOCK:
        state = RUNS.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return state


def _state_payload(state: RunState) -> dict[str, Any]:
    return {
        "run_id": state.run_id,
        "task": state.task,
        "model": state.model_name,
        "status": "error" if state.error else ("completed" if state.done else "running"),
        "done": state.done,
        "error": state.error,
        "result": state.result,
        "review": state.review,
        "workspace": str(state.workspace),
        "created_at": state.created_at,
        "test_cases": state.test_cases,
        "test_case_source": state.test_case_source,
        "events": list(state.events),
        "memory": state.memory,
    }


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _next_event_position(last_event_id: str | None) -> int:
    if last_event_id is None:
        return 0
    try:
        return int(last_event_id) + 1
    except ValueError:
        return 0


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("code_agent.api:app", host="127.0.0.1", port=int(os.getenv("CODE_AGENT_API_PORT", "8000")), reload=False)
