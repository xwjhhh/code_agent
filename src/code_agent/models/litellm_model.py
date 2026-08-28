"""LiteLLM-backed model adapter."""

import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from code_agent.exceptions import ModelError
from code_agent.models.utils.actions import BASH_TOOL, format_observation_messages, parse_tool_calls

PRIMARY_MODEL_NAME = "openai/zai-org/GLM-5.2"

def resolve_api_key(model_name: str | None = None) -> str | None:
    """Return the single SiliconFlow key used by GLM-5.2 calls."""
    return os.getenv("OPENAI_API_KEY")


def validate_model_name(model_name: str) -> str:
    if model_name != PRIMARY_MODEL_NAME:
        raise ValueError(
            f"This project is configured to use only {PRIMARY_MODEL_NAME}; "
            f"received {model_name!r}."
        )
    return model_name


@dataclass
class LitellmModelConfig:
    model_name: str
    model_kwargs: dict[str, Any] = field(default_factory=dict)
    max_retries: int = 3


class LitellmModel:
    def __init__(self, model_name: str, model_kwargs: dict[str, Any] | None = None, max_retries: int = 3):
        validate_model_name(model_name)
        self.config = LitellmModelConfig(model_name, model_kwargs or {}, max_retries)

    def query(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        try:
            import litellm
        except ImportError as error:
            raise ModelError("LiteLLM is not installed. Run 'pip install -e .' first.") from error

        prepared_messages = [{key: value for key, value in message.items() if key != "extra"} for message in messages]
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                response = litellm.completion(
                    model=self.config.model_name,
                    messages=prepared_messages,
                    tools=[BASH_TOOL],
                    **(self.config.model_kwargs | kwargs),
                )
            except Exception as error:  # Provider exceptions differ across LiteLLM backends.
                last_error = error
                if attempt + 1 < self.config.max_retries:
                    time.sleep(2**attempt)
            else:
                return self._format_response(response)
        raise ModelError(f"Model request failed after {self.config.max_retries} attempts: {last_error}") from last_error

    def _format_response(self, response: Any) -> dict[str, Any]:
        response_message = response.choices[0].message
        tool_calls = _get(response_message, "tool_calls") or []
        if hasattr(response_message, "model_dump"):
            message = response_message.model_dump()
        elif isinstance(response_message, dict):
            message = dict(response_message)
        else:
            message = vars(response_message)
        message["extra"] = {
            "actions": parse_tool_calls(tool_calls),
            "response": response.model_dump(mode="json") if hasattr(response, "model_dump") else repr(response),
        }
        return message

    def query_text(self, messages: list[dict[str, Any]], **kwargs: Any) -> str:
        """Run a normal model call without tools for tests and review."""
        try:
            import litellm
        except ImportError as error:
            raise ModelError("LiteLLM is not installed. Run 'pip install -e .' first.") from error

        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                response = litellm.completion(
                    model=self.config.model_name,
                    messages=messages,
                    **(self.config.model_kwargs | kwargs),
                )
            except Exception as error:
                last_error = error
                if attempt + 1 < self.config.max_retries:
                    time.sleep(2**attempt)
            else:
                return response.choices[0].message.content or ""
        raise ModelError(f"Model request failed after {self.config.max_retries} attempts: {last_error}") from last_error

    def format_message(self, **kwargs: Any) -> dict[str, Any]:
        return dict(kwargs)

    def format_observation_messages(
        self,
        message: dict[str, Any],
        outputs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return format_observation_messages(message.get("extra", {}).get("actions", []), outputs)

    def serialize(self) -> dict[str, Any]:
        config = asdict(self.config)
        config["model_kwargs"] = {
            key: "***" if any(secret in key.lower() for secret in ("key", "token", "secret", "password")) else value
            for key, value in config["model_kwargs"].items()
        }
        return {"model": config, "model_type": type(self).__name__}


def _get(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)
