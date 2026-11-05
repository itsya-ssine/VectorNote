"""Protection against oversized uploads."""

from __future__ import annotations

from collections.abc import Callable

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# A multipart body is a little bigger than the file inside it.
MULTIPART_OVERHEAD = 64 * 1024
# How much of a refused upload is read and thrown away, so the client can see the answer.
MAX_DRAIN_BYTES = 1024 * 1024 * 1024


def too_large_detail(limit_mb: int) -> str:
    return f"File is too large (the limit is {limit_mb} MB)."


class UploadSizeLimit:
    """Refuses an oversized upload from its Content-Length, before it is parsed or stored.

    Starlette writes a multipart upload to a temporary file before the route runs, so the check
    has to happen here. The body is read and discarded rather than left unread: a client that is
    still sending when the response arrives would otherwise see a dropped connection instead of
    the message. Uploads without a Content-Length are checked by the route after reading.
    """

    def __init__(self, app: ASGIApp, limit_mb: Callable[[], int]) -> None:
        self.app = app
        self.limit_mb = limit_mb

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST" and scope["path"] == "/ingest":
            limit_mb = self.limit_mb()
            declared = dict(scope["headers"]).get(b"content-length", b"")
            if declared.isdigit() and int(declared) > limit_mb * 1024 * 1024 + MULTIPART_OVERHEAD:
                await _drain(receive)
                response = JSONResponse({"detail": too_large_detail(limit_mb)}, status_code=413)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


async def _drain(receive: Receive) -> None:
    seen = 0
    while seen < MAX_DRAIN_BYTES:
        message = await receive()
        if message["type"] != "http.request":
            return
        seen += len(message.get("body", b""))
        if not message.get("more_body", False):
            return
