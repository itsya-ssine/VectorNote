"""Local sentence-transformers encoder (default: all-MiniLM-L6-v2)."""

from __future__ import annotations

import importlib
from collections.abc import Sequence
from typing import Any


class EmbedderUnavailableError(RuntimeError):
    """The embedding backend cannot run (for example, a missing dependency)."""


class Encoder:
    """Runs a sentence-transformers model on this machine.

    The model is loaded lazily on the first `encode` call, so importing VectorNote
    (or building the API) stays fast. The first load downloads the model once into
    the Hugging Face cache; set `HF_HUB_OFFLINE=1` afterwards to guarantee that
    nothing ever leaves your machine.
    """

    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self.name = model_name
        self.batch_size = batch_size
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            try:
                module = importlib.import_module("sentence_transformers")
            except ImportError as exc:
                raise EmbedderUnavailableError(
                    "sentence-transformers is not installed. Run: uv add sentence-transformers"
                ) from exc
            self._model = module.SentenceTransformer(self.name)
        return self._model

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        vectors = self._load().encode(
            items,
            batch_size=self.batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        result: list[list[float]] = vectors.tolist()
        return result
