"""HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile

from vectornote import __version__
from vectornote.api.deps import get_service, get_settings
from vectornote.api.schemas import (
    AskRequest,
    AskResponse,
    DocumentInfo,
    HealthResponse,
    IngestResponse,
    SourceRef,
)
from vectornote.config import Settings
from vectornote.ingestion.loaders import DocumentLoadError, UnsupportedFileTypeError
from vectornote.service import RagService

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]
ServiceDep = Annotated[RagService, Depends(get_service)]


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", version=__version__)


@router.get("/documents", response_model=list[DocumentInfo])
def list_documents(settings: SettingsDep) -> list[DocumentInfo]:
    """List the files currently in the data directory."""
    data_dir = settings.data_dir
    if not data_dir.is_dir():
        return []
    return [
        DocumentInfo(name=p.name, size_bytes=p.stat().st_size)
        for p in sorted(data_dir.iterdir())
        if p.is_file() and not p.name.startswith(".")
    ]


@router.post("/ingest", response_model=IngestResponse)
def ingest(file: UploadFile, service: ServiceDep) -> IngestResponse:
    """Upload a PDF, Markdown or text file and index it."""
    try:
        result = service.ingest_upload(file.filename or "upload", file.file.read())
    except UnsupportedFileTypeError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except DocumentLoadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return IngestResponse(
        filename=result.source, status=result.status, chunks_added=result.chunks_added
    )


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, service: ServiceDep) -> AskResponse:
    try:
        answer, results = service.ask(body.question, body.top_k)
    except NotImplementedError:
        raise HTTPException(status_code=501, detail="Question answering is not implemented yet.")
    sources = [
        SourceRef(
            source=r.chunk.source,
            page=r.chunk.page,
            snippet=r.chunk.text[:300],
            score=r.score,
        )
        for r in results
    ]
    return AskResponse(answer=answer, sources=sources)
