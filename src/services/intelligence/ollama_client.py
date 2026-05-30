"""Ollama HTTP client for local LLM inference."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Generator
from typing import Any

import httpx

from shared.metrics import current_metrics

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 300.0


class OllamaClient:
    """Thin wrapper around the Ollama HTTP API."""

    def __init__(self, base_url: str, model: str = "qwen3:4b") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

    @property
    def model(self) -> str:
        """The default model name used when no override is provided."""
        return self._model

    def generate(self, prompt: str, model: str | None = None) -> str:
        """Send a generate request to Ollama and return the response text.

        Args:
            prompt: The prompt to send.
            model: Override the default model. Uses the client default if None.

        Returns:
            The generated response text.

        Raises:
            httpx.HTTPStatusError: On non-2xx response.
            httpx.NetworkError: On connection failure.
        """
        target_model = model or self._model
        url = f"{self._base_url}/api/generate"
        payload: dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": False,
        }

        logger.debug(
            "Ollama generate model=%s prompt_len=%d",
            target_model,
            len(prompt),
        )

        metrics = current_metrics()
        start = time.perf_counter()
        try:
            response = httpx.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            data = response.json()
        except Exception:
            if metrics is not None:
                metrics.ollama_requests_total.labels("generate", "failure").inc()
                metrics.ollama_duration_seconds.labels("generate").observe(
                    time.perf_counter() - start
                )
            raise
        if metrics is not None:
            metrics.ollama_requests_total.labels("generate", "success").inc()
            metrics.ollama_duration_seconds.labels("generate").observe(time.perf_counter() - start)
        return str(data.get("response", ""))

    def generate_stream(self, prompt: str, model: str | None = None) -> Generator[str, None, None]:
        """Stream generated tokens from Ollama.

        Yields each token as it is produced by the model. Used by the SSE
        streaming chat endpoint (Phase G).
        """
        target_model = model or self._model
        url = f"{self._base_url}/api/generate"
        payload: dict[str, Any] = {
            "model": target_model,
            "prompt": prompt,
            "stream": True,
        }

        logger.debug(
            "Ollama generate_stream model=%s prompt_len=%d",
            target_model,
            len(prompt),
        )

        metrics = current_metrics()
        start = time.perf_counter()
        try:
            with httpx.stream("POST", url, json=payload, timeout=DEFAULT_TIMEOUT) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        yield token
        except Exception:
            if metrics is not None:
                metrics.ollama_requests_total.labels("generate_stream", "failure").inc()
                metrics.ollama_duration_seconds.labels("generate_stream").observe(
                    time.perf_counter() - start
                )
            raise
        if metrics is not None:
            metrics.ollama_requests_total.labels("generate_stream", "success").inc()
            metrics.ollama_duration_seconds.labels("generate_stream").observe(
                time.perf_counter() - start
            )

    @staticmethod
    def parse_json_array(text: str) -> list[Any]:
        """Extract the first JSON array found in *text*.

        LLMs sometimes wrap JSON in markdown fences or add explanatory text.
        This helper finds the first ``[...]`` block and parses it.

        Returns:
            The parsed list, or an empty list if no valid array is found.
        """
        # Try to find array between [...]
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1 or end <= start:
            return []
        try:
            parsed: list[Any] = json.loads(text[start : end + 1])
            return parsed
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON array from Ollama response")
            return []
