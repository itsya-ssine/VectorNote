"""HTTP routes."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from vectornote import __version__
from vectornote.api.deps import get_service, get_settings
from vectornote.api.schemas import (
    AskRequest,
    AskResponse,
    DeleteResponse,
    DocumentInfo,
    HealthResponse,
    IngestResponse,
    SourceRef,
)
from vectornote.config import Settings
from vectornote.generation import OllamaError
from vectornote.ingestion.loaders import DocumentLoadError, UnsupportedFileTypeError
from vectornote.models import AskResult
from vectornote.service import AskEvent, QueryEvent, RagService, TokenEvent

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


@router.delete("/documents/{name}", response_model=DeleteResponse)
def delete_document(name: str, service: ServiceDep) -> DeleteResponse:
    """Remove a file from the data directory and drop its chunks from the index."""
    try:
        removed = service.delete_document(name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"No document named '{name}'") from exc
    return DeleteResponse(filename=name, chunks_removed=removed)


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


def _response(result: AskResult) -> AskResponse:
    return AskResponse(
        answer=result.answer,
        answered=result.answered,
        standalone_question=result.standalone_question,
        cited=result.cited,
        sources=[
            SourceRef(
                number=c.number,
                source=c.source,
                page=c.page,
                snippet=c.snippet,
                score=c.score,
            )
            for c in result.citations
        ],
    )


@router.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, service: ServiceDep) -> AskResponse:
    """Answer a question from the indexed documents, with numbered source citations."""
    try:
        result = service.ask(body.question, body.top_k, body.sources, body.mode, body.history)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _response(result)


def _sse(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _encode(event: AskEvent) -> str:
    if isinstance(event, TokenEvent):
        return _sse("token", {"text": event.text})
    if isinstance(event, QueryEvent):
        return _sse("query", {"question": event.question})
    return _sse("done", _response(event.result).model_dump())


@router.post("/ask/stream")
async def ask_stream(body: AskRequest, service: ServiceDep) -> StreamingResponse:
    """Same as `/ask`, as a Server-Sent Events stream.

    Events: `query` (`{"question"}`, only when a follow-up was rewritten), `token`
    (`{"text"}`, many), then `done` (the same JSON as `/ask`), or `error`
    (`{"detail"}`) if the model fails midway. Problems that exist before the first token
    (bad input, Ollama down, model missing) are normal HTTP errors, as for `/ask`.

    If the client disconnects, the model's stream is closed, which stops the generation.
    """
    events = service.ask_stream(
        body.question, body.top_k, body.sources, body.mode, body.history
    )
    advance = partial(next, events, None)  # blocking: always run in a worker thread
    try:
        first = await run_in_threadpool(advance)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    async def generate() -> AsyncIterator[str]:
        # This must be an async generator: when the client goes away, Starlette cancels it
        # at the `await` below and the `finally` runs. A plain generator would just be
        # abandoned, leaving the model generating for nobody.
        try:
            event = first
            while event is not None:
                yield _encode(event)
                event = await run_in_threadpool(advance)
        except OllamaError as exc:
            yield _sse("error", {"detail": str(exc)})
        finally:
            events.close()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
