from fastapi.testclient import TestClient

from code_agent.api import app
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
