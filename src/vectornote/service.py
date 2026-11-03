"""Service layer: the single entry point the API and CLI call into.

Keep retrieval and generation behind this class so that no UI or route
handler ever touches the pipeline internals directly.
"""

from __future__ import annotations

import hashlib
import re
import tempfile
import threading
from collections.abc import Generator, Iterator, Sequence
from contextlib import closing
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
from vectornote.generation import ChatModel, OllamaClient
from vectornote.generation.citations import extract_citations, is_not_found
from vectornote.generation.rewrite import (
    REWRITE_MAX_TOKENS,
    build_rewrite_messages,
    clean_rewrite,
)
from vectornote.generation.streaming import NotFoundGate
from vectornote.generation.prompts import (
    Refusal,
    build_messages,
    refusal_message,
    select_context,
)
from vectornote.models import AskResult, ChatTurn, Chunk, Citation, SearchResult
from vectornote.retrieval import Retriever
from vectornote.store import ChromaStore

ENCODE_BATCH = 64

IngestStatus = Literal["added", "updated", "unchanged", "empty", "failed", "removed"]

_UNSAFE = re.compile(r"[^\w .()\-]")


@dataclass(frozen=True)
class TokenEvent:
    """A piece of the answer, ready to show."""

    text: str


@dataclass(frozen=True)
class QueryEvent:
    """The follow-up question was rewritten; this is what is being searched for."""

    question: str


@dataclass(frozen=True)
class DoneEvent:
    """The final result. `result.answer` is authoritative (it may differ from the tokens)."""

    result: AskResult


AskEvent = TokenEvent | QueryEvent | DoneEvent


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
        llm: ChatModel | None = None,
    ) -> None:
        self.settings = settings
        self._embedder = embedder
        self._store = store
        self._llm = llm
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
    def llm(self) -> ChatModel:
        if self._llm is None:
            self._llm = OllamaClient(self.settings.ollama_url, self.settings.llm_model)
        return self._llm

    @property
    def retriever(self) -> Retriever:
        if self._retriever is None:
            self._retriever = Retriever(
                self.embedder, self.store, mode=self.settings.retrieval_mode
            )
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

    def delete_document(self, name: str) -> int:
        """Remove a file from the data directory and from the index.

        Returns how many chunks were removed. Raises `FileNotFoundError` when the name is
        neither a file in the data directory nor an indexed source, and `ValueError` when it
        is not a plain file name (so it can never point outside the data directory).
        """
        if name != safe_filename(name) or name.startswith("."):
            raise ValueError(f"Invalid file name '{name}'")
        path = self.settings.data_dir / name
        had_file = path.is_file()
        removed = self.store.delete_by_source(name)
        if not had_file and removed == 0:
            raise FileNotFoundError(name)
        if had_file:
            path.unlink()
        return removed

    # ---- retrieval -------------------------------------------------------

    def search(
        self,
        query: str,
        top_k: int | None = None,
        sources: Sequence[str] | None = None,
        min_score: float | None = None,
        mode: str | None = None,
    ) -> list[SearchResult]:
        """Find the passages most relevant to `query`.

        `top_k` and the default `mode` (vector, bm25 or hybrid) come from settings.
        """
        return self.retriever.search(
            query,
            top_k or self.settings.top_k,
            sources=sources,
            min_score=min_score,
            mode=mode,
        )

    def indexed_sources(self) -> dict[str, int]:
        """Map each indexed file to its number of chunks."""
        return self.store.list_sources()

    def indexed_chunks(self) -> list[Chunk]:
        """Every indexed chunk (used by the evaluation tools)."""
        return self.store.all_chunks()

    # ---- question answering ----------------------------------------------

    def ask(
        self,
        question: str,
        top_k: int | None = None,
        sources: Sequence[str] | None = None,
        mode: str | None = None,
        history: Sequence[ChatTurn] | None = None,
    ) -> AskResult:
        """Answer a question from the indexed documents, with numbered citations.

        `history` holds the earlier messages of the conversation. When it is given, the
        question is first rewritten into a standalone one, so follow-ups such as
        "explain that more" are searched for correctly.

        Passages whose cosine similarity is below `min_relevance` are not used. If
        nothing relevant remains, or the model reports that the passages do not
        contain the answer, the result has `answered=False` and no model call is
        wasted on guessing.
        """
        text = self._standalone_question(question, history)
        early, context = self._retrieve_for_answer(text, top_k, sources, mode)
        if early is not None:
            return early
        reply = self.llm.complete(build_messages(text, context))
        return self._finish_answer(reply, context, text)

    def ask_stream(
        self,
        question: str,
        top_k: int | None = None,
        sources: Sequence[str] | None = None,
        mode: str | None = None,
        history: Sequence[ChatTurn] | None = None,
    ) -> Generator[AskEvent, None, None]:
        """Like `ask`, but yields the answer piece by piece.

        Yields a `QueryEvent` first when a follow-up was rewritten, then `TokenEvent`s
        while the model writes, then one final `DoneEvent` with the cited sources. When no
        model call is needed (or the model reports NOT_FOUND), no tokens are yielded, only
        the `DoneEvent`. Closing the generator early stops the model. Errors are raised
        when the first event is requested.
        """
        text = self._standalone_question(question, history)
        if text != question.strip():
            yield QueryEvent(text)
        early, context = self._retrieve_for_answer(text, top_k, sources, mode)
        if early is not None:
            yield DoneEvent(early)
            return
        gate = NotFoundGate()
        parts: list[str] = []
        # `closing` guarantees the model's stream is closed (and generation stopped) as soon
        # as this generator is closed, instead of whenever the garbage collector runs.
        with closing(self.llm.stream(build_messages(text, context))) as pieces:
            for piece in pieces:
                parts.append(piece)
                visible = gate.feed(piece)
                if visible:
                    yield TokenEvent(visible)
        tail = gate.finish()
        if tail:
            yield TokenEvent(tail)
        yield DoneEvent(self._finish_answer("".join(parts), context, text))

    def standalone_question(self, question: str, history: Sequence[ChatTurn] | None = None) -> str:
        """The question as it will be searched for: a follow-up rewritten using `history`."""
        return self._standalone_question(question, history)

    def _standalone_question(self, question: str, history: Sequence[ChatTurn] | None) -> str:
        """The question to search for: the follow-up rewritten using the conversation."""
        text = question.strip()
        if not text:
            raise ValueError("question must not be empty")
        if not history or self.index_size() == 0:
            return text  # nothing to resolve, or nothing to search (no model call wasted)
        reply = self.llm.complete(
            build_rewrite_messages(history, text), max_tokens=REWRITE_MAX_TOKENS
        )
        return clean_rewrite(reply, text)

    def _retrieve_for_answer(
        self,
        text: str,
        top_k: int | None,
        sources: Sequence[str] | None,
        mode: str | None,
    ) -> tuple[AskResult | None, list[SearchResult]]:
        """Retrieve the passages for a question, or return a fixed reply if there are none."""
        if self.index_size() == 0:
            return self._unanswered(text, "empty_index"), []

        effective_mode = mode or self.settings.retrieval_mode
        # The relevance gate is a cosine threshold, which keyword-only search cannot provide.
        gate = None if effective_mode == "bm25" else self.settings.min_relevance
        results = self.search(text, top_k, sources, min_score=gate, mode=mode)
        if not results:
            return self._unanswered(text, "not_found"), []
        return None, select_context(results)

    @staticmethod
    def _unanswered(
        text: str, reason: Refusal, context: list[SearchResult] | None = None
    ) -> AskResult:
        return AskResult(
            answer=refusal_message(text, reason),
            answered=False,
            standalone_question=text,
            context=context or [],
        )

    def _finish_answer(self, reply: str, context: list[SearchResult], text: str) -> AskResult:
        """Turn the model's raw reply into an AskResult with citations."""
        reply = reply.strip()
        if not reply or is_not_found(reply):
            return self._unanswered(text, "not_found", context)
        numbers = extract_citations(reply, len(context))
        citation_numbers = numbers or list(range(1, len(context) + 1))
        return AskResult(
            answer=reply,
            answered=True,
            standalone_question=text,
            cited=bool(numbers),
            citations=[self._citation(n, context[n - 1]) for n in citation_numbers],
            context=context,
        )

    @staticmethod
    def _citation(number: int, result: SearchResult) -> Citation:
        score = result.vector_score if result.vector_score is not None else result.score
        return Citation(
            number=number,
            source=result.chunk.source,
            page=result.chunk.page,
            snippet=result.chunk.text[:300],
            score=score,
        )
