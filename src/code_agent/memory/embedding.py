"""SiliconFlow OpenAI-compatible embedding client."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from code_agent.exceptions import MemoryServiceError

EMBEDDING_MODEL_NAME = "Qwen/Qwen3-Embedding-8B"


@dataclass(frozen=True)
class SiliconFlowEmbeddingConfig:
    api_key: str
    model: str = EMBEDDING_MODEL_NAME
    api_base: str = "https://api.siliconflow.cn/v1"
    dimensions: int | None = None
    timeout: int = 30
    max_retries: int = 3


class SiliconFlowEmbeddingClient:
    """Calls POST /v1/embeddings using the schema documented by SiliconFlow."""

    def __init__(self, config: SiliconFlowEmbeddingConfig):
        if not config.api_key:
            raise MemoryServiceError("SiliconFlow embedding API key is missing.")
        if config.model != EMBEDDING_MODEL_NAME:
            raise ValueError(f"This project fixes the embedding model to {EMBEDDING_MODEL_NAME}.")
        self.config = config

    def embed(self, texts: str | list[str]) -> list[list[float]]:
        inputs = [texts] if isinstance(texts, str) else list(texts)
        if not inputs or any(not isinstance(text, str) or not text.strip() for text in inputs):
            raise ValueError("Embedding input must contain at least one non-empty string.")

        payload: dict[str, Any] = {
            "model": self.config.model,
            "input": inputs,
            "encoding_format": "float",
        }
        if self.config.dimensions is not None:
            payload["dimensions"] = self.config.dimensions

        request = Request(
            f"{self.config.api_base.rstrip('/')}/embeddings",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        last_error: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                with urlopen(request, timeout=self.config.timeout) as response:
                    body = json.loads(response.read().decode("utf-8"))
                return self._parse_vectors(body, len(inputs))
            except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as error:
                last_error = error
                if attempt + 1 < self.config.max_retries:
                    time.sleep(2**attempt)
        raise MemoryServiceError(
            f"SiliconFlow embedding request failed after {self.config.max_retries} attempts: {self._describe(last_error)}"
        ) from last_error

    def _parse_vectors(self, body: dict[str, Any], expected_count: int) -> list[list[float]]:
        items = sorted(body["data"], key=lambda item: item["index"])
        vectors = [[float(value) for value in item["embedding"]] for item in items]
        if len(vectors) != expected_count or any(not vector for vector in vectors):
            raise ValueError("Embedding response did not contain one non-empty vector per input.")
        return vectors

    @staticmethod
    def _describe(error: Exception | None) -> str:
        if isinstance(error, HTTPError):
            try:
                detail = error.read().decode("utf-8", errors="replace")[:500]
            except OSError:
                detail = ""
            return f"HTTP {error.code} {detail}".strip()
        return str(error)
