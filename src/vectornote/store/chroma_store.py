"""ChromaDB-backed chunk store."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from vectornote.models import Chunk, SearchResult

# Stay well below Chroma's per-call batch limit.
BATCH_SIZE = 1000


class EmbeddingModelMismatchError(RuntimeError):
    """The store was built with a different embedding model than the one requested."""


class ChromaStore:
    """Persistent vector store, one collection, cosine similarity.

    Embeddings are always computed by VectorNote (never by Chroma), and Chroma's
    telemetry is switched off. The embedding model name is saved with the
    collection, so mixing vectors from two different models is refused.
    """

    def __init__(
        self,
        path: Path,
        embedding_model: str,
        collection_name: str = "vectornote",
    ) -> None:
        path.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(
            path=str(path),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = client.get_or_create_collection(
            name=collection_name,
            embedding_function=None,
            metadata={"hnsw:space": "cosine", "embedding_model": embedding_model},
        )
        stored = (self._collection.metadata or {}).get("embedding_model")
        if stored != embedding_model:
            raise EmbeddingModelMismatchError(
                f"The index in {path} was built with '{stored}', not '{embedding_model}'. "
                "Delete that folder and ingest again, or switch the model back."
            )

    def count(self) -> int:
        return int(self._collection.count())

    def add(self, chunks: Sequence[Chunk], embeddings: Sequence[Sequence[float]]) -> None:
        """Insert chunks, replacing any chunk with the same ID (safe to re-run)."""
        if len(chunks) != len(embeddings):
            raise ValueError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")
        for start in range(0, len(chunks), BATCH_SIZE):
            end = start + BATCH_SIZE
            batch = chunks[start:end]
            vectors: Any = [list(v) for v in embeddings[start:end]]
            self._collection.upsert(
                ids=[c.chunk_id for c in batch],
                embeddings=vectors,
                documents=[c.text for c in batch],
                metadatas=[{"source": c.source, "page": c.page} for c in batch],
            )

    def query(
        self,
        embedding: Sequence[float],
        top_k: int,
        sources: Sequence[str] | None = None,
    ) -> list[SearchResult]:
        """Return the `top_k` closest chunks, best first. `sources` limits the search."""
        total = self.count()
        if total == 0 or top_k <= 0:
            return []
        where: Any = {"source": {"$in": list(sources)}} if sources else None
        query_vectors: Any = [list(embedding)]
        raw: Any = self._collection.query(
            query_embeddings=query_vectors,
            n_results=min(top_k, total),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        results: list[SearchResult] = []
        for chunk_id, text, meta, distance in zip(
            raw["ids"][0],
            raw["documents"][0],
            raw["metadatas"][0],
            raw["distances"][0],
            strict=True,
        ):
            chunk = Chunk(
                chunk_id=chunk_id,
                text=text,
                source=str(meta["source"]),
                page=int(meta["page"]),
            )
            results.append(SearchResult(chunk=chunk, score=1.0 - float(distance)))
        return results

    def delete_by_source(self, source: str) -> int:
        """Remove every chunk of one file. Returns how many were removed."""
        found: Any = self._collection.get(where={"source": source}, include=[])
        ids: list[str] = list(found["ids"])
        for start in range(0, len(ids), BATCH_SIZE):
            self._collection.delete(ids=ids[start:start + BATCH_SIZE])
        return len(ids)

    def list_sources(self) -> dict[str, int]:
        """Map each indexed file to its number of chunks."""
        found: Any = self._collection.get(include=["metadatas"])
        counts = Counter(str(meta["source"]) for meta in found["metadatas"] or [])
        return dict(sorted(counts.items()))
