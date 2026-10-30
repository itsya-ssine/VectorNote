"""ChromaDB-backed chunk store."""

from __future__ import annotations

from vectornote.models import Chunk


class ChromaStore:
    """Persistent vector store. Implemented in Phase 1."""

    def add(self, chunks: list[Chunk], embeddings: list[list[float]]) -> None:
        raise NotImplementedError
