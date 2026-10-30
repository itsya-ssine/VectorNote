"""FastAPI application factory."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vectornote import __version__
from vectornote.api.routes import router


def create_app() -> FastAPI:
    app = FastAPI(title="VectorNote API", version=__version__)
    origins = os.environ.get("VECTORNOTE_CORS_ORIGINS", "http://localhost:3000").split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
