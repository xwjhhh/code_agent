"""Exceptions that control or terminate the agent loop."""


class AgentFlowError(Exception):
    def __init__(self, *messages: dict):
        self.messages = list(messages)
        super().__init__()


class FormatError(AgentFlowError):
    """The model response did not contain valid Bash tool calls."""


class Submitted(AgentFlowError):
    """The environment received the task submission command."""


class LimitsExceeded(AgentFlowError):
    """The agent reached its configured model-call limit."""


class ModelError(Exception):
    """The model request failed after retries."""
