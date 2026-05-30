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


def _build_headers(api_key: str | None) -> dict[str, str]:
    """Build HTTP headers for OpenAI-compatible requests.

    Never logs the API key value.
    """
    headers: dict[str, str] = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        logger.debug("Authorization header set (Bearer) — key length: %d", len(api_key))
    else:
        logger.debug("No API key — sending request without Authorization header")
    return headers


class OpenAICompatibleLLMProvider:
    """LLM provider using the OpenAI-compatible /v1/chat/completions endpoint.

    Supports Bearer auth when *api_key* is provided, non-streaming and SSE
    streaming generation, and cleans up common HTTP/JSON errors.

    Targets:
    - OpenAI API (``api_key`` required)
    - LiteLLM proxy (``api_key`` if configured)
    - llama.cpp HTTP server
    - LM Studio / vLLM / any OpenAI-compatible endpoint

    Air-gapped deployment stays first-class because the endpoint is addressed
    by base URL, not a cloud host.
    """

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    def generate(self, prompt: str, model: str | None = None) -> str:
        """POST to /v1/chat/completions and return the assistant message content.

        Args:
            prompt: The user prompt. Logged as length only — never the full text.
            model: Override the default model.

        Returns:
            The generated response text, or empty string on empty choices.

        Raises:
            httpx.HTTPStatusError: On non-2xx HTTP response.
            httpx.ConnectError: On connection failure.
            httpx.TimeoutException: On request timeout.
        """
        target_model = model or self._model
        url = f"{self._base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        logger.debug(
            "openai-compatible generate model=%s prompt_len=%d api_key=%s",
            target_model,
            len(prompt),
            bool(self._api_key),
        )
        try:
            response = httpx.post(
                url,
                json=payload,
                headers=_build_headers(self._api_key),
                timeout=self._timeout,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPStatusError:
            logger.warning(
                "openai-compatible HTTP error model=%s status=%s",
                target_model,
                response.status_code,
            )
            raise
        except httpx.ConnectError:
            logger.warning(
                "openai-compatible connection refused model=%s url=%s",
                target_model,
                self._base_url,
            )
            raise
        except httpx.TimeoutException:
            logger.warning(
                "openai-compatible timeout model=%s timeout=%.1f",
                target_model,
                self._timeout,
            )
            raise
        except json.JSONDecodeError:
            logger.warning(
                "openai-compatible malformed JSON response model=%s",
                target_model,
            )
            return ""

        choices = data.get("choices", [])
        if not choices:
            return ""
        return str(choices[0].get("message", {}).get("content", ""))

    def generate_stream(self, prompt: str, model: str | None = None) -> Iterator[str]:
        """Stream tokens via SSE from /v1/chat/completions.

        Parses the ``data: ...`` SSE lines. Yields each ``delta.content``
        fragment. Properly terminates on ``data: [DONE]``, connection close,
        or error.

        Args:
            prompt: The user prompt. Logged as length only.
            model: Override the default model.

        Yields:
            Content delta strings from each SSE chunk.

        Raises:
            httpx.HTTPStatusError: On non-2xx HTTP response.
            httpx.ConnectError: On connection failure.
            httpx.TimeoutException: On request timeout.
        """
        target_model = model or self._model
        url = f"{self._base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        }
        logger.debug(
            "openai-compatible generate_stream model=%s prompt_len=%d api_key=%s",
            target_model,
            len(prompt),
            bool(self._api_key),
        )

        headers = _build_headers(self._api_key)
        headers["Accept"] = "text/event-stream"

        try:
            with httpx.stream(
                "POST",
                url,
                json=payload,
                headers=headers,
                timeout=self._timeout,
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    # SSE data line
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data_str)
                        except json.JSONDecodeError:
                            logger.warning(
                                "openai-compatible stream bad JSON model=%s",
                                target_model,
                            )
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content", "")
                        if content:
                            yield content
        except httpx.HTTPStatusError:
            logger.warning(
                "openai-compatible stream HTTP error model=%s status=%s",
                target_model,
                response.status_code,
            )
            raise
        except httpx.ConnectError:
            logger.warning(
                "openai-compatible stream connection refused model=%s url=%s",
                target_model,
                self._base_url,
            )
            raise
        except httpx.TimeoutException:
            logger.warning(
                "openai-compatible stream timeout model=%s timeout=%.1f",
                target_model,
                self._timeout,
            )
            raise
