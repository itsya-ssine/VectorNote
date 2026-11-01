"""Client for the Ollama HTTP API."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Protocol

import httpx

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaError(RuntimeError):
    """Something went wrong while talking to Ollama."""


class OllamaUnavailableError(OllamaError):
    """Ollama is not reachable or did not answer in time."""


class OllamaModelNotFoundError(OllamaError):
    """The configured model is not installed in Ollama."""


class ChatModel(Protocol):
    """Anything that can complete a chat conversation."""

    def complete(self, messages: Sequence[Mapping[str, str]]) -> str: ...


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout: float = 300.0,
        temperature: float = 0.1,
        num_ctx: int = 4096,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.temperature = temperature
        self.num_ctx = num_ctx
        self._transport = transport

    def complete(self, messages: Sequence[Mapping[str, str]]) -> str:
        """Send a conversation and return the full reply (reasoning blocks removed)."""
        payload = {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "stream": False,
            "options": {"temperature": self.temperature, "num_ctx": self.num_ctx},
        }
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(f"{self.base_url}/api/chat", json=payload)
        except httpx.ConnectError as exc:
            raise OllamaUnavailableError(
                f"Cannot reach Ollama at {self.base_url}. "
                "Is it running? Start it with `ollama serve`."
            ) from exc
        except httpx.TimeoutException as exc:
            raise OllamaUnavailableError(
                f"Ollama did not answer within {self.timeout:.0f}s. "
                "The model may still be loading, or it is too large for this machine."
            ) from exc
        if response.status_code == 404:
            raise OllamaModelNotFoundError(
                f"Model '{self.model}' is not installed. Run: ollama pull {self.model}"
            )
        if response.is_error:
            raise OllamaError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")
        content = str(response.json()["message"]["content"])
        return _THINK_BLOCK.sub("", content).strip()

    def chat(self, prompt: str) -> str:
        """Send a single user message (used by the smoke script)."""
        return self.complete([{"role": "user", "content": prompt}])
