"""Request and response models for the HTTP API."""

from __future__ import annotations

from pydantic import BaseModel, Field

from vectornote.models import ChatTurn


class HealthResponse(BaseModel):
    status: str
    version: str


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)
    sources: list[str] | None = None
    mode: str | None = None
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


class SourceRef(BaseModel):
    number: int
    source: str
    page: int
    snippet: str
    score: float


class AskResponse(BaseModel):
    answer: str
    answered: bool
    standalone_question: str
    cited: bool
    sources: list[SourceRef]


class DocumentInfo(BaseModel):
    name: str
    size_bytes: int


class IngestResponse(BaseModel):
    filename: str
    status: str
    chunks_added: int
