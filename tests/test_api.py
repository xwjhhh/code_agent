import json

from fastapi.testclient import TestClient

import code_agent.api as api_module
from code_agent.api import RUNS, RUNS_LOCK, RunState, app
from code_agent.storage import RunStorage
from code_agent.test_cases import task_with_test_file


class StaticTextModel:
    def query_text(self, messages, **kwargs):
        return json.dumps(
            [
                {
                    "name": "sample",
                    "input": "a1b2",
                    "expected_output": "ab12",
                },
                {
                    "name": "no_digits",
                    "input": "abc",
                    "expected_output": "abc",
                },
            ]
        )


def test_health_endpoint():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_test_file_is_described_to_coding_agent():
    task = task_with_test_file("字符移动", 1)
    assert "test_cases.json" in task
    assert "solve(input_text: str)" in task


def test_generate_test_cases_endpoint_uses_selected_model(monkeypatch):
    model_name = "openai/Pro/zai-org/GLM-5.1"
    monkeypatch.setattr(api_module, "_build_model", lambda selected_model, config: StaticTextModel())

    response = TestClient(app).post(
        "/api/test-cases/generate",
        json={"task": "字符移动", "model": model_name, "count": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "generated"
    assert len(payload["cases"]) == 2
    assert payload["cases"][0]["input"] == "a1b2"


def test_generate_test_cases_endpoint_requires_model_name():
    response = TestClient(app).post(
        "/api/test-cases/generate",
        json={"task": "字符移动", "count": 2},
    )

    assert response.status_code == 422


def test_run_events_receive_stable_sequence_numbers(tmp_path):
    state = RunState(
        run_id="sequence-test",
        task="task",
        model_name="unit-test-model",
        workspace=tmp_path / "workspace",
        storage=RunStorage(tmp_path / "trajectory"),
    )

    state.emit("agent_started", {"step": 0})
    state.emit("run_finished", {"status": "completed", "verified": True})

    assert [event["sequence"] for event in state.events] == [0, 1]


def test_event_stream_resumes_after_last_received_event(tmp_path):
    state = RunState(
        run_id="reconnect-test",
        task="task",
        model_name="unit-test-model",
        workspace=tmp_path / "workspace",
        storage=RunStorage(tmp_path / "trajectory"),
    )
    state.emit("agent_started", {"step": 0})
    state.emit("run_finished", {"status": "completed", "verified": True})
    state.done = True
    with RUNS_LOCK:
        RUNS[state.run_id] = state

    try:
        response = TestClient(app).get(
            f"/api/runs/{state.run_id}/events",
            headers={"Last-Event-ID": "0"},
        )
    finally:
        with RUNS_LOCK:
            RUNS.pop(state.run_id, None)

    assert response.status_code == 200
    assert "id: 0\n" not in response.text
    assert "id: 1\n" in response.text
    assert "event: run_finished\n" in response.text
