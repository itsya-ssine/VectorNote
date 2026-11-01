"""Client for the Ollama HTTP API."""

from __future__ import annotations

import json
import re
from collections.abc import Generator, Mapping, Sequence
from typing import Any, Protocol

import httpx

from vectornote.generation.streaming import ThinkFilter

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


class OllamaError(RuntimeError):
    """Something went wrong while talking to Ollama."""


class OllamaUnavailableError(OllamaError):
    """Ollama is not reachable or did not answer in time."""


class OllamaModelNotFoundError(OllamaError):
    """The configured model is not installed in Ollama."""


class ChatModel(Protocol):
    """Anything that can complete a chat conversation."""

    def complete(
        self, messages: Sequence[Mapping[str, str]], max_tokens: int | None = None
    ) -> str: ...

    def stream(self, messages: Sequence[Mapping[str, str]]) -> Generator[str, None, None]: ...


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

    def _payload(
        self,
        messages: Sequence[Mapping[str, str]],
        stream: bool,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        options: dict[str, Any] = {"temperature": self.temperature, "num_ctx": self.num_ctx}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        return {
            "model": self.model,
            "messages": [dict(message) for message in messages],
            "stream": stream,
            "options": options,
        }

    def _unavailable(self, exc: httpx.HTTPError) -> OllamaUnavailableError:
        if isinstance(exc, httpx.TimeoutException):
            return OllamaUnavailableError(
                f"Ollama did not answer within {self.timeout:.0f}s. "
                "The model may still be loading, or it is too large for this machine."
            )
        return OllamaUnavailableError(
            f"Cannot reach Ollama at {self.base_url}. Is it running? Start it with `ollama serve`."
        )

    def complete(
        self, messages: Sequence[Mapping[str, str]], max_tokens: int | None = None
    ) -> str:
        """Send a conversation and return the full reply (reasoning blocks removed).

        `max_tokens` caps the length of the reply (used for short utility calls).
        """
        payload = self._payload(messages, stream=False, max_tokens=max_tokens)
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                response = client.post(f"{self.base_url}/api/chat", json=payload)
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise self._unavailable(exc) from exc
        if response.status_code == 404:
            raise OllamaModelNotFoundError(
                f"Model '{self.model}' is not installed. Run: ollama pull {self.model}"
            )
        if response.is_error:
            raise OllamaError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")
        content = str(response.json()["message"]["content"])
        return _THINK_BLOCK.sub("", content).strip()

    def stream(self, messages: Sequence[Mapping[str, str]]) -> Generator[str, None, None]:
        """Yield the reply piece by piece as the model produces it.

        Reasoning blocks are removed. Nothing is sent until the first piece is requested,
        and closing the iterator early closes the connection, which stops the generation.
        """
        payload = self._payload(messages, stream=True)
        visible = ThinkFilter()
        try:
            with httpx.Client(timeout=self.timeout, transport=self._transport) as client:
                with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    if response.status_code == 404:
                        raise OllamaModelNotFoundError(
                            f"Model '{self.model}' is not installed. Run: ollama pull {self.model}"
                        )
                    if response.is_error:
                        body = response.read().decode("utf-8", errors="replace")
                        raise OllamaError(
                            f"Ollama returned HTTP {response.status_code}: {body[:200]}"
                        )
                    for line in response.iter_lines():
                        if not line.strip():
                            continue
                        data = json.loads(line)
                        if "error" in data:
                            raise OllamaError(f"Ollama stopped the reply: {data['error']}")
                        piece = visible.feed(str(data.get("message", {}).get("content", "")))
                        if piece:
                            yield piece
                        if data.get("done"):
                            break
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise self._unavailable(exc) from exc
        rest = visible.finish()
        if rest:
            yield rest

    def chat(self, prompt: str) -> str:
        """Send a single user message (used by the smoke script)."""
        return self.complete([{"role": "user", "content": prompt}])
