"""Choose an embedder from the configured model name."""

from __future__ import annotations

from vectornote.embeddings.base import Embedder
from vectornote.embeddings.encoder import Encoder
from vectornote.embeddings.hashing import HashingEmbedder

HASHING_MODEL = "hashing"


def create_embedder(model_name: str) -> Embedder:
    """`hashing` is the light test embedder; any other name is a sentence-transformers model."""
    if model_name == HASHING_MODEL:
        return HashingEmbedder()
    return Encoder(model_name)
