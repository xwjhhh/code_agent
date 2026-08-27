import subprocess
from pathlib import Path

from code_agent.environments.local import LocalEnvironment


def test_local_environment_runs_command(tmp_path: Path, monkeypatch):
    bash = tmp_path / "bash.exe"
    bash.touch()
    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args[0], 0, stdout="hello", stderr="")

    monkeypatch.setattr("code_agent.environments.local.subprocess.run", fake_run)
    environment = LocalEnvironment(tmp_path, bash_path=str(bash))

    output = environment.execute({"command": "printf hello"})

    assert output["returncode"] == 0
    assert output["output"] == "hello"
    assert calls[0][0][0][1:] == ["-lc", "printf hello"]
    assert calls[0][1]["cwd"] == tmp_path.resolve()


def test_local_environment_returns_timeout(tmp_path: Path, monkeypatch):
    bash = tmp_path / "bash.exe"
    bash.touch()

    def raise_timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output="partial output")

    monkeypatch.setattr("code_agent.environments.local.subprocess.run", raise_timeout)
    environment = LocalEnvironment(tmp_path, timeout=1, bash_path=str(bash))

    output = environment.execute({"command": "sleep 2"})

    assert output["returncode"] == -1
    assert output["output"] == "partial output"
    assert "timed out" in output["exception_info"]
