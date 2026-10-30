"""Service layer: the single entry point the API (and CLI) call into.

Keep retrieval and generation behind this class so that no UI or route
handler ever touches the pipeline internals directly.
"""

from __future__ import annotations

from vectornote.config import Settings
from vectornote.models import SearchResult


class RagService:
    """Orchestrates ingestion, retrieval and generation."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def ingest(self, filename: str, content: bytes) -> int:
        """Ingest one uploaded file and return the number of chunks added.

        Implemented in Phase 1.
        """
        raise NotImplementedError

    def ask(self, question: str, top_k: int) -> tuple[str, list[SearchResult]]:
        """Answer a question and return the answer with its supporting chunks.

        Implemented in Phase 3.
        """
        raise NotImplementedError
