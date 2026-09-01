"""Run two difficult Codeforces problems with memory on and off.

The benchmark keeps the test suites deterministic and disables post-run
learning so the comparison measures task-time retrieval only.  The two
problems are Codeforces 868F (rating 2500) and 342E (rating 2400).
"""

from __future__ import annotations

import bisect
import csv
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "scripts"
RESULTS_PATH = OUTPUT_DIR / "codeforces_two_memory_benchmark_results.json"
SUMMARY_PATH = OUTPUT_DIR / "codeforces_two_memory_benchmark_summary.json"
CSV_PATH = OUTPUT_DIR / "codeforces_two_memory_benchmark_results.csv"
API_ROOT = "http://127.0.0.1:8002"
MODEL = "openai/deepseek-ai/DeepSeek-V4-Flash"
MAX_STEPS = 30
TIMEOUT = 120
POLL_SECONDS = 3
MEMORY_SOURCE = "manual-codeforces-two-benchmark"


PROBLEMS = {
    "868F": {
        "title": "Codeforces 868F - Yet Another Minimization Problem",
        "url": "https://codeforces.com/problemset/problem/868/F",
        "rating": 2500,
        "task": """Codeforces 868F - Yet Another Minimization Problem (rating 2500).

Given an integer sequence a[1..n] and an integer k, split the sequence into
exactly k non-empty contiguous groups.  The cost of a group [l,r] is the
number of pairs (i,j) with l <= i < j <= r and a[i] = a[j].  Minimize the sum
of group costs.

Input: the first line contains n and k (1 <= k <= n <= 100000).  The second
line contains n integers a[i] (1 <= a[i] <= n).  Output one integer, the
minimum possible cost.  The answer can exceed 32-bit signed integer range.

This is the standard Codeforces problem; implement solve(input_text: str) ->
str and read the complete input from input_text.""",
    },
    "342E": {
        "title": "Codeforces 342E - Xenia and Tree",
        "url": "https://codeforces.com/problemset/problem/342/E",
        "rating": 2400,
        "task": """Codeforces 342E - Xenia and Tree (rating 2400).

There is an undirected tree with n vertices and n-1 edges.  Initially only
vertex 1 is red.  Process m online operations:
1 v: paint vertex v red (it remains red forever).
2 v: print the minimum tree-edge distance from v to any red vertex.

Input: n and m (1 <= n,m <= 100000), followed by n-1 edges, followed by m
operations.  Output one line for every operation of type 2.  The input is a
single test case.  Implement solve(input_text: str) -> str and read the
complete input from input_text.""",
    },
}


def _cost_dp_reference(values: list[int], groups: int) -> int:
    """Reference D&C DP used only to produce a stress expected value."""
    n = len(values)
    inf = 10**30
    previous = [inf] * (n + 1)
    previous[0] = 0
    for group in range(1, groups + 1):
        current = [inf] * (n + 1)
        frequency = [0] * (max(values) + 1)
        left, right, pairs = 0, -1, 0

        def move(target_left: int, target_right: int) -> None:
            nonlocal left, right, pairs
            while left > target_left:
                left -= 1
                value = values[left]
                pairs += frequency[value]
                frequency[value] += 1
            while right < target_right:
                right += 1
                value = values[right]
                pairs += frequency[value]
                frequency[value] += 1
            while left < target_left:
                value = values[left]
                frequency[value] -= 1
                pairs -= frequency[value]
                left += 1
            while right > target_right:
                value = values[right]
                frequency[value] -= 1
                pairs -= frequency[value]
                right -= 1

        def divide(lo: int, hi: int, opt_lo: int, opt_hi: int) -> None:
            if lo > hi:
                return
            mid = (lo + hi) // 2
            best_value = inf
            best_at = -1
            start = max(group - 1, opt_lo)
            end = min(mid - 1, opt_hi)
            for split in range(start, end + 1):
                move(split, mid - 1)
                candidate = previous[split] + pairs
                if candidate < best_value:
                    best_value, best_at = candidate, split
            current[mid] = best_value
            divide(lo, mid - 1, opt_lo, best_at)
            divide(mid + 1, hi, best_at, opt_hi)

        divide(group, n, 0, n - 1)
        previous = current
    return previous[n]


def _make_868f_cases() -> list[dict[str, str]]:
    small = [1, 2, 1, 2, 1, 3, 3]
    stress = random.Random(868).randint
    values = [stress(1, 250) for _ in range(6000)]
    expected = _cost_dp_reference(values, 50)
    return [
        {"name": "sample_like", "input": "7 3\n1 2 1 2 1 3 3\n", "expected_output": str(_cost_dp_reference(small, 3))},
        {"name": "all_equal", "input": "5 2\n1 1 1 1 1\n", "expected_output": "4"},
        {"name": "large_optimized_dp", "input": f"6000 50\n{' '.join(map(str, values))}\n", "expected_output": str(expected)},
    ]


def _path_expected(red: list[int], queries: list[tuple[int, int]]) -> list[int]:
    ordered = [1]
    answers = []
    for kind, vertex in queries:
        if kind == 1:
            index = bisect.bisect_left(ordered, vertex)
            if index == len(ordered) or ordered[index] != vertex:
                ordered.insert(index, vertex)
        else:
            index = bisect.bisect_left(ordered, vertex)
            candidates = []
            if index:
                candidates.append(vertex - ordered[index - 1])
            if index < len(ordered):
                candidates.append(ordered[index] - vertex)
            answers.append(str(min(candidates)))
    return answers


def _make_342e_cases() -> list[dict[str, str]]:
    sample_queries = [(2, 7), (1, 6), (2, 5), (1, 4), (2, 3)]
    sample_lines = ["7 5", "1 2", "2 3", "3 4", "4 5", "5 6", "6 7"]
    sample_lines.extend(f"{kind} {vertex}" for kind, vertex in sample_queries)
    sample_expected = _path_expected([1], sample_queries)

    star_queries = [(2, 5), (1, 5), (2, 5), (2, 3), (1, 3), (2, 2)]
    star_lines = ["6 6"] + [f"1 {vertex}" for vertex in range(2, 7)]
    star_lines.extend(f"{kind} {vertex}" for kind, vertex in star_queries)
    # The helper above assumes a path, so calculate this tiny tree directly.
    star_expected = ["1", "0", "1", "1"]

    n = 50000
    queries: list[tuple[int, int]] = []
    for index in range(1, 20001):
        if index % 4 == 0:
            queries.append((1, 1 + (index * 7919) % n))
        else:
            queries.append((2, 1 + (index * 104729) % n))
    stress_lines = [f"{n} {len(queries)}"]
    stress_lines.extend(f"{vertex} {vertex + 1}" for vertex in range(1, n))
    stress_lines.extend(f"{kind} {vertex}" for kind, vertex in queries)
    stress_expected = _path_expected([1], queries)

    return [
        {"name": "path_sample", "input": "\n".join(sample_lines) + "\n", "expected_output": "\n".join(sample_expected)},
        {"name": "star_updates", "input": "\n".join(star_lines) + "\n", "expected_output": "\n".join(star_expected)},
        {"name": "long_path_online_stress", "input": "\n".join(stress_lines) + "\n", "expected_output": "\n".join(stress_expected)},
    ]


TEST_CASES = {"868F": _make_868f_cases(), "342E": _make_342e_cases()}


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


def _timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _usage(response: object) -> dict[str, int] | None:
    if isinstance(response, str):
        try:
            response = json.loads(response)
        except json.JSONDecodeError:
            return None
    if not isinstance(response, dict) or not isinstance(response.get("usage"), dict):
        return None
    return {key: int(response["usage"].get(key, 0) or 0) for key in ("prompt_tokens", "completion_tokens", "total_tokens")}


def _token_totals(state: dict) -> dict[str, int]:
    totals = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    for message in (state.get("result") or {}).get("messages", []):
        usage = _usage((message.get("extra") or {}).get("response")) if isinstance(message, dict) else None
        if usage:
            for key in totals:
                totals[key] += usage[key]
    return totals


def _latency(state: dict) -> float | None:
    start = _timestamp(state.get("created_at"))
    finish = next((_timestamp(event.get("timestamp")) for event in state.get("events", []) if event.get("type") == "run_finished"), None)
    if start is None or finish is None:
        return None
    return max(0.0, (finish - start).total_seconds())


def _summarize(problem_id: str, memory_enabled: bool, state: dict) -> dict:
    result = state.get("result") or {}
    usage = _token_totals(state)
    error = state.get("error")
    if not error and result.get("status") == "model_error":
        messages = result.get("messages") or []
        if messages:
            error = messages[-1].get("content") or "model_error"
    return {
        "problem": problem_id,
        "title": PROBLEMS[problem_id]["title"],
        "rating": PROBLEMS[problem_id]["rating"],
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
        "latency_seconds": _latency(state),
        "memory_state": state.get("memory", {}),
        "error": error,
    }


def _seed_memories() -> None:
    """Add the two manually verified strategy cards once, with real vectors."""
    load_dotenv(PROJECT_ROOT / ".env")
    from code_agent.memory.embedding import SiliconFlowEmbeddingClient, SiliconFlowEmbeddingConfig
    from code_agent.memory.schemas import MemoryNode
    from code_agent.memory.store import MemoryStore

    api_key = os.getenv("SILICONFLOW_EMBEDDING_API_KEY") or os.getenv("DEEPSEEK_API")
    if not api_key:
        raise RuntimeError("No embedding API key is available for seeding the benchmark memories.")
    store = MemoryStore(PROJECT_ROOT / "memory_store" / "memory.sqlite3")
    existing = {node.trigger for node in store.list(500, verified_only=False)}
    cards = [
        MemoryNode(
            category="strategy", experience_type="success",
            trigger="Codeforces 868F Yet Another Minimization Problem: partition a sequence into k groups and minimize equal-value pairs",
            content="Use dp[g][i] for the first i values in g groups. The transition is dp[g][i] = min over j<i of dp[g-1][j] + cost(j+1,i), where cost is equal-value pairs inside the interval. The optimal split index is monotone, so compute each DP layer with divide-and-conquer optimization. Maintain one global inclusive window and a frequency array while evaluating costs.",
            purpose="Prevent an O(k*n^2) transition and make the interval-cost invariant explicit.",
            steps=["Prove or use monotone opt indices for the quadrangle/partition DP", "For every midpoint evaluate only the allowed monotone split range", "Move the shared [L,R] window before each candidate", "When adding x add current frequency[x] to pairs then increment", "When removing x decrement frequency[x] then subtract the remaining frequency[x]", "Use 64-bit integers and verify small cases against brute force"],
            negative_example="Do not use a fresh frequency map for every interval or an O(k*n^2) nested transition; do not subtract before decrementing when removing an element.",
            problem_family=["sequence partition DP"], algorithm_tags=["divide-and-conquer optimization", "monotone opt", "sliding window cost"],
            constraints=["n up to 100000", "k up to n", "answer requires 64-bit"], priority=5, quality_score=1.0,
            source_run_id=MEMORY_SOURCE, source_verified=True,
            source_task=PROBLEMS["868F"]["task"], evidence=["Verified strategy card prepared from the Codeforces 868F editorial technique."],
            verification="Check all n<=10 sequences against brute-force DP, then run a large repeated/random case.",
        ),
        MemoryNode(
            category="strategy", experience_type="success",
            trigger="Codeforces 342E Xenia and Tree: online paint-red and nearest-red distance queries on a tree",
            content="Build a centroid decomposition tree. For every original vertex store each centroid ancestor and its distance. Maintain best[c], the minimum distance from centroid c to any red vertex. Initially update(1); on update(v), minimize best[c] with dist(v,c) for every centroid ancestor c. On query(v), return the minimum best[c]+dist(v,c) over the same ancestor list. This is O(log n) per operation after O(n log n) preprocessing.",
            purpose="Avoid rebuilding BFS for online queries and preserve the distance invariant through centroid levels.",
            steps=["Decompose each unblocked component and choose its centroid", "Record centroid ancestors and exact tree distances for every vertex", "Initialize all best values to INF and call update(1)", "For type 1 v walk v's centroid ancestors and lower best", "For type 2 v minimize best plus stored distance over those ancestors", "Use iterative or recursion-safe decomposition for n=100000"],
            negative_example="Do not run BFS/DFS from every query, and do not store only the nearest centroid without the distance for each level.",
            problem_family=["dynamic tree queries"], algorithm_tags=["centroid decomposition", "online nearest marked node", "distance aggregation"],
            constraints=["n,m up to 100000", "tree is unweighted", "vertex 1 is initially red"], priority=5, quality_score=1.0,
            source_run_id=MEMORY_SOURCE, source_verified=True,
            source_task=PROBLEMS["342E"]["task"], evidence=["Verified strategy card prepared from the Codeforces 342E editorial technique."],
            verification="Check a path and a star by brute force, then run a long path with many online operations.",
        ),
    ]
    missing = [card for card in cards if card.trigger not in existing]
    if not missing:
        return
    for card in missing:
        card.embedding_text = card.build_embedding_text()
    # source task is already set above; embed the two cards in one request.
    embedder = SiliconFlowEmbeddingClient(SiliconFlowEmbeddingConfig(api_key=api_key, api_base=os.getenv("OPENAI_API_BASE") or "https://api.siliconflow.cn/v1", timeout=60, max_retries=3))
    vectors = embedder.embed([card.embedding_text for card in missing])
    for card, vector in zip(missing, vectors, strict=True):
        card.embedding = vector
        card.source_task_embedding = embedder.embed([card.source_task])[0]
        card.embedding_model = embedder.config.model
        store.add(card)
    print(f"Seeded {len(missing)} benchmark memory card(s).", flush=True)


def _persist(questions: list[str], results: list[dict]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "api": API_ROOT,
        "model": MODEL,
        "question_selection": [{"id": key, "title": PROBLEMS[key]["title"], "url": PROBLEMS[key]["url"], "rating": PROBLEMS[key]["rating"]} for key in questions],
        "definition": {"pass_rate": "verified runs / runs", "avg_iterations": "mean result.model_calls", "token_cost": "sum usage.total_tokens in Agent model responses", "latency": "created_at to run_finished event", "memory_learning": "disabled for both groups"},
        "results": results,
    }
    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    SUMMARY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if results:
        with CSV_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=[key for key, value in results[0].items() if key != "memory_state"])
            writer.writeheader()
            for item in results:
                writer.writerow({key: value for key, value in item.items() if key != "memory_state"})


def _run_one(problem_id: str, memory_enabled: bool, index: int, total: int) -> dict:
    payload = {"task": PROBLEMS[problem_id]["task"], "model": MODEL, "max_steps": MAX_STEPS, "timeout": TIMEOUT, "test_cases": TEST_CASES[problem_id], "test_case_source": "manual", "memory_retrieval": memory_enabled, "memory_learning": False, "review_enabled": False}
    label = "on" if memory_enabled else "off"
    print(f"[{index}/{total}] {problem_id} memory={label} ...", flush=True)
    created = request_json("POST", "/api/runs", payload)
    state = wait_for_run(str(created["run_id"]))
    item = _summarize(problem_id, memory_enabled, state)
    print(f"    {item['result_status']} pass={item['pass']} iterations={item['iterations']} tokens={item['token_cost']} latency={item['latency_seconds']}", flush=True)
    return item


def main() -> int:
    if request_json("GET", "/api/health").get("status") != "ok":
        raise RuntimeError(f"API is not healthy at {API_ROOT}")
    _seed_memories()
    questions = ["868F", "342E"]
    results: list[dict] = []
    _persist(questions, results)
    for index, problem_id in enumerate(questions):
        results.append(_run_one(problem_id, True, index * 2 + 1, 4))
        _persist(questions, results)
        results.append(_run_one(problem_id, False, index * 2 + 2, 4))
        _persist(questions, results)
    for label in ("on", "off"):
        items = [item for item in results if item["memory"] == label]
        print(json.dumps({"memory": label, "pass_rate": sum(item["pass"] for item in items) / len(items), "avg_iterations": sum(item["iterations"] for item in items) / len(items), "avg_token_cost": sum(item["token_cost"] for item in items) / len(items), "avg_latency_seconds": sum(item["latency_seconds"] or 0 for item in items) / len(items)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (HTTPError, URLError, TimeoutError, KeyError, ValueError, OSError) as error:
        print(f"Benchmark failed: {error}", file=sys.stderr)
        raise SystemExit(1) from error
