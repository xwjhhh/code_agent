import json
from pathlib import Path

from code_agent.environments.local import LocalEnvironment
from code_agent.test_cases import generate_test_cases, normalize_cases, save_test_files


class StaticTextModel:
    def query_text(self, messages, **kwargs):
        return json.dumps(
            [
                {"name": "sample", "input": "ab4f35gr#a6", "expected_output": "abfgr#a4356"},
                {"name": "alternate", "input": "a1b2", "expected_output": "ab12"},
                {"name": "no_digits", "input": "abc", "expected_output": "abc"},
            ]
        )


def test_generated_cases_use_canonical_shape():
    cases = generate_test_cases(StaticTextModel(), "字符移动", count=3)

    assert len(cases) == 3
    assert cases[0]["input"] == "ab4f35gr#a6"
    assert cases[0]["source"] == "generated"


def test_saved_test_runner_reads_json(tmp_path: Path):
    cases = [{"name": "sample", "input": "a1", "expected_output": "a1", "source": "manual"}]
    save_test_files(tmp_path, "字符移动", cases, "manual")

    payload = json.loads((tmp_path / "test_cases.json").read_text(encoding="utf-8"))
    assert payload["cases"] == cases
    assert 'Path("test_cases.json")' in (tmp_path / "test_solution.py").read_text(encoding="utf-8")


def test_manual_case_can_represent_empty_input_and_output():
    cases = normalize_cases([{"input": "", "expected_output": ""}], "manual")

    assert cases == [{"name": "case_1", "input": "", "expected_output": "", "source": "manual"}]


def test_environment_restores_protected_test_file(tmp_path: Path, monkeypatch):
    bash = tmp_path / "bash.exe"
    bash.touch()
    protected = tmp_path / "test_cases.json"
    protected.write_text("original", encoding="utf-8")

    def fake_run(*args, **kwargs):
        protected.write_text("changed", encoding="utf-8")
        from subprocess import CompletedProcess
        return CompletedProcess(args[0], 0, stdout="", stderr="")

    monkeypatch.setattr("code_agent.environments.local.subprocess.run", fake_run)
    environment = LocalEnvironment(tmp_path, bash_path=str(bash), protected_files=["test_cases.json"])
    output = environment.execute({"command": "change tests"})

    assert output["returncode"] == -1
    assert protected.read_text(encoding="utf-8") == "original"
