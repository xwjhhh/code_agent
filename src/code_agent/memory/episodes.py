"""Build evidence-backed recovery episodes from a coding-agent run."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


TEST_COMMAND = "python -m pytest -q"


@dataclass
class RecoveryEpisode:
    """One contiguous failed-test -> edit -> passing-test episode."""

    failed_test: str
    failure_output: str
    code_before: str
    actions_between: list[str] = field(default_factory=list)
    code_after: str = ""
    passed_test: str = ""
    failure_count: int = 1
    source_verified: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RecoveryEpisodeBuilder:
    """Extract only recoveries with observable failure, edit, and pass evidence.

    Multiple failing test runs before the eventual pass are folded into one
    episode, preventing one bug from inflating the memory bank.
    """

    def build(self, result: dict[str, Any]) -> list[RecoveryEpisode]:
        steps = result.get("steps", [])
        if not isinstance(steps, list):
            return []
        changed_event_steps = self._changed_solution_steps(result.get("events"))

        episodes: list[RecoveryEpisode] = []
        pending: dict[str, Any] | None = None
        changed_since_failure = False
        actions_between: list[str] = []

        for step in steps:
            if not isinstance(step, dict):
                continue
            command = self._command(step)
            observation = step.get("observation") if isinstance(step.get("observation"), dict) else {}
            output = str(observation.get("output", "") or "").strip()
            returncode = observation.get("returncode")
            is_test = command.strip() == TEST_COMMAND or self._event_test_kind(step) is not None
            test_kind = self._event_test_kind(step)
            if is_test:
                passed = test_kind == "passed" or (test_kind is None and returncode == 0 and self._looks_passed(output))
                failed = test_kind == "failed" or (test_kind is None and not passed)
                if failed:
                    if pending is None:
                        pending = {
                            "failed_test": command or TEST_COMMAND,
                            "failure_output": output,
                            "code_before": self._snapshot(step, "before"),
                            "failure_count": 1,
                        }
                        actions_between = []
                        changed_since_failure = False
                    else:
                        pending["failure_count"] += 1
                        if output:
                            previous = str(pending.get("failure_output", ""))
                            pending["failure_output"] = "\n---\n".join(item for item in (previous, output) if item)
                    continue
                if passed and pending is not None and changed_since_failure:
                    episodes.append(
                        RecoveryEpisode(
                            failed_test=str(pending["failed_test"]),
                            failure_output=str(pending.get("failure_output", "")),
                            code_before=str(pending.get("code_before", "")),
                            actions_between=list(actions_between),
                            code_after=self._snapshot(step, "after"),
                            passed_test=output or command or TEST_COMMAND,
                            failure_count=int(pending.get("failure_count", 1)),
                        )
                    )
                    pending = None
                    actions_between = []
                    changed_since_failure = False
                elif passed and pending is not None:
                    # A flaky/repeated test without an intervening edit is not
                    # evidence that a repair caused the pass.
                    pending = None
                    actions_between = []
                    changed_since_failure = False
                continue

            if pending is not None:
                if command:
                    actions_between.append(command[:2000])
                if self._step_changed_solution(step, command) or step.get("step") in changed_event_steps:
                    changed_since_failure = True

        return episodes

    @staticmethod
    def _command(step: dict[str, Any]) -> str:
        action = step.get("action")
        if isinstance(action, dict):
            return str(action.get("command", "") or "").strip()
        return str(step.get("command", "") or "").strip()

    @staticmethod
    def _event_test_kind(step: dict[str, Any]) -> str | None:
        event_type = step.get("event_type") or step.get("type")
        if event_type in {"test_failed", "test_passed"}:
            return "failed" if event_type == "test_failed" else "passed"
        return None

    @staticmethod
    def _looks_passed(output: str) -> bool:
        return " passed" in output or output.endswith("passed")

    @staticmethod
    def _snapshot(step: dict[str, Any], which: str) -> str:
        for key in (f"solution_{which}", f"code_{which}", f"{which}_code"):
            value = step.get(key)
            if isinstance(value, str):
                return value
        snapshots = step.get("file_snapshots")
        if isinstance(snapshots, dict):
            value = snapshots.get(which) or snapshots.get(f"solution_{which}")
            if isinstance(value, str):
                return value
        return ""

    @staticmethod
    def _step_changed_solution(step: dict[str, Any], command: str) -> bool:
        if step.get("file_changed") or step.get("solution_changed"):
            return True
        changed = step.get("changed_files")
        if isinstance(changed, (list, tuple)) and any("solution.py" in str(name) for name in changed):
            return True
        if "solution.py" in command and "test_solution.py" not in command:
            return True
        before = RecoveryEpisodeBuilder._snapshot(step, "before")
        after = RecoveryEpisodeBuilder._snapshot(step, "after")
        return bool(before and after and before != after)

    @staticmethod
    def _changed_solution_steps(events: object) -> set[object]:
        changed: set[object] = set()
        if not isinstance(events, list):
            return changed
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "file_changed":
                continue
            data = event.get("data") if isinstance(event.get("data"), dict) else event
            if "solution.py" in str(data.get("filename", "")):
                changed.add(data.get("step"))
        return changed


def recovery_episode_context(episodes: list[RecoveryEpisode]) -> str:
    """Serialize episodes into a compact, model-readable evidence block."""
    sections: list[str] = []
    for index, episode in enumerate(episodes, start=1):
        sections.append(
            "\n".join(
                [
                    f"Episode {index}",
                    f"failed_test: {episode.failed_test}",
                    f"failure_output: {episode.failure_output[:5000]}",
                    f"code_before:\n```python\n{episode.code_before[:10000]}\n```",
                    "actions_between:\n" + "\n".join(f"- {item}" for item in episode.actions_between[:20]),
                    f"code_after:\n```python\n{episode.code_after[:10000]}\n```",
                    f"passed_test: {episode.passed_test[:5000]}",
                ]
            )
        )
    return "\n\n---\n\n".join(sections)
