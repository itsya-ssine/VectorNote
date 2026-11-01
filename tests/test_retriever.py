from __future__ import annotations

from collections.abc import Sequence
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
    assert all(r.vector_score is not None and r.vector_score >= 0.3 for r in strict)
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


def test_vector_mode_scores_are_cosine_similarities(retriever: Retriever) -> None:
    results = retriever.search("mutex critical section", k=2, mode="vector")
    assert results[0].chunk.chunk_id == "os.pdf#p1-c0"
    assert results[0].score == results[0].vector_score
    assert results[0].bm25_score is None
    assert 0.0 < results[0].score <= 1.0


def test_bm25_mode_matches_exact_terms_only(retriever: Retriever) -> None:
    results = retriever.search("subnet", k=5, mode="bm25")
    assert [r.chunk.chunk_id for r in results] == ["net.md#p1-c0"]
    assert results[0].score == results[0].bm25_score
    assert results[0].vector_score is None
    assert retriever.search("zebra", k=5, mode="bm25") == []


def test_bm25_mode_respects_source_filter(retriever: Retriever) -> None:
    assert retriever.search("memory address", k=5, mode="bm25", sources=["db.pdf"]) == []
    hits = retriever.search("memory address", k=5, mode="bm25", sources=["os.pdf", "net.md"])
    assert {r.chunk.source for r in hits} == {"os.pdf", "net.md"}


def test_bm25_mode_rejects_min_score(retriever: Retriever) -> None:
    with pytest.raises(ValueError, match="cosine"):
        retriever.search("mutex", mode="bm25", min_score=0.5)


def test_hybrid_results_carry_both_scores(retriever: Retriever) -> None:
    results = retriever.search("mutex critical section", k=3, mode="hybrid")
    assert results[0].chunk.chunk_id == "os.pdf#p1-c0"
    assert all(r.vector_score is not None and r.bm25_score is not None for r in results)
    assert results[0].bm25_score is not None and results[0].bm25_score > 0
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_unknown_mode_is_rejected(retriever: Retriever, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown retrieval mode"):
        retriever.search("mutex", mode="semantic")
    with pytest.raises(ValueError, match="unknown retrieval mode"):
        Retriever(EMBEDDER, ChromaStore(tmp_path / "other", EMBEDDER.name), mode="nope")


def test_default_mode_is_hybrid_and_can_be_set(tmp_path: Path) -> None:
    store = ChromaStore(tmp_path / "db", EMBEDDER.name)
    assert Retriever(EMBEDDER, store).mode == "hybrid"
    assert Retriever(EMBEDDER, store, mode="bm25").mode == "bm25"


class StubEmbedder:
    """Maps exact texts to hand-made 3-d vectors so rankings are fully controlled."""

    name = "stub"

    def __init__(self, vectors: dict[str, list[float]]) -> None:
        self._vectors = vectors

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vectors[text] for text in texts]


NEIGHBOUR = "a semantic neighbour of the question"
RARE = "contains the rare token zeta somewhere inside"
BOTH = "zeta also appears with a neighbour"


def _stub_retriever(tmp_path: Path, candidate_pool: int | None = None) -> Retriever:
    vectors = {
        "zeta": [1.0, 0.0, 0.0],
        NEIGHBOUR: [0.99, 0.141, 0.0],   # closest by meaning, no keyword
        RARE: [0.0, 1.0, 0.0],           # far by meaning, has the keyword
        BOTH: [0.8, 0.6, 0.0],           # fairly close and has the keyword
    }
    embedder = StubEmbedder(vectors)
    store = ChromaStore(tmp_path / "db", "stub")
    chunks = [
        Chunk(chunk_id=f"d{i}", source="s.txt", page=1, text=text)
        for i, text in enumerate([NEIGHBOUR, RARE, BOTH], start=1)
    ]
    store.add(chunks, embedder.encode([c.text for c in chunks]))
    return Retriever(embedder, store, candidate_pool=candidate_pool)


def test_hybrid_ranks_agreement_above_either_ranker_alone(tmp_path: Path) -> None:
    retriever = _stub_retriever(tmp_path)
    vector = [r.chunk.chunk_id for r in retriever.search("zeta", k=3, mode="vector")]
    keyword = [r.chunk.chunk_id for r in retriever.search("zeta", k=3, mode="bm25")]
    hybrid = [r.chunk.chunk_id for r in retriever.search("zeta", k=3, mode="hybrid")]
    assert vector == ["d1", "d3", "d2"]
    assert keyword == ["d3", "d2"]
    assert hybrid == ["d3", "d2", "d1"]  # d3 is high in both lists; d1 only in one


def test_hybrid_fills_in_the_missing_scores_for_one_sided_candidates(tmp_path: Path) -> None:
    retriever = _stub_retriever(tmp_path, candidate_pool=1)  # each ranker contributes 1 item
    results = {r.chunk.chunk_id: r for r in retriever.search("zeta", k=5, mode="hybrid")}
    assert set(results) == {"d1", "d3"}  # d1 from vectors, d3 from BM25
    assert results["d3"].vector_score == pytest.approx(0.8)  # read back from the store
    assert results["d1"].bm25_score == 0.0  # no keyword match


def test_hybrid_min_score_filters_on_cosine(tmp_path: Path) -> None:
    retriever = _stub_retriever(tmp_path)
    kept = retriever.search("zeta", k=3, mode="hybrid", min_score=0.5)
    assert [r.chunk.chunk_id for r in kept] == ["d3", "d1"]  # d2 has cosine 0.0


def test_keyword_index_follows_changes_made_by_another_process(tmp_path: Path) -> None:
    path = tmp_path / "db"
    first = ChromaStore(path, EMBEDDER.name)
    retriever = Retriever(EMBEDDER, first, mode="bm25")
    assert retriever.search("kernel", k=3) == []

    second = ChromaStore(path, EMBEDDER.name)  # stands in for a CLI `ingest`
    chunk = Chunk(chunk_id="k#p1-c0", source="k.md", page=1, text="The kernel schedules threads.")
    second.add([chunk], EMBEDDER.encode([chunk.text]))
    assert [r.chunk.chunk_id for r in retriever.search("kernel", k=3)] == ["k#p1-c0"]

    second.delete_by_source("k.md")
    assert retriever.search("kernel", k=3) == []
