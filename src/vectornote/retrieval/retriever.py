"""Vector retrieval: embed the question, ask the store for the closest chunks."""

from __future__ import annotations

from collections.abc import Sequence

from vectornote.embeddings import Embedder
from vectornote.models import SearchResult
from vectornote.store import ChromaStore


class Retriever:
    """Semantic search over the indexed chunks.

    Scores are cosine similarities (higher is closer, 1.0 is identical).
    """

    def __init__(self, embedder: Embedder, store: ChromaStore) -> None:
        self._embedder = embedder
        self._store = store

    def search(
        self,
        query: str,
        k: int = 5,
        sources: Sequence[str] | None = None,
        min_score: float | None = None,
    ) -> list[SearchResult]:
        """Return up to `k` chunks, best first.

        `sources` limits the search to those files; `min_score` drops weak matches.
        """
        text = query.strip()
        if not text:
            raise ValueError("query must not be empty")
        if k <= 0:
            raise ValueError("k must be positive")
        [vector] = self._embedder.encode([text])
        results = self._store.query(vector, k, sources)
        if min_score is not None:
            results = [r for r in results if r.score >= min_score]
        return results
