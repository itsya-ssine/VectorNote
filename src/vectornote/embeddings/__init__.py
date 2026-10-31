"""Embedding models."""

from vectornote.embeddings.base import Embedder
from vectornote.embeddings.factory import create_embedder

__all__ = ["Embedder", "create_embedder"]
