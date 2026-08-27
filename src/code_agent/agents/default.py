"""Core model-action-environment agent loop."""

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from code_agent import Environment, Model, __version__
from code_agent.exceptions import FormatError, LimitsExceeded, ModelError

TEST_COMMAND = "python -m pytest -q"
SUBMISSION_COMMAND = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
PASSED_TEST_PATTERN = re.compile(r"\b[1-9]\d* passed\b")


@dataclass
class AgentConfig:
    system_prompt: str
    task_template: str
    step_limit: int = 20
    output_path: Path | None = None


class DefaultAgent:
    def __init__(
        self,
        model: Model,
        env: Environment,
        system_prompt: str,
        task_template: str,
        step_limit: int = 20,
        output_path: str | Path | None = None,
    ):
        self.config = AgentConfig(
            system_prompt=system_prompt,
            task_template=task_template,
            step_limit=step_limit,
            output_path=Path(output_path) if output_path else None,
        )
        self.model = model
        self.env = env
        self.messages: list[dict[str, Any]] = []
        self.steps: list[dict[str, Any]] = []
        self.n_calls = 0
        self.verified = False
        self.last_test_output = ""
        self.exit_status = "running"

    def run(self, task: str) -> dict[str, Any]:
        self._reset(task)
        try:
            while self.exit_status == "running":
                self.step()
        except LimitsExceeded as error:
            self._finish_from_flow(error, "max_steps")
        except ModelError as error:
            self.exit_status = "model_error"
            self.add_messages({"role": "exit", "content": str(error), "extra": {"exit_status": self.exit_status}})
        finally:
            self.save()
        return self.result()

    def step(self) -> list[dict[str, Any]]:
        message = self.query()
        return self.execute_actions(message)

    def query(self) -> dict[str, Any]:
        if self.n_calls >= self.config.step_limit:
            raise LimitsExceeded()
        self.n_calls += 1
        try:
            message = self.model.query(self.messages)
        except FormatError as error:
            self.add_messages(*error.messages)
            self.steps.append({"step": self.n_calls, "format_error": error.messages})
            return {"role": "assistant", "content": "", "extra": {"actions": []}}
        self.add_messages(message)
        return message

    def execute_actions(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        actions = message.get("extra", {}).get("actions", [])
        if not actions:
            return []

        outputs = []
        submitted = False
        for action in actions:
            command = action["command"]
            if self.verified and command.strip() != SUBMISSION_COMMAND:
                self.verified = False
            output = self.env.execute(action)
            outputs.append(output)
            submitted = submitted or output.get("extra", {}).get("submitted", False)
            if command.strip() == TEST_COMMAND:
                self.verified = (
                    output["returncode"] == 0
                    and bool(PASSED_TEST_PATTERN.search(output["output"]))
                    and self._required_files_exist()
                )
                self.last_test_output = output["output"]
            self.steps.append({"step": self.n_calls, "action": action, "observation": output})

        observations = self.model.format_observation_messages(message, outputs)
        result_messages = self.add_messages(*observations)
        if submitted:
            result_messages.extend(self._handle_submission(message))
        return result_messages

    def _handle_submission(
        self,
        message: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self.verified:
            self.exit_status = "success"
            exit_message = {
                "role": "exit",
                "content": "Task completed after local tests passed.",
                "extra": {"exit_status": "success", "submission": ""},
            }
            return self.add_messages(exit_message)

        rejection = self.model.format_message(
            role="user",
            content=(
                "Submission rejected: local verification has not passed. "
                "Create solution.py and test_solution.py, then run exactly "
                "'python -m pytest -q' successfully before submitting."
            ),
            extra={"error_type": "UnverifiedSubmission"},
        )
        self.steps.append({"step": self.n_calls, "rejected_submission": True})
        return self.add_messages(rejection)

    def _reset(self, task: str) -> None:
        self.messages = []
        self.steps = []
        self.n_calls = 0
        self.verified = False
        self.last_test_output = ""
        self.exit_status = "running"
        self.add_messages(
            self.model.format_message(role="system", content=self.config.system_prompt),
            self.model.format_message(role="user", content=self.config.task_template.format(task=task)),
        )

    def _finish_from_flow(self, error: LimitsExceeded, status: str) -> None:
        self.exit_status = status
        messages = error.messages or [
            {"role": "exit", "content": "Model call limit reached.", "extra": {"exit_status": status}}
        ]
        self.add_messages(*messages)

    def add_messages(self, *messages: dict[str, Any]) -> list[dict[str, Any]]:
        self.messages.extend(messages)
        return list(messages)

    def _required_files_exist(self) -> bool:
        environment = self.env.serialize().get("environment", {})
        workspace = Path(environment.get("cwd", "."))
        return (workspace / "solution.py").is_file() and (workspace / "test_solution.py").is_file()

    def result(self) -> dict[str, Any]:
        environment = self.env.serialize().get("environment", {})
        workspace = Path(environment.get("cwd", "."))
        return {
            "status": self.exit_status,
            "verified": self.verified,
            "model_calls": self.n_calls,
            "workspace": str(workspace),
            "solution_path": str(workspace / "solution.py"),
            "test_path": str(workspace / "test_solution.py"),
            "last_test_output": self.last_test_output,
            "messages": self.messages,
            "steps": self.steps,
        }

    def serialize(self, **extra: Any) -> dict[str, Any]:
        return {
            "version": __version__,
            "agent": {**asdict(self.config), "output_path": str(self.config.output_path or "")},
            "model": self.model.serialize(),
            "environment": self.env.serialize(),
            "result": self.result(),
            **extra,
        }

    def save(self, path: Path | None = None, **extra: Any) -> dict[str, Any]:
        data = self.serialize(**extra)
        destination = path or self.config.output_path
        if destination:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return data
