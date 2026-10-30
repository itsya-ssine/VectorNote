"""Thin client for the Ollama HTTP API."""

from __future__ import annotations

import httpx


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(self, prompt: str) -> str:
        """Send one user message and return the full reply."""
        response = httpx.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        content: str = response.json()["message"]["content"]
        return content
