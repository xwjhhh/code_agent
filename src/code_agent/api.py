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
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from code_agent.agents import DefaultAgent
from code_agent.environments import LocalEnvironment
from code_agent.models import DemoModel, LitellmModel
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
    model: str = Field(default="demo", description="demo 或 LiteLLM 模型名")
    max_steps: int = Field(default=20, ge=1, le=100)
    timeout: int = Field(default=120, ge=1, le=600)
    test_cases: list[TestCaseInput] = Field(default_factory=list)
    test_case_source: str = Field(default="manual", pattern="^(manual|generated)$")


class GenerateTestsRequest(BaseModel):
    task: str = Field(min_length=1, description="算法题目")
    model: str = Field(default="demo", description="用于生成测试的模型")
    count: int = Field(default=6, ge=1, le=20)


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

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        event = {
            "type": event_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with self.condition:
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


@app.post("/api/test-cases/generate")
def generate_cases(request: GenerateTestsRequest) -> dict[str, Any]:
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    model = _build_model(request.model, request.task, [], config)
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
def stream_events(run_id: str, cursor: int = 0) -> StreamingResponse:
    state = _get_state(run_id)

    def generate() -> Iterator[str]:
        position = max(0, min(cursor, len(state.events)))
        while True:
            with state.condition:
                while position >= len(state.events) and not state.done:
                    state.condition.wait(timeout=1)
                pending = state.events[position:]
                position = len(state.events)
                finished = state.done and not pending
            for event in pending:
                payload = {**event["data"], "_timestamp": event["timestamp"]}
                yield f"event: {event['type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
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
    model = _build_model(request.model, state.task, submitted_cases, config)
    try:
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
        )
        state.result = agent.run(task)
        if state.result["status"] == "success" and state.result["verified"]:
            state.emit("review_started", {"step": state.result["model_calls"]})
            try:
                state.review = Reviewer(model).review(task, state.result)
            except Exception as error:
                state.review = {"status": "error", "local_verification": "passed", "content": f"Reviewer 执行失败：{error}"}
            state.storage.save_review(state.review)
            state.emit("review_finished", {"step": state.result["model_calls"], "review": state.review})
        state.storage.save_trajectory(task, agent.serialize(review=state.review))
    except Exception as error:  # The event stream must expose failures to the UI.
        state.error = str(error)
        state.emit("run_error", {"error": state.error})
    finally:
        with state.condition:
            state.done = True
            state.condition.notify_all()


def _build_model(model_name: str, task: str, cases: list[dict[str, str]], config: dict[str, Any]) -> Any:
    if model_name.lower() in {"demo", "演示", "mock"}:
        return DemoModel(task, cases)
    model_kwargs = dict(config["model"].get("model_kwargs", {}))
    api_base = os.getenv("OPENAI_API_BASE") or os.getenv("OPENAI_BASE_URL")
    if api_base:
        model_kwargs["api_base"] = api_base
    return LitellmModel(model_name=model_name, model_kwargs=model_kwargs, max_retries=config["model"].get("max_retries", 3))


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
    }


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("code_agent.api:app", host="127.0.0.1", port=int(os.getenv("CODE_AGENT_API_PORT", "8000")), reload=False)
