"""Split documents into overlapping chunks with citation metadata."""

from __future__ import annotations

from vectornote.models import Chunk, Document


def chunk_document(doc: Document, size: int, overlap: int) -> list[Chunk]:
    """Chunk a document. Implemented in Phase 1."""
    raise NotImplementedError
