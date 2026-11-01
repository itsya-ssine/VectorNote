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
    """A chunk returned by retrieval.

    `score` is the ranking score of the search mode that produced the result
    (cosine similarity, BM25 or fused RRF score), so only compare scores within
    one mode. `vector_score` (cosine similarity) and `bm25_score` are filled in
    whenever the mode computed them.
    """

    chunk: Chunk
    score: float
    vector_score: float | None = None
    bm25_score: float | None = None


class Citation(BaseModel):
    """A numbered source passage an answer refers to as `[number]`."""

    number: int = Field(ge=1)
    source: str
    page: int = Field(ge=1)
    snippet: str
    score: float


class AskResult(BaseModel):
    """The outcome of asking a question.

    `answered` is False when the notes do not cover the question (the model was not
    called, or it said it could not find the answer). `cited` is True when the answer
    contains valid `[n]` markers; otherwise `citations` falls back to every passage
    the model was given, so the reader can still check them.
    """

    answer: str
    answered: bool
    cited: bool = False
    citations: list[Citation] = Field(default_factory=list)
    context: list[SearchResult] = Field(default_factory=list)
