from fastapi.testclient import TestClient

from code_agent.api import RUNS, RUNS_LOCK, RunState, app
from code_agent.storage import RunStorage
from code_agent.test_cases import task_with_test_file


def test_health_endpoint():
    response = TestClient(app).get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_test_file_is_described_to_coding_agent():
    task = task_with_test_file("字符移动", 1)
    assert "test_cases.json" in task
    assert "solve(input_text: str)" in task


def test_generate_test_cases_endpoint_uses_selected_model():
    response = TestClient(app).post(
        "/api/test-cases/generate",
        json={"task": "字符移动", "model": "demo", "count": 2},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "generated"
    assert len(payload["cases"]) == 2
    assert payload["cases"][0]["input"] == "ab4f35gr#a6"


def test_run_events_receive_stable_sequence_numbers(tmp_path):
    state = RunState(
        run_id="sequence-test",
        task="task",
        model_name="demo",
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
        model_name="demo",
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
