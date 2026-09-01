"""Run a fixed LeetCode Hot 100 memory on/off comparison.

The benchmark uses the first ten ranked question files (ranks 1-10), submits
one manual test suite per question, and waits for one completed Agent run for
each memory setting.  It intentionally disables reviewer and test generation
calls so the 20 runs are comparable.
"""

from __future__ import annotations

import csv
import html
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_DIR = PROJECT_ROOT.parents[2] / "机试" / "力扣100" / "questions"
OUTPUT_DIR = PROJECT_ROOT / "scripts"
RESULTS_PATH = OUTPUT_DIR / "leetcode_memory_benchmark_results.json"
SUMMARY_PATH = OUTPUT_DIR / "leetcode_memory_benchmark_summary.json"
CSV_PATH = OUTPUT_DIR / "leetcode_memory_benchmark_results.csv"
API_ROOT = "http://127.0.0.1:8002"
MODEL = "openai/deepseek-ai/DeepSeek-V4-Flash"
MAX_STEPS = 30
# Keep provider and shell calls within the same generous per-call budget. A
# shorter value can turn a transient provider stall into a false failed run.
TIMEOUT = 120
POLL_SECONDS = 3


# Inputs are deliberately small, deterministic, and cover the common boundary
# behavior while keeping the exact-output runner stable for each problem.
TEST_CASES: dict[str, list[dict[str, str]]] = {
    "1": [
        {"name": "sample", "input": "[2,7,11,15]\n9", "expected_output": "[0, 1]"},
        {"name": "duplicates", "input": "[3,3]\n6", "expected_output": "[0, 1]"},
    ],
    "49": [
        {"name": "two_words", "input": '["eat","tea"]', "expected_output": '[["eat", "tea"]]'},
        {"name": "single_empty", "input": '[""]', "expected_output": '[[""]]'},
    ],
    "128": [
        {"name": "unsorted_run", "input": "[100,4,200,1,3,2]", "expected_output": "4"},
        {"name": "empty", "input": "[]", "expected_output": "0"},
    ],
    "283": [
        {"name": "mixed", "input": "[0,1,0,3,12]", "expected_output": "[1, 3, 12, 0, 0]"},
        {"name": "all_zero", "input": "[0,0]", "expected_output": "[0, 0]"},
    ],
    "11": [
        {"name": "sample", "input": "[1,8,6,2,5,4,8,3,7]", "expected_output": "49"},
        {"name": "two_bars", "input": "[1,1]", "expected_output": "1"},
    ],
    "15": [
        {"name": "one_triplet", "input": "[-1,0,1]", "expected_output": "[[-1, 0, 1]]"},
        {"name": "no_triplet", "input": "[0,1,1]", "expected_output": "[]"},
    ],
    "42": [
        {"name": "sample", "input": "[0,1,0,2,1,0,1,3,2,1,2,1]", "expected_output": "6"},
        {"name": "flat", "input": "[1,1,1]", "expected_output": "0"},
    ],
    "3": [
        {"name": "sample", "input": "abcabcbb", "expected_output": "3"},
        {"name": "repeat", "input": "bbbbb", "expected_output": "1"},
    ],
    "438": [
        {"name": "sample", "input": "cbaebabacd\nabc", "expected_output": "[0, 6]"},
        {"name": "overlap", "input": "abab\nab", "expected_output": "[0, 1, 2]"},
    ],
    "560": [
        {"name": "sample", "input": "[1,1,1]\n2", "expected_output": "2"},
        {"name": "negative", "input": "[1,2,3]\n3", "expected_output": "2"},
    ],
}


def request_json(method: str, path: str, payload: dict | None = None) -> dict:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = Request(API_ROOT + path, data=body, headers=headers, method=method)
    with urlopen(request, timeout=30) as response:
        value = json.loads(response.read().decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object from {path}")
    return value


def wait_for_run(run_id: str) -> dict:
    while True:
        state = request_json("GET", f"/api/runs/{run_id}")
        if state.get("done"):
            return state
        time.sleep(POLL_SECONDS)


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def response_usage(response: object) -> dict[str, int] | None:
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            return None
    if not isinstance(response, dict):
        return None
    usage = response.get("usage")
    if not isinstance(usage, dict):
        return None
    values: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        try:
            values[key] = int(usage.get(key, 0) or 0)
        except (TypeError, ValueError):
            values[key] = 0
    return values


def token_totals(state: dict) -> dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    result = state.get("result") or {}
    for message in result.get("messages", []):
        if not isinstance(message, dict):
            continue
        usage = response_usage((message.get("extra") or {}).get("response"))
        if not usage:
            continue
        for key in totals:
            totals[key] += usage[key]
    return totals


def latency_seconds(state: dict) -> float | None:
    start = parse_timestamp(state.get("created_at"))
    events = state.get("events") or []
    finish = None
    for event in events:
        if isinstance(event, dict) and event.get("type") == "run_finished":
            finish = parse_timestamp(event.get("timestamp"))
    if start is None or finish is None:
        return None
    return max(0.0, (finish - start).total_seconds())


def plain_problem(question: dict) -> str:
    raw = str(question.get("content") or question.get("translated_content") or "")
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:8000]


def summarize(question: dict, memory_enabled: bool, state: dict) -> dict:
    result = state.get("result") or {}
    usage = token_totals(state)
    error = state.get("error")
    if not error and result.get("status") == "model_error":
        messages = result.get("messages") or []
        if messages and isinstance(messages[-1], dict):
            error = messages[-1].get("content") or "model_error"
    return {
        "rank": question["rank"],
        "question_id": question["question_id"],
        "title": question["title"],
        "difficulty": question["difficulty"],
        "memory": "on" if memory_enabled else "off",
        "run_id": state.get("run_id"),
        "status": state.get("status"),
        "result_status": result.get("status"),
        "pass": bool(result.get("verified")),
        "iterations": int(result.get("model_calls", 0) or 0),
        "recovered_from_model_error": bool(result.get("recovered_from_model_error")),
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "token_cost": usage["total_tokens"],
        "latency_seconds": latency_seconds(state),
        "error": error,
    }


def run_one(question: dict, memory_enabled: bool, index: int, total: int) -> dict:
    qid = str(question["question_id"])
    payload = {
        "task": f"{question['question_id']}. {question['title']}\n\n{plain_problem(question)}",
        "model": MODEL,
        "max_steps": MAX_STEPS,
        "timeout": TIMEOUT,
        "test_cases": TEST_CASES[qid],
        "test_case_source": "manual",
        "memory_retrieval": memory_enabled,
        "memory_learning": False,
        "review_enabled": False,
    }
    label = "on" if memory_enabled else "off"
    print(f"[{index:02d}/{total}] rank={question['rank']} {question['title']} memory={label} ...", flush=True)
    created = request_json("POST", "/api/runs", payload)
    state = wait_for_run(str(created["run_id"]))
    item = summarize(question, memory_enabled, state)
    print(
        f"    {item['result_status']} pass={item['pass']} iterations={item['iterations']} "
        f"tokens={item['token_cost']} latency={item['latency_seconds']}",
        flush=True,
    )
    return item


def aggregate(results: list[dict]) -> list[dict]:
    summaries = []
    for memory in ("on", "off"):
        items = [item for item in results if item["memory"] == memory]
        latency = [item["latency_seconds"] for item in items if item["latency_seconds"] is not None]
        summaries.append(
            {
                "memory": memory,
                "runs": len(items),
                "pass_rate": sum(bool(item["pass"]) for item in items) / len(items) if items else 0.0,
                "avg_iterations": sum(item["iterations"] for item in items) / len(items) if items else 0.0,
                "avg_token_cost": sum(item["token_cost"] for item in items) / len(items) if items else 0.0,
                "total_token_cost": sum(item["token_cost"] for item in items),
                "avg_latency_seconds": sum(latency) / len(latency) if latency else None,
                "total_latency_seconds": sum(latency) if latency else None,
            }
        )
    return summaries


def main() -> int:
    files = sorted(QUESTIONS_DIR.glob("*-question.json"))
    questions = [json.loads(path.read_text(encoding="utf-8")) for path in files[:10]]
    if len(questions) != 10:
        raise RuntimeError(f"Expected 10 question files in {QUESTIONS_DIR}, found {len(questions)}")
    missing = [str(question["question_id"]) for question in questions if str(question["question_id"]) not in TEST_CASES]
    if missing:
        raise RuntimeError(f"Missing manual cases for question ids: {', '.join(missing)}")
    if request_json("GET", "/api/health").get("status") != "ok":
        raise RuntimeError(f"API is not healthy at {API_ROOT}")

    results: list[dict] = []
    total = len(questions) * 2
    for index, question in enumerate(questions, start=1):
        results.append(run_one(question, True, index * 2 - 1, total))
        results.append(run_one(question, False, index * 2, total))

    summary = {
        "api": API_ROOT,
        "model": MODEL,
        "question_selection": [
            {"rank": question["rank"], "question_id": question["question_id"], "title": question["title"]}
            for question in questions
        ],
        "definition": {
            "pass_rate": "verified runs / runs",
            "avg_iterations": "mean result.model_calls",
            "token_cost": "sum of usage.total_tokens in Agent model responses",
            "latency": "created_at to run_finished event, seconds",
            "memory_on": "memory_retrieval=true",
            "memory_off": "memory_retrieval=false",
            "memory_learning": "disabled for both groups so post-run extraction does not confound retrieval comparison",
        },
        "groups": aggregate(results),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)
    print(json.dumps(summary["groups"], ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, OSError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
