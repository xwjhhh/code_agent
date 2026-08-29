"""Export public, static GitHub Pages data from local run and memory storage.

The SQLite database, vectors, model messages, workspace paths, and environment
configuration never leave the local project. Only fields required by the
project showcase are written to docs/data/.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "data"
MEMORY_DB = PROJECT_ROOT / "memory_store" / "memory.sqlite3"
TRAJECTORY_DIR = PROJECT_ROOT / "trajectories"
MAX_MEMORIES = 200
MAX_RUNS = 100


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def safe_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in value] if isinstance(value, list) else []


def read_solution_code(run_dir: Path, result: dict[str, Any]) -> str:
    """Read the generated solution for the public, static run detail view."""
    candidates: list[Path] = []
    solution_path = result.get("solution_path")
    if isinstance(solution_path, str) and solution_path:
        candidates.append(Path(solution_path))
    workspace = result.get("workspace")
    if isinstance(workspace, str) and workspace:
        candidates.append(Path(workspace) / "solution.py")
    candidates.append(PROJECT_ROOT / "workspace" / run_dir.name / "solution.py")
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return ""


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or len(left) != len(right):
        return -1.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return -1.0
    return dot / (left_norm * right_norm)


def export_memories() -> dict[str, Any]:
    if not MEMORY_DB.is_file():
        return {"generated_at": now(), "count": 0, "embedding_model": None, "nodes": [], "edges": []}

    with sqlite3.connect(MEMORY_DB) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT id, category, granularity, trigger_text, content, purpose,
                   steps_json, negative_example, problem_family_json,
                   algorithm_tags_json, constraints_json, priority, quality_score,
                   source_run_id, source_verified, embedding_model, embedding_json,
                   created_at, retrieval_count
            FROM memories
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (MAX_MEMORIES,),
        ).fetchall()

    nodes: list[dict[str, Any]] = []
    vectors: dict[str, list[float]] = {}
    for row in rows:
        try:
            vector = json.loads(row["embedding_json"])
        except json.JSONDecodeError:
            vector = []
        if isinstance(vector, list) and all(isinstance(value, (int, float)) for value in vector):
            vectors[row["id"]] = [float(value) for value in vector]
        nodes.append(
            {
                "id": row["id"],
                "category": row["category"],
                "granularity": row["granularity"],
                "trigger": row["trigger_text"],
                "content": row["content"],
                "purpose": row["purpose"],
                "steps": safe_list(row["steps_json"]),
                "negative_example": row["negative_example"],
                "problem_family": safe_list(row["problem_family_json"]),
                "algorithm_tags": safe_list(row["algorithm_tags_json"]),
                "constraints": safe_list(row["constraints_json"]),
                "priority": row["priority"],
                "quality_score": row["quality_score"],
                "source_run_id": row["source_run_id"],
                "source_verified": bool(row["source_verified"]),
                "created_at": row["created_at"],
                "retrieval_count": row["retrieval_count"],
            }
        )

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
            edge["similarity"] = round(similarity, 4)
        edges.append(edge)

    by_source: dict[str, list[dict[str, Any]]] = {}
    for node in nodes:
        source = node["source_run_id"]
        if source:
            by_source.setdefault(source, []).append(node)
    for group in by_source.values():
        anchor = next((node for node in group if node["granularity"] == "task"), group[0])
        for node in group:
            if node["id"] != anchor["id"]:
                add_edge(anchor["id"], node["id"], "solid")

    task_nodes = [node for node in nodes if node["granularity"] == "task"]
    candidates: list[tuple[float, str, str]] = []
    for index, left in enumerate(task_nodes):
        for right in task_nodes[index + 1 :]:
            similarity = cosine_similarity(vectors.get(left["id"], []), vectors.get(right["id"], []))
            if similarity >= 0.35:
                candidates.append((similarity, left["id"], right["id"]))
    degrees = {node["id"]: 0 for node in task_nodes}
    for similarity, left_id, right_id in sorted(candidates, reverse=True):
        if degrees[left_id] >= 3 or degrees[right_id] >= 3:
            continue
        add_edge(left_id, right_id, "dotted", similarity)
        degrees[left_id] += 1
        degrees[right_id] += 1

    embedding_model = next((row["embedding_model"] for row in rows if row["embedding_model"]), None)
    return {"generated_at": now(), "count": len(nodes), "embedding_model": embedding_model, "nodes": nodes, "edges": edges}


def status_for(result: dict[str, Any], error: str | None) -> str:
    if error or not result.get("verified"):
        return "failed"
    return "passed" if result.get("status") == "success" else "reviewing"


def export_runs() -> dict[str, Any]:
    runs: list[dict[str, Any]] = []
    if not TRAJECTORY_DIR.is_dir():
        return {"generated_at": now(), "count": 0, "items": []}

    for run_dir in TRAJECTORY_DIR.iterdir():
        path = run_dir / "trajectory.json"
        if not run_dir.is_dir() or not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
        model = payload.get("model") if isinstance(payload.get("model"), dict) else {}
        model_config = model.get("model") if isinstance(model.get("model"), dict) else {}
        model_name = str(model_config.get("model_name") or model.get("model_name") or "unknown")
        review = payload.get("review") if isinstance(payload.get("review"), dict) else {}
        error = str(payload.get("error")) if payload.get("error") else None
        if not error and result.get("status") == "model_error":
            messages = result.get("messages")
            if isinstance(messages, list) and messages and isinstance(messages[-1], dict):
                content = messages[-1].get("content")
                if content:
                    error = str(content)[:1000]
        task = str(payload.get("task", "")).strip()
        if not task:
            continue
        cases = payload.get("test_cases") if isinstance(payload.get("test_cases"), list) else []
        solution_code = read_solution_code(run_dir, result)
        runs.append(
            {
                "run_id": run_dir.name,
                "task": task,
                "model": model_name,
                "status": status_for(result, error),
                "verified": bool(result.get("verified")),
                "model_calls": result.get("model_calls", 0),
                "created_at": str(payload.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()),
                "test_case_count": len(cases),
                "last_test_output": str(result.get("last_test_output", "")),
                "solution_code": solution_code,
                "review": {"status": review.get("status"), "content": review.get("content", "")},
                "error": error,
            }
        )
    runs.sort(key=lambda item: item["created_at"], reverse=True)
    return {"generated_at": now(), "count": len(runs[:MAX_RUNS]), "items": runs[:MAX_RUNS]}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    runs = export_runs()
    memories = export_memories()
    write_json(OUTPUT_DIR / "runs.json", runs)
    write_json(OUTPUT_DIR / "memories.json", memories)
    print(f"Exported {runs['count']} runs and {memories['count']} memories to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
