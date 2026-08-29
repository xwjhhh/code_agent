"""Run the curated AcWing DP set through the local backend.

The script intentionally uses the HTTP API, so every run follows the same
workflow as the application and writes trajectory/reviewer/memory data.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
TASKS_PATH = ROOT / "scripts" / "acwing_dp_tasks.json"
RESULTS_PATH = ROOT / "scripts" / "acwing_dp_run_results.json"
API_ROOT = "http://127.0.0.1:8001"
MODEL = "openai/deepseek-ai/DeepSeek-V4-Flash"
MAX_STEPS = 50
TIMEOUT = 120
POLL_SECONDS = 4


def request_json(method: str, path: str, payload: dict | None = None) -> dict | list:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(API_ROOT + path, data=body, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def wait_for_run(run_id: str) -> dict:
    while True:
        state = request_json("GET", f"/api/runs/{run_id}")
        if state.get("done"):
            return state
        time.sleep(POLL_SECONDS)


def summarize(task: dict, state: dict) -> dict:
    result = state.get("result") or {}
    review = state.get("review") or {}
    memory = state.get("memory") or {}
    learned = memory.get("learned")
    error = state.get("error")
    if not error and result.get("status") == "model_error":
        messages = result.get("messages")
        if isinstance(messages, list) and messages and isinstance(messages[-1], dict):
            error = messages[-1].get("content") or "模型调用失败"
    return {
        "acwing_id": task["acwing_id"],
        "difficulty": task["difficulty"],
        "title": task["title"],
        "model": MODEL,
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "verified": bool(result.get("verified")),
        "result_status": result.get("status"),
        "model_calls": result.get("model_calls", 0),
        "review_status": review.get("status"),
        "error": error,
        "learned_count": len(learned) if isinstance(learned, list) else 0,
    }


def run_task(index: int, task: dict) -> dict:
    payload = {
        "task": task["task"],
        "model": MODEL,
        "max_steps": MAX_STEPS,
        "timeout": TIMEOUT,
        "test_cases": task["test_cases"],
        "test_case_source": "manual",
        "memory_retrieval": False,
        "review_enabled": False,
    }
    print(f"[{index:02d}/30] AcWing {task['acwing_id']} {task['title']} ...", flush=True)
    try:
        created = request_json("POST", "/api/runs", payload)
        state = wait_for_run(str(created["run_id"]))
        return summarize(task, state)
    except (HTTPError, URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
        return {
            "acwing_id": task["acwing_id"],
            "difficulty": task["difficulty"],
            "title": task["title"],
            "model": MODEL,
            "run_id": None,
            "status": "client_error",
            "verified": False,
            "result_status": None,
            "model_calls": 0,
            "review_status": None,
            "error": str(error),
            "learned_count": 0,
        }


def main() -> int:
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    if len(tasks) != 30:
        raise RuntimeError(f"expected 30 tasks, got {len(tasks)}")
    results: list[dict] = []
    if RESULTS_PATH.is_file():
        loaded = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            results = [item for item in loaded if isinstance(item, dict)]
    # Old result files predate the model field. They are intentionally retried
    # so a newly selected model gets a complete, comparable batch run.
    completed_ids = {
        item.get("acwing_id")
        for item in results
        if item.get("model") == MODEL
        and item.get("result_status") == "success"
        and item.get("verified") is True
    }
    pending = [
        (index, task)
        for index, task in enumerate(tasks, start=1)
        if task["acwing_id"] not in completed_ids
    ]
    for index, task in enumerate(tasks, start=1):
        if task["acwing_id"] in completed_ids:
            print(f"[{index:02d}/30] AcWing {task['acwing_id']} {task['title']} already recorded", flush=True)

    # Two workers keep the provider busy while avoiding an aggressive burst of
    # requests and letting SQLite serialize the short persistence operations.
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(run_task, index, task) for index, task in pending]
        for future in as_completed(futures):
            item = future.result()
            results = [existing for existing in results if existing.get("acwing_id") != item.get("acwing_id")]
            results.append(item)
            RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(
                f"    {item['status']} verified={item['verified']} "
                f"review={item['review_status']} calls={item['model_calls']} "
                f"learned={item['learned_count']}",
                flush=True,
            )
    results.sort(key=lambda item: next((i for i, task in enumerate(tasks) if task["acwing_id"] == item.get("acwing_id")), 999))
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    passed = sum(item["verified"] for item in results)
    learned = sum(item["learned_count"] for item in results)
    print(f"Finished: {passed}/30 verified; {learned} memories learned", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
