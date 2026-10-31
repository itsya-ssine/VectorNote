"""Try the embedding + vector store pipeline on one file.

    uv run python scripts/smoke_store.py add notes.pdf
    uv run python scripts/smoke_store.py query "what is a mutex?"
    uv run python scripts/smoke_store.py sources

Run `query` in a separate process after `add` to confirm the index survives a restart.
Use VECTORNOTE_EMBEDDING_MODEL=hashing to skip the model download.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from vectornote.config import Settings
from vectornote.embeddings import create_embedder
from vectornote.ingestion.chunking import chunk_document
from vectornote.ingestion.cleaning import clean_document
from vectornote.ingestion.loaders import load_document
from vectornote.store import ChromaStore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("path", type=Path)
    query = sub.add_parser("query")
    query.add_argument("text")
    query.add_argument("-k", type=int, default=3)
    sub.add_parser("sources")
    args = parser.parse_args()

    settings = Settings()
    embedder = create_embedder(settings.embedding_model)
    store = ChromaStore(settings.chroma_dir, embedder.name)

    if args.command == "add":
        doc = clean_document(load_document(args.path))
        chunks = chunk_document(doc, settings.chunk_size, settings.chunk_overlap)
        store.delete_by_source(doc.source)
        store.add(chunks, embedder.encode([c.text for c in chunks]))
        print(f"added {len(chunks)} chunks from {doc.source}; store now has {store.count()}")
    elif args.command == "query":
        [vector] = embedder.encode([args.text])
        for result in store.query(vector, args.k):
            snippet = result.chunk.text[:120].replace("\n", " / ")
            print(f"{result.score:.3f}  {result.chunk.source} p.{result.chunk.page}  {snippet}")
    else:
        for source, count in store.list_sources().items():
            print(f"{count:5d}  {source}")


if __name__ == "__main__":
    main()
