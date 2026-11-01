"""Retrieval: vector search, BM25 keyword search, or both fused with RRF."""

from __future__ import annotations

import math
import threading
from collections.abc import Sequence
from typing import Literal

from vectornote.embeddings import Embedder
from vectornote.models import Chunk, SearchResult
from vectornote.retrieval.bm25 import Bm25Index
from vectornote.retrieval.fusion import RRF_K, reciprocal_rank_fusion
from vectornote.store import ChromaStore

RetrievalMode = Literal["vector", "bm25", "hybrid"]
MODES: tuple[RetrievalMode, ...] = ("vector", "bm25", "hybrid")

# Hybrid search fuses the top candidates of each ranker: at least this many, or 4x `k`.
MIN_CANDIDATES = 20
CANDIDATE_FACTOR = 4


def parse_mode(mode: str) -> RetrievalMode:
    for known in MODES:
        if mode == known:
            return known
    raise ValueError(f"unknown retrieval mode '{mode}' (use one of: {', '.join(MODES)})")


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


class Retriever:
    """Search over the indexed chunks.

    Modes:
      * `vector`: cosine similarity of embeddings (understands paraphrases).
      * `bm25`: keyword matching (exact terms, acronyms, identifiers).
      * `hybrid`: both, fused with Reciprocal Rank Fusion.

    `score` is only comparable within one mode. In `hybrid` mode every result also
    carries its cosine similarity (`vector_score`) and BM25 score (`bm25_score`).
    """

    def __init__(
        self,
        embedder: Embedder,
        store: ChromaStore,
        mode: str = "hybrid",
        rrf_k: int = RRF_K,
        candidate_pool: int | None = None,
    ) -> None:
        self._embedder = embedder
        self._store = store
        self.mode = parse_mode(mode)
        self._rrf_k = rrf_k
        self._candidate_pool = candidate_pool
        self._bm25: tuple[tuple[int, int], Bm25Index] | None = None
        self._lock = threading.Lock()

    def search(
        self,
        query: str,
        k: int = 5,
        sources: Sequence[str] | None = None,
        min_score: float | None = None,
        mode: str | None = None,
    ) -> list[SearchResult]:
        """Return up to `k` chunks, best first.

        `sources` limits the search to those files. `min_score` is a minimum *cosine
        similarity* (so it needs the `vector` or `hybrid` mode) and drops weak matches.
        """
        text = query.strip()
        if not text:
            raise ValueError("query must not be empty")
        if k <= 0:
            raise ValueError("k must be positive")
        chosen = parse_mode(mode) if mode is not None else self.mode
        if chosen == "bm25":
            if min_score is not None:
                raise ValueError("min_score is a cosine threshold: use mode 'vector' or 'hybrid'")
            return self._bm25_search(text, k, sources)
        if chosen == "vector":
            return self._vector_search(text, k, sources, min_score)
        return self._hybrid_search(text, k, sources, min_score)

    # ---- single rankers --------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        [vector] = self._embedder.encode([text])
        return vector

    def _vector_search(
        self, text: str, k: int, sources: Sequence[str] | None, min_score: float | None
    ) -> list[SearchResult]:
        results = self._store.query(self._embed(text), k, sources)
        if min_score is not None:
            results = [r for r in results if r.score >= min_score]
        return results

    def _bm25_index(self) -> Bm25Index:
        key = (self._store.revision(), self._store.count())
        with self._lock:
            if self._bm25 is None or self._bm25[0] != key:
                self._bm25 = (key, Bm25Index(self._store.all_chunks()))
            return self._bm25[1]

    def _bm25_search(
        self, text: str, k: int, sources: Sequence[str] | None
    ) -> list[SearchResult]:
        hits = self._bm25_index().search(text, k, sources)
        return [SearchResult(chunk=chunk, score=score, bm25_score=score) for chunk, score in hits]

    # ---- fusion ----------------------------------------------------------

    def _hybrid_search(
        self, text: str, k: int, sources: Sequence[str] | None, min_score: float | None
    ) -> list[SearchResult]:
        pool = self._candidate_pool or max(MIN_CANDIDATES, k * CANDIDATE_FACTOR)
        query_vector = self._embed(text)
        vector_hits = self._store.query(query_vector, pool, sources)
        index = self._bm25_index()
        keyword_hits = index.search(text, pool, sources)

        fused = reciprocal_rank_fusion(
            [
                [r.chunk.chunk_id for r in vector_hits],
                [chunk.chunk_id for chunk, _ in keyword_hits],
            ],
            self._rrf_k,
        )
        chunks: dict[str, Chunk] = {r.chunk.chunk_id: r.chunk for r in vector_hits}
        chunks.update({chunk.chunk_id: chunk for chunk, _ in keyword_hits})
        cosines = {r.chunk.chunk_id: r.score for r in vector_hits}
        keyword_scores = {chunk.chunk_id: score for chunk, score in keyword_hits}

        # Candidates found by only one ranker still get the other ranker's score.
        missing = [chunk_id for chunk_id in fused if chunk_id not in cosines]
        for chunk_id, vector in self._store.get_embeddings(missing).items():
            cosines[chunk_id] = _cosine(query_vector, vector)

        results = [
            SearchResult(
                chunk=chunks[chunk_id],
                score=rrf_score,
                vector_score=cosines.get(chunk_id),
                bm25_score=keyword_scores.get(chunk_id, index.score(text, chunk_id)),
            )
            for chunk_id, rrf_score in fused.items()
        ]
        results.sort(key=lambda r: (-r.score, -(r.vector_score or 0.0), r.chunk.chunk_id))
        if min_score is not None:
            results = [r for r in results if (r.vector_score or 0.0) >= min_score]
        return results[:k]
