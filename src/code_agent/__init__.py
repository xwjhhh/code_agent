"""Core protocols for the coding agent."""

from pathlib import Path
from typing import Any, Protocol

__version__ = "0.1.0"

package_dir = Path(__file__).resolve().parent


class Model(Protocol):
    def query(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]: ...

    def format_message(self, **kwargs: Any) -> dict[str, Any]: ...

    def format_observation_messages(
        self,
        message: dict[str, Any],
        outputs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]: ...

    def serialize(self) -> dict[str, Any]: ...


class Environment(Protocol):
    def execute(self, action: dict[str, Any]) -> dict[str, Any]: ...

    def serialize(self) -> dict[str, Any]: ...


class Agent(Protocol):
    def run(self, task: str) -> dict[str, Any]: ...

    def save(self, path: Path | None = None, **extra: Any) -> dict[str, Any]: ...


__all__ = ["Agent", "Environment", "Model", "__version__", "package_dir"]
