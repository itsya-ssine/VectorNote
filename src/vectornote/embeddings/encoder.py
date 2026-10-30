"""Local sentence-transformers encoder."""

from __future__ import annotations


class Encoder:
    """Wraps all-MiniLM-L6-v2. Implemented in Phase 1."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    def encode(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError
