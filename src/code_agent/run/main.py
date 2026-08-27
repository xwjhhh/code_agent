"""Command-line entry point."""

import argparse
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from dotenv import load_dotenv

from code_agent import package_dir
from code_agent.agents import DefaultAgent
from code_agent.environments import LocalEnvironment
from code_agent.exceptions import ModelError
from code_agent.models import LitellmModel
from code_agent.reviewer import Reviewer
from code_agent.storage import RunStorage


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    load_dotenv()
    config = load_config(args.config)
    task = read_task(args)
    if not task.strip():
        raise SystemExit("Task cannot be empty.")
    model_name = args.model or os.getenv("CODE_AGENT_MODEL") or config["model"].get("model_name")
    if not model_name:
        raise SystemExit("Model name is required. Use --model or set CODE_AGENT_MODEL.")

    run_id = args.run_id or create_run_id(task)
    workspace = Path(args.workspace_root).resolve() / run_id
    storage = RunStorage(Path(args.trajectory_root).resolve() / run_id)

    model_kwargs = dict(config["model"].get("model_kwargs", {}))
    if args.base_url:
        model_kwargs["api_base"] = args.base_url
    model = LitellmModel(
        model_name=model_name,
        model_kwargs=model_kwargs,
        max_retries=config["model"].get("max_retries", 3),
    )
    try:
        environment = LocalEnvironment(
            cwd=workspace,
            timeout=args.timeout or config["environment"].get("timeout", 30),
            bash_path=args.bash_path or config["environment"].get("bash_path"),
        )
    except FileNotFoundError as error:
        raise SystemExit(str(error)) from error
    agent = DefaultAgent(
        model=model,
        env=environment,
        system_prompt=config["agent"]["system_prompt"],
        task_template=config["agent"]["task_template"],
        step_limit=args.max_steps or config["agent"].get("step_limit", 20),
        output_path=storage.trajectory_path,
    )

    print(f"Run: {run_id}")
    print(f"Workspace: {workspace}")
    result = agent.run(task)
    review = None
    if result["status"] == "success" and result["verified"]:
        try:
            print("Local verification passed. Running reviewer...")
            review = Reviewer(model).review(task, result)
            storage.save_review(review)
        except (ModelError, OSError, ValueError) as error:
            review = {"status": "error", "content": str(error)}
            storage.save_review(review)
    storage.save_trajectory(task, agent.serialize(review=review))
    print_result(result, review, storage)
    return 0 if result["status"] == "success" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Solve a Python algorithm problem with a local coding agent.")
    task_group = parser.add_mutually_exclusive_group(required=True)
    task_group.add_argument("--task", help="Natural-language algorithm problem.")
    task_group.add_argument("--task-file", type=Path, help="UTF-8 text file containing the problem.")
    parser.add_argument("--model", help="LiteLLM model name; defaults to CODE_AGENT_MODEL.")
    parser.add_argument("--base-url", help="Optional OpenAI-compatible API base URL.")
    parser.add_argument("--bash-path", help="Full path to Git Bash bin\\bash.exe.")
    parser.add_argument("--max-steps", type=int, help="Maximum number of model calls.")
    parser.add_argument("--timeout", type=int, help="Bash command timeout in seconds.")
    parser.add_argument("--workspace-root", default="workspace")
    parser.add_argument("--trajectory-root", default="trajectories")
    parser.add_argument("--run-id", help="Optional fixed run directory name.")
    parser.add_argument("--config", type=Path, default=package_dir / "config" / "default.yaml")
    return parser


def load_config(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def read_task(args: argparse.Namespace) -> str:
    return args.task if args.task is not None else args.task_file.read_text(encoding="utf-8")


def create_run_id(task: str) -> str:
    words = re.findall(r"[a-zA-Z0-9]+", task.lower())[:4]
    slug = "-".join(words) or "task"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{timestamp}-{slug}-{uuid4().hex[:6]}"


def print_result(result: dict[str, Any], review: dict[str, Any] | None, storage: RunStorage) -> None:
    print(f"Status: {result['status'].upper()}")
    print(f"Local verification: {'PASS' if result['verified'] else 'NOT PASSED'}")
    print(f"Solution: {result['solution_path']}")
    print(f"Tests: {result['test_path']}")
    print(f"Trajectory: {storage.trajectory_path}")
    if review:
        print(f"Review: {storage.review_path}")
        print(review.get("content", ""))


if __name__ == "__main__":
    raise SystemExit(main())
