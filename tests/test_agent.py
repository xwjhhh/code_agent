from pathlib import Path

from code_agent.agents import DefaultAgent


class FakeModel:
    def __init__(self, responses):
        self.responses = iter(responses)

    def format_message(self, **kwargs):
        return kwargs

    def query(self, messages):
        return next(self.responses)

    def format_observation_messages(self, message, outputs):
        action = message["extra"]["actions"][0]
        return [
            {
                "role": "tool",
                "tool_call_id": action["tool_call_id"],
                "content": outputs[0]["output"],
                "extra": {"observation": outputs[0]},
            }
        ]

    def serialize(self):
        return {"model_type": "FakeModel"}


class FakeEnvironment:
    def __init__(self, workspace: Path, test_returncode: int):
        self.workspace = workspace
        self.test_returncode = test_returncode

    def execute(self, action):
        if action["command"] == "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT":
            return {"output": "Task submitted", "returncode": 0, "exception_info": "", "extra": {"submitted": True}}
        if action["command"] == "python -m pytest -q":
            return {
                "output": "1 passed" if self.test_returncode == 0 else "1 failed",
                "returncode": self.test_returncode,
                "exception_info": "",
            }
        return {"output": "ok", "returncode": 0, "exception_info": ""}

    def serialize(self):
        return {"environment": {"cwd": str(self.workspace)}, "environment_type": "FakeEnvironment"}


def action(command: str, call_id: str) -> dict:
    return {"role": "assistant", "content": "", "extra": {"actions": [{"command": command, "tool_call_id": call_id}]}}


def test_agent_requires_test_pass_before_submission(tmp_path: Path):
    (tmp_path / "solution.py").write_text("def answer(): return 1", encoding="utf-8")
    (tmp_path / "test_solution.py").write_text("def test_answer(): assert True", encoding="utf-8")
    (tmp_path / "test_cases.json").write_text('{"cases": []}', encoding="utf-8")
    model = FakeModel(
        [
            action("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT", "submit-1"),
            action("python -m pytest -q", "test-1"),
            action("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT", "submit-2"),
        ]
    )
    agent = DefaultAgent(
        model,
        FakeEnvironment(tmp_path, test_returncode=0),
        system_prompt="system",
        task_template="{task}",
        step_limit=5,
    )

    result = agent.run("solve")

    assert result["status"] == "success"
    assert result["verified"] is True
    assert any(step.get("rejected_submission") for step in result["steps"])


def test_agent_marks_failed_test_as_unverified(tmp_path: Path):
    (tmp_path / "solution.py").write_text("def answer(): return 1", encoding="utf-8")
    (tmp_path / "test_solution.py").write_text("def test_answer(): assert False", encoding="utf-8")
    (tmp_path / "test_cases.json").write_text('{"cases": []}', encoding="utf-8")
    model = FakeModel([action("python -m pytest -q", "test-1")])
    agent = DefaultAgent(
        model,
        FakeEnvironment(tmp_path, test_returncode=1),
        system_prompt="system",
        task_template="{task}",
        step_limit=1,
    )

    result = agent.run("solve")

    assert result["status"] == "max_steps"
    assert result["verified"] is False
    assert any(event["type"] == "test_failed" for event in result["events"])
    failed_step = next(step for step in result["steps"] if step.get("action", {}).get("command") == "python -m pytest -q")
    assert "solution_before" in failed_step
    assert "solution_after" in failed_step


def test_agent_injects_recovery_memory_after_failed_pytest(tmp_path: Path):
    (tmp_path / "solution.py").write_text("def answer(): return 1", encoding="utf-8")
    (tmp_path / "test_solution.py").write_text("def test_answer(): assert False", encoding="utf-8")
    (tmp_path / "test_cases.json").write_text('{"cases": []}', encoding="utf-8")
    model = FakeModel([action("python -m pytest -q", "test-1")])
    agent = DefaultAgent(
        model,
        FakeEnvironment(tmp_path, test_returncode=1),
        system_prompt="system",
        task_template="{task}",
        step_limit=1,
        recovery_context_provider=lambda task, output, steps: "Relevant Past Experience: preserve line boundaries.",
    )

    agent.run("solve")

    assert any(message.get("extra", {}).get("memory_phase") == "recovery" for message in agent.messages)


def test_agent_snapshots_edits_even_when_command_hides_solution_path(tmp_path: Path):
    (tmp_path / "solution.py").write_text("def answer(): return 1", encoding="utf-8")
    (tmp_path / "test_solution.py").write_text("def test_answer(): assert True", encoding="utf-8")
    (tmp_path / "test_cases.json").write_text('{"cases": []}', encoding="utf-8")

    class HiddenEditEnvironment(FakeEnvironment):
        def execute(self, action):
            if action["command"] == "python -c hidden-edit":
                (self.workspace / "solution.py").write_text("def answer(): return 2", encoding="utf-8")
                return {"output": "ok", "returncode": 0, "exception_info": ""}
            return super().execute(action)

    agent = DefaultAgent(
        FakeModel([]),
        HiddenEditEnvironment(tmp_path, test_returncode=0),
        system_prompt="system",
        task_template="{task}",
        step_limit=1,
    )
    agent.execute_actions(action("python -c hidden-edit", "edit-1"))

    edited_step = agent.steps[0]
    assert edited_step["solution_changed"] is True
    assert edited_step["solution_before"] != edited_step["solution_after"]
    assert any(event["type"] == "file_changed" for event in agent.event_history)
