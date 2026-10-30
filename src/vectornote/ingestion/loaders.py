"""Load PDF, Markdown and text files into Document objects."""

from __future__ import annotations

from pathlib import Path

from vectornote.models import Document


def load_document(path: Path) -> Document:
    """Load a single file. Implemented in Phase 1."""
    raise NotImplementedError
