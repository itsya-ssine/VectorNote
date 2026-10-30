"""Vector, BM25 and hybrid retrieval."""

from __future__ import annotations

from vectornote.models import SearchResult


class Retriever:
    """Top-k retrieval. Implemented in Phase 2."""

    def search(self, query: str, k: int) -> list[SearchResult]:
        raise NotImplementedError
