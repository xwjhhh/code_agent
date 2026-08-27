"""Local Git Bash execution environment."""

import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SUBMISSION_COMMAND = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"


@dataclass
class LocalEnvironmentConfig:
    cwd: Path
    timeout: int = 30
    bash_path: str | None = None
    env: dict[str, str] = field(default_factory=dict)


class LocalEnvironment:
    def __init__(
        self,
        cwd: str | Path,
        timeout: int = 30,
        bash_path: str | None = None,
        env: dict[str, str] | None = None,
    ):
        workspace = Path(cwd).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        self.config = LocalEnvironmentConfig(workspace, timeout, bash_path, env or {})
        self.bash_path = resolve_bash_path(bash_path)

    def execute(self, action: dict[str, Any]) -> dict[str, Any]:
        command = action.get("command", "")

        try:
            completed = subprocess.run(
                [self.bash_path, "-lc", command],
                cwd=self.config.cwd,
                env=os.environ | self.config.env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.config.timeout,
                check=False,
            )
            combined_output = completed.stdout
            if completed.stderr:
                combined_output += ("\n" if combined_output else "") + completed.stderr
            output = {"output": combined_output, "returncode": completed.returncode, "exception_info": ""}
            if command.strip() == SUBMISSION_COMMAND and completed.returncode == 0:
                output["extra"] = {"submitted": True}
            return output
        except subprocess.TimeoutExpired as error:
            output = _decode_output(error.stdout) + _decode_output(error.stderr)
            return {
                "output": output,
                "returncode": -1,
                "exception_info": f"Command timed out after {self.config.timeout} seconds.",
            }
        except OSError as error:
            return {
                "output": "",
                "returncode": -1,
                "exception_info": f"Failed to execute command: {error}",
            }

    def serialize(self) -> dict[str, Any]:
        config = asdict(self.config)
        config["cwd"] = str(config["cwd"])
        config["bash_path"] = self.bash_path
        config["env"] = sorted(config["env"])
        return {"environment": config, "environment_type": type(self).__name__}


def resolve_bash_path(configured_path: str | None = None) -> str:
    candidates = [
        configured_path,
        os.getenv("CODE_AGENT_BASH_PATH"),
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        str(Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Git" / "bin" / "bash.exe")
        if os.getenv("LOCALAPPDATA")
        else None,
        shutil.which("bash") if os.name != "nt" else None,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    if os.name == "nt":
        raise FileNotFoundError(
            "Git Bash was not found. Install Git for Windows or set CODE_AGENT_BASH_PATH "
            "to the full path of Git's bin\\bash.exe."
        )
    raise FileNotFoundError("Bash was not found on PATH.")


def _decode_output(value: str | bytes | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""
