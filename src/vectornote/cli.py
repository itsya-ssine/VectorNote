"""Command-line interface for VectorNote."""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from pathlib import Path

from vectornote import __version__
from vectornote.config import Settings
from vectornote.embeddings.encoder import EmbedderUnavailableError
from vectornote.ingestion.chunking import chunk_document
from vectornote.ingestion.cleaning import clean_document
from vectornote.ingestion.loaders import (
    DocumentLoadError,
    UnsupportedFileTypeError,
    load_document,
)
from vectornote.models import Document
from vectornote.service import IngestResult, RagService
from vectornote.store import EmbeddingModelMismatchError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vectornote",
        description="Offline RAG study assistant.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    ingest = sub.add_parser("ingest", help="Index documents (default: the data directory).")
    ingest.add_argument("paths", nargs="*", type=Path, help="files or folders to ingest")
    ingest.add_argument("--force", action="store_true", help="re-index unchanged files too")
    ingest.add_argument(
        "--prune", action="store_true", help="drop indexed files that left the data directory"
    )
    ask = sub.add_parser("ask", help="Ask a question about your documents.")
    ask.add_argument("question")
    search = sub.add_parser("search", help="Find the most relevant passages for a question.")
    search.add_argument("query")
    search.add_argument("-k", "--top-k", type=int, default=None, help="number of results")
    search.add_argument(
        "--source", action="append", dest="sources", help="only search this file (repeatable)"
    )
    search.add_argument("--min-score", type=float, default=None, help="drop weaker matches")
    search.add_argument("--full", action="store_true", help="print the whole chunk text")
    inspect = sub.add_parser("inspect", help="Load and clean one file and show the result.")
    inspect.add_argument("path", type=Path)
    inspect.add_argument("--chars", type=int, default=300, help="preview length per page")
    inspect.add_argument("--chunks", action="store_true", help="also show chunking statistics")
    serve = sub.add_parser("serve", help="Run the HTTP API.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--reload", action="store_true")
    return parser


def _inspect(path: Path, chars: int, show_chunks: bool) -> int:
    try:
        raw = load_document(path)
    except (FileNotFoundError, UnsupportedFileTypeError, DocumentLoadError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    doc = clean_document(raw)
    total = sum(len(page.text) for page in doc.pages)
    print(f"{doc.source}: {len(raw.pages)} page(s) loaded, {len(doc.pages)} kept, {total} chars")
    for page in doc.pages:
        preview = page.text[:chars].replace("\n", " / ")
        print(f"--- page {page.number} ({len(page.text)} chars)\n{preview}")
    if show_chunks:
        _print_chunk_stats(doc, chars)
    return 0


def _print_chunk_stats(doc: Document, chars: int) -> None:
    settings = Settings()
    chunks = chunk_document(doc, settings.chunk_size, settings.chunk_overlap)
    if not chunks:
        print("no chunks")
        return
    sizes = [len(c.text) for c in chunks]
    print(
        f"\n{len(chunks)} chunks (size={settings.chunk_size}, overlap={settings.chunk_overlap}): "
        f"min {min(sizes)}, avg {sum(sizes) // len(sizes)}, max {max(sizes)} chars"
    )
    for chunk in chunks[:5]:
        preview = chunk.text[:chars].replace("\n", " / ")
        print(f"--- {chunk.chunk_id}\n{preview}")
    if len(chunks) > 5:
        print(f"... and {len(chunks) - 5} more")


def _describe(result: IngestResult) -> str:
    line = f"{result.status:<10} {result.source}"
    if result.status in ("added", "updated"):
        line += f"  ({result.chunks_added} chunks)"
    if result.error:
        line += f"  ({result.error})"
    return line


def _ingest(paths: list[Path], force: bool, prune: bool) -> int:
    settings = Settings()
    service = RagService(settings)
    if prune and paths:
        print("error: --prune only works on the data directory (give no paths)", file=sys.stderr)
        return 2

    counts: Counter[str] = Counter()
    for target in paths or [settings.data_dir]:
        results: Iterator[IngestResult]
        if target.is_dir():
            results = service.ingest_directory(target, force=force, prune=prune)
        elif target.is_file():
            results = iter([_ingest_file(service, target, force)])
        else:
            print(f"error: {target} not found", file=sys.stderr)
            return 2
        for result in results:
            counts[result.status] += 1
            print(_describe(result))

    summary = ", ".join(f"{n} {status}" for status, n in sorted(counts.items())) or "nothing to do"
    print(f"\n{summary}. Index holds {service.index_size()} chunks.")
    return 1 if counts["failed"] else 0


def _search(
    query: str, top_k: int | None, sources: list[str] | None, min_score: float | None, full: bool
) -> int:
    service = RagService(Settings())
    if service.index_size() == 0:
        print("The index is empty. Run `vectornote ingest` first.", file=sys.stderr)
        return 1
    indexed = service.indexed_sources()
    unknown = [name for name in sources or [] if name not in indexed]
    if unknown:
        print(f"error: not indexed: {', '.join(unknown)}", file=sys.stderr)
        print(f"indexed files: {', '.join(indexed)}", file=sys.stderr)
        return 2
    try:
        results = service.search(query, top_k, sources, min_score)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not results:
        print("No results.")
        return 0
    for rank, result in enumerate(results, start=1):
        chunk = result.chunk
        print(f"{rank:>2}. {result.score:.3f}  {chunk.source}, p. {chunk.page}")
        body = chunk.text if full else chunk.text[:220].replace("\n", " / ")
        print("    " + body.replace("\n", "\n    "))
    return 0


def _ingest_file(service: RagService, path: Path, force: bool) -> IngestResult:
    try:
        return service.ingest_path(path, force=force)
    except (UnsupportedFileTypeError, DocumentLoadError, OSError) as exc:
        return IngestResult(path.name, "failed", error=str(exc))


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return _run(args)
    except (EmbeddingModelMismatchError, EmbedderUnavailableError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


def _run(args: argparse.Namespace) -> int:
    if args.command == "ingest":
        return _ingest(args.paths, args.force, args.prune)
    if args.command == "search":
        return _search(args.query, args.top_k, args.sources, args.min_score, args.full)
    if args.command == "inspect":
        return _inspect(args.path, args.chars, args.chunks)
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "vectornote.api.app:app", host=args.host, port=args.port, reload=args.reload
        )
        return 0
    print(f"'{args.command}' is not implemented yet.")
    return 1
