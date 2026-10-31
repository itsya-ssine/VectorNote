"""FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from vectornote.config import Settings
from vectornote.service import RagService


@lru_cache
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=8)
def _service_for(settings: Settings) -> RagService:
    """One service (and so one loaded model and one open index) per configuration."""
    return RagService(settings)


def get_service(settings: Annotated[Settings, Depends(get_settings)]) -> RagService:
    return _service_for(settings)
