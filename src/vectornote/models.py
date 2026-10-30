"""Core data models shared across the pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Document(BaseModel):
    """A loaded source file split into pages."""

    source: str
    pages: list[str]


class Chunk(BaseModel):
    """A retrievable piece of text with citation metadata."""

    chunk_id: str
    text: str
    source: str
    page: int = Field(ge=1)


class SearchResult(BaseModel):
    """A chunk returned by retrieval, with its relevance score."""

    chunk: Chunk
    score: float
