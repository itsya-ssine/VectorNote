from __future__ import annotations

import pytest

from vectornote.models import Chunk
from vectornote.retrieval import Bm25Index, reciprocal_rank_fusion, tokenize


def _chunk(chunk_id: str, text: str, source: str = "s.txt") -> Chunk:
    return Chunk(chunk_id=chunk_id, text=text, source=source, page=1)


def test_tokenize_lowercases_folds_accents_and_drops_stop_words() -> None:
    assert tokenize("Le RÉSEAU et the Network, ça marche!") == ["reseau", "network", "ca", "marche"]


def test_tokenize_keeps_identifiers_and_the_c_language() -> None:
    assert tokenize("pthread_mutex_lock in C") == ["pthread_mutex_lock", "c"]


def test_rare_terms_outweigh_common_ones() -> None:
    chunks = [
        _chunk("a", "thread scheduler"),
        _chunk("b", "thread semaphore"),
        _chunk("c", "thread mutex"),
        _chunk("d", "thread paging"),
    ]
    index = Bm25Index(chunks)
    hits = index.search("thread semaphore", k=4)
    assert hits[0][0].chunk_id == "b"
    assert hits[0][1] > hits[1][1]


def test_repeated_term_saturates_and_short_documents_win() -> None:
    chunks = [
        _chunk("short", "mutex lock"),
        _chunk("long", "mutex " + "filler " * 40),
        _chunk("other", "paging frames"),
    ]
    hits = Bm25Index(chunks).search("mutex", k=3)
    assert [c.chunk_id for c, _ in hits] == ["short", "long"]


def test_no_match_gives_no_results() -> None:
    index = Bm25Index([_chunk("a", "mutex lock")])
    assert index.search("zebra", k=5) == []
    assert index.search("the and of", k=5) == []  # only stop words


def test_source_filter_and_limit() -> None:
    chunks = [
        _chunk("a", "mutex", source="os.pdf"),
        _chunk("b", "mutex", source="net.md"),
        _chunk("c", "mutex", source="net.md"),
    ]
    index = Bm25Index(chunks)
    assert {c.source for c, _ in index.search("mutex", k=5, sources=["net.md"])} == {"net.md"}
    assert len(index.search("mutex", k=2)) == 2


def test_ties_are_broken_by_chunk_id() -> None:
    index = Bm25Index([_chunk("b", "mutex"), _chunk("a", "mutex")])
    assert [c.chunk_id for c, _ in index.search("mutex", k=2)] == ["a", "b"]


def test_score_matches_search_and_handles_unknown_ids() -> None:
    index = Bm25Index([_chunk("a", "mutex lock section"), _chunk("b", "paging frames")])
    [(chunk, score)] = index.search("mutex section", k=5)
    assert index.score("mutex section", chunk.chunk_id) == pytest.approx(score)
    assert index.score("mutex section", "b") == 0.0
    assert index.score("mutex section", "missing") == 0.0


def test_empty_index() -> None:
    index = Bm25Index([])
    assert len(index) == 0
    assert index.search("anything", k=3) == []


def test_common_terms_still_score_positively() -> None:
    chunks = [_chunk(str(i), "thread") for i in range(5)]
    assert all(score > 0 for _, score in Bm25Index(chunks).search("thread", k=5))


def test_rrf_rewards_items_found_by_both_rankers() -> None:
    scores = reciprocal_rank_fusion([["a", "b"], ["c", "b"]])
    assert max(scores, key=lambda item: scores[item]) == "b"
    assert scores["b"] == pytest.approx(2 / 62)
    assert scores["a"] == pytest.approx(1 / 61)


def test_rrf_handles_empty_and_single_rankings() -> None:
    assert reciprocal_rank_fusion([]) == {}
    assert reciprocal_rank_fusion([[], ["a"]]) == {"a": pytest.approx(1 / 61)}


def test_rrf_constant_flattens_rank_differences() -> None:
    sharp = reciprocal_rank_fusion([["a", "b"]], rrf_k=1)
    flat = reciprocal_rank_fusion([["a", "b"]], rrf_k=100)
    assert sharp["a"] / sharp["b"] > flat["a"] / flat["b"]
