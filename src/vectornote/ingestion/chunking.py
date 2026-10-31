"""Split documents into overlapping chunks with citation metadata.

Chunks never cross a page boundary, so every chunk maps to exactly one
`[source, page]` citation. Text is split into small units (lines and
sentences) which are packed greedily up to `size` characters; the overlap
between consecutive chunks is made of whole trailing units, so it is at most
`overlap` characters and never starts mid-word.
"""

from __future__ import annotations

import hashlib
import re

from vectornote.models import Chunk, Document

# A trailing piece shorter than this is merged into the previous chunk of the page.
MIN_CHUNK_CHARS = 80

# A unit ends after sentence punctuation + spaces, or after a run of newlines.
_UNIT_BREAK = re.compile(r"(?<=[.!?])[ \t]+|\n+")
_WORD = re.compile(r"\S+\s*")


def make_chunk_id(source: str, page: int, index: int, text: str) -> str:
    """Stable ID: same input gives the same ID, edited text gives a new one."""
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{source}#p{page}-c{index}-{digest}"


def _units(text: str) -> list[str]:
    """Split into lines/sentences, each keeping its trailing whitespace."""
    units: list[str] = []
    start = 0
    for match in _UNIT_BREAK.finditer(text):
        end = match.end()
        units.append(text[start:end])
        start = end
    if start < len(text):
        units.append(text[start:])
    return units


def _split_long(unit: str, size: int) -> list[str]:
    """Split a unit longer than `size` on word boundaries (hard-cut giant tokens)."""
    pieces: list[str] = []
    current = ""
    for word in _WORD.findall(unit):
        while len(word) > size:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(word[:size])
            word = word[size:]
        if current and len(current) + len(word) > size:
            pieces.append(current)
            current = ""
        current += word
    if current:
        pieces.append(current)
    return pieces


def _pieces(text: str, size: int) -> list[str]:
    pieces: list[str] = []
    for unit in _units(text):
        pieces.extend([unit] if len(unit) <= size else _split_long(unit, size))
    return pieces


def _pack(pieces: list[str], size: int, overlap: int, min_chunk_chars: int) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    carried = 0  # leading pieces in `current` that came from the previous chunk
    for piece in pieces:
        if current and length + len(piece) > size:
            chunks.append("".join(current))
            while current and (length > overlap or length + len(piece) > size):
                length -= len(current.pop(0))
            carried = len(current)
        current.append(piece)
        length += len(piece)
    if current:
        fresh = "".join(current[carried:])
        if chunks and len(fresh.strip()) < min_chunk_chars:
            chunks[-1] += fresh
        else:
            chunks.append("".join(current))
    return chunks


def chunk_text(
    text: str, size: int, overlap: int, min_chunk_chars: int = MIN_CHUNK_CHARS
) -> list[str]:
    """Chunk one piece of text. Returned chunks are stripped and non-empty."""
    if size <= 0:
        raise ValueError("size must be positive")
    if not 0 <= overlap < size:
        raise ValueError("overlap must be between 0 and size - 1")
    packed = _pack(_pieces(text, size), size, overlap, min_chunk_chars)
    return [chunk.strip() for chunk in packed if chunk.strip()]


def chunk_document(
    doc: Document, size: int, overlap: int, min_chunk_chars: int = MIN_CHUNK_CHARS
) -> list[Chunk]:
    """Chunk every page of a document, keeping source and page on each chunk."""
    chunks: list[Chunk] = []
    for page in doc.pages:
        texts = chunk_text(page.text, size, overlap, min_chunk_chars)
        for index, text in enumerate(texts):
            chunks.append(
                Chunk(
                    chunk_id=make_chunk_id(doc.source, page.number, index, text),
                    text=text,
                    source=doc.source,
                    page=page.number,
                )
            )
    return chunks
