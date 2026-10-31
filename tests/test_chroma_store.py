from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from vectornote.embeddings.hashing import HashingEmbedder
from vectornote.models import Chunk, SearchResult
from vectornote.store import ChromaStore, EmbeddingModelMismatchError

EMBEDDER = HashingEmbedder()

CHUNKS = [
    Chunk(chunk_id="os.pdf#p1-c0", source="os.pdf", page=1,
          text="A mutex gives mutual exclusion to a critical section."),
    Chunk(chunk_id="os.pdf#p2-c0", source="os.pdf", page=2,
          text="Paging splits virtual memory into fixed size frames."),
    Chunk(chunk_id="net.md#p1-c0", source="net.md", page=1,
          text="A subnet mask separates the network and host parts of an address."),
]


def _store(path: Path) -> ChromaStore:
    return ChromaStore(path, EMBEDDER.name)


def _fill(store: ChromaStore) -> None:
    store.add(CHUNKS, EMBEDDER.encode([c.text for c in CHUNKS]))


def _ask(
    store: ChromaStore, text: str, k: int = 3, sources: list[str] | None = None
) -> list[SearchResult]:
    [vector] = EMBEDDER.encode([text])
    return store.query(vector, k, sources)


def test_query_returns_best_chunk_first(tmp_path: Path) -> None:
    store = _store(tmp_path / "db")
    _fill(store)
    results = _ask(store, "how does a mutex lock a critical section")
    assert results[0].chunk.chunk_id == "os.pdf#p1-c0"
    assert results[0].chunk.source == "os.pdf"
    assert results[0].chunk.page == 1
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_top_k_larger_than_store(tmp_path: Path) -> None:
    store = _store(tmp_path / "db")
    _fill(store)
    assert len(_ask(store, "memory", k=50)) == 3


def test_query_empty_store(tmp_path: Path) -> None:
    assert _ask(_store(tmp_path / "db"), "anything") == []


def test_source_filter(tmp_path: Path) -> None:
    store = _store(tmp_path / "db")
    _fill(store)
    results = _ask(store, "address", k=5, sources=["net.md"])
    assert {r.chunk.source for r in results} == {"net.md"}


def test_add_is_idempotent(tmp_path: Path) -> None:
    store = _store(tmp_path / "db")
    _fill(store)
    _fill(store)
    assert store.count() == 3


def test_add_checks_lengths(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _store(tmp_path / "db").add(CHUNKS, [[0.0] * 384])


def test_list_sources_and_delete_by_source(tmp_path: Path) -> None:
    store = _store(tmp_path / "db")
    _fill(store)
    assert store.list_sources() == {"net.md": 1, "os.pdf": 2}
    assert store.delete_by_source("os.pdf") == 2
    assert store.list_sources() == {"net.md": 1}
    assert store.delete_by_source("missing.pdf") == 0


def test_index_survives_reopening(tmp_path: Path) -> None:
    path = tmp_path / "db"
    _fill(_store(path))
    reopened = _store(path)
    assert reopened.count() == 3
    assert _ask(reopened, "subnet mask")[0].chunk.source == "net.md"


def test_index_survives_a_new_process(tmp_path: Path) -> None:
    path = tmp_path / "db"
    _fill(_store(path))
    code = textwrap.dedent(
        f"""
        from pathlib import Path
        from vectornote.embeddings.hashing import HashingEmbedder
        from vectornote.store import ChromaStore
        e = HashingEmbedder()
        s = ChromaStore(Path({str(path)!r}), e.name)
        [v] = e.encode(["virtual memory paging"])
        print(s.count(), s.query(v, 1)[0].chunk.chunk_id)
        """
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    assert out.split() == ["3", "os.pdf#p2-c0"]


def test_different_embedding_model_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "db"
    _fill(_store(path))
    with pytest.raises(EmbeddingModelMismatchError, match="hashing"):
        ChromaStore(path, "sentence-transformers/all-MiniLM-L6-v2")
