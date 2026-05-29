"""LLM generation provider protocol and implementations."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300.0


class LLMProvider(Protocol):
    """Structural protocol for LLM generation providers."""

    @property
    def model(self) -> str:
        """Default model name."""
        ...

    def generate(self, prompt: str, model: str | None = None) -> str:
        """Generate a response for *prompt* and return the text."""
        ...

    def generate_stream(self, prompt: str, model: str | None = None) -> Iterator[str]:
        """Stream generated tokens for *prompt*."""
        ...


def parse_json_array(text: str) -> list[Any]:
    """Extract the first JSON array found in *text*.

    LLMs sometimes wrap JSON in markdown fences or prepend explanatory text.
    Finds the first ``[...]`` block and parses it; returns ``[]`` on failure.
    """
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        parsed: list[Any] = json.loads(text[start : end + 1])
        return parsed
    except json.JSONDecodeError:
        logger.warning("Failed to parse JSON array from LLM response")
        return []


class OpenAICompatibleLLMProvider:
    """LLM provider using the OpenAI-compatible /v1/chat/completions endpoint.

    Targets local inference servers (LM Studio, llama.cpp HTTP server, vLLM)
    without the openai SDK dependency. Air-gapped deployment stays first-class
    because the endpoint is addressed by base URL, not a cloud host.
    """

    def __init__(self, base_url: str, model: str, timeout: float = DEFAULT_TIMEOUT) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    def generate(self, prompt: str, model: str | None = None) -> str:
        """POST to /v1/chat/completions and return the assistant message content."""
        target_model = model or self._model
        url = f"{self._base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        logger.debug(
            "openai-compatible generate model=%s prompt_len=%d",
            target_model,
            len(prompt),
        )
        response = httpx.post(url, json=payload, timeout=self._timeout)
        response.raise_for_status()
        data = response.json()
        choices = data.get("choices", [])
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", ""))

    def generate_stream(self, prompt: str, model: str | None = None) -> Iterator[str]:
        """Not implemented — OpenAI SSE streaming format is out of scope for this provider."""
        raise NotImplementedError(
            "Streaming is not implemented for the openai-compatible provider. "
            "Set LLM_PROVIDER=ollama to use streaming."
        )
