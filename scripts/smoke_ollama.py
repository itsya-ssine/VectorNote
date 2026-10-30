"""Check that Ollama is reachable and the configured model responds."""

from __future__ import annotations

from vectornote.config import Settings
from vectornote.generation.ollama_client import OllamaClient


def main() -> None:
    s = Settings()
    client = OllamaClient(s.ollama_url, s.llm_model)
    print(client.chat("Say hello in one sentence."))


if __name__ == "__main__":
    main()
