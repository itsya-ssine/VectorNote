"""FastAPI dependencies."""

from __future__ import annotations

from functools import lru_cache

from vectornote.config import Settings
from vectornote.service import RagService


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_service() -> RagService:
    return RagService(get_settings())
