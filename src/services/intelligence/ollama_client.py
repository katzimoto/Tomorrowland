"""Ollama HTTP client for local LLM inference."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from shared.metrics import current_metrics

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 120.0


class OllamaClient:
    """Thin wrapper around the Ollama HTTP API."""

    def __init__(self, base_url: str, model: str = "mistral") -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model

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
