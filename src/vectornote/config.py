"""Runtime settings, read from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(name: str, default: str) -> str:
    return os.environ.get(f"VECTORNOTE_{name}", default)


@dataclass(frozen=True)
class Settings:
    """Central configuration for VectorNote."""

    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    llm_model: str = field(default_factory=lambda: _env("LLM_MODEL", "llama3.2:3b"))
    embedding_model: str = field(
        default_factory=lambda: _env(
            "EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"
        )
    )
    data_dir: Path = field(default_factory=lambda: Path(_env("DATA_DIR", "data")))
    chroma_dir: Path = field(default_factory=lambda: Path(_env("CHROMA_DIR", "chroma_db")))
    chunk_size: int = 800
    chunk_overlap: int = 100
    top_k: int = 5
