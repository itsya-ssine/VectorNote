"""Service layer: the single entry point the API and CLI call into.

Keep retrieval and generation behind this class so that no UI or route
handler ever touches the pipeline internals directly.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from vectornote.config import Settings
from vectornote.embeddings import Embedder, create_embedder
from vectornote.ingestion.chunking import chunk_document
from vectornote.ingestion.cleaning import clean_document
from vectornote.ingestion.loaders import (
    SUPPORTED_EXTENSIONS,
    DocumentLoadError,
    UnsupportedFileTypeError,
    list_supported_files,
    load_document,
)
from vectornote.models import SearchResult
from vectornote.retrieval import Retriever
from vectornote.store import ChromaStore

ENCODE_BATCH = 64

IngestStatus = Literal["added", "updated", "unchanged", "empty", "failed", "removed"]

_UNSAFE = re.compile(r"[^\w .()\-]")


@dataclass(frozen=True)
class IngestResult:
    """Outcome of ingesting one file."""

    source: str
    status: IngestStatus
    chunks_added: int = 0
    error: str | None = None


def safe_filename(name: str) -> str:
    """Reduce an uploaded file name to a safe name inside the data directory."""
    base = Path(name.replace("\\", "/")).name
    base = _UNSAFE.sub("_", base).strip(" .")
    return base or "upload"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


class RagService:
    """Orchestrates ingestion, retrieval and generation."""

    def __init__(
        self,
        settings: Settings,
        embedder: Embedder | None = None,
        store: ChromaStore | None = None,
    ) -> None:
        self.settings = settings
        self._embedder = embedder
        self._store = store
        self._retriever: Retriever | None = None
        self._lock = threading.Lock()

    @property
    def embedder(self) -> Embedder:
        if self._embedder is None:
            self._embedder = create_embedder(self.settings.embedding_model)
        return self._embedder

    @property
    def store(self) -> ChromaStore:
        if self._store is None:
            self._store = ChromaStore(self.settings.chroma_dir, self.embedder.name)
        return self._store

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = Retriever(self.embedder, self.store)
        return self._retriever

    def index_size(self) -> int:
        """Number of chunks currently indexed."""
        return self.store.count()

    # ---- ingestion -------------------------------------------------------

    def ingest_path(
        self, path: Path, source: str | None = None, force: bool = False
    ) -> IngestResult:
        """Ingest one file: load, clean, chunk, embed and store it.

        Unchanged files (same content hash) are skipped unless `force` is set.
        An edited file replaces its old chunks, but only after the new ones were
        embedded successfully, so a failure never wipes the existing index.
        """
        name = source or path.name
        with self._lock:
            file_hash = hash_file(path)
            if not force and self.store.get_file_hash(name) == file_hash:
                return IngestResult(name, "unchanged")

            doc = clean_document(load_document(path, source=name))
            chunks = chunk_document(
                doc, self.settings.chunk_size, self.settings.chunk_overlap
            )
            texts = [chunk.text for chunk in chunks]
            vectors: list[list[float]] = []
            for start in range(0, len(texts), ENCODE_BATCH):
                vectors.extend(self.embedder.encode(texts[start:start + ENCODE_BATCH]))

            removed = self.store.delete_by_source(name)
            if not chunks:
                return IngestResult(name, "empty")
            self.store.add(chunks, vectors, file_hash=file_hash)
            return IngestResult(name, "updated" if removed else "added", len(chunks))

    def ingest_directory(
        self, directory: Path, force: bool = False, prune: bool = False
    ) -> Iterator[IngestResult]:
        """Ingest every supported file under `directory`, one result per file.

        A file that cannot be read yields a `failed` result and does not stop the run.
        With `prune`, sources that are no longer in the directory are removed
        from the index.
        """
        if not directory.is_dir():
            raise FileNotFoundError(directory)
        seen: set[str] = set()
        for path, source in list_supported_files(directory):
            seen.add(source)
            try:
                yield self.ingest_path(path, source=source, force=force)
            except (UnsupportedFileTypeError, DocumentLoadError, OSError) as exc:
                yield IngestResult(source, "failed", error=str(exc))
        if prune:
            with self._lock:
                stale = [name for name in self.store.list_sources() if name not in seen]
                for name in stale:
                    self.store.delete_by_source(name)
            for name in stale:
                yield IngestResult(name, "removed")

    def ingest_upload(self, filename: str, content: bytes) -> IngestResult:
        """Save an uploaded file into the data directory and ingest it.

        The file only replaces an existing one if it ingests successfully.
        """
        name = safe_filename(filename)
        suffix = Path(name).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
            raise UnsupportedFileTypeError(f"Unsupported file type '{suffix}' (use {supported})")

        data_dir = self.settings.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=data_dir, prefix=".upload-", suffix=suffix, delete=False
        ) as handle:
            handle.write(content)
        temp = Path(handle.name)
        try:
            result = self.ingest_path(temp, source=name)
            temp.replace(data_dir / name)
            return result
        finally:
            temp.unlink(missing_ok=True)

    # ---- retrieval -------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int | None = None,
        sources: Sequence[str] | None = None,
        min_score: float | None = None,
    ) -> list[SearchResult]:
        """Find the passages most relevant to `query` (default `top_k` from settings)."""
        return self.retriever.search(
            query, top_k or self.settings.top_k, sources=sources, min_score=min_score
        )

    def indexed_sources(self) -> dict[str, int]:
        """Map each indexed file to its number of chunks."""
        return self.store.list_sources()

    # ---- question answering ----------------------------------------------

    def ask(self, question: str, top_k: int) -> tuple[str, list[SearchResult]]:
        """Answer a question and return the answer with its supporting chunks.

        Implemented in Phase 3.
        """
        raise NotImplementedError
