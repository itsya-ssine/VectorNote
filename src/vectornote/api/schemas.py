"""Request and response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    version: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


class SourceRef(BaseModel):
    source: str
    page: int
    snippet: str
    score: float


class AskResponse(BaseModel):
    answer: str
    sources: list[SourceRef]


class DocumentInfo(BaseModel):
    name: str
    size_bytes: int


class IngestResponse(BaseModel):
    filename: str
    status: str
    chunks_added: int
