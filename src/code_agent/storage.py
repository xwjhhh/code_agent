"""Persistence for trajectories and review results."""

import json
from pathlib import Path
from typing import Any


class RunStorage:
    def __init__(self, run_dir: str | Path):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)

    @property
    def trajectory_path(self) -> Path:
        return self.run_dir / "trajectory.json"

    @property
    def review_path(self) -> Path:
        return self.run_dir / "review.json"

    def save_trajectory(self, task: str, agent_data: dict[str, Any]) -> Path:
        self._write_json(self.trajectory_path, {"task": task, **agent_data})
        return self.trajectory_path

    def save_review(self, review: dict[str, Any]) -> Path:
        self._write_json(self.review_path, review)
        return self.review_path

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
