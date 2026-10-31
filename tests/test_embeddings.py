from __future__ import annotations

import math
import sys
import types

import pytest

from vectornote.embeddings import create_embedder
from vectornote.embeddings.encoder import Encoder
from vectornote.embeddings.hashing import HashingEmbedder


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingEmbedder()
    [first] = embedder.encode(["A mutex protects a critical section."])
    [second] = embedder.encode(["A mutex protects a critical section."])
    assert first == second
    assert len(first) == 384
    assert math.isclose(sum(v * v for v in first), 1.0, rel_tol=1e-9)


def test_hashing_embedder_ranks_shared_words_higher() -> None:
    embedder = HashingEmbedder()
    query, near, far = embedder.encode(
        ["mutex lock critical section", "a mutex is a lock", "paging and virtual memory"]
    )
    assert _cosine(query, near) > _cosine(query, far)


def test_hashing_embedder_handles_text_without_words() -> None:
    [vector] = HashingEmbedder().encode(["--- ***"])
    assert math.isclose(sum(v * v for v in vector), 1.0)


def test_factory_picks_backend() -> None:
    assert isinstance(create_embedder("hashing"), HashingEmbedder)
    encoder = create_embedder("sentence-transformers/all-MiniLM-L6-v2")
    assert isinstance(encoder, Encoder)
    assert encoder.name == "sentence-transformers/all-MiniLM-L6-v2"


class _FakeArray:
    def __init__(self, rows: list[list[float]]) -> None:
        self._rows = rows

    def tolist(self) -> list[list[float]]:
        return self._rows


def test_encoder_is_lazy_and_passes_batching_options(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, object]] = []
    loaded: list[str] = []

    class FakeModel:
        def __init__(self, name: str) -> None:
            loaded.append(name)

        def encode(self, texts: list[str], **kwargs: object) -> _FakeArray:
            calls.append({"texts": texts, **kwargs})
            return _FakeArray([[1.0, 0.0] for _ in texts])

    fake_module = types.ModuleType("sentence_transformers")
    fake_module.SentenceTransformer = FakeModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_module)

    encoder = Encoder("some/model", batch_size=8)
    assert loaded == []
    assert encoder.encode([]) == []
    assert loaded == []

    assert encoder.encode(["a", "b"]) == [[1.0, 0.0], [1.0, 0.0]]
    encoder.encode(["c"])
    assert loaded == ["some/model"]
    assert calls[0]["batch_size"] == 8
    assert calls[0]["normalize_embeddings"] is True


def test_encoder_explains_missing_dependency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sentence_transformers", None)
    with pytest.raises(RuntimeError, match="uv add sentence-transformers"):
        Encoder("some/model").encode(["text"])
