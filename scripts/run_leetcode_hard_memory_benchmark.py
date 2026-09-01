"""Run a fixed Hard-question memory on/off comparison."""

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
QUESTIONS_DIR = next(
    path
    for path in PROJECT_ROOT.parents[2].rglob("questions")
    if len(list(path.glob("*-question.json"))) >= 100
)
OUTPUT_DIR = PROJECT_ROOT / "scripts"
RESULTS_PATH = OUTPUT_DIR / "leetcode_hard_memory_benchmark_results.json"
SUMMARY_PATH = OUTPUT_DIR / "leetcode_hard_memory_benchmark_summary.json"
CSV_PATH = OUTPUT_DIR / "leetcode_hard_memory_benchmark_results.csv"
API_ROOT = "http://127.0.0.1:8002"
MODEL = "openai/deepseek-ai/DeepSeek-V4-Flash"
RANKS = (11, 12, 17, 31, 34, 50, 62, 68, 73, 76)
MAX_STEPS = 30
TIMEOUT = 120
POLL_SECONDS = 3


# These cases target the invariants most likely to be missed while keeping a
# deterministic JSON/text contract for solve(input_text: str) -> str.
TEST_CASES: dict[str, list[dict[str, str]]] = {
    "239": [
        {"name": "sample", "input": '{"nums":[1,3,-1,-3,5,3,6,7],"k":3}', "expected_output": "[3, 3, 5, 5, 6, 7]"},
        {"name": "duplicate_max", "input": '{"nums":[1,1,1,1],"k":2}', "expected_output": "[1, 1, 1]"},
        {"name": "window_one", "input": '{"nums":[4,-2,7],"k":1}', "expected_output": "[4, -2, 7]"},
    ],
    "76": [
        {"name": "sample", "input": '{"s":"ADOBECODEBANC","t":"ABC"}', "expected_output": "BANC"},
        {"name": "repeated_required", "input": '{"s":"aa","t":"aa"}', "expected_output": "aa"},
        {"name": "no_window", "input": '{"s":"a","t":"aa"}', "expected_output": ""},
    ],
    "41": [
        {"name": "mixed", "input": "[3,4,-1,1]", "expected_output": "2"},
        {"name": "zero_gap", "input": "[1,2,0]", "expected_output": "3"},
        {"name": "all_large", "input": "[7,8,9,11,12]", "expected_output": "1"},
        {"name": "duplicate", "input": "[1,1]", "expected_output": "2"},
    ],
    "25": [
        {"name": "pairs", "input": '{"head":[1,2,3,4,5],"k":2}', "expected_output": "[2, 1, 4, 3, 5]"},
        {"name": "triples_with_remainder", "input": '{"head":[1,2,3,4,5],"k":3}', "expected_output": "[3, 2, 1, 4, 5]"},
        {"name": "single_group", "input": '{"head":[1,2,3],"k":3}', "expected_output": "[3, 2, 1]"},
    ],
    "23": [
        {"name": "three_lists", "input": "[[1,4,5],[1,3,4],[2,6]]", "expected_output": "[1, 1, 2, 3, 4, 4, 5, 6]"},
        {"name": "empty_members", "input": "[[],[1],[],[0,2]]", "expected_output": "[0, 1, 2]"},
        {"name": "no_lists", "input": "[]", "expected_output": "[]"},
    ],
    "124": [
        {"name": "through_root", "input": '{"root":[-10,9,20,null,null,15,7]}', "expected_output": "42"},
        {"name": "all_negative", "input": '{"root":[-3]}', "expected_output": "-3"},
        {"name": "one_child", "input": '{"root":[2,-1]}', "expected_output": "2"},
    ],
    "51": [
        {"name": "four_queens", "input": '{"n":4}', "expected_output": '[[".Q..", "...Q", "Q...", "..Q."], ["..Q.", "Q...", "...Q", ".Q.."]]'},
        {"name": "one_queen", "input": '{"n":1}', "expected_output": '[["Q"]]'},
    ],
    "4": [
        {"name": "even_total", "input": '{"nums1":[1,2],"nums2":[3,4]}', "expected_output": "2.5"},
        {"name": "odd_total", "input": '{"nums1":[1,3],"nums2":[2]}', "expected_output": "2.0"},
        {"name": "empty_left", "input": '{"nums1":[],"nums2":[-5,-3,-2,-1]}', "expected_output": "-2.5"},
    ],
    "84": [
        {"name": "sample", "input": "[2,1,5,6,2,3]", "expected_output": "10"},
        {"name": "equal_heights", "input": "[2,2,2]", "expected_output": "6"},
        {"name": "decreasing", "input": "[5,4,3,2,1]", "expected_output": "9"},
    ],
    "295": [
        {
            "name": "standard_stream",
            "input": '{"operations":["MedianFinder","addNum","addNum","findMedian","addNum","findMedian"],"arguments":[[],[1],[2],[],[3],[]]}',
            "expected_output": "[null, null, null, 1.5, null, 2]",
        },
        {
            "name": "negative_duplicates",
            "input": '{"operations":["MedianFinder","addNum","addNum","addNum","findMedian","addNum","findMedian"],"arguments":[[],[-1],[-1],[5],[],[0],[]]}',
            "expected_output": "[null, null, null, null, -1, null, -0.5]",
        },
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
    if not isinstance(response, dict) or not isinstance(response.get("usage"), dict):
        return None
    usage = response["usage"]
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
        if usage:
            for key in totals:
                totals[key] += usage[key]
    return totals


def latency_seconds(state: dict) -> float | None:
    start = parse_timestamp(state.get("created_at"))
    finish = None
    for event in state.get("events") or []:
        if isinstance(event, dict) and event.get("type") == "run_finished":
            finish = parse_timestamp(event.get("timestamp"))
    if start is None or finish is None:
        return None
    return max(0.0, (finish - start).total_seconds())


def plain_problem(question: dict) -> str:
    raw = str(question.get("content") or question.get("translated_content") or "")
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"\s+", " ", text).strip()[:8000]


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
        "recovered_from_model_error": bool(result.get("recovered_from_model_error")),
        "iterations": int(result.get("model_calls", 0) or 0),
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "token_cost": usage["total_tokens"],
        "latency_seconds": latency_seconds(state),
        "error": error,
    }


def aggregate(results: list[dict]) -> list[dict]:
    summaries = []
    for memory in ("on", "off"):
        items = [item for item in results if item["memory"] == memory]
        latencies = [item["latency_seconds"] for item in items if item["latency_seconds"] is not None]
        summaries.append(
            {
                "memory": memory,
                "runs": len(items),
                "pass_rate": sum(bool(item["pass"]) for item in items) / len(items) if items else 0.0,
                "avg_iterations": sum(item["iterations"] for item in items) / len(items) if items else 0.0,
                "avg_token_cost": sum(item["token_cost"] for item in items) / len(items) if items else 0.0,
                "total_token_cost": sum(item["token_cost"] for item in items),
                "avg_latency_seconds": sum(latencies) / len(latencies) if latencies else None,
                "total_latency_seconds": sum(latencies) if latencies else None,
            }
        )
    return summaries


def build_summary(questions: list[dict], results: list[dict]) -> dict:
    return {
        "api": API_ROOT,
        "model": MODEL,
        "question_selection": [
            {"rank": q["rank"], "question_id": q["question_id"], "title": q["title"]}
            for q in questions
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


def persist(questions: list[dict], results: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(build_summary(questions, results), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if results:
        with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(results[0]))
            writer.writeheader()
            writer.writerows(results)


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


def main() -> int:
    files = sorted(QUESTIONS_DIR.glob("*-question.json"))
    by_rank = {}
    for path in files:
        question = json.loads(path.read_text(encoding="utf-8"))
        by_rank[int(question["rank"])] = question
    missing_ranks = [rank for rank in RANKS if rank not in by_rank]
    if missing_ranks:
        raise RuntimeError(f"Missing question ranks: {missing_ranks}")
    questions = [by_rank[rank] for rank in RANKS]
    missing_cases = [str(q["question_id"]) for q in questions if str(q["question_id"]) not in TEST_CASES]
    if missing_cases:
        raise RuntimeError(f"Missing manual cases for question ids: {', '.join(missing_cases)}")
    if request_json("GET", "/api/health").get("status") != "ok":
        raise RuntimeError(f"API is not healthy at {API_ROOT}")

    results: list[dict] = []
    total = len(questions) * 2
    persist(questions, results)
    for index, question in enumerate(questions, start=1):
        results.append(run_one(question, True, index * 2 - 1, total))
        persist(questions, results)
        results.append(run_one(question, False, index * 2, total))
        persist(questions, results)
    print(json.dumps(build_summary(questions, results)["groups"], ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, OSError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
