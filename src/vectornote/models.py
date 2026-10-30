"""Core data models shared across the pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Page(BaseModel):
    """One page of a source file. `number` is the original 1-based page number."""

    number: int = Field(ge=1)
    text: str


class Document(BaseModel):
    """A loaded source file split into pages.

    Pages that were dropped during cleaning leave gaps in the numbering,
    so `Page.number` always matches the page in the original file.
    """

    source: str
    pages: list[Page]


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
