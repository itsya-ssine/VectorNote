from __future__ import annotations

from pathlib import Path

import pytest

from vectornote.embeddings.hashing import HashingEmbedder
from vectornote.models import Chunk
from vectornote.retrieval import Retriever
from vectornote.store import ChromaStore

EMBEDDER = HashingEmbedder()

CHUNKS = [
    Chunk(chunk_id="os.pdf#p1-c0", source="os.pdf", page=1,
          text="A mutex gives mutual exclusion to a critical section."),
    Chunk(chunk_id="os.pdf#p2-c0", source="os.pdf", page=2,
          text="Paging splits virtual memory into fixed size frames."),
    Chunk(chunk_id="net.md#p1-c0", source="net.md", page=1,
          text="A subnet mask separates the network and host parts of an address."),
    Chunk(chunk_id="db.pdf#p4-c0", source="db.pdf", page=4,
          text="An index speeds up lookups in a database table."),
]


@pytest.fixture
def retriever(tmp_path: Path) -> Retriever:
    store = ChromaStore(tmp_path / "db", EMBEDDER.name)
    store.add(CHUNKS, EMBEDDER.encode([c.text for c in CHUNKS]))
    return Retriever(EMBEDDER, store)


def test_best_match_is_first_with_citation_fields(retriever: Retriever) -> None:
    results = retriever.search("how does a mutex protect a critical section?", k=3)
    assert results[0].chunk.chunk_id == "os.pdf#p1-c0"
    assert (results[0].chunk.source, results[0].chunk.page) == ("os.pdf", 1)
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)
    assert len(results) == 3


def test_k_limits_results(retriever: Retriever) -> None:
    assert len(retriever.search("memory", k=1)) == 1
    assert len(retriever.search("memory", k=50)) == len(CHUNKS)


def test_source_filter(retriever: Retriever) -> None:
    results = retriever.search("memory and address", k=5, sources=["net.md", "db.pdf"])
    assert {r.chunk.source for r in results} == {"net.md", "db.pdf"}


def test_min_score_drops_weak_matches(retriever: Retriever) -> None:
    everything = retriever.search("mutex critical section", k=4)
    strict = retriever.search("mutex critical section", k=4, min_score=0.3)
    assert len(strict) < len(everything)
    assert all(r.score >= 0.3 for r in strict)
    assert retriever.search("zebra giraffe", k=4, min_score=0.9) == []


def test_empty_index_returns_nothing(tmp_path: Path) -> None:
    empty = Retriever(EMBEDDER, ChromaStore(tmp_path / "db", EMBEDDER.name))
    assert empty.search("anything") == []


@pytest.mark.parametrize("query", ["", "   \n"])
def test_blank_query_is_rejected(retriever: Retriever, query: str) -> None:
    with pytest.raises(ValueError, match="empty"):
        retriever.search(query)


def test_non_positive_k_is_rejected(retriever: Retriever) -> None:
    with pytest.raises(ValueError, match="positive"):
        retriever.search("mutex", k=0)
