from __future__ import annotations

import pytest

from vectornote.ingestion.chunking import (
    MIN_CHUNK_CHARS,
    chunk_document,
    chunk_text,
    make_chunk_id,
)
from vectornote.models import Document, Page

SENTENCES = [
    "A mutex gives mutual exclusion to a critical section.",
    "Semaphores generalize mutexes with a counter.",
    "Deadlock needs four conditions to hold at the same time.",
    "Paging splits memory into fixed-size frames.",
    "The scheduler picks the next runnable thread.",
    "Caches exploit temporal and spatial locality.",
]


def _prose(n: int) -> str:
    return " ".join(f"{SENTENCES[i % len(SENTENCES)]} ({i})" for i in range(n))


def test_short_text_is_one_chunk() -> None:
    assert chunk_text("Just one short line.", size=800, overlap=100) == ["Just one short line."]


def test_empty_text_gives_no_chunks() -> None:
    assert chunk_text("  \n\n ", size=800, overlap=100) == []


def test_chunks_respect_size_and_are_not_empty() -> None:
    chunks = chunk_text(_prose(80), size=300, overlap=60, min_chunk_chars=0)
    assert len(chunks) > 5
    assert all(c.strip() for c in chunks)
    assert all(len(c) <= 300 for c in chunks)


def test_merged_tail_stays_within_size_plus_min() -> None:
    chunks = chunk_text(_prose(80), size=300, overlap=60)
    assert all(len(c) <= 300 + MIN_CHUNK_CHARS for c in chunks)


def test_consecutive_chunks_overlap_by_whole_sentences() -> None:
    chunks = chunk_text(_prose(40), size=300, overlap=100, min_chunk_chars=0)
    for before, after in zip(chunks, chunks[1:], strict=False):
        shared = next((n for n in range(min(len(before), len(after)), 0, -1)
                       if before.endswith(after[:n])), 0)
        assert 0 < shared <= 100


def test_zero_overlap_has_no_shared_text() -> None:
    chunks = chunk_text(_prose(40), size=300, overlap=0, min_chunk_chars=0)
    joined = " ".join(chunks)
    for i in range(40):
        assert joined.count(f"({i})") == 1


def test_no_content_is_lost() -> None:
    chunks = chunk_text(_prose(60), size=250, overlap=50)
    joined = "\n".join(chunks)
    for i in range(60):
        assert f"({i})" in joined


def test_newlines_are_unit_boundaries() -> None:
    text = "\n".join(f"- bullet number {i} about operating systems" for i in range(30))
    chunks = chunk_text(text, size=200, overlap=40, min_chunk_chars=0)
    assert all(len(c) <= 200 for c in chunks)
    assert all(c.startswith("- bullet") for c in chunks)


def test_giant_token_is_hard_split() -> None:
    chunks = chunk_text("x" * 2500, size=1000, overlap=100, min_chunk_chars=0)
    assert [len(c) for c in chunks] == [1000, 1000, 500]


def test_long_sentence_without_punctuation_splits_on_words() -> None:
    text = " ".join(f"word{i}" for i in range(400))
    chunks = chunk_text(text, size=200, overlap=0, min_chunk_chars=0)
    assert all(len(c) <= 200 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_tiny_tail_is_merged_into_previous_chunk() -> None:
    body = _prose(6)
    text = body + " Tail."
    with_merge = chunk_text(text, size=len(body) + 1, overlap=0, min_chunk_chars=80)
    without = chunk_text(text, size=len(body) + 1, overlap=0, min_chunk_chars=0)
    assert len(without) == len(with_merge) + 1
    assert with_merge[-1].endswith("Tail.")


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (-5, 0), (100, 100), (100, -1)])
def test_invalid_parameters(size: int, overlap: int) -> None:
    with pytest.raises(ValueError):
        chunk_text("text", size=size, overlap=overlap)


def _doc() -> Document:
    return Document(
        source="os-lecture.pdf",
        pages=[
            Page(number=1, text=_prose(30)),
            Page(number=3, text="Short slide."),
            Page(number=7, text=_prose(30)),
        ],
    )


def test_chunks_keep_source_and_original_page_numbers() -> None:
    chunks = chunk_document(_doc(), size=300, overlap=50)
    assert {c.source for c in chunks} == {"os-lecture.pdf"}
    assert {c.page for c in chunks} == {1, 3, 7}
    assert [c.text for c in chunks if c.page == 3] == ["Short slide."]


def test_chunk_ids_are_unique_and_stable() -> None:
    first = chunk_document(_doc(), size=300, overlap=50)
    second = chunk_document(_doc(), size=300, overlap=50)
    ids = [c.chunk_id for c in first]
    assert ids == [c.chunk_id for c in second]
    assert len(set(ids)) == len(ids)


def test_chunk_id_changes_when_text_changes() -> None:
    assert make_chunk_id("a.pdf", 1, 0, "hello") != make_chunk_id("a.pdf", 1, 0, "hello!")
    assert make_chunk_id("a.pdf", 1, 0, "hello") == make_chunk_id("a.pdf", 1, 0, "hello")
